# Requisitos de producto — Audiology AI Assistant (MVP)

## 1. Contexto

Durante una consulta audioprotésica, el profesional mantiene una
conversación con el paciente y realiza una anamnesis. Gran parte de esa
información se transcribe manualmente hoy. El MVP explora si, a partir de
una grabación de la consulta, es posible generar un borrador de
documentación clínica que el profesional revise, corrija y apruebe, en
lugar de redactarlo desde cero.

Este documento es la fuente de verdad sobre **qué construye el MVP y qué
queda fuera**. Cualquier ambigüedad entre este documento y el código debe
resolverse actualizando primero este documento.

## 2. Objetivo del MVP

Validar el flujo completo: **grabar → transcribir → generar borrador →
revisar/editar → aprobar → exportar**, con datos ficticios, sin ninguna
integración real, y con salvaguardas clínicas desde el primer commit.

No es objetivo del MVP optimizar la calidad de la transcripción o del
modelo de lenguaje (se usan mocks), sino validar el **modelo de datos, el
flujo de trabajo y las salvaguardas** que tendrá que respetar cualquier
proveedor real que se conecte después.

## 3. Alcance exacto del MVP

1. CRUD de pacientes ficticios (identidad mínima).
2. Creación de una sesión clínica asociada a un paciente.
3. Subida de un archivo de audio para una sesión.
4. Transcripción del audio (mock determinista, no IA real).
5. Generación, a partir de la transcripción, de:
   - anamnesis estructurada por campos con estado (`informado` /
     `negado_explicitamente` / `no_preguntado` / `no_determinado`);
   - resumen profesional de la sesión;
   - lista de información ausente que convendría preguntar;
   - lista de señales de alerta / posibles motivos de derivación.
6. Edición manual de todo el contenido generado por el profesional.
7. Aprobación humana explícita como paso obligatorio antes de considerar
   "definitivo" cualquier documento.
8. Conservación de la versión original generada por IA **y** la versión
   final editada, con historial de cambios.
9. Registro de fecha, usuario, cambios y estado de cada documento
   (auditoría).
10. Exportación de anamnesis y resumen como PDF o texto plano.
11. Capa de integración abstracta (interfaces + mocks) para Noah y
    calendario, sin implementación real.
12. Control de acceso básico por rol (administrador / audioprotesista).
13. Registro de consentimiento del paciente para grabación y procesamiento
    por IA (registrable, no verificado contra ningún sistema externo).
14. Validación de audio en subida: tamaño máximo 200 MB, duración máxima 60
    minutos (ambos configurables por variable de entorno), extensión y tipo
    MIME permitidos (lista blanca configurable). Ver
    [data-model.md](data-model.md) y [architecture.md](architecture.md).
15. Eliminación manual de audios según política de retención (30 días por
    defecto, configurable) y borrado lógico auditado de documentos clínicos
    aprobados. Sin scheduler automático en el MVP (ver
    [privacy-and-security.md](privacy-and-security.md)).

## 4. Explícitamente fuera de alcance del MVP

- Integración real con Noah o cualquier otro sistema de historia clínica.
- Integración real con calendarios.
- Transcripción o generación mediante proveedores de IA reales/de pago.
- Diagnóstico clínico o recomendaciones de tratamiento.
- Multi-tenant / multi-clínica (se asume una única organización).
- Aplicación móvil nativa.
- Gestión de facturación, citas o flujos administrativos ajenos a la
  documentación clínica.
- Notificaciones, recordatorios o comunicación con el paciente.
- Firma electrónica avanzada/cualificada de documentos (se registra
  aprobación con usuario + timestamp, no firma criptográfica de paciente).
- Cumplimiento certificado de MDR / EU AI Act / ISO 13485 — se diseña
  **con esos marcos en mente**, pero el MVP no reclama conformidad.
- Internacionalización (se asume español como idioma único por ahora).
- Grabación de audio en vivo desde la propia app (solo subida de fichero ya
  grabado).

## 5. Usuarios y roles (MVP)

- **Audioprotesista (clinician)**: crea pacientes y sesiones, sube audio,
  revisa/edita/aprueba documentos, exporta.
- **Administrador**: gestiona usuarios y puede consultar el registro de
  auditoría. En el MVP puede coincidir con el mismo usuario que el
  audioprotesista en entornos de demo de un solo perfil.

Ver detalle de permisos en [privacy-and-security.md](privacy-and-security.md).

## 6. Restricciones clínicas de producto

- Ninguna pantalla puede presentar contenido de IA como hecho confirmado.
- Todo contenido de IA lleva el aviso obligatorio (ver
  [clinical-safety.md](clinical-safety.md)).
- Los campos de anamnesis nunca se autocompletan con una suposición: si no
  está en la transcripción, el estado es `no_preguntado` o
  `no_determinado`.
- El sistema no bloquea al profesional: puede aprobar, editar o descartar
  cualquier sugerencia libremente.

## 7. Backlog priorizado (alto nivel)

Detalle de fases y criterios de aceptación en
[development-plan.md](development-plan.md). Orden de prioridad:

1. Documentación fundacional (este conjunto de documentos).
2. Esqueleto de proyecto (Docker Compose, backend, frontend, lint/CI local).
3. Módulo `patients` + `users` + auth básica.
4. Módulo `clinical_sessions` + `audio` (subida, almacenamiento local).
5. Módulo `transcription` (mock) sobre el audio subido.
6. Módulo `anamnesis` + `session_notes` + `clinical_flags` (generación mock
   a partir de la transcripción).
7. Flujo de revisión/edición/aprobación + versionado + `audit_log`.
8. Exportación PDF/texto.
9. `integrations` (interfaces + mocks para Noah/calendario), consentimiento,
   retención/eliminación configurables.
10. RBAC más fino y hardening de seguridad si el tiempo lo permite.

## 8. Decisiones cerradas (previamente preguntas abiertas)

Decisiones tomadas por el usuario el 2026-08-05. Sustituyen a las preguntas
abiertas de la versión anterior de este documento; vinculantes para el
resto de la documentación y para la implementación.

1. **Formato de anamnesis fijo.** Los campos son fijos durante todo el MVP.
   Se añade `schema_version` al documento de anamnesis para poder
   versionar el esquema en el futuro sin necesidad de formularios
   configurables por clínica ahora. Ver [data-model.md](data-model.md) §3.
2. **Español único, preparado para i18n futura.** El MVP funciona
   exclusivamente en español. Todos los textos de UI, etiquetas y prompts
   del `LanguageModelProvider` se centralizan en recursos únicos (no
   hardcodeados dispersos) para facilitar una futura internacionalización,
   sin implementar multiidioma ahora. Ver [architecture.md](architecture.md) §8.
3. **Límites de audio.** Tamaño máximo 200 MB, duración máxima 60 minutos,
   ambos configurables por variable de entorno
   (`AUDIO_MAX_SIZE_MB`, `AUDIO_MAX_DURATION_MINUTES`). Se valida tamaño,
   duración, extensión y tipo MIME antes de aceptar un audio como válido
   (estado `validating` → `ready` o `failed`).
4. **Almacenamiento de audio abstracto.** Interfaz `AudioStorage` con
   implementación local durante el desarrollo. El dominio de `audio` no
   depende de rutas de disco ni de ningún SDK de almacenamiento en objeto;
   solo de la interfaz. Ver [architecture.md](architecture.md) §4.
5. **Un único profesional responsable por sesión.** Confirmado. No se
   implementa edición colaborativa ni multi-profesional sobre la misma
   sesión en el MVP.
6. **Retención de 30 días por defecto, configurable**
   (`RETENTION_DAYS_DEFAULT`). Se diseña la eliminación manual y la
   interfaz de un servicio de limpieza (`RetentionCleanupService`), sin
   scheduler/cron todavía — ver [privacy-and-security.md](privacy-and-security.md) §8.
7. **Checklist de señales de alerta genérico de demostración.** No
   validado clínicamente, no apto para uso real; así se etiqueta en toda
   salida relacionada. Su lógica vive detrás de una interfaz
   (`ClinicalFlagRuleset`) aislada para poder sustituirla por protocolos
   validados en el futuro sin tocar el resto del módulo `clinical_flags`.
   Ver [clinical-safety.md](clinical-safety.md) §7.

## 9. Decisiones adicionales cerradas

8. **Sin blobs de audio en PostgreSQL.** Solo se guardan metadatos, hash,
   estado y una referencia opaca al proveedor de almacenamiento
   (`storage_reference`). El binario nunca pasa por la base de datos.
9. **UUID como identificador público** en todas las entidades, sin IDs
   secuenciales expuestos.
10. **Borrado lógico para documentos clínicos aprobados.** Nunca se
    eliminan mediante borrado físico; se marcan `deleted` con auditoría,
    conservando `document_versions` íntegro. Los audios sí pueden
    eliminarse físicamente conforme a la política de retención (el
    registro de metadatos permanece, con `storage_reference` invalidado).
11. **Estados de procesamiento explícitos y unificados**
    (`ProcessingStatus`): como mínimo `uploaded`, `validating`, `ready`,
    `transcribing`, `transcribed`, `generating`, `review_pending`,
    `approved`, `failed`, `deleted` — con las transiciones válidas
    definidas y verificadas en la capa de dominio/servicio, nunca
    dependiendo únicamente de la API. Detalle completo en
    [data-model.md](data-model.md) §6.
12. **Auditoría universal.** Toda operación relevante (incluyendo fallos y
    borrados) debe poder asociarse a una entrada de `audit_log`.

Estas decisiones ya están reflejadas de forma coherente en
[architecture.md](architecture.md), [data-model.md](data-model.md),
[api-specification.md](api-specification.md),
[privacy-and-security.md](privacy-and-security.md) y
[clinical-safety.md](clinical-safety.md).

## 10. Decisiones cerradas — Fase 2 (clínicas, usuarios, pacientes, auditoría)

Decisiones tomadas por el usuario el 2026-08-05 para el alcance concreto
de la Fase 2. El alcance clínico del producto (descrito en §1-§8) **no
cambia**; esta fase solo construye el módulo administrativo de pacientes
y su infraestructura transversal (usuarios, clínicas, auditoría).

1. **Multi-clínica desde el modelo, mono-clínica en el MVP.** Se añade la
   entidad `Clinic`; toda entidad de negocio referencia `clinic_id` y todo
   acceso se acota a la clínica del usuario actual. Sin gestión completa
   de clínicas desde el frontend todavía. Ver
   [data-model.md](data-model.md) §2 y [architecture.md](architecture.md)
   §10.
2. **Roles cerrados en `admin`, `audiologist`, `viewer`** (sustituyen al
   placeholder `admin`/`clinician` de versiones anteriores de este
   documento). `audiologist` puede archivar pacientes pero no
   restaurarlos — la fase no fijaba explícitamente esta regla, así que se
   adopta la opción conservadora (restaurar reservado a `admin`). Matriz
   completa en [api-specification.md](api-specification.md) §Autorización.
3. **Sin autenticación real.** `CurrentUserProvider` resuelve la
   identidad; el MVP solo implementa `FakeCurrentUserProvider` (cabecera
   de desarrollo `X-Dev-User-Id`, validada contra la base de datos,
   rechazada en `ENVIRONMENT=production`). Ver
   [architecture.md](architecture.md) §9 y
   [privacy-and-security.md](privacy-and-security.md) §12.
4. **`patients` sin campo `is_fictional`.** El modelo de la Fase 2 fija
   exactamente los campos administrativos mínimos (identidad, código
   interno único por clínica, año de nacimiento, sexo administrativo,
   idioma preferido, notas administrativas, archivado). Ningún campo
   clínico. La ausencia de datos reales es una política de proceso, no un
   campo de base de datos. Ver [data-model.md](data-model.md) §2.
5. **Valores de `sex`**: `female`, `male`, `other`, `unspecified` —
   administrativos, no clínicos.
6. **Archivado, no borrado físico**, para `patients`: `is_archived` +
   `archived_at`, operaciones idempotentes, edición bloqueada mientras
   está archivado. Ver [data-model.md](data-model.md) §7.
7. **Auditoría transaccional** de las cuatro acciones sobre `patients`
   (`created`/`updated`/`archived`/`restored`), con `request_id` y, para
   actualizaciones, solo los nombres de los campos modificados. Ver
   [privacy-and-security.md](privacy-and-security.md) §6.
8. **Endpoints de apoyo `/me` y `/dev/users`**, fuera de la lista mínima
   original de endpoints de `patients`, añadidos porque son
   estructuralmente necesarios para que el frontend pueda seleccionar y
   mostrar el usuario ficticio activo sin autenticación real. Ausentes en
   producción. Ver [api-specification.md](api-specification.md).

## 11. Fase 3 — Diseño de `clinical_sessions` (cerrado)

Diseño cerrado el 2026-08-05, con las últimas decisiones (antes preguntas
abiertas) resueltas el mismo día. **Implementación de backend en curso a
partir de este cierre** (ver [development-plan.md](development-plan.md)
Fase 3). El alcance clínico del producto no cambia: `clinical_sessions`
sigue sin contener contenido clínico real (`administrative_notes` es
estrictamente administrativo, igual que `patients.notes`).

### Decisiones cerradas

1. **`is_archived` separado de `status`, no un valor `archived` dentro
   del enumerado principal.** Mismo patrón que `patients` (Fase 2). Ver
   [data-model.md](data-model.md) §8.
2. **Estados iniciales válidos en creación: solo `scheduled`,
   `in_progress`, `completed`.** `review_pending`, `reviewed` y
   `cancelled` únicamente se alcanzan mediante los endpoints de
   transición — nunca como valor inicial.
3. **Reglas de edición por estado (revisadas — ya no es una única
   ventana):**
   - `scheduled`, `in_progress`, `completed`: editables todos los campos
     administrativos permitidos (`title`, `administrative_notes`,
     `session_type`, `scheduled_at`, y `professional_id` si quien edita
     tiene permiso de cambiar profesional).
   - `review_pending`: **editables únicamente `title` y
     `administrative_notes`**. Cualquier intento de modificar
     `professional_id`, `session_type`, `scheduled_at` u otro campo
     devuelve `409`. No se puede cambiar `patient_id`, `professional_id`
     (aunque se sea `admin`), tipo, ni el estado mediante `PATCH`.
   - `reviewed`, `cancelled`: no editables.
   - Sesión archivada (cualquier `status`): no editable.
4. **`cancel` solo desde `scheduled`/`in_progress`.** No se implementa
   ninguna acción de "reabrir" o "revertir" una sesión `completed` por
   error en esta fase.
5. **`archive` solo desde `completed`, `reviewed` o `cancelled` —
   explícitamente NO desde `review_pending`** (revisado respecto al
   cierre de diseño anterior, que sí lo permitía). Tampoco desde
   `scheduled`/`in_progress`.
6. **`review` exclusivo de `admin`; sin autorrevisión.** No se implementa
   "devolver a revisión" (`review_pending → in_progress` o similar).
7. **Un `audiologist` solo puede crear/editar/transicionar/cancelar/
   archivar sus propias sesiones** (`professional_id == current_user.id`
   — no `created_by`). `admin` sin esta restricción.
8. **Un `audiologist` que crea una sesión solo puede asignarse a sí mismo
   como `professional_id`.** Solo `admin` puede cambiar el profesional
   responsable de una sesión ya creada.
9. **Sin endpoint genérico de transición de estado.** Todas las
   transiciones se ejecutan mediante endpoints explícitos.
10. **Rutas planas `/clinical-sessions`, no anidadas bajo `/patients`.**
11. **Se añaden `reviewed_by` (FK `users.id`, opcional) y `reviewed_at`
    (datetime, opcional) como columnas propias** — decisión revisada
    respecto al cierre de diseño anterior (que optaba por derivarlo
    solo de `audit_logs`). Las asigna exclusivamente el servidor al
    ejecutar `.../review` (actor y momento de la revisión); no se
    aceptan en ningún esquema de entrada (`POST` ni `PATCH`); no se
    derivan de `audit_logs` en tiempo de lectura (son la fuente directa
    para mostrar "revisado por/cuándo" sin unir contra la auditoría, que
    sigue conservando el historial completo de todas formas).
12. **Auditoría de `cancel` como acción propia
    (`clinical_session.cancelled`)**, no fusionada en
    `clinical_session.status_changed` — igual criterio que
    `archived`/`restored`. `start`/`complete`/`submit-review`/`review`
    comparten la acción genérica `status_changed`
    (`from_status`/`to_status`); la entrada de `review` incluye además
    el actor (ya redundante con `reviewed_by`, pero el log conserva
    histórico completo si `reviewed_by` se sobrescribiera alguna vez).
13. **Filtro de rango de fechas del listado sobre `scheduled_at`
    exclusivamente**, con los parámetros de query `scheduled_from` y
    `scheduled_to` (nombres cerrados). **No se crea una fecha "efectiva"
    combinada.** Limitación aceptada: sesiones creadas directamente como
    `in_progress`/`completed` sin `scheduled_at` no aparecen en ese
    filtro.
14. **Invariantes cruzadas** (`patient_id`/`professional_id` deben
    pertenecer a `clinic_id`) **validadas en la capa de servicio; no se
    implementan triggers de base de datos.**
15. **Sin límite de sesiones `in_progress` simultáneas** por profesional
    ni por paciente.
16. **`started_at` y `ended_at` nunca se aceptan desde el cliente, ni en
    creación ni en edición** — revisado respecto al cierre de diseño
    anterior (que permitía informarlos opcionalmente al crear
    directamente en `in_progress`/`completed`). Siempre los fija el
    servidor:
    - creación directa en `in_progress`: `started_at = now()`;
    - creación directa en `completed`: `started_at = ended_at = now()`
      (mismo instante — sin información del cliente para distinguirlos,
      es la única asignación coherente posible);
    - `.../start`: `started_at = now()` si no existía ya (no-op si ya
      estaba fijado — idempotencia sin reescribir la fecha original);
    - `.../complete`: `ended_at = now()` si no existía ya;
    - ninguna fecha generada por el servidor puede ser futura.
17. **Sin endpoint `GET /clinical-sessions/{id}/timeline`** en esta fase.
18. **Idempotencia estricta**: un reintento que no produce cambio real
    (p. ej. `.../start` cuando ya está `in_progress`) responde `200`,
    **no crea entrada de auditoría** y **no modifica ninguna fecha ya
    fijada** (`started_at`, `ended_at`, `reviewed_at` conservan su valor
    original).
