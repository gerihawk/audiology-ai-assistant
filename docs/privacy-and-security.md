# Privacidad y seguridad — Audiology AI Assistant

## 1. Principio general

Durante todo el desarrollo del MVP se usan exclusivamente pacientes, audios
y conversaciones **ficticios**. No se introducen datos sanitarios reales
bajo ninguna circunstancia. Esto es una política de proceso (seed
controlado, revisión antes de cualquier commit, sin conexión a sistemas
reales) más que un campo de base de datos: `patients` no incluye un
campo `is_fictional` — el modelo de la Fase 2 solo contiene identidad y
datos administrativos mínimos, deliberadamente sin ningún campo que
pudiera sugerir contenido clínico o sanitario real (ver
[data-model.md](data-model.md)).

Aun así, el sistema se diseña como si fuera a manejar datos reales en el
futuro (privacidad desde el diseño), para no tener que rediseñar el modelo
cuando eso ocurra.

## 2. Minimización de datos

- `patients` almacena solo lo estrictamente necesario para distinguir un
  paciente en la UI (nombre para mostrar, año de nacimiento, código
  interno). Explícitamente **sin** DNI, número de seguridad social,
  dirección, teléfono, email personal, historia clínica, diagnóstico,
  audiometrías, anamnesis ni contenido de sesiones — esos campos no
  existen en el modelo, no se ocultan a posteriori.
- `audit_logs.metadata` nunca contiene el contenido clínico completo, ni
  siquiera en las actualizaciones: solo los **nombres** de los campos
  modificados, nunca sus valores anteriores ni nuevos (ver
  [data-model.md](data-model.md) §2 `audit_logs`).
- No se solicitan campos "por si acaso"; cada campo del modelo de datos
  tiene un uso identificado en [data-model.md](data-model.md).

## 3. Separación identidad / contenido clínico

`patients` (identidad) está desacoplado de `clinical_sessions`,
`anamnesis_documents`, `session_notes`, `clinical_flags` y
`transcriptions` (contenido clínico), que solo referencian `patient_id` o
`clinical_session_id`. Esto permite, a futuro:

- aplicar cifrado o controles de acceso distintos a cada conjunto;
- purgar/anonimizar identidad sin perder valor analítico del contenido
  clínico agregado, o viceversa;
- limitar qué roles pueden ver identidad frente a contenido clínico.

## 4. Cifrado

- **En tránsito**: TLS obligatorio en cualquier despliegue no local
  (terminación TLS en el proxy/reverse proxy; HTTP interno solo en la red
  de contenedores). En desarrollo local sobre `docker compose` se documenta
  como excepción explícita, nunca como el modo de producción.
- **En reposo**: se diseña para poder activar cifrado a nivel de disco/volumen
  y, para campos especialmente sensibles (p. ej. `patients.display_name`,
  `patients.birth_year`), se deja preparada la posibilidad de cifrado a
  nivel de aplicación (columna) como mejora futura — **no implementado
  todavía en el MVP**, documentado como deuda consciente.
- Los ficheros de audio se almacenan fuera del control de versiones, en un
  volumen/almacenamiento dedicado con acceso restringido al backend.

## 5. Control de acceso basado en roles (RBAC) y aislamiento multi-clínica

Roles del MVP (desde la Fase 2): `admin`, `audiologist`, `viewer`. Matriz
completa de permisos sobre `patients` en
[api-specification.md](api-specification.md) §Autorización, centralizada
en `core/authorization.py` (ver [architecture.md](architecture.md) §9) —
ningún endpoint implementa su propia comprobación de rol.

- **Aislamiento por clínica** (`clinic_id`): estructural, no una
  comprobación añadida — todo método de repositorio exige `clinic_id`
  como parámetro y lo deriva siempre de `current_user.clinic_id`, nunca
  del cliente. Un usuario nunca puede consultar ni inferir la existencia
  de datos de otra clínica: un identificador válido de otra clínica
  devuelve `404` (recurso no encontrado), no `403` (prohibido) — ver
  [architecture.md](architecture.md) §10.
- Sin autenticación real todavía: la identidad se resuelve vía
  `CurrentUserProvider` (ver §12 más abajo). Todas las reglas de RBAC se
  aplican igualmente sobre el usuario simulado que resuelva ese proveedor.
- La exportación de un documento no aprobado está bloqueada a nivel de API,
  no solo de UI (aplica a fases futuras de documentos clínicos).
- **`clinical_sessions` (Fase 3):** un `audiologist` solo puede
  crear/editar/iniciar/completar/enviar a revisión/cancelar/archivar
  sesiones donde figura como `professional_id` — nunca las de otro
  profesional de la misma clínica. Revisar (`.../review`) y restaurar
  (`.../restore`) quedan reservados a `admin`. `admin` no tiene esta
  restricción de propiedad. Matriz completa en
  [api-specification.md](api-specification.md) §Clinical sessions.

## 6. Registro de auditoría

La tabla `audit_logs` (módulo `audit_log`) es append-only (sin `UPDATE` ni
`DELETE` desde la aplicación). Implementada desde la Fase 2 para
`patients`: `patient.created`, `patient.updated`, `patient.archived`,
`patient.restored`. Cada entrada incluye `clinic_id`, `actor_user_id`,
`request_id` (correlation ID de la petición HTTP, ver
[architecture.md](architecture.md) §9) y, para `*.updated`, únicamente los
**nombres** de los campos modificados en `metadata.changed_fields` —
nunca sus valores.

**Transaccionalidad**: la escritura de la entidad (`patients`, y en fases
futuras `clinical_sessions`/documentos) y su entrada de `audit_logs` se
realizan dentro de la misma transacción de base de datos y se confirman
con un único `commit`. Si cualquiera de las dos falla, ambas se revierten
(`rollback`) — nunca debe poder existir un cambio persistido sin su
auditoría correspondiente, ni una entrada de auditoría sin el cambio que
la originó. Ver `PatientService` en [architecture.md](architecture.md).

**`clinical_sessions` (Fase 3):** `clinical_session.created`,
`clinical_session.updated` (metadatos; `changed_fields`, sin valores),
`clinical_session.professional_changed` (UUID anterior y nuevo del
profesional — identificadores técnicos, no contenido sensible),
`clinical_session.status_changed` (`from_status` / `to_status`, usado por
`start`/`complete`/`submit-review`/`review`; la entrada de `review`
incluye el actor, redundante de forma deliberada con las columnas
`reviewed_by`/`reviewed_at` de la propia entidad — ver
[data-model.md](data-model.md) §2), `clinical_session.cancelled` (acción
propia, no fusionada en `status_changed`, igual que
`archived`/`restored`), `clinical_session.archived`,
`clinical_session.restored`. Un reintento idempotente que no produce
ningún cambio real (p. ej. `.../start` cuando ya está `in_progress`) **no
genera entrada de auditoría**. Un mismo `PATCH` que cambie tanto
`professional_id` como algún campo de metadatos genera dos entradas de
auditoría (una por cada tipo de cambio) dentro de la **misma
transacción/commit** — nunca un cambio sin su auditoría correspondiente.
Ningún valor de `title`/`administrative_notes` se duplica en auditoría.
Detalle completo en
[api-specification.md](api-specification.md) §Clinical sessions y
[data-model.md](data-model.md) §8.

Registro previsto para fases futuras (diseño, no implementado):

- subida de audio y resultado de su validación (`ready`/`failed`);
- solicitud de transcripción y su resultado;
- generación de documentos IA y su resultado;
- cada edición de anamnesis/resumen (referenciando la versión creada);
- aprobación de documentos;
- exportaciones;
- **borrado lógico** de documentos clínicos (`deleted_by`/`deleted_at`);
- **borrado físico** de audio por retención (manual, vía
  `RetentionCleanupService`);
- cualquier transición a `failed` (con `failure_reason`);
- cambios de configuración de integraciones;
- accesos de administrador al propio `audit_logs` (opcional, evaluar en
  Fase 10).

Regla general: toda operación relevante debe poder asociarse a una
entrada de `audit_log` — no se considera completa una funcionalidad que
escriba en pacientes, sesiones, audio o documentos sin su auditoría
correspondiente.

## 7. Consentimiento

`consents` registra si el paciente (ficticio, en el MVP) ha consentido
grabación de audio, procesamiento por IA y almacenamiento. El sistema no
verifica el consentimiento contra ningún documento externo; es un registro
declarativo por parte del profesional. La generación de documentos IA
debería, a futuro, poder bloquearse si no existe consentimiento de
`procesamiento_ia` — **se documenta como regla deseable, no forzada en el
MVP** (ver pregunta abierta en product-requirements.md si debe forzarse ya).

## 8. Retención y eliminación

- **Retención por defecto: 30 días**, configurable mediante
  `RETENTION_DAYS_DEFAULT`. Se cuenta desde `uploaded_at` del audio.
- **Audio**: puede eliminarse **físicamente** una vez superado el periodo
  de retención, a través de la interfaz `RetentionCleanupService`
  (`find_expired_audio`, `purge`) — ver [architecture.md](architecture.md)
  §4. En el MVP la ejecución es **manual** (endpoint de administración,
  ver [api-specification.md](api-specification.md) §Retention); no existe
  scheduler/cron todavía, eso queda para la Fase 10 del
  [plan de desarrollo](development-plan.md). El borrado físico invalida
  `storage_reference` pero conserva la fila de `audio_recordings`
  (`status = deleted`) para trazabilidad.
- **Documentos clínicos** (`anamnesis_documents`, `session_notes`): **nunca**
  se eliminan físicamente, ni siquiera pasado el periodo de retención.
  Solo admiten **borrado lógico** (`status = deleted`, `deleted_by`,
  `deleted_at`), conservando `document_versions` y `audit_log` íntegros.
  Esto aplica con más razón a documentos ya `approved`: la trazabilidad de
  lo que se aprobó no puede perderse.
- `clinical_sessions` sigue el mismo criterio que los documentos: borrado
  lógico únicamente; su audio asociado puede haberse eliminado físicamente
  de forma independiente por retención.
- En desarrollo, se recomienda limpiar periódicamente los datos ficticios
  de prueba usando el mismo mecanismo de limpieza manual, no un borrado
  directo en base de datos.

## 9. Proveedores externos y envío de datos

- Ningún dato (audio, transcripción, texto clínico) sale del entorno
  controlado hacia un proveedor externo sin que (a) exista una integración
  configurada explícitamente distinta de `mock`, y (b) exista consentimiento
  y configuración explícitos para ese tipo de envío.
- En el MVP esto es estructural: las únicas implementaciones disponibles
  de `TranscriptionProvider` y `LanguageModelProvider` son `Mock*`, que no
  hacen ninguna llamada de red.

## 10. Gestión de secretos

- Todo secreto (credenciales de base de datos, futuras claves de API o de
  autenticación) se lee exclusivamente de variables de entorno.
- Se mantiene un `.env.example` versionado con las claves necesarias y
  valores de ejemplo no funcionales; `.env` real nunca se versiona
  (incluido en `.gitignore` desde el primer commit del esqueleto de
  proyecto).
- Nunca se registran secretos en logs ni en `audit_logs.metadata`.
- Revisión obligatoria antes de cualquier commit: que no se haya
  incrustado ninguna clave, token o contraseña en código o configuración.

## 11. Amenazas consideradas (resumen, no exhaustivo)

| Amenaza | Mitigación en el MVP |
|---|---|
| Fuga de identidad de paciente vía logs/errores | Identidad separada del contenido clínico; `audit_logs.metadata` sin contenido clínico completo |
| Acceso no autorizado a recursos de una clínica | RBAC centralizado + filtrado obligatorio por `clinic_id` en cada repositorio (ver [architecture.md](architecture.md) §9-10) |
| Fuga de existencia de datos de otra clínica | UUID de otra clínica devuelve `404`, nunca `403` |
| Suplantación de usuario vía cabecera de desarrollo | `X-Dev-User-Id` se valida contra `users` (existencia + `is_active`); `FakeCurrentUserProvider` se rechaza si `ENVIRONMENT=production` |
| Exportación de documento no revisado | Bloqueo a nivel de API si `status != approved` |
| Secretos filtrados en el repositorio | Solo variables de entorno, `.env` en `.gitignore`, revisión previa a commit |
| Envío accidental a proveedor de pago real | Solo implementaciones `Mock*` disponibles en el MVP; activar un proveedor real requiere cambio explícito de configuración |
| Pérdida de trazabilidad de cambios clínicos o administrativos | `document_versions`/`audit_logs` obligatorios y transaccionales en cada escritura |
| Borrado accidental de un documento aprobado o de un paciente | Borrado lógico obligatorio en dominio/servicio; no existe operación de borrado físico expuesta para `patients`, `anamnesis_documents`/`session_notes` |
| Audio ficticio acumulado indefinidamente | Retención configurable (30 días por defecto) + `RetentionCleanupService`, purgable manualmente |
| Subida de audio malicioso/con formato no soportado | Validación de tamaño, duración, extensión y tipo MIME contra lista blanca antes de pasar a `ready` |
| Un `audiologist` modifica/cancela/revisa sesiones de un compañero de la misma clínica | Comprobación de propiedad (`professional_id == current_user.id`) en `authorize_clinical_session_action`, no solo de rol (Fase 3, diseño) |
| Autorrevisión de una sesión clínica (quien la registra también la "revisa") | `review` restringido a `admin`, ningún `audiologist` puede revisar sus propias sesiones (Fase 3, diseño) |
| Sesión creada para un paciente archivado o con un profesional inválido (inactivo, rol `viewer`, de otra clínica) | Validado en `ClinicalSessionService.create` antes de persistir; `409`/`404` según el caso (Fase 3, diseño) |

## 12. `CurrentUserProvider`: alcance y limitaciones (Fase 2)

`FakeCurrentUserProvider` es una herramienta de desarrollo, **no** un
mecanismo de autenticación:

- No verifica contraseña, posesión de dispositivo ni ningún factor real —
  solo confirma que el `id` recibido corresponde a un usuario existente y
  activo en la base de datos.
- Cualquiera con acceso a la API de desarrollo puede actuar como
  cualquier usuario simplemente enviando su UUID en `X-Dev-User-Id`. Esto
  es aceptable únicamente porque no hay datos reales ni exposición
  pública durante el MVP.
- Se rechaza estructuralmente en `ENVIRONMENT=production` (la aplicación
  falla al arrancar si es la única implementación disponible, ver
  [architecture.md](architecture.md) §9): **la API no tiene, todavía, un
  modo de funcionamiento válido en producción**. Esa es una limitación
  conocida y deliberada de la Fase 2, no un descuido — implementar
  autenticación real es trabajo de una fase futura no planificada aún.
- El endpoint de apoyo `/dev/users` (que lista usuarios para poblar el
  selector del frontend) tampoco existe cuando `ENVIRONMENT=production`.
