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
`ai_artifacts`/`ai_artifact_versions` (transcripción, resumen, señales de
alerta, información ausente, anamnesis — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md)) y
`clinical_flags` (contenido clínico), que solo referencian `patient_id` o
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
  `patients.birth_year`, `ai_artifact_versions.content` — contiene
  transcripción, resúmenes y anamnesis, el contenido clínico-adyacente
  más sensible del sistema — y, si se activa la opción de §6,
  `ai_generation_runs.rendered_system_prompt`/`rendered_user_prompt`/`raw_response`),
  se deja preparada la posibilidad de cifrado a nivel de aplicación
  (columna) como mejora futura — **no implementado todavía en el MVP**,
  documentado como deuda consciente.
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
  [architecture.md](architecture.md) §10. **Única excepción deliberada**:
  `integration_configs` (Fase 7.3) no tiene `clinic_id` propio —
  configuración global de aplicación, no de clínica; cualquier `admin` de
  cualquier clínica puede leer/editarla (ver
  [data-model.md](data-model.md) §2 y hito 7.3 en
  [development-plan.md](development-plan.md)). Verificado en la auditoría
  del hito 8.1 (§13 más abajo) que no existe ninguna otra excepción sin
  documentar.
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

**AI Pipeline (Fase 4, diseño cerrado):** `ai_pipeline.triggered`
(agregado por ejecución completa, `metadata = {"outcomes": {artifact_type:
status}}` — solo nombres de tipo y estado, nunca contenido),
`ai_artifact.approved`, `ai_artifact.rejected` (incluye
`rejection_reason` en metadata — texto breve del profesional, no
contenido clínico generado), `ai_artifact.edited`. **No** se registra una
entrada de `audit_log` por cada paso individual del pipeline ni por cada
reintento — ese nivel de detalle técnico (proveedor, modelo, latencia,
tokens, coste, plantilla usada) vive exclusivamente en `ai_generation_runs`
(ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.6),
una tabla distinta con un propósito distinto:

| | `audit_logs` | `ai_generation_runs` |
|---|---|---|
| Propósito | Quién hizo qué, cuándo (trazabilidad de acciones humanas y de negocio) | Telemetría técnica de cada ejecución del pipeline |
| Contenido | Acción, actor, `entity_id`, nombres de campos modificados | Proveedor, modelo, latencia, tokens, coste, plantilla — nunca contenido |
| Nunca contiene | Contenido clínico, valores de campos, secretos | Contenido clínico (salvo activación explícita, ver §6.1 más abajo), secretos |

### 6.1 Prompt renderizado: almacenamiento configurable (Fase 4)

**Decisión cerrada** (ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.5): se
soporta guardar el prompt completamente renderizado y la respuesta cruda
del proveedor en `ai_generation_runs`, pero de forma **configurable y
desactivada por defecto** (`ai_store_rendered_prompts: bool = False`).

**Implicaciones de privacidad**: activar esta opción duplica en una
segunda tabla el mismo contenido clínico-adyacente que ya vive, de forma
versionada, en `ai_artifact_versions.content` — es la razón por la que el
valor por defecto es `false` (minimización de datos, §2). Si se activa,
las columnas correspondientes se añaden a la lista de columnas candidatas
a cifrado de §4. Activarla es una decisión explícita por entorno, nunca
el comportamiento por defecto — ni siquiera en desarrollo. **Nunca**, en
ningún caso, se almacena una clave de API ni ningún otro secreto en estas
columnas.

Registro previsto para fases futuras (diseño, no implementado):

- subida de audio y resultado de su validación (`ready`/`failed`);
- **borrado físico** de audio por retención (manual, vía
  `RetentionCleanupService`);
- cambios de configuración de integraciones;
- accesos de administrador al propio `audit_logs` (opcional, evaluar en
  Fase 8).

Regla general: toda operación relevante debe poder asociarse a una
entrada de `audit_log` — no se considera completa una funcionalidad que
escriba en pacientes, sesiones, audio o artefactos de IA sin su auditoría
correspondiente.

## 7. Consentimiento

`consents` registra si el paciente (ficticio, en el MVP) ha consentido
grabación de audio, procesamiento por IA y almacenamiento. El sistema no
verifica el consentimiento contra ningún documento externo; es un registro
declarativo por parte del profesional.

**Decisión cerrada (Fase 4)**: `consents` se amplía con `consent_version`
(qué versión de la política de consentimiento se aceptó), además de
`granted` y `recorded_at` ya existentes — ver
[data-model.md](data-model.md) §2 y
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.3.
`AIPipelineService.run_pipeline` incluye ya el punto de extensión donde
se comprobaría el consentimiento de `procesamiento_ia` antes de generar
— **en el MVP no bloquea**: si no existe un registro, se asume `true`
implícitamente (mismo comportamiento que antes de esta fase). El día que
deba exigirse explícitamente, esta misma comprobación pasa a rechazar la
generación (`409`) sin rediseñar nada — el campo y el punto de extensión
ya existen.

**Decisión revisada y cerrada (Fase 8, hito 8.3)**: se evaluó si activar
`AI_PROCESSING_CONSENT_ENFORCED=true` incondicionalmente por defecto en
producción (ver [development-plan.md](development-plan.md) §Fase 8, punto
4). Se mantiene el flag tal cual — **no** se fuerza `true`
incondicionalmente. Motivo: hoy los tres `artifact_type` de
`run_pipeline` (`summary`, `patient_summary`, `missing_information`)
siguen configurados en `mock` (`LLM_PROVIDER_*`, ver
`core/config.py`); el validador `Settings._validate_production_safety`
(`core/config.py`, líneas ~256-267) ya exige
`ai_processing_consent_enforced=true` en production en el único
escenario que importa hoy — cuando al menos un `artifact_type` tiene
configurado un proveedor LLM real (`anthropic`/`openai`/`google`).
Forzarlo siempre, tenga o no un proveedor real activo, no reduce ningún
riesgo adicional mientras todo siga en `mock`, y sí añade fricción
innecesaria en development/test sin ningún beneficio de seguridad. Se
revisará cuando se **active de verdad** un proveedor LLM real en
producción — no cuando exista solamente la posibilidad técnica de
hacerlo —, momento en el que el propio validador ya obliga a tener el
flag en `true`, así que no haría falta ningún cambio de código en ese
momento, solo confirmar que la variable de entorno está puesta.

## 8. Retención y eliminación

- **Retención por defecto: 30 días**, configurable mediante
  `RETENTION_DAYS_DEFAULT`. Se cuenta desde `uploaded_at` del audio.
- **Audio**: puede eliminarse **físicamente** una vez superado el periodo
  de retención, a través de la interfaz `RetentionCleanupService`
  (`find_expired_audio`, `purge`) — ver [architecture.md](architecture.md)
  §4. `RetentionCleanupService.purge()` no cambia entre ejecución manual y
  automatizada: sigue exigiendo un `CurrentUser` admin y operando por
  clínica. Dos formas de invocarla:
  - **Manual**: endpoint de administración (ver
    [api-specification.md](api-specification.md) §Retention), un admin
    autenticado purga su propia clínica bajo demanda.
  - **Automatizada (Fase 8, hito 8.2)**: comando de gestión
    `app/retention/cli.py` (`make retention-purge`), pensado para que un
    **cron externo** (host o sidecar de docker-compose) lo invoque
    periódicamente — deliberadamente **sin scheduler en proceso**
    (ni APScheduler ni hilos de fondo), una sola ejecución por invocación,
    mismo patrón que `app.seed` pero sí permitido en
    `ENVIRONMENT=production`. Ejemplo de entrada de crontab (purga diaria a
    las 3:00, log append en el host):

    ```
    0 3 * * * docker compose run --rm backend python -m app.retention.cli >> /var/log/retention-purge.log 2>&1
    ```

    Como no hay petición HTTP de la que resolver un `CurrentUser`, el
    comando recorre todos los usuarios, agrupa por `clinic_id` y purga
    cada clínica actuando como su primer admin activo (orden determinista
    por `created_at`); una clínica sin ningún admin activo se omite y se
    registra en stdout, sin abortar la purga de las demás. Decisión de
    diseño: se deriva el conjunto de clínicas a procesar directamente de
    los `clinic_id` presentes entre los admins activos (`UserRepository.
    list_all()`), no de una tabla `clinics` completa — funciona igual con
    la única clínica de hoy que con varias en el futuro, sin tocar
    `app/seed.py` ni añadir configuración nueva por clínica.

  El borrado físico invalida `storage_reference` pero conserva la fila de
  `audio_recordings` (`status = deleted`) para trazabilidad, en ambos
  casos.
- **Artefactos de IA** (`ai_artifacts`/`ai_artifact_versions`): **nunca**
  se eliminan físicamente, ni siquiera pasado el periodo de retención.
  Solo admiten **borrado lógico** (`deleted_by`, `deleted_at` en
  `ai_artifacts`), conservando `ai_artifact_versions`,
  `ai_generation_runs` y `audit_log` íntegros. Esto aplica con más razón a
  artefactos ya `approved`: la trazabilidad de lo que se aprobó no puede
  perderse.
- `clinical_sessions` sigue el mismo criterio que los artefactos de IA:
  borrado lógico únicamente; su audio asociado puede haberse eliminado
  físicamente de forma independiente por retención.
- En desarrollo, se recomienda limpiar periódicamente los datos ficticios
  de prueba usando el mismo mecanismo de limpieza manual, no un borrado
  directo en base de datos.

## 9. Proveedores externos y envío de datos

- Ningún dato (audio, transcripción, texto clínico) sale del entorno
  controlado hacia un proveedor externo sin que (a) exista una integración
  configurada explícitamente distinta de `mock`, y (b) exista consentimiento
  y configuración explícitos para ese tipo de envío.
- En el MVP esto es estructural: las únicas implementaciones disponibles
  de las ocho interfaces del AI Pipeline (`TranscriptionProvider`,
  `LanguageModelProvider`, `SummaryGenerator`, `ClinicalFlagsGenerator`,
  `MissingInformationGenerator`, `AnamnesisGenerator`, `CostEstimator`,
  `TokenCounter` — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6) son
  `Mock*`, que no hacen ninguna llamada de red. No se integra ningún
  proveedor real (OpenAI, Anthropic, Claude API, Gemini, Ollama, Llama,
  Whisper, Azure, AWS u otra API externa) en esta fase.

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
| Pérdida de trazabilidad de cambios clínicos o administrativos | `ai_artifact_versions`/`audit_logs` obligatorios y transaccionales en cada escritura |
| Borrado accidental de un artefacto de IA aprobado o de un paciente | Borrado lógico obligatorio en dominio/servicio; no existe operación de borrado físico expuesta para `patients`, `ai_artifacts` |
| Audio ficticio acumulado indefinidamente | Retención configurable (30 días por defecto) + `RetentionCleanupService`, purgable manualmente |
| Subida de audio malicioso/con formato no soportado | Validación de tamaño, duración, extensión y tipo MIME contra lista blanca antes de pasar a `ready` |
| Un `audiologist` modifica/cancela/revisa sesiones de un compañero de la misma clínica | Comprobación de propiedad (`professional_id == current_user.id`) en `authorize_clinical_session_action`, no solo de rol (Fase 3, diseño) |
| Autorrevisión de una sesión clínica (quien la registra también la "revisa") | `review` restringido a `admin`, ningún `audiologist` puede revisar sus propias sesiones (Fase 3, diseño) |
| Sesión creada para un paciente archivado o con un profesional inválido (inactivo, rol `viewer`, de otra clínica) | Validado en `ClinicalSessionService.create` antes de persistir; `409`/`404` según el caso (Fase 3, diseño) |
| Inyección de prompt: texto de transcripción (no confiable) insertado en un prompt destinado a un LLM | Solo puede ocupar variables declaradas del `user_prompt_template`, nunca el `system_prompt` (Fase 4, diseño — ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.4) |
| Duplicación de contenido clínico-adyacente en una segunda tabla al activar el almacenamiento de prompt renderizado | `ai_store_rendered_prompts = false` por defecto; activación explícita y documentada por entorno (Fase 4, diseño — §6.1 más arriba) |
| Uso indebido de `confidence` para aprobar artefactos de IA automáticamente | Prohibido estructuralmente: ninguna ruta de código condiciona una transición a `approved` por el valor de `confidence` (Fase 4, diseño) |
| Generación de artefactos de IA sin consentimiento de `procesamiento_ia` | Campo y punto de extensión ya preparados en `consents`/`AIPipelineService`; no forzado en el MVP con datos ficticios — riesgo aceptado conscientemente (Fase 4, diseño, ver §7) |
| Envío de datos clínicos reales a un proveedor de IA de pago sin acuerdo de tratamiento de datos | Bloqueo estructural mientras tanto (solo `Mock*` disponibles); activar un proveedor real es una decisión de producto/legal explícita y posterior, fuera de esta fase |
| Ausencia de cabeceras de seguridad HTTP, rate limiting y límites de subida sin revisar (Fase 8, hito 8.4) | **Deuda consciente, aplazada, no un descuido**: `app/main.py` monta hoy exactamente tres middlewares (`CORSMiddleware`, `RequestIdMiddleware`, `log_requests`) — ningún middleware de cabeceras (`X-Content-Type-Options`, `X-Frame-Options`, etc.) ni de rate limiting. El propio plan marcaba este punto como opcional ("si el tiempo lo permite", ver [development-plan.md](development-plan.md) §Fase 8). Se aplaza porque no existe todavía ningún objetivo de despliegue real ni datos reales (§1) — endurecer cabeceras/rate limiting/límites de subida tiene sentido frente a un entorno de producción real concreto, no en abstracto. Se retoma cuando exista ese objetivo de despliegue. |

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

## 13. Auditoría RBAC (Fase 8, hito 8.1)

Auditoría endpoint por endpoint de los diez enums de `core/authorization.py`
(`PatientAction`, `ClinicalSessionAction`, `AudioRecordingAction`,
`AIPipelineAction`, `AIArtifactAction`, `ClinicalDocumentAction`,
`ClinicalRecordAction`, `ConsentAction`, `RetentionAction`,
`IntegrationConfigAction`) contra los routers reales de `patients`,
`clinical_sessions`, `audio`, `ai_pipeline`, `clinical_record`, `export`,
`consents`, `retention` e `integrations`, y contra los repositorios
SQLAlchemy correspondientes, verificando los cuatro invariantes de §5: (1)
toda escritura/lectura sensible pasa por `authorize_<módulo>_action()`, sin
comprobaciones de rol ad-hoc; (2) aislamiento por clínica estructural
(`clinic_id` siempre derivado de `current_user`, nunca del cliente; recurso
de otra clínica → `404`, nunca `403`); (3) propiedad de recurso
(`professional_id == current_user.id`) donde aplica; (4) toda escritura
genera su entrada de `audit_log` en la misma transacción.

**Desviación estructural encontrada y corregida:**

- `ClinicalSessionService.create()` (`app/clinical_sessions/service.py`)
  comprobaba la propiedad del profesional asignado con un `if
  current_user.role == Role.AUDIOLOGIST and data.professional_id !=
  current_user.id: raise ForbiddenError(...)` manual, en vez de a través de
  `authorize_clinical_session_action()` — única excepción, en todo el
  backend, al invariante "ningún router ni repositorio implementa
  comprobaciones de rol propias: todo pasa por las funciones `authorize_*`"
  (docstring de `core/authorization.py`). El comportamiento observable ya
  era correcto (un `audiologist` solo podía crear sesiones asignadas a sí
  mismo; `403` verificado por `test_audiologist_can_only_create_for_self`)
  — no era una fuga de autorización, sino autorización descentralizada.
  **Corregido**: `CREATE` se añadió a `_OWNERSHIP_REQUIRED_ACTIONS` y
  `authorize_clinical_session_action()` ahora acepta, para esta acción
  concreta, que `professional_id` sea el profesional que se pide asignar a
  la sesión nueva (no el dueño de una sesión ya existente, como en el resto
  de acciones) — mismo mecanismo ya usado por `CHANGE_PROFESSIONAL`, sin
  introducir un parámetro ni una función nueva. Cubierto por
  `tests/test_clinical_session_authorization.py` (nuevo, 4 casos:
  audiologist sobre sí mismo, audiologist sobre otro, admin sin
  restricción, viewer sin permiso alguno); la suite de API existente
  (`test_clinical_sessions_api.py`) sigue en verde sin cambios, porque el
  código de estado HTTP resultante (`403`) no varía.

**Deuda consciente documentada (no corregida en esta ronda):**

- `AIPipelineAction.READ` está declarado en `core/authorization.py` y tiene
  una entrada en `AI_PIPELINE_PERMISSIONS`, pero ningún endpoint lo invoca
  — no existe `GET .../pipeline-runs/{run_id}` (ver
  [api-specification.md](api-specification.md) §AI Pipeline, "el resultado
  del disparo se devuelve directamente en la respuesta de
  `run-mock-pipeline`/`run-pipeline`"); la lectura de artefactos ya
  generados pasa por `AIArtifactAction.READ`, no por este permiso. Es el
  único miembro sin uso de los diez enums auditados. No representa un
  riesgo — un permiso que nunca se comprueba no protege nada, pero tampoco
  deja nada desprotegido — así que se documenta como permiso vestigial en
  vez de eliminarlo a ciegas: `AIPipelineAction` seguiría necesitando
  `TRIGGER` en cualquier caso, y borrar `READ` es un cambio cosmético sin
  beneficio de seguridad que puede abordarse, si procede, en un futuro
  cambio de la matriz de la Fase 4.
- Confirmado que `integration_configs` (Fase 7.3) sigue siendo la única
  excepción al aislamiento por clínica de §5 — ver nota añadida a §5 más
  arriba. No es un hallazgo nuevo (ya documentado en
  [data-model.md](data-model.md) §2 y el cierre del hito 7.3 en
  [development-plan.md](development-plan.md)), solo confirmado como
  exhaustivo por esta auditoría: ningún otro repositorio omite `clinic_id`.

**Fuera de alcance de esta ronda** (hitos 8.2/8.3/8.4, sin tocar): scheduler
de retención, activación por defecto de `AI_PROCESSING_CONSENT_ENFORCED`,
hardening general (cabeceras HTTP, rate limiting, límites de subida). El
`clinical_flags`/`audit_log` de [api-specification.md](api-specification.md)
(§Clinical flags, §Audit log) siguen sin implementación (ni router, ni
módulo `app/clinical_flags/`, ni endpoint `GET /audit-log`) — brecha de
funcionalidad pendiente de fases anteriores, no de autorización: no hay
endpoint que auditar porque no hay endpoint.
