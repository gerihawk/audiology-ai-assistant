# Audiology AI Assistant

Aplicación complementaria (no sustitutiva) para audioprotesistas. Asiste en la
documentación clínica de una consulta: transcribe la conversación, propone una
anamnesis estructurada y un resumen profesional, y señala información ausente
o posibles motivos de derivación — siempre como borrador que el profesional
debe revisar y aprobar.

> **Estado: Fase 2 completada.** Módulo administrativo funcional de
> clínicas/usuarios/pacientes ficticios, con auditoría, autorización por
> rol y aislamiento multi-clínica. Sin autenticación real ni ninguna
> entidad clínica todavía (sesiones, audio, transcripción, anamnesis) —
> eso empieza en la Fase 3 (ver
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

Solo se utilizan clínicas, usuarios, pacientes, audios y transcripciones
**ficticios**. Nunca introduzcas datos sanitarios reales, ni siquiera para
pruebas rápidas.

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
| `make seed` | Crea la clínica y los usuarios/pacientes ficticios de desarrollo (idempotente) |
| `make test` | Ejecuta los tests del backend (Pytest) dentro de Docker |
| `make test-frontend` | Ejecuta los tests del frontend (Vitest) dentro de Docker |
| `make lint` | Ejecuta Ruff, Black --check, ESLint y Prettier --check |
| `make format` | Aplica Ruff --fix, Black y Prettier |

### Migraciones (Alembic)

```bash
make migrate
# equivalente a: docker compose run --rm backend alembic upgrade head
```

Crea las tablas `clinics`, `users`, `patients` y `audit_logs` (una única
migración inicial, `5bc62034fa75`). Se puede ejecutar repetidamente sin
efecto si ya está al día. Para revertirla por completo (borra esas
tablas):

```bash
docker compose run --rm backend alembic downgrade base
```

### Datos de desarrollo (seed)

```bash
make seed
# equivalente a: docker compose run --rm backend python -m app.seed
```

Crea, si no existen ya (idempotente, localiza por `code`/`email`/
`internal_code`):

- una clínica ficticia (`DEV-CLINIC`);
- tres usuarios ficticios, uno por rol (`admin@dev.local`,
  `audiologist@dev.local`, `viewer@dev.local`);
- tres pacientes ficticios de ejemplo (`PAT-0001`, `PAT-0002`, `PAT-0003`).

El comando imprime los UUID de los tres usuarios al final, útiles para
probar la API directamente con `curl`. El seed se niega a ejecutarse si
`ENVIRONMENT=production`.

Los tres usuarios comparten la misma contraseña ficticia de desarrollo
(constante `DEV_USER_PASSWORD` en `backend/app/seed.py`) — solo hace
falta con `AUTH_MODE=real` (Fase 9, ver más abajo); con `AUTH_MODE=fake`
(por defecto) no se usa para nada.

### Selección del usuario ficticio (sin autenticación real)

La Fase 2 no implementa login. La identidad se resuelve mediante la
cabecera de desarrollo `X-Dev-User-Id: <uuid de un usuario existente>`, o
mediante la variable de entorno `DEV_DEFAULT_USER_ID` si no se envía
cabecera. Esta cabecera se valida siempre contra la base de datos (nunca
se confía en el UUID a ciegas) y queda **bloqueada por completo si
`ENVIRONMENT=production`** — ver
[docs/privacy-and-security.md](docs/privacy-and-security.md) §12.

- **Frontend**: la app consulta `GET /api/v1/dev/users` al cargar y
  muestra un selector ("Usuario ficticio activo") con los usuarios
  creados por el seed; la elección se recuerda en `localStorage`.
- **API directa**: añade la cabecera a mano, usando uno de los UUID que
  imprime `make seed` (o consultando `GET /api/v1/dev/users`).

### Autenticación real (Fase 9)

Con `AUTH_MODE=real` en `.env`, `X-Dev-User-Id` deja de resolver la
identidad: hace falta `POST /api/v1/auth/login` (email + contraseña de
uno de los usuarios del seed, ver arriba) para obtener un JWT Bearer de
8h, que se envía como `Authorization: Bearer <token>` en el resto de
llamadas. `AUTH_MODE=fake` (por defecto) no cambia nada de lo descrito
arriba.

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@dev.local","password":"<DEV_USER_PASSWORD>"}'

curl http://localhost:8000/api/v1/me -H "Authorization: Bearer <access_token>"
```

**Frontend (Fase 9, hito 9.2)**: `VITE_AUTH_MODE` en `.env` es el espejo
en el frontend de `AUTH_MODE` — el frontend no detecta el modo
dinámicamente contra el backend, se configura igual, vía entorno.
`VITE_AUTH_MODE=fake` (por defecto) mantiene exactamente el
comportamiento de hoy: selector de usuario ficticio
(`DevUserSwitcher`), `X-Dev-User-Id` en cada petición.
`VITE_AUTH_MODE=real` sustituye el selector por una pantalla de login
(email + contraseña, contra `POST /api/v1/auth/login`); con sesión
iniciada, el resto de la aplicación es idéntico (mismas rutas y
páginas), con un botón "Cerrar sesión" donde antes vivía el selector. El
JWT se guarda en `sessionStorage` (nunca `localStorage`, no sobrevive a
cerrar la pestaña) y se adjunta automáticamente en cada llamada a la API
— ningún componente de `features/*` necesita saber nada de esto. Ambos
valores de `AUTH_MODE`/`VITE_AUTH_MODE` deben coincidir para que el
frontend y el backend hablen el mismo protocolo de identidad.

### Ejemplos de llamadas a la API

```bash
# Descubrir los usuarios de desarrollo disponibles
curl http://localhost:8000/api/v1/dev/users

ADMIN_ID=<uuid del usuario admin>

# Quién soy
curl http://localhost:8000/api/v1/me -H "X-Dev-User-Id: $ADMIN_ID"

# Crear un paciente ficticio
curl -X POST http://localhost:8000/api/v1/patients \
  -H "X-Dev-User-Id: $ADMIN_ID" -H "Content-Type: application/json" \
  -d '{"internal_code":"PAT-0100","display_name":"Paciente de prueba","sex":"other"}'

# Listar pacientes (búsqueda + paginación)
curl "http://localhost:8000/api/v1/patients?search=PAT-01&limit=10&offset=0" \
  -H "X-Dev-User-Id: $ADMIN_ID"

# Archivar y restaurar
curl -X POST http://localhost:8000/api/v1/patients/<patient_id>/archive -H "X-Dev-User-Id: $ADMIN_ID"
curl -X POST http://localhost:8000/api/v1/patients/<patient_id>/restore -H "X-Dev-User-Id: $ADMIN_ID"
```

Especificación completa de endpoints, validaciones y matriz de
autorización en [docs/api-specification.md](docs/api-specification.md).

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

## Tests

```bash
make test            # backend: pytest contra una base de datos de test aislada
                      # (audiology_ai_assistant_test, se crea sola en el primer run)
make test-frontend   # frontend: vitest + Testing Library
```

Los tests del backend nunca tocan la base de datos de desarrollo: crean y
truncan una base de datos separada en el mismo servidor Postgres. No
requieren el seed ejecutado previamente — cada test crea sus propias
clínicas/usuarios ficticios.

## Verificación rápida

- `curl http://localhost:8000/health` → `{"status":"ok"}`
- `curl http://localhost:8000/ready` → `{"status":"ok","database":"connected"}`
  (una vez PostgreSQL esté disponible)
- `curl http://localhost:8000/api/v1/dev/users` → lista de usuarios ficticios
  (tras ejecutar `make seed`)
- `http://localhost:5173` muestra el estado del frontend, el usuario
  ficticio activo y permite crear/buscar/archivar/restaurar pacientes.
