FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests

# Mismo criterio que Dockerfile.prod (uv.lock manda, `--locked` falla si
# está desincronizado), más los extras de dev (pytest, ruff, black,
# pip-audit). Venv en /opt/venv (UV_PROJECT_ENVIRONMENT) y no en /app/.venv:
# el volumen `./backend:/app` de docker-compose.yml lo taparía al arrancar.
# Instalación editable del proyecto, que apunta a /app — el código montado.
RUN pip install uv==0.12.3 && uv sync --locked --extra dev

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
