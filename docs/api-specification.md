# Especificación de API — Audiology AI Assistant (MVP)

API REST bajo `/api/v1`. La identidad del usuario se resuelve mediante
`CurrentUserProvider` (ver [architecture.md](architecture.md) §9), con dos
implementaciones seleccionadas por `AUTH_MODE` (Fase 9, hito 9.1):
`FakeCurrentUserProvider` (`AUTH_MODE=fake`, por defecto fuera de
producción) la obtiene de la cabecera de desarrollo `X-Dev-User-Id` (UUID
de un usuario existente y activo en `users`) o, si no se envía, de
`DEV_DEFAULT_USER_ID`; `RealCurrentUserProvider` (`AUTH_MODE=real`,
**obligatorio en `ENVIRONMENT=production`**, arranque fallido si no) exige
un JWT Bearer emitido por `POST /auth/login` (ver sección **Auth**).
`FakeCurrentUserProvider` no puede usarse en producción bajo ningún
`AUTH_MODE`. Todas las rutas de negocio requieren un `CurrentUser`
resuelto (401 si no); las marcadas con un rol exigen que
`current_user.role` tenga permiso para la acción, según la matriz de
autorización de cada recurso (ver más abajo). El acceso está siempre
acotado a `current_user.clinic_id`; nunca se acepta un `clinic_id` desde
el cliente (excepción explícita: las rutas de invitaciones, ver sección
**Onboarding**). Las rutas de `Auth` y `Onboarding` son públicas por
diseño — no requieren `CurrentUser` — al ser el propio punto de entrada
antes de tener sesión.

Respuestas de error usan el formato `{"error": {"code": ..., "message":
..., ...}}` (ver [architecture.md](architecture.md), manejo global de
errores).

Esta especificación es de alto nivel (contratos y propósito). El detalle
fino de esquemas Pydantic se define en el código durante la implementación
de cada módulo, siguiendo esta forma.

**Estado de implementación**: a fecha de esta revisión (2026-09-18, tras
cerrar la Fase 12) todas las secciones de este documento describen
funcionalidad ya implementada y con tests — no queda ninguna sección en
estado de solo diseño. Esta nota se dejó desactualizada desde la Fase 2 (cuando
solo **Patients** estaba implementado) hasta ahora; si en el futuro se
añade una sección de diseño para una fase todavía no implementada,
márquese explícitamente aquí de nuevo para no repetir el mismo desfase.
Ver [development-plan.md](development-plan.md) para el histórico de fases.

## Dev tools (solo desarrollo, ausentes en producción)

No forman parte del alcance mínimo pedido para `patients`, pero son
necesarias para poder ejercitar `CurrentUserProvider` desde el frontend
sin autenticación real. Estas rutas **no se registran** cuando
`ENVIRONMENT=production` (no existen, no devuelven 403: menor superficie).

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/dev/users` | público (solo no-producción) | Lista `{id, display_name, role, clinic_id}` de todos los usuarios, para poblar un selector de "usuario activo" en el frontend de desarrollo |
| GET | `/me` | autenticado | Datos del `CurrentUser` resuelto (id, clinic_id, email, display_name, role) |

## Auth

Implementado en la Fase 9, hito 9.1. Público (sin `CurrentUser` previo) —
es el propio punto de entrada de autenticación.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/login` | Autentica con `email`/`password`; devuelve `{"access_token": string, "token_type": "bearer"}` (JWT firmado HS256, verificado por `RealCurrentUserProvider`) |

- Límite propio de `5/minute` (frente al general de `120/minute`), para
  frenar fuerza bruta de contraseñas.
- No-enumeración: email inexistente, contraseña incorrecta y usuario
  inactivo devuelven exactamente el mismo `401` (`UnauthenticatedError`),
  sin distinguir el motivo. La comparación de contraseña (`bcrypt`) se
  ejecuta siempre, incluso si el usuario no existe (contra un hash señuelo
  fijo), para no abrir un canal lateral de timing.

## Onboarding (alta self-service y colaboración, Fase 12)

Endpoints para que una clínica nueva se dé de alta sola, verifique su
email, resetee su contraseña, e invite a compañeros — sin intervención
manual. Los cuatro primeros bloques (alta, verificación, reset de
contraseña, aceptar invitación) son **públicos** (sin `CurrentUser`) y
comparten el mismo límite de `5/minute` que `/auth/login` — mismo riesgo
de abuso que un endpoint de autenticación. Las invitaciones (crear,
listar, revocar) sí requieren `CurrentUser` y usan el límite general de la
app.

### Alta de clínica (`POST /clinics/signup`)

| Campo | Notas |
|---|---|
| `clinic_name` | normalizado; se deriva un `code` único de clínica (slug + sufijo aleatorio si colisiona) |
| `admin_email` | normalizado; único en toda la app |
| `admin_display_name` | normalizado |
| `admin_password` | longitud mínima validada |
| `turnstile_token` | valor `cf-turnstile-response` del widget de Cloudflare Turnstile (hito 12.4 ampliado, 2026-09-18) |

Crea la `Clinic` y su primer `User` (rol `admin`, `is_active=False`) y
envía un email de verificación con un enlace de un solo uso
(`EMAIL_VERIFICATION_TOKEN_TTL_HOURS`, 24h por defecto). El usuario no
puede iniciar sesión hasta verificar el email.

Anti-abuso, comprobado en este orden — barato/local primero, llamada de
red después:

1. Dominio de email desechable/temporal (lista curada) → `409 Conflict`
   (`field: admin_email`).
2. Verificación Cloudflare Turnstile → `403 Forbidden` si falla.
3. Email ya registrado → `409 Conflict` (`field: admin_email`). A
   diferencia del resto de este bloque, aquí sí se comunica
   explícitamente: quien rellena el formulario ya conoce su propio email,
   así que no hay riesgo real de enumeración.

Además, `5/minute` por IP a nivel de router (extraída de
`X-Forwarded-For`, no de la IP del proxy de Railway).

### Verificación de email (`POST /onboarding/verify-email`)

Body: `{"token": string}`. Activa (`is_active=True`) al usuario asociado
si el token es válido. `404` si el token no existe; `409` si ya se usó o
caducó.

### Recuperación de contraseña

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/onboarding/password-reset/request` | Emite un token de reseteo (`PASSWORD_RESET_TOKEN_TTL_HOURS`, 2h por defecto) y lo envía por email |
| POST | `/onboarding/password-reset/confirm` | Body `{"token", "new_password"}`; consume el token y fija la nueva contraseña |

`request` responde siempre `204`, exista o no la cuenta — no-enumeración
(no hace falta además igualar tiempos de respuesta: no hay ninguna
operación lenta en la rama "no existe"). `confirm` devuelve `404` (token
inexistente) o `409` (ya usado/caducado); al confirmar, cualquier otro
reseteo pendiente del mismo usuario queda invalidado.

### Invitaciones (hitos 12.2/12.3)

Autenticadas — a diferencia del resto de este bloque. Solo `admin`, y
solo sobre su propia clínica (`{clinic_id}` de la ruta debe coincidir con
`current_user.clinic_id`; si no, `403` — la clínica sí existe, simplemente
no es la del usuario).

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/clinics/{clinic_id}/invitations` | admin (de esa clínica) | Body `{"email", "role"}` (`role` restringido a `audiologist`/`viewer`, nunca `admin`); responde `202` siempre |
| GET | `/clinics/{clinic_id}/invitations` | admin (de esa clínica) | Lista invitaciones pendientes, incluidas las caducadas (`is_expired` calculado en la respuesta) |
| DELETE | `/clinics/{clinic_id}/invitations/{invitation_id}` | admin (de esa clínica) | Revoca una invitación pendiente; `409` si ya no está pendiente |
| POST | `/invitations/{token}/accept` | público, `5/minute` | Body `{"new_password", "display_name"}`; crea el `User` con el rol propuesto, `is_active=True` desde el principio (a diferencia del alta de clínica: quien acepta ya demostró control del email) |

- No-enumeración en la creación: si el email ya tiene cuenta (en
  cualquier clínica), la respuesta al admin sigue siendo `202` y en su
  lugar se envía un aviso a ese email — nunca se revela al admin que ya
  existía.
- Reinvitar (mismo email, misma clínica) invalida el enlace anterior.
  Token con TTL de `INVITATION_TOKEN_TTL_DAYS` (7 días por defecto).
- Aceptar: `404` si el token no existe; `409` si ya se usó/caducó, o si ya
  existe una cuenta con ese email (aquí sí se comunica: quien acepta ya
  conoce su propio email).

### Limpieza de clínicas fantasma (`POST /onboarding/system-cleanup`)

Acción de sistema cross-clínica, **sin** `CurrentUser`: autenticada con la
cabecera `X-Onboarding-Cleanup-Cron-Secret` (comparación con
`secrets.compare_digest`, nunca `==`), pensada para un cron externo —
mismo patrón que `POST /retention/system-purge`. Purga las clínicas cuyo
admin nunca verificó su email dentro de `UNVERIFIED_CLINIC_TTL_DAYS` (7
días por defecto). Respuesta `200`: `{"purged_clinics": [string]}` (los
`clinic.code` purgados).

## Patients

Recurso implementado en la Fase 2. Todas las rutas requieren un
`CurrentUser` resuelto y operan exclusivamente sobre `current_user.clinic_id`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/patients` | Crea un paciente ficticio en la clínica del usuario actual |
| GET | `/patients` | Lista paginada, con búsqueda y filtro de archivados (ver Listado) |
| GET | `/patients/{patient_id}` | Detalle; `404` si no existe o pertenece a otra clínica |
| PATCH | `/patients/{patient_id}` | Actualización parcial; `409` si el paciente está archivado |
| POST | `/patients/{patient_id}/archive` | Archiva (idempotente); ver Autorización |
| POST | `/patients/{patient_id}/restore` | Restaura (idempotente); ver Autorización |

### Autorización (matriz de permisos)

Centralizada en `core/authorization.py` (ver
[architecture.md](architecture.md) §9); ningún endpoint implementa
comprobaciones de rol propias.

| Acción | admin | audiologist | viewer |
|---|:---:|:---:|:---:|
| Crear (`POST /patients`) | ✅ | ✅ | ❌ |
| Leer (`GET /patients`, `GET /patients/{id}`) | ✅ | ✅ | ✅ |
| Actualizar (`PATCH /patients/{id}`) | ✅ | ✅ | ❌ |
| Archivar (`POST .../archive`) | ✅ | ✅ | ❌ |
| Restaurar (`POST .../restore`) | ✅ | ❌ | ❌ |

`audiologist` puede archivar pero no restaurar — la fase no especifica el
permiso de restauración para este rol de forma explícita, así que se
adopta la regla más conservadora (restaurar queda reservado a `admin`),
documentada aquí como decisión cerrada.

Un intento sin permiso devuelve `403`. Un `patient_id` válido de otra
clínica devuelve `404`, nunca `403` (ver
[architecture.md](architecture.md) §10) — no debe ser posible distinguir
"no tienes permiso" de "no existe" para recursos ajenos a la propia
clínica.

### Listado (`GET /patients`)

Parámetros de query:

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `search` | string, opcional | — | Coincidencia parcial (case-insensitive) contra `internal_code` o `display_name` |
| `include_archived` | bool | `false` | Si es `false`, excluye pacientes con `is_archived = true` |
| `limit` | int | `20` | Máximo `PAGINATION_MAX_LIMIT` (configurable, default 100); `422` si se supera |
| `offset` | int | `0` | |

Orden estable: `created_at ASC, id ASC`. Respuesta:
`{"items": [...], "total": N, "limit": L, "offset": O}`.

### Validaciones (`POST` / `PATCH`)

- `internal_code`: obligatorio en creación, `1-64` caracteres tras
  normalizar (recorte de espacios), patrón `[A-Za-z0-9._-]+`. Conflicto
  (`409`, con `field: "internal_code"`) si ya existe otro paciente con el
  mismo código en la misma clínica.
- `display_name`: opcional, hasta 200 caracteres, espacios internos
  colapsados.
- `birth_year`: opcional, entero entre 1900 y el año actual.
- `sex`: opcional, uno de `female`, `male`, `other`, `unspecified`.
- `preferred_language`: opcional en creación (default `es`); único valor
  aceptado en el MVP es `es`.
- `notes`: opcional, hasta 2000 caracteres, exclusivamente administrativas.
- Cualquier campo no reconocido en el cuerpo (incluidos `clinic_id`,
  `created_by`, `updated_by`, `created_at`, `updated_at`, `id`,
  `schema_version`) se **rechaza con `422`** — estos campos ni siquiera
  existen en los esquemas de entrada, no se filtran en tiempo de
  ejecución.
- `PATCH` sobre un paciente archivado devuelve `409` (debe restaurarse
  primero).

## Clinical sessions

Diseño cerrado en la Fase 3, backend en implementación. Reemplaza el
diseño anterior basado en `ProcessingStatus` y rutas anidadas bajo
`/patients/{id}/sessions` — ver nota de corrección en
[data-model.md](data-model.md) §6.

Todas las rutas van bajo `/clinical-sessions` (no anidadas bajo
`/patients`, a diferencia del diseño previo) y requieren un `CurrentUser`
resuelto, operando exclusivamente sobre `current_user.clinic_id`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/clinical-sessions` | Crea una sesión; `status` inicial elegido entre `scheduled`, `in_progress`, `completed` |
| GET | `/clinical-sessions` | Lista paginada, con filtros (ver Listado) |
| GET | `/clinical-sessions/{session_id}` | Detalle; `404` si no existe o pertenece a otra clínica |
| PATCH | `/clinical-sessions/{session_id}` | Actualización parcial de metadatos y, si autorizado, `professional_id`; `409` si no editable en el estado actual |
| POST | `/clinical-sessions/{session_id}/start` | `scheduled → in_progress` (no-op si ya `in_progress`) |
| POST | `/clinical-sessions/{session_id}/complete` | `in_progress → completed` (no-op si ya `completed`) |
| POST | `/clinical-sessions/{session_id}/submit-review` | `completed → review_pending` (no-op si ya `review_pending`) |
| POST | `/clinical-sessions/{session_id}/review` | `review_pending → reviewed` (no-op si ya `reviewed`); solo `admin` |
| POST | `/clinical-sessions/{session_id}/cancel` | `{scheduled,in_progress} → cancelled` (no-op si ya `cancelled`) |
| POST | `/clinical-sessions/{session_id}/archive` | Archiva (idempotente); solo desde `completed`, `reviewed` o `cancelled` — nunca desde `review_pending` |
| POST | `/clinical-sessions/{session_id}/restore` | Restaura (idempotente); solo `admin` |

No existe un endpoint genérico de cambio de estado
(`PATCH .../status`): se prioriza claridad, trazabilidad y permisos
explícitos por acción — ver decisión en
[architecture.md](architecture.md) §11. Tampoco existe `DELETE`: el
borrado físico no se implementa, igual que en `patients`.

### Máquina de estados (resumen)

```
creación → scheduled | in_progress | completed
scheduled      --start-->          in_progress
scheduled      --cancel-->         cancelled
in_progress    --complete-->       completed
in_progress    --cancel-->         cancelled
completed      --submit-review-->  review_pending
review_pending --review-->         reviewed
```

`reviewed` y `cancelled` son terminales para `status` (solo admiten
archivar). Detalle completo de transiciones, idempotencia y efectos sobre
fechas en [data-model.md](data-model.md) §8.

### Autorización (matriz de permisos)

Centralizada en `core/authorization.py`
(`authorize_clinical_session_action`, ver
[architecture.md](architecture.md) §9), con una dimensión adicional de
**propiedad** respecto a `patients`: para `audiologist`, "sus propias
sesiones" significa `professional_id == current_user.id`.

| Acción | admin | audiologist | viewer |
|---|:---:|:---:|:---:|
| Crear (`POST`) | ✅ (cualquier profesional admin/audiologist de la clínica) | ✅ (solo con `professional_id = sí mismo`) | ❌ |
| Leer (`GET` lista/detalle) | ✅ | ✅ (sin restricción de propiedad) | ✅ |
| Actualizar metadatos (`PATCH` sin `professional_id`) | ✅ (`review_pending` limita a `title`/`administrative_notes`, ver [data-model.md](data-model.md) §8) | ✅ (solo sesiones propias; misma limitación en `review_pending`) | ❌ |
| Cambiar profesional (`PATCH` con `professional_id`) | ✅ (nunca en `review_pending`) | ❌ | ❌ |
| Iniciar (`.../start`) | ✅ | ✅ (solo propias) | ❌ |
| Completar (`.../complete`) | ✅ | ✅ (solo propias) | ❌ |
| Enviar a revisión (`.../submit-review`) | ✅ | ✅ (solo propias) | ❌ |
| Revisar (`.../review`) | ✅ | ❌ | ❌ |
| Cancelar (`.../cancel`) | ✅ | ✅ (solo propias, y solo desde `scheduled`/`in_progress`) | ❌ |
| Archivar (`.../archive`) | ✅ | ✅ (solo propias, y solo desde `completed`/`reviewed`/`cancelled` — nunca `review_pending`) | ❌ |
| Restaurar (`.../restore`) | ✅ | ❌ | ❌ |

Decisiones no fijadas explícitamente por el encargo y resueltas aquí de
la forma más simple y segura para el MVP (ver justificación en
[product-requirements.md](product-requirements.md) §11):

- **Un `audiologist` no puede editar, iniciar, completar, enviar a
  revisión, cancelar ni archivar sesiones de otros profesionales de su
  misma clínica** — solo las suyas. Evita que un profesional modifique el
  registro clínico de un compañero sin su intervención.
- **`review` es exclusivo de `admin`.** Con solo tres roles y sin una
  noción de "profesional senior" o revisor por pares, permitir que un
  `audiologist` revisara sus propias sesiones habría vaciado de sentido
  el paso de revisión (autorrevisión). Si se necesita revisión entre
  pares en el futuro, requiere un rol o regla nueva, fuera de esta fase.
- **Un `audiologist` que crea una sesión solo puede asignarse a sí mismo
  como `professional_id`.** Evita que cree registros nominalmente
  responsabilidad de un compañero sin su participación. `admin` puede
  asignar a cualquier `admin`/`audiologist` de la clínica.

Un intento sin permiso devuelve `403`. Un `session_id` válido de otra
clínica devuelve `404`, nunca `403` (igual que `patients`, ver
[architecture.md](architecture.md) §10).

### Listado (`GET /clinical-sessions`)

Parámetros de query:

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `patient_id` | UUID, opcional | — | Sesiones de un paciente (usado también en la vista de detalle de paciente) |
| `professional_id` | UUID, opcional | — | Filtro por profesional responsable |
| `status` | string, opcional | — | Uno de `ClinicalSessionStatus` |
| `session_type` | string, opcional | — | Uno de los tipos fijos (ver Validaciones) |
| `scheduled_from` / `scheduled_to` | date, opcional | — | Rango sobre `scheduled_at` exclusivamente (ver limitación en [data-model.md](data-model.md) §9); nombres de parámetro cerrados, no `date_from`/`date_to` |
| `search` | string, opcional | — | Coincidencia parcial (case-insensitive) contra `title` o `administrative_notes` |
| `include_archived` | bool | `false` | Si es `false`, excluye sesiones con `is_archived = true` |
| `limit` | int | `20` | Máximo `PAGINATION_MAX_LIMIT`; `422` si se supera |
| `offset` | int | `0` | |

Orden estable: `created_at ASC, id ASC` (igual que `patients`, ver
[data-model.md](data-model.md) §9 sobre por qué el orden no usa
`scheduled_at`). Respuesta: `{"items": [...], "total": N, "limit": L,
"offset": O}`.

### Validaciones (`POST` / `PATCH`)

- `patient_id` (solo `POST`, inmutable después): obligatorio; `404` si no
  existe en la clínica; `409` si el paciente está archivado.
- `professional_id`: obligatorio en creación; `404` si el usuario no
  existe en la clínica; `409` si existe pero está inactivo, o si su rol
  no es `admin`/`audiologist` (un `viewer` nunca puede ser profesional
  responsable).
- `session_type`: obligatorio, uno de `initial_assessment`, `follow_up`,
  `hearing_aid_fitting`, `hearing_aid_adjustment`, `review`, `other`.
- `status` (solo `POST`): opcional, default `scheduled`; si se informa,
  debe ser uno de `scheduled`, `in_progress`, `completed` — cualquier
  otro valor (`review_pending`, `reviewed`, `cancelled`) se rechaza con
  `422`, ya que solo se alcanzan mediante los endpoints de transición.
- `scheduled_at`: datetime ISO 8601 opcional; puede ser futura. Único
  campo de fecha que acepta el cliente.
- `started_at`, `ended_at`, `reviewed_by`, `reviewed_at`: **no existen en
  ningún esquema de entrada** (ni `POST` ni `PATCH`); enviarlos se
  rechaza con `422` como cualquier otro campo no reconocido. Los fija
  siempre el servidor — ver [data-model.md](data-model.md) §8.
- `title`: opcional, hasta 200 caracteres, espacios normalizados.
- `administrative_notes`: opcional, hasta 2000 caracteres, espacios
  normalizados, exclusivamente administrativas.
- Campos no reconocidos (incluidos `clinic_id`, `status`, `started_at`,
  `ended_at`, `reviewed_by`, `reviewed_at`, `created_by`, `created_at`,
  `updated_at`, `id`, `schema_version` en `PATCH`) se **rechazan con
  `422`** — no existen en los esquemas de entrada correspondientes.
- `PATCH` sobre una sesión no editable en su estado actual (`reviewed`,
  `cancelled`) o archivada devuelve `409`. En `review_pending`, `PATCH`
  con cualquier campo distinto de `title`/`administrative_notes`
  (incluido `professional_id`) también devuelve `409`.
- Las transiciones (`start`/`complete`/`submit-review`/`review`/`cancel`)
  devuelven `409` si el estado actual no admite esa transición ni es ya
  el estado de destino (ver tabla de idempotencia en
  [data-model.md](data-model.md) §8).
- `archive` devuelve `409` si `status ∉ {completed, reviewed,
  cancelled}` — explícitamente incluye `review_pending` como estado que
  **no** admite archivado.

## Audio (Fase 5)

Varias grabaciones por sesión, cada una direccionable por su propio ID —
**supera al diseño anterior** de esta sección (un único audio por sesión,
con endpoint de descarga), documentado así desde la Fase 5 (ver
[development-plan.md](development-plan.md)). Sin `clinic_id` propio en
`audio_recordings`: el aislamiento se resuelve mediante join contra
`clinical_sessions` en cada consulta (ver
[architecture.md](architecture.md) §10).

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/clinical-sessions/{session_id}/audio-recordings` | admin/audiologist (propias sesiones) | Sube fichero de audio (multipart: campo `file` + `duration_seconds`); crea `audio_recordings` en `ready` o `failed` (validación síncrona de tamaño/duración/extensión/MIME; sin estado `validating` intermedio persistido en esta fase) |
| GET | `/clinical-sessions/{session_id}/audio-recordings` | admin/audiologist/viewer | Lista las grabaciones de la sesión, más reciente primero |
| DELETE | `/audio-recordings/{audio_recording_id}` | admin/audiologist (propias sesiones) | Borrado físico inmediato vía `AudioStorage.delete` (`status → deleted`, `storage_reference` invalidado); metadatos conservados; idempotente |
| POST | `/audio-recordings/{audio_recording_id}/transcribe` | admin/audiologist (propias sesiones) | Transcribe el audio (debe estar `ready` o `transcribed`) con el `TranscriptionProvider` resuelto por `TRANSCRIPTION_PROVIDER`; crea o versiona el `AIArtifact` `transcript` — independiente de `run-mock-pipeline`/`run-pipeline` (ver más abajo), que no cambian; `409` si el audio no está en un estado transcribible, si falla el proveedor, o si ya hay un `ai_pipeline_run` en curso para la sesión |

**Disparo del pipeline (implementado, fuera del diseño `/ai/...` de la
sección "AI Pipeline" siguiente — nombres heredados de fases previas, no
renombrados para no romper compatibilidad con el frontend existente, ver
docs/fase-6-rfc.md).** Dos entrypoints deliberadamente distintos
(corrección de frontera mock/real, Fase 6.3): `POST
/clinical-sessions/{session_id}/run-mock-pipeline` es **Mock** —
estructuralmente incapaz de invocar un proveedor LLM real o gastar
dinero, sin importar cómo esté configurado `Settings.llm_provider_*`
(`AIPipelineService.run_mock_pipeline`/`_build_mock_steps`, que nunca
consulta el routing); único uso legítimo: development/tests/demo. `POST
/clinical-sessions/{session_id}/run-pipeline` es el **pipeline
configurado** — respeta el routing real por `artifact_type`
(`Settings.llm_provider_summary`/`llm_provider_patient_summary`/
`llm_provider_missing_information`) y puede invocar Anthropic/OpenAI/
Google si así está configurado, pasando antes por consentimiento y
límite de coste (`AIPipelineService.run_pipeline`). Ambos comparten la
misma forma de respuesta (`RunPipelineResponse`) y el mismo modelo de
permisos (`AIPipelineAction.TRIGGER`).

**Deuda técnica explícita (Fase 5)**: sin
`GET .../audio-recordings/{id}/download` (el diseño anterior lo incluía;
fuera de alcance de esta fase); sin `RetentionCleanupService` todavía
(borrado manual únicamente, sin política de expiración automática —
sigue siendo Fase 7).

### Autorización

Mismo patrón que `clinical_sessions` (`AudioRecordingAction` en
`core/authorization.py`, ver [architecture.md](architecture.md) §9):
`admin` sin restricción; `audiologist` solo sobre grabaciones de sus
propias sesiones (`professional_id == current_user.id`, resuelto vía la
`ClinicalSession` dueña del audio — `audio_recordings` no tiene
profesional responsable propio); `viewer` solo lectura (`GET`).

## AI Pipeline

Diseño cerrado en la Fase 4 (ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md)), sustituye
por completo al diseño previo de secciones independientes
"Transcription"/"Anamnesis"/"Session notes" — eliminadas de este
documento, no quedan rutas alternativas para el mismo propósito.
Requieren un `CurrentUser` resuelto, operando exclusivamente sobre
`current_user.clinic_id`.

**Corrección de ruteo (Fase 6.3 — deuda documental, sin cambio de
comportamiento)**: la implementación real direcciona los artefactos por
`artifact_id` (UUID), no por `{session_id}/ai/artifacts/{artifact_type}`
como describía el diseño original de la Fase 4 — mismo criterio de
direccionamiento ya usado por `Export` (`/ai-artifacts/{artifact_id}/export`).
El disparo del pipeline (`run-mock-pipeline`/`run-pipeline`) vive bajo
`/clinical-sessions/{session_id}/...`, no bajo un prefijo `/ai/` — ver
nota de la sección [Audio](#audio-fase-5). No existe endpoint
`GET .../pipeline-runs/{run_id}`: el resultado del disparo se devuelve
directamente en la respuesta de `run-mock-pipeline`/`run-pipeline`
(`RunPipelineResponse`), no se consulta después por separado.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/clinical-sessions/{session_id}/run-mock-pipeline` | Dispara el pipeline **Mock** (grafo de dependencias, ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.4); estructuralmente incapaz de invocar un proveedor real; devuelve `RunPipelineResponse` |
| POST | `/clinical-sessions/{session_id}/run-pipeline` | Dispara el pipeline **configurado** (routing real por `artifact_type`, puede invocar Anthropic/OpenAI/Google); `409` si ya hay un `ai_pipeline_run` `queued`/`processing` para la sesión; devuelve `RunPipelineResponse` |
| POST | `/clinical-sessions/{session_id}/propose-anamnesis-update` | Acción explícita (hito 6.5.3, nunca automática): propone una nueva versión de `ANAMNESIS` a partir del transcript actual; `200` con `created=false` si no hay cambios que proponer |
| POST | `/audio-recordings/{audio_recording_id}/transcribe` | Ver sección [Audio](#audio-fase-5) |
| GET | `/clinical-sessions/{session_id}/artifacts` | Lista los artefactos vigentes de la sesión (uno por `artifact_type` ya generado) |
| GET | `/ai-artifacts/{artifact_id}` | Artefacto vigente (contenido de la versión actual + `schema_version` + `confidence` + estado + aviso IA); `404` si no existe o es de otra clínica |
| GET | `/ai-artifacts/{artifact_id}/versions` | Historial de versiones (solo lectura) |
| PATCH | `/ai-artifacts/{artifact_id}/content` | Guarda contenido editado; crea una `AIArtifactVersion` (`source = human_edited`); si el artefacto estaba `approved` o `rejected`, vuelve a `review_pending` |
| POST | `/ai-artifacts/{artifact_id}/approve` | Aprobación explícita; `status → approved`, registra `approved_by/at` |
| POST | `/ai-artifacts/{artifact_id}/reject` | Rechazo explícito (`rejection_reason` opcional); `status → rejected`, registra `rejected_by/at`; no es un estado terminal, el artefacto puede editarse o regenerarse después |
| DELETE | `/ai-artifacts/{artifact_id}` | Borrado lógico (`deleted_by/at`); nunca físico; `ai_artifact_versions` se conserva; `204` |

No existe un endpoint por artefacto para "generar" individualmente: el
pipeline siempre se dispara completo (`run-mock-pipeline`/`run-pipeline`),
y el orquestador decide qué pasos ejecutar según sus dependencias — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §8. `confidence`
se expone en las respuestas de artefacto pero nunca decide nada
automáticamente por sí solo. `artifact_type` de un `AIArtifact` es uno de
los 7 `AIArtifactType` actuales (`transcript`, `summary`, `clinical_flags`,
`missing_information`, `anamnesis`, `patient_summary`, `session_notes`),
aunque `patient_summary` no se genera todavía en producción (hito 6.3, ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §4).

### Autorización

Mismo patrón que `clinical_sessions` (matriz centralizada en
`core/authorization.py`, dimensión de propiedad para `audiologist`):
`admin` sin restricción; `audiologist` dispara el pipeline y
aprueba/rechaza/edita/elimina/propone actualización de anamnesis
únicamente sobre sesiones propias (`professional_id ==
current_user.id`); `viewer` solo lectura. Un intento sin permiso
devuelve `403`; un `session_id`/`artifact_id` de otra clínica devuelve
`404`.

### Validaciones

- Cualquier campo no reconocido en el cuerpo de `PATCH
  .../ai-artifacts/{artifact_id}/content` (incluidos `confidence`,
  `source_map`, `status`, cualquier campo de auditoría) se rechaza con
  `422` — no existen en el esquema de entrada.
- `POST .../ai-artifacts/{artifact_id}/approve`/`reject` sobre un
  artefacto que no existe todavía (u otra clínica) devuelve `404`.
- `POST .../run-pipeline`/`run-mock-pipeline` mientras ya hay una
  ejecución `queued`/`processing` para la misma sesión devuelve `409`.

## Clinical flags

Disposición humana por ítem sobre las señales generadas por el paso
`clinical_flags` del AI Pipeline — no genera contenido (eso lo hace
`POST .../ai/generate`), solo gestiona la revisión individual de cada
señal ya generada.

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/clinical-sessions/{session_id}/clinical-flags` | audiologist/admin | Lista de señales sugeridas/confirmadas/descartadas, generadas por el `ClinicalFlagsGenerator` activo (`ruleset_name` en cada ítem, ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6.1); respuesta incluye aviso de checklist no validado clínicamente |
| PATCH | `/clinical-flags/{flag_id}` | audiologist | Cambia estado (`confirmada_por_profesional` / `descartada`) |

## Export

`scope=session` implementado en la Fase 6.6 (ver
[fase-6-rfc.md](fase-6-rfc.md) §7 y `app/export/`). La exportación
longitudinal (`scope=patient`) está implementada en la Fase 6.7 vía el
módulo `clinical_record` — ver la sección [Clinical record](#clinical-record)
más abajo; reutiliza `DocumentExporter`/`PdfDocumentExporter`/
`TextDocumentExporter`, sin un exportador propio.

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/ai-artifacts/{artifact_id}/export?format=pdf\|text` | admin, audiologist (`ClinicalDocumentAction.EXPORT`) | Exporta la versión vigente del artefacto de IA indicado (identificado por `artifact_id`, no por `artifact_type` de sesión), en PDF o texto plano; **solo si `status = approved`**, vigente y no eliminado |

Aplica a los 7 `AIArtifactType` actuales (`transcript`, `summary`,
`patient_summary`, `clinical_flags`, `missing_information`, `anamnesis`,
`session_notes`), no solo a `summary`/`anamnesis`. A diferencia de
aprobar/rechazar/editar, exportar **no** exige ser el profesional
responsable de la sesión: cualquier `admin`/`audiologist` con acceso a la
clínica puede exportar; `viewer` recibe `403` (permiso vacío). El
documento nunca incluye `source_excerpt`, `source_map`, `confidence` ni
metadata de proveedor/modelo/coste — solo contenido clínico aprobado y
metadata mínima (clínica, paciente, sesión, `session_type` o "Sin
especificar", artefacto, versión, aprobación humana, fecha, hash de
contenido). `clinical_flags` incluye además, de forma obligatoria, el
aviso de checklist no validado clínicamente (ver
[clinical-safety.md](clinical-safety.md) §7). Cada descarga registra
`document.exported` en `audit_log` (metadata mínima, sin contenido
clínico). `format` inválido devuelve `422` nativo; artefacto inexistente,
de otra clínica o eliminado devuelve `404`.

## Clinical record

Implementado en la Fase 6.7 (ver [fase-6-rfc.md](fase-6-rfc.md) §8 y
`app/clinical_record/`). Módulo independiente de solo lectura — sin
tabla ni ORM propios — que agrega, por paciente, las sesiones clínicas y
sus documentos de IA `approved`, vigentes y no eliminados, ordenados
cronológicamente (sesiones) y por `PIPELINE_STEP_ORDER` (documentos
dentro de cada sesión).

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/patients/{patient_id}/clinical-record` | admin, audiologist, viewer (`ClinicalRecordAction.READ`) | Vista longitudinal paginada (`limit`/`offset`, mismo tope `PAGINATION_MAX_LIMIT` que el resto de listados); `404` si el paciente no existe o es de otra clínica |
| GET | `/patients/{patient_id}/clinical-record/export?format=pdf\|text` | admin, audiologist (`ClinicalRecordAction.READ` **y** `ClinicalDocumentAction.EXPORT`) | Exporta el mismo universo de sesiones/documentos que la vista, en un único PDF/texto; `limit` opcional (por defecto `clinical_record_export_max_sessions`, configurable); `offset` para segmentar |

`viewer` puede consultar la vista JSON pero nunca exportar (`403`, le
falta `clinical_document:export`). Las `ANAMNESIS` históricas permanecen
visibles en su sesión original; solo la aprobación más reciente de todo
el paciente lleva `is_current_baseline=true`; ningún otro
`artifact_type` usa ese campo (siempre `false`). `session_type` se
devuelve `null` cuando no está especificado (nunca inferido); el
exportador lo etiqueta como "Sin especificar". La respuesta nunca
incluye `source_excerpt`, `source_map` ni metadata de generación (mismo
criterio que `Export`); `clinical_flags` incluye
`ruleset_disclaimer` obligatorio.

Respuestas de `.../export`: `409` si `limit` supera el máximo
configurado (segmentar con `offset`), si el paciente tiene más sesiones
que el máximo y no se indicó `limit` explícito, o si no hay ningún
documento aprobado en la ventana solicitada — nunca se exporta un
PDF/texto vacío. Cada descarga registra `document.exported`
(`scope=patient`); consultar la vista registra `clinical_record.viewed`
(la exportación **no** genera este segundo evento). `format` inválido
devuelve `422` nativo.

## Consents

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/patients/{patient_id}/consents` | audiologist/admin | Lista consentimientos registrados |
| POST | `/patients/{patient_id}/consents` | audiologist | Registra un consentimiento (tipo, otorgado sí/no) |

## Audit log

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/audit-log` | admin | Consulta paginada, filtrable por entidad/usuario/rango de fechas |

## Integrations (configuración, no ejecución real)

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/integrations` | admin | Estado de cada integración abstracta (proveedor activo, habilitada) |
| PATCH | `/integrations/{integration_name}` | admin | Cambia proveedor activo (en el MVP, solo valores `mock`) |

## Retention (limpieza manual)

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/retention/expired-audio` | admin | Lista audios que superan `RETENTION_DAYS_DEFAULT` vía `RetentionCleanupService.find_expired_audio` |
| POST | `/retention/expired-audio/purge` | admin | Ejecuta el borrado físico manual de los audios listados; no hay scheduler en el MVP |
| POST | `/retention/patients/{patient_id}/purge` | admin | Purga definitiva (física, irreversible) de todas las sesiones clínicas, artefactos de IA y audio de un paciente — añadido 2026-09-18, ver [privacy-and-security.md](privacy-and-security.md) §8.2 |

### Purga definitiva de paciente (`POST /retention/patients/{patient_id}/purge`)

- Body requerido: `{"confirm": true}` — `PatientDataPurgeRequest.confirm`
  es `Literal[True]`, por lo que `confirm: false` o el campo ausente se
  **rechaza con `422`** antes de ejecutar ninguna lógica de dominio; el
  servicio repite la comprobación (`ConflictError` → `409`) como defensa
  en profundidad para otros llamadores (tests, CLI futuro).
- `patient_id` inexistente (o de otra clínica) devuelve `404`.
- Solo `admin` (`RetentionAction.PURGE_PATIENT_DATA`); cualquier otro rol
  recibe `403`.
- Respuesta `200` (`PatientDataPurgeResponse`): recuento exacto de filas
  borradas físicamente —
  `{"clinical_sessions_purged": int, "ai_artifacts_purged": int, "audio_recordings_purged": int}`.
  Un paciente sin sesiones clínicas es una operación válida que devuelve
  todos los recuentos a `0` (no error).
- La operación es **atómica**: una sola transacción sobre las 6 tablas
  implicadas (audio, `ai_artifact_versions`, `ai_generation_runs`,
  `ai_artifacts`, `ai_pipeline_runs`, `clinical_sessions`); si falla
  cualquier paso, no se borra nada. No afecta a otros pacientes ni
  clínicas. Queda una entrada en `audit_log`
  (`action = "retention.patient_data_purged"`) que sobrevive al borrado.
  Detalle completo, orden de borrado y justificación de por qué existe
  esta excepción al criterio general de "los artefactos de IA nunca se
  eliminan físicamente": [privacy-and-security.md](privacy-and-security.md)
  §8.2.

## Convenciones transversales

- Toda respuesta que incluya contenido generado por IA (cualquier
  `artifact_type` del AI Pipeline) incluye un campo `ai_disclaimer` con el
  texto obligatorio definido en [clinical-safety.md](clinical-safety.md).
  Las respuestas de `clinical-flags` incluyen además `ruleset_disclaimer`
  (checklist de demostración, no validado clínicamente).
- Las rutas de exportación devuelven `409 Conflict` si el artefacto no
  está `approved`.
- Las rutas de escritura sobre pacientes/sesiones/artefactos de IA
  registran una entrada en `audit_log` de forma síncrona antes de
  responder `2xx`, incluidos fallos y borrados. La auditoría técnica de
  cada generación (proveedor, modelo, coste, tiempo) vive en
  `ai_generation_runs`, no en `audit_log` — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.6.
- Cualquier transición de estado inválida (p. ej. aprobar sin generar,
  transcribir sin audio `ready`) devuelve `409 Conflict` con el motivo;
  la validación ocurre en la capa de dominio/servicio, no solo en el
  router (ver [architecture.md](architecture.md) §5).
- Las respuestas de audio y sesión nunca incluyen `storage_reference` en
  bruto al frontend; solo se usa internamente para resolver
  `/audio/download`.
