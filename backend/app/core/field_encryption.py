"""Cifrado de campos a nivel de aplicación (columna) para el contenido
clínico más sensible. Añadido 2026-09-18 — ver docs/privacy-and-security.md
§4 y la EIPD (docs/eipd-dpia.md, riesgo R9, marcado como el único riesgo
residual alto que quedaba abierto).

AES-256-GCM (cifrado autenticado: detecta manipulación, no solo confidencia-
lidad) vía la librería `cryptography`. Diseño con CLAVES VERSIONADAS desde
el principio (encargo explícito de Gerard, no una clave fija de "MVP"):
cada valor cifrado lleva incrustado el identificador de la clave que lo
cifró, así que rotar la clave activa (`FIELD_ENCRYPTION_ACTIVE_KEY_ID`)
nunca rompe la lectura de datos cifrados con una clave anterior, mientras
esa clave anterior siga presente en `FIELD_ENCRYPTION_KEYS`. Ver
`app/core/field_encryption_cli.py` para el procedimiento de re-cifrado
tras una rotación (necesario antes de poder retirar la clave antigua).

Formato del valor almacenado — siempre texto, nunca bytes crudos, para
poder guardarlo en una columna `TEXT` sin problemas de codificación:

    "<key_id>:<base64(nonce de 12 bytes + ciphertext_con_tag_GCM)>"

`key_id` es un identificador corto arbitrario (p. ej. "1", "2026a"), nunca
un número de versión implícito por posición — así se pueden añadir o
retirar claves del mapa sin reordenar ni renumerar nada.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator

_NONCE_LENGTH_BYTES = 12
_KEY_LENGTH_BYTES = 32  # AES-256


class FieldEncryptionError(Exception):
    """Fallo de cifrado/descifrado de un campo: clave desconocida, valor
    corrupto/manipulado, o formato irreconocible. Nunca se captura en
    silencio en ningún punto de este módulo — un fallo aquí significa que
    el dato no se puede leer de forma fiable, y ocultarlo sería peor que
    dejar que se propague como error."""


class FieldCipher:
    """Cifra/descifra con un conjunto de claves versionadas.

    `keys` mapea key_id -> 32 bytes crudos. `active_key_id` decide qué
    clave se usa para cifrar valores NUEVOS; cualquier key_id presente en
    `keys` puede seguir descifrando valores antiguos aunque ya no sea la
    activa — eso es lo que hace posible rotar sin tiempo de inactividad.
    """

    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        if not keys:
            raise FieldEncryptionError("FIELD_ENCRYPTION_KEYS está vacío o mal formado.")
        if active_key_id not in keys:
            raise FieldEncryptionError(
                f"FIELD_ENCRYPTION_ACTIVE_KEY_ID={active_key_id!r} no aparece dentro de "
                "FIELD_ENCRYPTION_KEYS."
            )
        for key_id, key_bytes in keys.items():
            if len(key_bytes) != _KEY_LENGTH_BYTES:
                raise FieldEncryptionError(
                    f"La clave {key_id!r} de FIELD_ENCRYPTION_KEYS no tiene {_KEY_LENGTH_BYTES} "
                    "bytes (AES-256 requiere una clave de exactamente 32 bytes)."
                )
        self._keys = keys
        self._active_key_id = active_key_id

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    @property
    def known_key_ids(self) -> frozenset[str]:
        return frozenset(self._keys)

    def encrypt(self, plaintext: bytes) -> str:
        key_id = self._active_key_id
        aesgcm = AESGCM(self._keys[key_id])
        nonce = os.urandom(_NONCE_LENGTH_BYTES)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        payload = base64.b64encode(nonce + ciphertext).decode("ascii")
        return f"{key_id}:{payload}"

    def decrypt(self, token: str) -> bytes:
        try:
            key_id, payload = token.split(":", 1)
        except ValueError as exc:
            raise FieldEncryptionError(
                "Valor cifrado con formato irreconocible (falta el separador 'key_id:')."
            ) from exc
        key_bytes = self._keys.get(key_id)
        if key_bytes is None:
            raise FieldEncryptionError(
                f"No existe ninguna clave con id {key_id!r} en FIELD_ENCRYPTION_KEYS — ¿se "
                "retiró una clave antigua antes de re-cifrar todos los datos que la usaban? "
                "Ver app/core/field_encryption_cli.py."
            )
        try:
            raw = base64.b64decode(payload)
            nonce, ciphertext = raw[:_NONCE_LENGTH_BYTES], raw[_NONCE_LENGTH_BYTES:]
            aesgcm = AESGCM(key_bytes)
            return aesgcm.decrypt(nonce, ciphertext, None)
        except FieldEncryptionError:
            raise
        except Exception as exc:
            # `cryptography` lanza `InvalidTag` (sin garantía de subclase
            # pública estable entre versiones) para autenticación fallida;
            # cualquier otro fallo de parseo cae aquí también — en ambos
            # casos el dato no es de fiar, nunca se intenta "recuperar"
            # parcialmente.
            raise FieldEncryptionError(
                "No se pudo descifrar el valor: clave incorrecta, o dato corrupto/manipulado."
            ) from exc


def parse_keys_env(raw: str) -> dict[str, bytes]:
    """Parsea el formato `"key_id:base64key,key_id:base64key,..."` de
    `Settings.field_encryption_keys`. Función independiente (no un método
    de `Settings`) para poder reutilizarla desde `field_encryption_cli.py`
    sin importar `app.core.config` en scripts que solo necesitan las claves."""
    keys: dict[str, bytes] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key_id, separator, encoded = entry.partition(":")
        if not separator or not key_id or not encoded:
            raise FieldEncryptionError(
                f"FIELD_ENCRYPTION_KEYS mal formado en la entrada {entry!r} "
                "(se espera 'key_id:base64key')."
            )
        try:
            keys[key_id] = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise FieldEncryptionError(
                f"FIELD_ENCRYPTION_KEYS: la clave {key_id!r} no es base64 válido."
            ) from exc
    return keys


@lru_cache
def get_field_cipher() -> FieldCipher:
    """Cacheado igual que `get_settings()` — construir un `FieldCipher`
    nuevo en cada acceso re-parsearía y re-validaría las claves en cada
    fila leída/escrita. Un proceso nuevo (p. ej. cada invocación de
    `field_encryption_cli.py`) parte de una caché limpia, así que una
    rotación de claves sí se recoge sin reiniciar nada más que el propio
    proceso."""
    from app.core.config import get_settings

    settings = get_settings()
    return FieldCipher(
        keys=parse_keys_env(settings.field_encryption_keys),
        active_key_id=settings.field_encryption_active_key_id,
    )


class EncryptedString(TypeDecorator):
    """Columna de texto cifrada a nivel de aplicación.

    Declarada con `impl=Text` para no imponer un límite de longitud
    arbitrario al ciphertext (siempre más largo que el texto plano
    original, por el nonce/tag/prefijo de key_id) — cualquier validación
    de longitud del dato de negocio en claro vive en el schema Pydantic de
    la capa API, nunca en esta columna.

    El cifrado NO es determinista (nonce aleatorio en cada llamada):
    NUNCA debe usarse en un `WHERE`/`ORDER BY`/`ilike` de SQL — cualquier
    filtro sobre el valor en claro debe resolverse en Python, después de
    leer y descifrar la fila (ver `SqlAlchemyPatientRepository.list`, que
    hace exactamente esto con `display_name`)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_field_cipher().encrypt(value.encode("utf-8"))

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_field_cipher().decrypt(value).decode("utf-8")


class EncryptedInt(TypeDecorator):
    """Como `EncryptedString`, para una columna de dominio `int | None`
    (p. ej. `patients.birth_year`): se serializa a texto decimal antes de
    cifrar — nunca se cifra la representación binaria del entero."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: int | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_field_cipher().encrypt(str(value).encode("utf-8"))

    def process_result_value(self, value: str | None, dialect: Any) -> int | None:
        if value is None:
            return None
        return int(get_field_cipher().decrypt(value).decode("utf-8"))


class EncryptedJSON(TypeDecorator):
    """Como `EncryptedString`, para una columna de dominio `dict`/`list`
    (p. ej. `ai_artifact_versions.content`, antes `JSONB` en claro) —
    serializada con `json.dumps`/`json.loads` antes/después de
    cifrar/descifrar.

    Al pasar de `JSONB` a un `TEXT` cifrado se pierde la capacidad de
    consultar la estructura interna desde SQL (operadores `->`/`->>`/
    `@>`, índices GIN). Verificado antes de este cambio que ningún código
    del proyecto lo necesitaba: siempre se carga la fila completa y se
    accede al `dict` ya en Python (p. ej.
    `AIPipelineService._apply_anamnesis_update`, que indexa
    `previous_ref.content[field_name]["status"]` sobre un valor Python ya
    materializado, nunca dentro de una cláusula SQL)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: dict | list | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_field_cipher().encrypt(json.dumps(value).encode("utf-8"))

    def process_result_value(self, value: str | None, dialect: Any) -> dict | list | None:
        if value is None:
            return None
        return json.loads(get_field_cipher().decrypt(value).decode("utf-8"))
