FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests

RUN pip install --upgrade pip && pip install -e ".[dev]"

# Hardening del red team (docs/security/red-team-app-2026-09-22.md, hallazgo
# de dependencias/infra pendiente): sin USER, uvicorn/pytest corrían como
# root. UID/GID 1000 (convención del primer usuario no-root en Linux) tras
# la instalación de dependencias, que sí necesita privilegios de escritura
# en site-packages.
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --home /app appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
