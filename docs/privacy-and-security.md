# Privacidad y seguridad — Audiology AI Assistant

## 1. Principio general

Durante todo el desarrollo del MVP se usan exclusivamente pacientes, audios
y conversaciones **ficticios**. No se introducen datos sanitarios reales
bajo ninguna circunstancia. `patients.is_fictional` se fuerza a `true` a
nivel de aplicación en el MVP.

Aun así, el sistema se diseña como si fuera a manejar datos reales en el
futuro (privacidad desde el diseño), para no tener que rediseñar el modelo
cuando eso ocurra.

## 2. Minimización de datos

- `patients` almacena solo lo estrictamente necesario para distinguir un
  paciente en la UI (nombre, fecha de nacimiento, referencia interna).
- `audit_log.metadata` nunca contiene el contenido clínico completo, solo
  identificadores y una descripción breve de la acción.
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
  `patients.date_of_birth`), se deja preparada la posibilidad de cifrado a
  nivel de aplicación (columna) como mejora futura — **no implementado
  todavía en el MVP**, documentado como deuda consciente.
- Los ficheros de audio se almacenan fuera del control de versiones, en un
  volumen/almacenamiento dedicado con acceso restringido al backend.

## 5. Control de acceso basado en roles (RBAC)

Roles del MVP: `admin`, `clinician`. Ver matriz completa de permisos por
endpoint en [api-specification.md](api-specification.md). Reglas generales:

- Un `clinician` solo puede generar/editar/aprobar documentos de sesiones
  donde figura como `clinician_id` responsable (a definir en Fase 7 si se
  permite acceso cruzado entre profesionales; por defecto, **no**).
- Solo `admin` accede a `audit_log` y a la gestión de usuarios.
- La exportación de un documento no aprobado está bloqueada a nivel de API,
  no solo de UI.

## 6. Registro de auditoría

`audit_log` es append-only (sin `UPDATE` ni `DELETE` desde la aplicación).
Se registra, como mínimo:

- creación/edición de pacientes y sesiones;
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
- accesos de administrador al propio `audit_log` (opcional, evaluar en
  Fase 9).

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
  scheduler/cron todavía, eso queda para la Fase 9 del
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

- Todo secreto (credenciales de base de datos, futuras claves de API,
  `SECRET_KEY` de JWT) se lee exclusivamente de variables de entorno.
- Se mantiene un `.env.example` versionado con las claves necesarias y
  valores de ejemplo no funcionales; `.env` real nunca se versiona
  (incluido en `.gitignore` desde el primer commit del esqueleto de
  proyecto).
- Nunca se registran secretos en logs ni en `audit_log.metadata`.
- Revisión obligatoria antes de cualquier commit: que no se haya
  incrustado ninguna clave, token o contraseña en código o configuración.

## 11. Amenazas consideradas (resumen, no exhaustivo)

| Amenaza | Mitigación en el MVP |
|---|---|
| Fuga de identidad de paciente vía logs/errores | Identidad separada del contenido clínico; `audit_log.metadata` sin contenido clínico completo |
| Acceso no autorizado a documentos clínicos | JWT + RBAC por endpoint |
| Exportación de documento no revisado | Bloqueo a nivel de API si `status != approved` |
| Secretos filtrados en el repositorio | Solo variables de entorno, `.env` en `.gitignore`, revisión previa a commit |
| Envío accidental a proveedor de pago real | Solo implementaciones `Mock*` disponibles en el MVP; activar un proveedor real requiere cambio explícito de configuración |
| Pérdida de trazabilidad de cambios clínicos | `document_versions` + `audit_log` obligatorios en cada escritura |
| Borrado accidental de un documento aprobado | Borrado lógico obligatorio en dominio/servicio; no existe operación de borrado físico expuesta para `anamnesis_documents`/`session_notes` |
| Audio ficticio acumulado indefinidamente | Retención configurable (30 días por defecto) + `RetentionCleanupService`, purgable manualmente |
| Subida de audio malicioso/con formato no soportado | Validación de tamaño, duración, extensión y tipo MIME contra lista blanca antes de pasar a `ready` |
