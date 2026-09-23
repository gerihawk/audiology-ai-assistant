# Base con pg_dump ya incluido (misma familia de versión que el Postgres
# de Railway). `age` y `aws` desde los repos de Alpine. Sin dependencias
# del backend.
FROM postgres:18-alpine
RUN apk add --no-cache python3 age aws-cli
COPY backup.py /backup.py
# Hardening del red team (docs/security/red-team-app-2026-09-22.md):
# reutiliza el usuario "postgres" ya creado por la imagen base
# postgres:18-alpine, no hace falta crear uno nuevo. Solo escribe a /tmp
# (línea 132 de backup.py), mundialmente escribible por defecto — sin
# necesidad de ningún chown adicional.
USER postgres
ENTRYPOINT []
CMD ["python3", "/backup.py"]
