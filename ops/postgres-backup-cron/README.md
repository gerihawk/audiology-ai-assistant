# Backups y recuperación ante desastres — Postgres de production

Fase 11 del [plan de desarrollo](../../docs/development-plan.md). Solo
cubre **production** (staging es desechable: datos de seed y transcripción
mock, riesgo aceptado).

Tres capas complementarias, las tres recomendadas por la documentación de
Railway para producción:

| Capa | Qué cubre | Qué NO cubre | Dónde se configura |
|------|-----------|--------------|--------------------|
| 11.1 Volume Backups nativos | Error de despliegue, corrupción accidental (restaura en el mismo proyecto/servicio) | Pérdida del proyecto o de la cuenta de Railway | Dashboard de Railway |
| 11.2 Point-in-Time Recovery | Volver a un instante concreto dentro de la ventana (WAL continuo) | Instantes anteriores a la activación; pérdida de la cuenta | Dashboard/CLI de Railway |
| 11.3 `pg_dump` externo cifrado | Pérdida total de Railway (proyecto o cuenta); copia bajo control de Gerard, fuera de Railway | Recuperación al segundo (granularidad = frecuencia del cron) | Este servicio + Cron Job de Railway |

---

## Hito 11.1 — Volume Backups nativos (dashboard, sin código)

1. Railway → proyecto de production → servicio **Postgres** → pestaña
   **Backups** (o **Settings → Backups**, según versión del dashboard).
2. Activar los snapshots del volumen. **Frecuencia: diaria como mínimo.**
3. Anotar la retención que ofrece el plan.

Restaura **dentro del mismo proyecto/servicio**. Sirve para deshacer un
despliegue que corrompió datos o un borrado accidental; **no** protege
frente a la pérdida del proyecto o de la cuenta de Railway — para eso está
el hito 11.3.

## Hito 11.2 — Point-in-Time Recovery (dashboard/CLI, sin código)

1. Railway → servicio **Postgres** de production → activar **Point-in-Time
   Recovery** (pgBackRest: base + WAL continuo a un bucket gestionado por
   Railway).
2. **La ventana NO es retroactiva.** Empieza a contar desde el momento de
   activación; anota esa fecha. La ventana de recuperación es de
   **~4 semanas** desde ese punto.

Procedimiento de restore (manual, nunca automático):

1. Railway provisiona un **servicio hermano** de Postgres restaurado al
   instante elegido.
2. Se verifica ese servicio hermano (conectar, revisar tablas y filas).
3. **El cutover a producción es manual**: cambiar la `DATABASE_URL` del
   backend al servicio restaurado (o promover el hermano), redeploy.
   Railway nunca hace este paso solo.

## Hito 11.3 — `pg_dump` externo cifrado (este servicio)

Mismo patrón que [`ops/retention-cron/`](../retention-cron/): un servicio
mínimo (`Dockerfile` + `backup.py`), sin dependencias del backend, con sus
propias variables de entorno, disparado por un **Cron Job de Railway
independiente** del backend.

### Puesta en marcha (una vez)

**1. Generar el par de claves `age` — OFFLINE, en la máquina de Gerard:**

```sh
age-keygen -o ~/audiology-backup-key.txt
# imprime: Public key: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- `~/audiology-backup-key.txt` contiene la **clave privada**. **NUNCA**
  sube a Railway, ni al repo, ni a ningún sitio online. Copia offline
  (gestor de contraseñas + copia en frío). Sin ella los dumps son
  irrecuperables — es el objetivo del diseño.
- La `Public key` (`age1...`) es lo único que va a Railway.

**2. Crear el bucket S3-compatible en la UE.** Recomendado Cloudflare R2
con jurisdicción EU; sirve cualquier endpoint S3-compatible en región UE
sin tocar código. Crear un token de acceso con permiso de **escritura**
sobre ese bucket (no hace falta lectura para el cron; la lectura se usa
solo en el restore, con credenciales aparte si se quiere).

**3. Configurar la retención en el bucket (no en código).** Lifecycle
rule nativa: **borrar objetos con más de 30 días** bajo el prefijo
`production/`. R2 y S3 la soportan en su panel. Decisión de diseño: la
retención vive en la infraestructura del bucket, no en `backup.py` —
menos código, y funciona aunque el cron no llegue a ejecutarse.

**4. Crear el servicio y el Cron Job en Railway:**

- Nuevo servicio a partir de este directorio (`ops/postgres-backup-cron/`,
  root directory del servicio).
- Variables de entorno (todas obligatorias, sin default; `backup.py`
  falla y sale con código ≠ 0 si falta alguna):

  | Variable | Valor |
  |----------|-------|
  | `DATABASE_URL` | referencia a la del servicio Postgres de production |
  | `POSTGRES_BACKUP_AGE_PUBLIC_KEY` | la `age1...` del paso 1 |
  | `POSTGRES_BACKUP_BUCKET_ENDPOINT` | endpoint del bucket (UE) |
  | `POSTGRES_BACKUP_BUCKET_NAME` | nombre del bucket |
  | `POSTGRES_BACKUP_ACCESS_KEY_ID` | credencial de escritura |
  | `POSTGRES_BACKUP_SECRET_ACCESS_KEY` | credencial secreta |
  | `POSTGRES_BACKUP_BUCKET_REGION` | opcional; `auto` para R2, `eu-west-1`/etc para S3 real |

- **Cron Schedule** (Railway → servicio → Settings → Cron Schedule):
  `0 3 * * *` (diario a las 03:00 UTC). Railway ejecuta el servicio, el
  contenedor corre `python3 /backup.py` una vez y termina.

### Verificación

Tras la primera ejecución programada: Railway → servicio → **Deployments/
Logs** debe mostrar `backup subido: s3://<bucket>/production/<fecha>.dump.age`
y salida con código 0. Comprobar que el objeto existe en el bucket.

### Sobre `DATABASE_URL` vs. un usuario de solo lectura

`backup.py` usa `DATABASE_URL` (superusuario de Railway). Un usuario de
Postgres con permisos reducidos (solo `SELECT`) sería preferible, pero
Railway no lo provisiona por defecto y crearlo a mano es frágil. **No
bloqueante para el primer corte**; si más adelante se crea, basta apuntar
`DATABASE_URL` de este servicio a ese usuario — sin cambios de código.

---

## Hito 11.4 — Runbook de restore (VERIFICAR EJECUTÁNDOLO)

> Railway: *"a backup you have never restored is unverified"*. Este
> procedimiento debe **ejecutarse una vez de verdad** contra un dump real
> de production antes de dar la Fase 11 por cerrada, y dejar constancia
> (fecha + resultado) en [development-plan.md](../../docs/development-plan.md).

Requisitos en la máquina donde se restaura: `age`, `pg_restore`
(`postgresql-client`), acceso de lectura al bucket, y
`~/audiology-backup-key.txt` (clave privada `age`).

```sh
# 1. Descargar el último dump cifrado del bucket
aws s3 ls s3://<bucket>/production/ --endpoint-url <endpoint>
aws s3 cp s3://<bucket>/production/<fecha>.dump.age ./restore.dump.age \
  --endpoint-url <endpoint>

# 2. Descifrar con la clave privada offline
age -d -i ~/audiology-backup-key.txt -o ./restore.dump ./restore.dump.age

# 3. Crear una base temporal y restaurar (formato custom -Fc)
createdb -h <host> -U <user> audiology_restore_check
pg_restore -h <host> -U <user> -d audiology_restore_check \
  --no-owner --no-privileges ./restore.dump

# 4. Verificar: filas en las tablas clave
psql -h <host> -U <user> -d audiology_restore_check -c "
  SELECT 'users', count(*) FROM users
  UNION ALL SELECT 'patients', count(*) FROM patients
  UNION ALL SELECT 'clinical_sessions', count(*) FROM clinical_sessions
  UNION ALL SELECT 'ai_artifacts', count(*) FROM ai_artifacts;"

# 5. Limpiar
dropdb -h <host> -U <user> audiology_restore_check
rm ./restore.dump ./restore.dump.age
```

Restaurar en local (contra la `db` de `docker-compose`, puerto 5433) es
suficiente para verificar. **No** restaurar sobre la base de production.

### Recuperación real ante pérdida total de Railway

1. Nuevo proyecto Railway (o proveedor equivalente) con un servicio
   Postgres vacío y el backend desplegado desde el repo.
2. Pasos 1-3 de arriba apuntando `pg_restore` a la nueva base
   (`--clean --if-exists` si ya corrió `alembic upgrade head`).
3. Reconfigurar secretos (`JWT_SECRET_KEY`, etc.) y `DATABASE_URL` del
   backend, redeploy.
4. Reactivar los hitos 11.1–11.3 en el nuevo proyecto.

Pérdida máxima de datos = tiempo desde el último dump (≤ 24 h con el cron
diario). Las capas 11.1/11.2 dan RPO menor pero solo mientras Railway
exista.
