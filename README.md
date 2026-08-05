# Audiology AI Assistant

Aplicación complementaria (no sustitutiva) para audioprotesistas. Asiste en la
documentación clínica de una consulta: transcribe la conversación, propone una
anamnesis estructurada y un resumen profesional, y señala información ausente
o posibles motivos de derivación — siempre como borrador que el profesional
debe revisar y aprobar.

> **Estado: Fase 1 completada.** Esqueleto técnico funcional (backend,
> frontend, PostgreSQL, Docker Compose). Sin funcionalidad clínica todavía
> — eso empieza en la Fase 2 (ver
> [docs/development-plan.md](docs/development-plan.md)).

## Qué NO es este proyecto

- No es un dispositivo médico ni una herramienta de diagnóstico.
- No sustituye a Noah ni a ningún sistema de historia clínica.
- No se integra (todavía) con sistemas reales de pacientes ni calendarios.
- No debe usarse con datos de pacientes reales durante el desarrollo.

Todo contenido generado por IA se marca explícitamente como borrador y
requiere aprobación humana antes de considerarse parte del expediente.
Ver [docs/clinical-safety.md](docs/clinical-safety.md).

## Stack

- **Frontend**: React + TypeScript + Vite
- **Backend**: Python 3.12 + FastAPI
- **Base de datos**: PostgreSQL, SQLAlchemy 2, Alembic
- **Validación**: Pydantic
- **Tests backend**: Pytest
- **Contenedores**: Docker Compose
- **Estilo**: Ruff + Black (Python), ESLint + Prettier (TypeScript)

## Documentación

| Documento | Contenido |
|---|---|
| [docs/product-requirements.md](docs/product-requirements.md) | Alcance del MVP, fuera de alcance, backlog, preguntas abiertas |
| [docs/architecture.md](docs/architecture.md) | Arquitectura modular, capas, interfaces abstractas |
| [docs/data-model.md](docs/data-model.md) | Entidades, relaciones, estados |
| [docs/api-specification.md](docs/api-specification.md) | Endpoints REST por módulo |
| [docs/privacy-and-security.md](docs/privacy-and-security.md) | Principios de privacidad, cifrado, RBAC, auditoría |
| [docs/clinical-safety.md](docs/clinical-safety.md) | Lenguaje clínico permitido, límites de la IA, flujo de aprobación |
| [docs/development-plan.md](docs/development-plan.md) | Fases de desarrollo y criterios de aceptación |
| [CLAUDE.md](CLAUDE.md) | Guía para asistentes de IA que trabajen en este repo |

## Datos de desarrollo

Solo se utilizan pacientes, audios y transcripciones **ficticios**. Nunca
introduzcas datos sanitarios reales, ni siquiera para pruebas rápidas.

## Estructura del repositorio

```
backend/    API FastAPI (Python 3.12)
frontend/   SPA React + TypeScript + Vite
docs/       Documentación fundacional del producto y la arquitectura
infra/      Artefactos de infraestructura local (vacío en la Fase 1)
```

## Puesta en marcha (Docker Compose)

Requisitos: Docker y Docker Compose.

```bash
cp .env.example .env
# Revisa .env y ajusta valores si hace falta (los de ejemplo sirven para
# desarrollo local tal cual).

make up
# equivalente a: docker compose up --build
```

Esto levanta tres servicios:

- **db** — PostgreSQL 16, con volumen persistente `postgres_data`.
- **backend** — FastAPI en `http://localhost:8000` (`/health`, `/ready`).
- **frontend** — Vite dev server en `http://localhost:5173`.

Para pararlo: `make down` (equivalente a `docker compose down`; los datos
de PostgreSQL persisten en el volumen).

### Comandos habituales

| Comando | Qué hace |
|---|---|
| `make up` | Construye y levanta los tres servicios |
| `make down` | Detiene los servicios |
| `make logs` | Sigue los logs de todos los servicios |
| `make migrate` | Ejecuta las migraciones de Alembic (`alembic upgrade head`) |
| `make test` | Ejecuta los tests del backend (Pytest) dentro de Docker |
| `make lint` | Ejecuta Ruff, Black --check, ESLint y Prettier --check |
| `make format` | Aplica Ruff --fix, Black y Prettier |

### Desarrollo sin Docker (opcional)

Backend (requiere Python 3.12 y una instancia de PostgreSQL accesible):

```bash
cd backend
pip install -e ".[dev]"
export $(grep -v '^#' ../.env | xargs)   # o exporta las variables a mano
export POSTGRES_HOST=localhost
uvicorn app.main:app --reload
```

Frontend (requiere Node 20+):

```bash
cd frontend
npm install
npm run dev
```

## Verificación rápida

- `curl http://localhost:8000/health` → `{"status":"ok"}`
- `curl http://localhost:8000/ready` → `{"status":"ok","database":"connected"}`
  (una vez PostgreSQL esté disponible)
- `http://localhost:5173` muestra el estado del frontend y el resultado de
  consultar `/health` en el backend.
