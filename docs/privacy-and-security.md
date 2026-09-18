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

**Activado (2026-09-14)**: `summary` → `anthropic`/`claude-sonnet-5`,
`patient_summary` y `missing_information` → `openai`/`gpt-5.2` (decisión
de negocio completa en [development-plan.md](development-plan.md) §Fase
10). `AI_PROCESSING_CONSENT_ENFORCED=true` en production desde hoy, tal
como preveía esta sección — sin cambio de código, solo la variable de
entorno, confirmado. `LLM_COST_LIMIT_ENFORCED=true` y
`MAX_LLM_COST_PER_SESSION_USD=1.00` activados junto con los proveedores
(el validador exige los tres a la vez si hay algún `artifact_type` no
`mock`). Efecto real: cualquier paciente sin consentimiento de
`procesamiento_ia` registrado y vigente recibe `409` al intentar generar
— sin impacto inmediato porque production no tiene pacientes reales
todavía (ver [development-plan.md](development-plan.md) §Fase 11).
`ANAMNESIS`/`SESSION_NOTES`/`CLINICAL_FLAGS` siguen en `mock`, sin
benchmark propio todavía.

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
- **Artefactos de IA** (`ai_artifacts`/`ai_artifact_versions`): por
  defecto **nunca** se eliminan físicamente, ni siquiera pasado el
  periodo de retención — solo admiten **borrado lógico**
  (`deleted_by`, `deleted_at` en `ai_artifacts`), conservando
  `ai_artifact_versions`, `ai_generation_runs` y `audit_log` íntegros.
  Esto aplica con más razón a artefactos ya `approved`: la trazabilidad
  de lo que se aprobó no puede perderse. **Excepción, añadida
  2026-09-18** (ver §8.2 más abajo): `RetentionCleanupService.
  purge_patient_clinical_data()` sí borra físicamente estos artefactos,
  pero solo a petición explícita y admin-only, nunca automáticamente ni
  por el paso del tiempo — cierra el hueco de que, hasta esa fecha, no
  existía NINGÚN camino posible para honrar una solicitud de supresión
  de un paciente una vez pasado el plazo legal de conservación de la
  clínica.
- `clinical_sessions` sigue el mismo criterio que los artefactos de IA:
  borrado lógico por defecto (`is_archived`/`archived_at`); su audio
  asociado puede haberse eliminado físicamente de forma independiente
  por retención; y la misma excepción de §8.2 aplica también a esta
  tabla.
- En desarrollo, se recomienda limpiar periódicamente los datos ficticios
  de prueba usando el mismo mecanismo de limpieza manual, no un borrado
  directo en base de datos.

### 8.1 Continuidad y recuperación ante desastres (Fase 11)

Retención (arriba) responde a *"borrar lo que ya no debe conservarse"*.
Esta subsección responde a lo contrario: *"no perder lo que sí debe
conservarse"*. **Solo cubre production** — staging es un entorno
desechable (seed + transcripción mock) y se deja sin backups a propósito.

Tres capas complementarias sobre el Postgres de production de Railway;
detalle operativo en
[`ops/postgres-backup-cron/README.md`](../ops/postgres-backup-cron/README.md):

| Capa | Mecanismo | Ventana de recuperación | Cubre / no cubre |
|------|-----------|-------------------------|------------------|
| **Volume Backups nativos** (11.1) | Snapshots diarios del volumen, gestionados por Railway | Según retención del plan de Railway | Restaura en el mismo proyecto/servicio: error de despliegue, corrupción accidental. **No** cubre pérdida del proyecto/cuenta. |
| **Point-in-Time Recovery** (11.2) | pgBackRest: base + WAL continuo a bucket gestionado por Railway | ~4 semanas, **contadas desde la activación** (no retroactiva) | Volver a un instante concreto. Restore a servicio hermano, cutover manual. **No** cubre pérdida de la cuenta. |
| **`pg_dump` externo cifrado** (11.3) | Cron Job de Railway independiente del backend (`ops/postgres-backup-cron/`): `pg_dump -Fc` → `age` → bucket S3-compatible en la UE | Diaria (granularidad = frecuencia del cron); retención de 30 días por lifecycle rule del bucket | **La única capa que sobrevive a la pérdida total de Railway.** Copia fuera de Railway, bajo control directo de Gerard. |

Puntos de seguridad de la capa 11.3:

- **La clave privada de `age` NUNCA vive en Railway** — ni en variables de
  entorno, ni en el repo, ni online. La genera Gerard offline
  (`age-keygen`) y la guarda offline (gestor de contraseñas + copia en
  frío). Railway solo conoce la **clave pública** (`POSTGRES_BACKUP_AGE_PUBLIC_KEY`),
  con la que se cifra pero no se descifra. Un atacante con acceso total a
  Railway (o a Railway comprometido) no puede leer los dumps del bucket.
- **Acceso al bucket externo**: bucket S3-compatible en región/jurisdicción
  UE (recomendado Cloudflare R2 con jurisdicción EU). El token que usa el
  cron tiene permiso de **escritura** sobre el prefijo `production/`; la
  lectura (restore) usa credenciales aparte, en poder de Gerard. Los
  objetos del bucket están cifrados en cliente con `age` **además** del
  cifrado en reposo del proveedor.
- `POSTGRES_BACKUP_AGE_PUBLIC_KEY` y las credenciales del bucket
  (`POSTGRES_BACKUP_*`) son **obligatorias, sin default inseguro** — mismo
  criterio de guardarraíl que `RETENTION_CRON_SECRET`/`JWT_SECRET_KEY`
  (ver §10); `backup.py` sale con `KeyError` si falta alguna.
- El dump en claro **nunca se escribe a disco**: `pg_dump | age` por pipe,
  solo el `.dump.age` ya cifrado toca `/tmp` del contenedor (efímero).

**Un backup no restaurado es un backup no verificado** (criterio de
Railway). El runbook de restore
([`README.md`](../ops/postgres-backup-cron/README.md) §Hito 11.4) debe
ejecutarse de verdad al menos una vez contra un dump real de production,
con constancia en [development-plan.md](development-plan.md) §Fase 11
(fecha + resultado).

### 8.2 Purga definitiva de datos clínicos de un paciente (Fase 12) — añadido 2026-09-18

Hasta esta fecha, **ningún** camino del sistema podía borrar físicamente
`ai_artifacts`/`clinical_sessions`: el criterio de §8 (arriba) era
correcto para la operación normal — evitar que retención automática por
antigüedad destruyera trazabilidad clínica — pero como efecto colateral
dejaba sin implementar el derecho de supresión (RGPD art. 17) *una vez
superado* el plazo mínimo legal de conservación de la clínica (en España,
5 años desde el alta, art. 17 Ley 41/2002). Un paciente podía solicitar
legítimamente la eliminación de sus datos y la plataforma no tenía forma
de cumplirla. `RetentionCleanupService.purge_patient_clinical_data()`
cierra ese hueco.

Diferencias deliberadas frente a `purge()` (audio por antigüedad, arriba):

| | `purge()` (§8) | `purge_patient_clinical_data()` (§8.2) |
|---|---|---|
| Alcance | Solo audio expirado por `RETENTION_DAYS_DEFAULT` | Todo el contenido clínico de **un paciente**: audio, `ai_artifacts`/`ai_artifact_versions`, `ai_generation_runs`, `ai_pipeline_runs`, `clinical_sessions` |
| Disparo | Manual (endpoint admin) o automatizado (cron externo, hito 8.2 de arriba) | **Solo manual**, nunca cron ni automático — "cuándo procede legalmente borrar" es un juicio de la clínica, no un valor por defecto del sistema |
| Atomicidad | No — cada `AudioRecordingService.delete()` confirma de forma independiente | **Sí** — una única transacción; cualquier fallo revierte todo el borrado |
| Confirmación | Ninguna adicional (ya requiere admin) | Doble barrera: `confirm: Literal[True]` en el schema Pydantic (rechaza `false`/ausente con 422 antes de tocar dominio) + comprobación `if not confirm` en el servicio (defensa en profundidad para otros llamadores, p. ej. tests/CLI) |

**Autorización**: acción dedicada `RetentionAction.PURGE_PATIENT_DATA` en
`app/core/authorization.py`, admin-only (igual criterio que el resto de
`RetentionAction`) — ver [architecture.md](architecture.md) §4.

**Orden de borrado** (una sola transacción, `except Exception: rollback()`
si algo falla): audio físico + filas de `audio_recordings` → se
desvinculan las referencias circulares de `ai_artifacts`
(`current_version_id`, `baseline_artifact_id`, `baseline_version_id` a
`NULL`) → `ai_artifact_versions` → `ai_generation_runs` →
`ai_artifacts` → `ai_pipeline_runs` → `clinical_sessions`. Este orden
existe porque `ai_artifacts` y `ai_artifact_versions` se referencian
mutuamente (FK circular con `use_alter=True`); intentar borrar en
cualquier otro orden viola una constraint de clave foránea.

**Auditoría que sobrevive al borrado**: se escribe una entrada en
`audit_log` (`action = "retention.patient_data_purged"`,
`entity_type = "patient"`, `entity_id = <patient_id>`, con el recuento de
filas purgadas por tabla en `audit_metadata`) **antes** del commit final.
Como `audit_logs.entity_id` es una columna UUID sin restricción de clave
foránea (ver §6), esta entrada permanece íntegra aunque el paciente, sus
sesiones y sus artefactos ya no existan — es la única prueba que queda de
que esos datos existieron y de quién solicitó su eliminación.

**Aislamiento**: opera exclusivamente sobre las sesiones clínicas del
`patient_id` indicado dentro de la clínica del usuario autenticado; no
afecta a otros pacientes ni a otras clínicas (verificado en
`tests/test_retention_service.py::test_purge_does_not_touch_other_patients_data`).

Endpoint: `POST /api/v1/retention/patients/{patient_id}/purge` (ver
[api-specification.md](api-specification.md) §Retention). Cobertura de
test: `tests/test_retention_service.py` (capa de servicio: cascada
completa, atomicidad, permisos, auditoría, aislamiento, caso sin
sesiones) y `tests/test_retention_api.py` (capa HTTP: validación 422 de
`confirm`, 403 no-admin, 200 con recuento exacto).

## 9. Proveedores externos y envío de datos

**Actualizado en el cierre de la Fase 10 (2026-09-01) — desactualizado
desde la Fase 5**: esta sección afirmaba que las únicas implementaciones
disponibles de las ocho interfaces del AI Pipeline eran `Mock*` y que no
se integraba ningún proveedor real. Eso dejó de ser cierto en la Fase 5
(transcripción) sin que esta sección se actualizara — se corrige aquí,
junto con dos proveedores externos nuevos de la Fase 10 (Sentry, Railway)
que nunca formaron parte del AI Pipeline y por tanto nunca estuvieron
cubiertos por esta sección.

- Ningún dato (audio, transcripción, texto clínico) sale del entorno
  controlado hacia un proveedor externo sin que (a) exista una integración
  configurada explícitamente distinta de `mock`, y (b) exista consentimiento
  y configuración explícitos para ese tipo de envío.
- De las ocho interfaces del AI Pipeline (`TranscriptionProvider`,
  `LanguageModelProvider`, `SummaryGenerator`, `ClinicalFlagsGenerator`,
  `MissingInformationGenerator`, `AnamnesisGenerator`, `CostEstimator`,
  `TokenCounter` — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6), las
  siete relacionadas con generación por modelo de lenguaje siguen siendo
  exclusivamente `Mock*` en todos los entornos — ningún proveedor de pago
  (OpenAI, Anthropic, Claude API, Gemini u otro) se ha activado nunca,
  pese a que `Settings` ya soporta su configuración por `artifact_type`
  (Fase 6.3) — ver [development-plan.md](development-plan.md) §Fuera de
  las fases del MVP.
- **`TranscriptionProvider` es la excepción**, integrada desde la Fase 5
  (AssemblyAI) y la Fase 5.3 (Deepgram), seleccionable vía
  `TRANSCRIPTION_PROVIDER=mock|assemblyai|deepgram`:
  - **AssemblyAI** (`app/integrations/providers/assemblyai_transcription_provider.py`):
    endpoint configurado por defecto `https://api.assemblyai.com` (EE.UU.
    salvo indicación contraria). AssemblyAI **sí ofrece** un endpoint de
    residencia de datos en la UE (`https://api.eu.assemblyai.com`,
    servido desde AWS eu-west-1/Dublín, verificado en su documentación
    oficial en el cierre de esta fase) pero **la integración actual no lo
    usa por defecto** — `Settings.assemblyai_base_url` es configurable, la
    migración al endpoint UE (variable de entorno, sin cambio de código)
    queda pendiente de revisión si en el futuro se prefiere AssemblyAI
    sobre Deepgram (relevante para RGPD).
  - **Deepgram** (`app/integrations/providers/deepgram_transcription_provider.py`):
    endpoint UE por defecto y ya en uso, `https://api.eu.deepgram.com`
    (mismas credenciales que el genérico, sin coste ni activación
    adicional) — decisión deliberada para un producto sanitario, ver
    [transcription-benchmark.md](transcription-benchmark.md) §Endpoint EU
    por defecto.
  - **Estado real por entorno**: `TRANSCRIPTION_PROVIDER` permaneció en
    `mock` en todos los entornos, incluida production, hasta el cierre de
    la Fase 10 — las variables `ASSEMBLYAI_API_KEY`/`DEEPGRAM_API_KEY` de
    Railway seguían con el valor placeholder de `.env.example`. Se activó
    Deepgram (real) primero solo en staging; **actualizado el
    2026-09-14**: decisión de negocio explícita ya tomada, Deepgram
    (real) activado también en production, con `DEEPGRAM_API_KEY` propia
    de production (aislada de la de staging) — ver
    [development-plan.md](development-plan.md) §Fase 10 y §Fase 11 (nota
    de decisión de negocio). Ver más abajo el estado de los DPA de cada
    proveedor de IA real, ahora que hay tráfico de pago en production.
- **Sentry** (`app/core/sentry.py` backend, `frontend/src/shared/sentry.ts`),
  proveedor externo nuevo de la Fase 10.6 — EXCLUSIVAMENTE error
  tracking, nunca contenido clínico. Antes de que cualquier evento salga
  hacia Sentry: cuerpo de request/response eliminado, variables locales de
  traceback eliminadas, cabeceras reducidas a una lista blanca mínima
  (`content-type`, `x-request-id`), parámetros de breadcrumbs SQL
  eliminados (solo la sentencia parametrizada), `scope.user` limitado a
  `id` (UUID opaco, nunca email/nombre), sin Session Replay ni Profiling.
  Activo únicamente si `SENTRY_DSN`/`VITE_SENTRY_DSN` están configuradas
  — no-op en cualquier entorno sin ellas (ver §10).
- **Railway**, proveedor de hosting/infraestructura desde la Fase 10 (no
  un proveedor de IA): aloja los servicios de backend, frontend y
  PostgreSQL de production y de staging. Toda la base de datos (identidad
  de pacientes, contenido clínico, auditoría) reside físicamente en la
  infraestructura de Railway — no hay opción de despliegue alternativa
  todavía. Región `ams` (`europe-west4-drams3a`, Amsterdam) — confirmado
  en UE. Los Volume Backups y el WAL continuo del PITR (Fase 11, §8.1)
  también residen en Railway.
- **Bucket S3-compatible en la UE** (Fase 11.3, recomendado Cloudflare R2
  con jurisdicción EU): almacena los `pg_dump` completos de production,
  **cifrados en cliente con `age`** antes de salir del cron. El proveedor
  del bucket ve únicamente objetos `.dump.age` opacos — no puede
  descifrarlos (la clave privada de `age` nunca sale de la custodia
  offline de Gerard).

**Confirmado el 2026-09-17 — se mantiene el reparto dual de proveedor de
LLM.** Se planteó consolidar a un único proveedor de LLM (en vez del
reparto actual, `sonnet-5` para `summary` y `gpt-5.2` para
`patient_summary`/`missing_information`, decisión del 2026-09-14 más
arriba) por simplicidad de cara al DPA/subencargados. Decisión explícita
de Gerard: se deja como está — Anthropic y OpenAI siguen ambos activos en
production, cada uno con su propio DPA (ver justo abajo). Implicación
para la documentación legal: el DPA/RAT de Audiology AI Assistant debe
listar ambos como subencargados activos con su alcance real (Anthropic →
`summary`; OpenAI → `patient_summary` y `missing_information`), nunca
como proveedor "de respaldo" o alternativa intercambiable.

**Acuerdos de tratamiento de datos (DPA) — investigado el 2026-09-14,
resuelto el 2026-09-15.** Bloqueo estructural de §9 (arriba): ninguno de
los proveedores de pago con acceso a datos clínicos reales debe recibir
tráfico real de paciente hasta que esto se resuelva. Estado por
proveedor, verificado contra la documentación legal pública de cada uno:

- **Anthropic** (`ANTHROPIC_API_KEY`, `LLM_PROVIDER_SUMMARY=anthropic` en
  production): el DPA está incorporado automáticamente en los Commercial
  Terms of Service — se acepta al mismo tiempo que esos términos, sin
  firma aparte. Sin acción pendiente, salvo confirmar que la cuenta de
  Gerard está bajo esos Commercial Terms (cuenta de API/Console estándar,
  no un plan personal/gratuito). Texto: <https://www.anthropic.com/legal/data-processing-addendum>.
- **OpenAI** (`OPENAI_API_KEY`, `LLM_PROVIDER_PATIENT_SUMMARY`/
  `LLM_PROVIDER_MISSING_INFORMATION=openai` en production): mismo patrón
  — el DPA se incorpora automáticamente al usar la API/aceptar el OpenAI
  Services Agreement. Existe además un botón "Execute Data Processing
  Agreement" para obtener una copia firmada aparte — recomendado hacerlo
  para el propio archivo de cumplimiento, aunque no sea legalmente
  necesario. <https://openai.com/policies/data-processing-addendum/>.
- **Deepgram** (`DEEPGRAM_API_KEY`, activo en production desde hoy):
  **resuelto, firmado el 2026-09-15** — no era automático, se solicitó vía
  `success@deepgram.com` (Typeform de intake), Deepgram envió el DPA por
  DocuSign y quedó firmado por ambas partes el mismo día. Incluye Annex I
  (Scope of Processing, con las SCCs y el UK Addendum referenciados) y
  Annex II (medidas técnicas y organizativas). Copia firmada en
  `docs/legal/deepgram-dpa-signed-2026-09-15.pdf` (fuera de git, ver
  `docs/legal/README.md`).
- **Railway**: **resuelto, firmado el 2026-09-15** — DPA vía DocuSign
  (autoservicio, <https://railway.com/legal/dpa>), incluye EU SCCs y UK
  Addendum. Copia firmada en `docs/legal/railway-dpa-signed-2026-09-15.pdf`
  (fuera de git, ver `docs/legal/README.md`).
- **Cloudflare** (bucket R2 de backups): **resuelto, sin acción** —
  confirmado en su FAQ pública de GDPR que el DPA estándar "se incorpora
  por referencia" automáticamente al Self-Serve Subscription Agreement de
  cualquier cuenta de autoservicio (solo las cuentas enterprise lo
  gestionan aparte con su Customer Success Manager) — la cuenta de
  Cloudflare de Gerard (dominio + R2) ya lo tiene en vigor.

**Actualizado el 2026-09-15: los cinco DPA de proveedores con acceso a
datos clínicos reales están resueltos** (Anthropic y OpenAI automáticos,
Cloudflare automático, Railway y Deepgram firmados vía DocuSign). Queda
satisfecha la condición explícita de §9 para dar de alta el primer
paciente real, en lo que respecta a este bloqueo — sin perjuicio de
cualquier otro requisito legal/regulatorio que surja por separado (ver
[development-plan.md](development-plan.md) para el resto de deuda técnica
de Fase 10/11).

**Sexto proveedor, añadido el 2026-09-15 — Brevo** (email transaccional,
aún no activo en production: dependencia nueva de la Fase 12, onboarding
self-service multi-clínica, ver [fase-12-rfc.md](fase-12-rfc.md) §5). A
diferencia de los cinco anteriores, Brevo **nunca procesa datos de
pacientes** — solo datos de contacto del personal de clínica (nombre,
email de quien se registra o es invitado). **Resuelto, sin acción** — el
DPA (Anexo 2 de los Términos de Servicio de Brevo, entidad Sendinblue SAS
para clientes de España) se incorpora por referencia automáticamente
desde la creación de la cuenta, sin firma independiente. Copia en
`docs/legal/brevo-dpa-2026-09-15.pdf` (fuera de git, ver
`docs/legal/README.md`).

**Actualizado el 2026-09-16 — política de no entrenamiento en Deepgram
(`mip_opt_out`).** El DPA firmado de Deepgram (cláusula 8.1) supedita sus
protecciones más fuertes (procesamiento estrictamente en memoria, sin
persistencia) a que la petición incluya el parámetro `mip_opt_out=true`;
sin él, Deepgram inscribe por defecto al cliente en su "Model Improvement
Partnership Program" y puede retener audio/transcripciones para mejorar
sus modelos — es opt-out, no opt-in. Se verificó que la integración no lo
enviaba y se corrigió: `DeepgramTranscriptionProvider` incluye
`mip_opt_out=true` de forma incondicional en toda petición
(`app/integrations/providers/deepgram_transcription_provider.py`),
trazado en `provider_metadata.mip_opt_out_requested`, y cubierto por dos
tests dedicados de compliance/seguridad
(`tests/test_deepgram_provider.py`) para que un futuro refactor no lo
elimine sin que CI lo detecte. Decisión de negocio: los datos de
pacientes no se utilizan para entrenamiento ni mejora general de modelos
por parte de ningún proveedor, salvo decisión explícita y documentada en
sentido contrario — primer paso concreto de esa política más amplia (ver
[transcription-benchmark.md](transcription-benchmark.md) §Política de no
entrenamiento).

### 9.1 Política de no entrenamiento de modelos por proveedores externos — añadido 2026-09-16

Política de negocio explícita: ningún dato de paciente (audio,
transcripción, texto clínico) se utiliza para entrenar o mejorar modelos
de un proveedor externo, salvo decisión explícita y documentada en
sentido contrario. Estado verificado, proveedor por proveedor, a fecha de
esta entrada:

- **Deepgram**: por defecto (opt-out, no opt-in) un cliente estándar está
  inscrito en su "Model Improvement Partnership Program". Resuelto a
  nivel técnico — ver más arriba, `mip_opt_out=true` incondicional en
  toda petición, cubierto por tests de compliance dedicados.
- **Anthropic** (`ANTHROPIC_API_KEY`, API/Claude for Work — no Claude.ai
  consumer): por defecto NO se usan inputs/outputs de productos
  comerciales para entrenar modelos
  (<https://privacy.claude.com>, verificado 2026-09-16). Única excepción:
  feedback explícito (botón de pulgar arriba/abajo), aplicable a un uso
  interactivo tipo consola/playground, no al tráfico programático de
  producción. **Acción pendiente de Gerard** (no ejecutable desde aquí,
  requiere su cuenta): confirmar/desactivar el toggle "Rate chats" en
  Organization settings → Data and Privacy del Console de Anthropic, como
  medida de defensa en profundidad — nunca se debe además probar prompts
  con datos reales de pacientes en el playground del Console.
- **OpenAI** (`OPENAI_API_KEY`): por defecto NO se usan datos de la API
  para entrenar modelos, requiere opt-in explícito que nunca se ha
  activado (<https://developers.openai.com/api/docs/guides/your-data>,
  verificado 2026-09-16). Retención por defecto: hasta 30 días en logs de
  prevención de abuso, no como dato de entrenamiento. Sin acción
  pendiente.
- **Railway, Cloudflare, Brevo**: no son proveedores de modelos de IA —
  fuera del alcance de esta política (infraestructura/hosting y email
  transaccional, ver más arriba en esta misma sección).

Esta política se refleja también, a nivel contractual, en los DPA ya
firmados/incorporados de cada proveedor (arriba), y debe trasladarse al
apartado correspondiente de los Términos de Servicio/DPA propios de
Audiology AI Assistant cuando se redacten o revisen (ver
[fase-13-rfc.md](fase-13-rfc.md) para el resto de documentación legal
pendiente de cierre).

## 10. Gestión de secretos

- Todo secreto (credenciales de base de datos, claves de API, clave de
  firma de autenticación) se lee exclusivamente de variables de entorno.
- Se mantiene un `.env.example` versionado con las claves necesarias y
  valores de ejemplo no funcionales; `.env` real nunca se versiona
  (incluido en `.gitignore` desde el primer commit del esqueleto de
  proyecto).
- `JWT_SECRET_KEY` (Fase 9, hito 9.1): clave de firma HS256 del JWT de
  autenticación (`app/auth/service.py`, `core/current_user.py`), leída
  exclusivamente de `Settings.jwt_secret_key` — nunca hardcodeada.
  Obligatoria en todos los entornos (sin default de Python, mismo
  criterio que `POSTGRES_PASSWORD`); `_validate_production_safety`
  rechaza el arranque en production **o staging** (Fase 10.7 —
  `is_production or is_staging`, ver
  [development-plan.md](development-plan.md) §Fase 10) si coincide con
  el placeholder de `.env.example` (`CHANGE_ME_LOCAL_ONLY`, mismo
  mecanismo que ya protegía `POSTGRES_PASSWORD`). Práctica ya implementada desde el
  despliegue a Railway (Fase 10.3/10.7): **`JWT_SECRET_KEY` es distinto
  entre production y staging** — nunca la misma clave de firma
  compartida entre los dos entornos, para que un token emitido en uno no
  sea válido en el otro.
- `RETENTION_CRON_SECRET` (Fase 10.4): autentica al cron externo de
  Railway que dispara `POST /api/v1/retention/system-purge` — mismo
  criterio de guardarraíl que `JWT_SECRET_KEY` (obligatorio, sin default,
  rechazado en production/staging si coincide con el placeholder). El
  endpoint lo compara con `secrets.compare_digest`, nunca `==`.
- `ONBOARDING_CLEANUP_CRON_SECRET` (Fase 12, hito 12.4): mismo patrón que
  `RETENTION_CRON_SECRET` de arriba, pero para el cron externo de Railway
  que dispara `POST /api/v1/onboarding/system-cleanup` (purga de clínicas
  fantasma nunca verificadas, ver
  [development-plan.md](development-plan.md) §Fase 12) — obligatorio, sin
  default, rechazado en production/staging si coincide con el
  placeholder, comparado con `secrets.compare_digest`. Secreto propio y
  distinto de `RETENTION_CRON_SECRET`, no reutilizado entre ambos crons,
  para que revocar/rotar uno no afecte al otro.
- `ASSEMBLYAI_API_KEY`/`DEEPGRAM_API_KEY` (Fase 5/5.3, activación real
  decidida en la Fase 10 — ver §9): opcionales, solo obligatorias si
  `TRANSCRIPTION_PROVIDER` selecciona ese proveedor.
  `.env.example` las documenta con el placeholder
  `CHANGE_ME_LOCAL_ONLY`, igual que el resto de secretos — hasta el
  cierre de la Fase 10 ambas seguían con ese placeholder en Railway en
  todos los entornos. Nunca se registran en logs ni en
  `ai_generation_runs` (que de todos modos nunca captura credenciales,
  ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.5).
  **Política de manejo de la clave real activada en staging (acordada
  2026-09-01, cierre de la Fase 10; ampliada a production el
  2026-09-14)**:
  1. Heredar una clave real de un proveedor de transcripción está
     permitido en staging **y, desde el 2026-09-14, en production**
     (`TRANSCRIPTION_PROVIDER=deepgram`, decisión de negocio documentada
     en [development-plan.md](development-plan.md) §Fase 10 — prioriza
     la separación correcta de hablantes sobre el menor WER de
     AssemblyAI). **Claves distintas por entorno**: la `DEEPGRAM_API_KEY`
     de production es propia, nunca la misma que la de staging, para
     aislar cuota y facturación entre los dos.
  2. Ninguna prueba automática (CI, suite de tests) debe poder disparar
     una transcripción real bajo ninguna circunstancia, en ningún
     entorno — la suite completa sigue usando exclusivamente
     `MockTranscriptionProvider`; ningún test se ejecuta contra staging
     ni production.
  3. Las pruebas manuales contra staging que ejerciten el proveedor real
     deben ser deliberadamente mínimas — nunca una fuente sistemática o
     recurrente de tráfico de prueba. **En production, el tráfico real
     es tráfico de uso real del producto, no de prueba** — no aplica
     esta restricción de minimizar, pero sí el resto de puntos.
  4. Debe quedar documentado (aquí) que tanto las pruebas manuales en
     staging como el uso en production consumen cuota/facturación real
     del proveedor, no una simulación.

     Se sustituirá por credenciales de entorno sandbox si AssemblyAI o
     Deepgram llegan a ofrecerlas más adelante — ver
     [development-plan.md](development-plan.md) §Fase 10 para el
     hallazgo completo (transcripción llevaba en `mock` en todos los
     entornos, incluida production, hasta el cierre de la Fase 10) y la
     decisión de activación en production del 2026-09-14.
- `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` (proveedor LLM real, activación
  decidida el 2026-09-14 — ver §7 y
  [development-plan.md](development-plan.md) §Fase 10): mismo criterio
  que `ASSEMBLYAI_API_KEY`/`DEEPGRAM_API_KEY` — obligatorias solo si el
  `artifact_type` correspondiente (`LLM_PROVIDER_SUMMARY`/
  `LLM_PROVIDER_PATIENT_SUMMARY`/`LLM_PROVIDER_MISSING_INFORMATION`)
  selecciona ese proveedor, `.env.example` con placeholder
  `CHANGE_ME_LOCAL_ONLY`, claves de production propias y distintas de
  cualquier clave de desarrollo o de benchmark (`benchmark/generation`
  usa `OPENROUTER_API_KEY`, una clave y una cuenta completamente
  distintas). Nunca se registran en logs ni en `ai_generation_runs`.
- `SENTRY_DSN` (backend) / `VITE_SENTRY_DSN` (frontend, inyectada en
  build-time del `Dockerfile.prod`, ver §9): opcionales, sin valor por
  defecto — si no están configuradas, Sentry no se inicializa en ningún
  entorno, ni siquiera production. El DSN de Sentry no es, en sí, un
  secreto de alto riesgo (es de solo-escritura hacia el proyecto Sentry,
  pensado para ir embebido en el bundle del frontend), pero se gestiona
  con el mismo mecanismo que el resto de configuración por entorno —
  nunca hardcodeado, nunca commiteado con un valor real.
- Nunca se registran secretos en logs ni en `audit_logs.metadata` — esto
  incluye contraseñas en claro (nunca se persisten, solo su hash
  `bcrypt`) y JWT emitidos.
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
| Ausencia de cabeceras de seguridad HTTP, rate limiting y límites de subida sin revisar (Fase 8, hito 8.4) | **Cerrado en la Fase 10.5** (deuda de la Fase 8.4, aplazada hasta que existiera un objetivo de despliegue real): `SecurityHeadersMiddleware` (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security` en production/staging), rate limiting con `slowapi` (120/minute general, 5/minute en `POST /auth/login`, `/health`/`/ready` exentos, cliente identificado por `X-Forwarded-For` detrás del proxy de Railway) y `RequestSizeLimitMiddleware` — ver [development-plan.md](development-plan.md) §Fase 10, hito 10.5. Limitación conocida y aceptada: el `Limiter` es en memoria del proceso (sin Redis), correcto solo mientras el despliegue sea de una única réplica. |

## 12. `CurrentUserProvider`: alcance y limitaciones (Fase 2, actualizado Fase 9)

Dos implementaciones de `CurrentUserProvider`, seleccionadas por
`settings.auth_mode` (`core/deps.py::get_current_user_provider()`):

**`FakeCurrentUserProvider`** (`auth_mode=fake`, por defecto) es una
herramienta de desarrollo, **no** un mecanismo de autenticación:

- No verifica contraseña, posesión de dispositivo ni ningún factor real —
  solo confirma que el `id` recibido corresponde a un usuario existente y
  activo en la base de datos.
- Cualquiera con acceso a la API de desarrollo puede actuar como
  cualquier usuario simplemente enviando su UUID en `X-Dev-User-Id`. Esto
  es aceptable únicamente porque no hay datos reales ni exposición
  pública durante el MVP.
- Se rechaza estructuralmente en `ENVIRONMENT=production` (la aplicación
  falla al arrancar si es la implementación resuelta, ver
  [architecture.md](architecture.md) §9).
- El endpoint de apoyo `/dev/users` (que lista usuarios para poblar el
  selector del frontend) tampoco existe cuando `ENVIRONMENT=production`.

**`RealCurrentUserProvider`** (`auth_mode=real`, Fase 9, hito 9.1) sí es
un mecanismo de autenticación válido para producción — cierra la
limitación que esta misma sección documentaba hasta la Fase 8 ("la API
no tiene, todavía, un modo de funcionamiento válido en producción"):

- Decodifica y valida un JWT Bearer del header `Authorization: Bearer
  <token>`, firmado por `AuthService.login`
  (`POST /api/v1/auth/login`, `app/auth/`) — email + contraseña
  verificada con `bcrypt` contra `users.password_hash`.
- Token de vida media (8h), sin refresh tokens ni blacklist de
  revocación en esta ronda — logout es solo del lado cliente (descarta
  el token). MFA queda fuera de esta ronda; rate limiting del endpoint de
  login conecta con la deuda ya documentada en el hito 8.4 (5/minute,
  cerrado en la Fase 10.5).
- Mismo criterio de validación de usuario que `FakeCurrentUserProvider`:
  el usuario referenciado por el token debe existir y estar activo — un
  JWT válido pero de un usuario desactivado después de emitirlo se
  rechaza igualmente.
- `_validate_production_safety` (`core/config.py`) exige `auth_mode ==
  "real"` en `ENVIRONMENT=production` — production con
  `FakeCurrentUserProvider` ya no es posible ni siquiera por omisión de
  configuración.
- **Corregido 2026-09-18**: esta sección decía "sin pantalla de login en
  el frontend todavía (hito 9.2, pendiente)" — quedó desactualizada sin
  que nadie volviera a corregirla. El hito 9.2 (`frontend/src/shared/
  auth/LoginForm.tsx` + `AuthContext.tsx`) está implementado y mergeado
  desde hace tiempo: con `VITE_AUTH_MODE=real`, `App.tsx` renderiza
  `RealAuthApp`, que bloquea todas las rutas tras la pantalla de login
  hasta que exista un token válido (verificado leyendo el código fuente
  actual, no solo esta documentación — ver `frontend/src/App.tsx`,
  función `RealAuthApp`). Reseteo de contraseña también está
  implementado, pero para el personal de clínica (Fase 12, hito 12.0 —
  `PasswordResetRequestPage`/`PasswordResetConfirmPage`), no como parte
  de esta ronda de Fase 9. **Pendiente de verificar** (no ejecutable
  desde el código: requiere mirar la configuración real de Railway): que
  la variable de build `VITE_AUTH_MODE` de production esté efectivamente
  en `real` — aunque, aunque no lo estuviera, la barrera de seguridad
  real está en el backend (`AUTH_MODE=real` obligatorio en producción,
  punto anterior), así que un frontend mal configurado degradaría la
  experiencia de uso, no abriría una vía de acceso sin autenticación a
  la API.

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
