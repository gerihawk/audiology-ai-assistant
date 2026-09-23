FROM python:3.12-slim
COPY purge.py /purge.py
# Hardening del red team (docs/security/red-team-app-2026-09-22.md): script
# sin dependencias del backend, sin escritura a disco.
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup appuser
USER appuser
CMD ["python3", "/purge.py"]
