"""Backup cifrado externo del Postgres de production (Fase 11, hito 11.3).

Servicio mínimo, disparado por un Cron Job de Railway **independiente** del
backend. NO importa nada de `app.*`: lee sus propias variables de entorno,
igual que `ops/retention-cron/purge.py`.

Flujo, sin escribir nunca el dump en claro a disco (solo cruza el pipe):

    pg_dump -Fc "$DATABASE_URL"  |  age -r "$AGE_PUBLIC_KEY"  ->  /tmp/*.dump.age
    aws s3 cp /tmp/*.dump.age  s3://$BUCKET/production/<timestamp>.dump.age

La retención de dumps antiguos NO se aplica aquí: se configura como
lifecycle rule nativa del bucket (R2 y S3 la soportan). Ver
`ops/postgres-backup-cron/README.md` y `docs/privacy-and-security.md` §8.

Variables de entorno (obligatorias, sin default inseguro — mismo criterio
de guardarraíl que `RETENTION_CRON_SECRET` / `JWT_SECRET_KEY`):

- DATABASE_URL                       conexión al Postgres de production
- POSTGRES_BACKUP_AGE_PUBLIC_KEY     clave pública age (la privada NUNCA vive en Railway)
- POSTGRES_BACKUP_BUCKET_ENDPOINT    endpoint S3-compatible (jurisdicción/región UE)
- POSTGRES_BACKUP_BUCKET_NAME        nombre del bucket
- POSTGRES_BACKUP_ACCESS_KEY_ID      credencial de acceso al bucket
- POSTGRES_BACKUP_SECRET_ACCESS_KEY  credencial secreta del bucket

Opcional:

- POSTGRES_BACKUP_BUCKET_REGION      región para `aws` (default "auto", válido para R2)

Sale con código != 0 si `pg_dump`, el cifrado o la subida fallan, para que
Railway marque la ejecución del cron como fallida (mismo criterio que
`purge.py`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

_REQUIRED_VARS = (
    "DATABASE_URL",
    "POSTGRES_BACKUP_AGE_PUBLIC_KEY",
    "POSTGRES_BACKUP_BUCKET_ENDPOINT",
    "POSTGRES_BACKUP_BUCKET_NAME",
    "POSTGRES_BACKUP_ACCESS_KEY_ID",
    "POSTGRES_BACKUP_SECRET_ACCESS_KEY",
)


@dataclass(frozen=True)
class Config:
    database_url: str
    age_public_key: str
    bucket_endpoint: str
    bucket_name: str
    access_key_id: str
    secret_access_key: str
    bucket_region: str


def normalize_database_url(url: str) -> str:
    """Railway expone `DATABASE_URL` como `postgresql://`; si llega la forma
    SQLAlchemy `postgresql+psycopg://` (copiada del backend por error), la
    reduce al esquema que entiende `pg_dump`.

    `.strip()` además defiende contra espacios/saltos de línea colados al
    declarar una variable de referencia en el dashboard de Railway (p. ej.
    un espacio delante de `${{Postgres.DATABASE_URL}}`): un solo carácter
    de más rompe el `startswith("postgresql://")` que usa libpq para
    reconocer la URI, y `pg_dump` cae silenciosamente al socket local en
    vez de fallar con un error claro de formato."""
    return url.strip().replace("postgresql+psycopg://", "postgresql://", 1)


def load_config(environ: Mapping[str, str]) -> Config:
    """Lee y valida el entorno. Lanza `KeyError` nombrando las variables
    obligatorias que falten o estén vacías — nunca aplica un default.

    `.strip()` en cada valor: Railway ya nos ha colado espacios/saltos de
    línea invisibles alrededor de una variable de referencia declarada en
    el dashboard (ver `normalize_database_url`), y con credenciales AWS
    un solo carácter de más rompe el cálculo de la firma SigV4 con un
    'SignatureDoesNotMatch' que no delata la causa real."""
    missing = [name for name in _REQUIRED_VARS if not environ.get(name)]
    if missing:
        raise KeyError(f"variables de entorno obligatorias sin definir: {', '.join(missing)}")
    return Config(
        database_url=normalize_database_url(environ["DATABASE_URL"]),
        age_public_key=environ["POSTGRES_BACKUP_AGE_PUBLIC_KEY"].strip(),
        bucket_endpoint=environ["POSTGRES_BACKUP_BUCKET_ENDPOINT"].strip(),
        bucket_name=environ["POSTGRES_BACKUP_BUCKET_NAME"].strip(),
        access_key_id=environ["POSTGRES_BACKUP_ACCESS_KEY_ID"].strip(),
        secret_access_key=environ["POSTGRES_BACKUP_SECRET_ACCESS_KEY"].strip(),
        bucket_region=(environ.get("POSTGRES_BACKUP_BUCKET_REGION") or "auto").strip(),
    )


def object_key(now: datetime) -> str:
    """Clave del objeto en el bucket, ordenable cronológicamente como texto
    (anchura fija): `production/2026-09-02T09-23-00Z.dump.age`."""
    return f"production/{now.strftime('%Y-%m-%dT%H-%M-%SZ')}.dump.age"


def aws_env(config: Config) -> dict[str, str]:
    """Traduce las credenciales `POSTGRES_BACKUP_*` a las variables que
    espera el binario `aws` en el subproceso.

    Los dos `AWS_REQUEST_CHECKSUM_CALCULATION`/`AWS_RESPONSE_CHECKSUM_VALIDATION`
    desactivan el checksum flexible que AWS CLI v2 activa por defecto desde
    botocore ~1.36 (envía `x-amz-sdk-checksum-algorithm` + trailer en el
    cuerpo del PutObject). Un proveedor S3-compatible que no sea AWS real
    (R2 en nuestro caso) no lo soporta y la firma calculada no coincide con
    la esperada — el síntoma es un `SignatureDoesNotMatch` que no delata
    que el problema es el checksum y no las credenciales."""
    return {
        "AWS_ACCESS_KEY_ID": config.access_key_id,
        "AWS_SECRET_ACCESS_KEY": config.secret_access_key,
        "AWS_DEFAULT_REGION": config.bucket_region,
        "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
        "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required",
    }


def main(environ: Mapping[str, str] | None = None, now: datetime | None = None) -> int:
    config = load_config(os.environ if environ is None else environ)
    now = now or datetime.now(UTC)
    key = object_key(now)
    encrypted_path = f"/tmp/{now.strftime('%Y-%m-%dT%H-%M-%SZ')}.dump.age"

    # ponytail: dump completo en /tmp del contenedor (efímero). Si la BD
    # crece por encima del disco del contenedor, subir por stream con
    # `aws s3 cp -` en vez de a fichero intermedio.
    with open(encrypted_path, "wb") as encrypted_file:
        dump = subprocess.Popen(["pg_dump", "-Fc", config.database_url], stdout=subprocess.PIPE)
        assert dump.stdout is not None
        encrypt = subprocess.run(
            ["age", "-r", config.age_public_key],
            stdin=dump.stdout,
            stdout=encrypted_file,
        )
        dump.stdout.close()
        dump_returncode = dump.wait()

    if dump_returncode != 0:
        print(f"pg_dump falló (código {dump_returncode})", file=sys.stderr)
        return 1
    if encrypt.returncode != 0:
        print(f"age falló (código {encrypt.returncode})", file=sys.stderr)
        return 1

    upload = subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            encrypted_path,
            f"s3://{config.bucket_name}/{key}",
            "--endpoint-url",
            config.bucket_endpoint,
        ],
        env={**os.environ, **aws_env(config)},
    )
    if upload.returncode != 0:
        print(f"subida a S3 falló (código {upload.returncode})", file=sys.stderr)
        return 1

    print(f"backup subido: s3://{config.bucket_name}/{key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
