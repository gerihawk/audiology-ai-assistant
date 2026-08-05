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
