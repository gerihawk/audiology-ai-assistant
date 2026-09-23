FROM python:3.12-slim
COPY reconcile.py /reconcile.py
# Hardening del red team (docs/security/red-team-app-2026-09-22.md): script
# sin dependencias del backend, sin escritura a disco — no necesita ningún
# ajuste de permisos más allá de crear el usuario.
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup appuser
USER appuser
CMD ["python3", "/reconcile.py"]
