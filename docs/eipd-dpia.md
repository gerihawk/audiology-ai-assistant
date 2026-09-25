# Evaluación de Impacto relativa a la Protección de Datos (EIPD/DPIA) — Audiology AI Assistant

## 0. Aviso legal sobre este documento

Este documento es un **borrador de trabajo técnico**, elaborado a partir
de la documentación de arquitectura, seguridad y privacidad ya existente
del proyecto ([privacy-and-security.md](privacy-and-security.md),
[clinical-safety.md](clinical-safety.md),
[data-model.md](data-model.md)) y de la metodología pública de la Agencia
Española de Protección de Datos (AEPD) para la gestión del riesgo y la
evaluación de impacto[^1]. **No sustituye el asesoramiento de un abogado
o de un Delegado de Protección de Datos (DPO)**, y no debe presentarse
como la EIPD formal y definitiva de la clínica o de Audiology AI
Assistant hasta que un profesional cualificado la revise, la complete
donde haga falta juicio legal (en particular §3, §7 y §8) y la firme.
Es el paso previo pactado en la hoja de ruta del proyecto antes de esa
revisión ("EIPD → DPA/ToS → abogado").

Responsable de la evaluación: Gerard Abelló Falcó (responsable del
tratamiento / desarrollador del producto). Fecha de esta versión:
2026-09-18. Alcance: el tratamiento de datos de pacientes realizado por
la plataforma Audiology AI Assistant (backend + integraciones), no el
tratamiento que cada clínica cliente realice por sus propios medios
fuera de la plataforma.

[^1]: AEPD, *Gestión del riesgo y evaluación de impacto en tratamientos
    de datos personales* (2021) y *Listas de tipos de tratamiento de
    datos que requieren/no requieren una evaluación de impacto*, ambas
    disponibles en aepd.es; y Directrices WP248 rev.01 del anterior Grupo
    de Trabajo del Artículo 29 (hoy Comité Europeo de Protección de
    Datos).

## 1. Descripción del tratamiento

### 1.1 Finalidad

Prestar a clínicas de audiología un servicio SaaS de apoyo documental
clínico: grabación y transcripción de sesiones con el paciente,
generación asistida por IA de un resumen de sesión, un resumen para el
paciente, un listado de información pendiente de recabar (anamnesis) y,
en el futuro, un checklist de señales de alerta — todo ello como
**borrador sujeto a revisión y aprobación humana explícita**, nunca como
diagnóstico ni decisión automatizada (ver
[clinical-safety.md](clinical-safety.md) §1 y §5).

### 1.2 Base jurídica

- Para el **audioprotesista/clínica** (responsable del tratamiento frente
  a su paciente): art. 9.2.h RGPD (asistencia sanitaria) en relación con
  la Ley 41/2002 de autonomía del paciente, más el consentimiento
  específico del paciente para la grabación/procesamiento por IA
  (registrado en `consents`, ver §1.5).
- Para **Audiology AI Assistant** frente a la clínica: encargado del
  tratamiento (art. 28 RGPD) — la relación se formaliza en un contrato de
  encargo de tratamiento (DPA) propio de Audiology AI Assistant hacia sus
  clínicas clientes, pendiente de redacción (ver
  [fase-13-rfc.md](fase-13-rfc.md) y la hoja de ruta de este mismo
  documento en §9).
- **Importante**: esta EIPD la realiza Audiology AI Assistant como
  encargado, anticipando y documentando el riesgo del tratamiento que
  diseña y opera técnicamente; no sustituye la EIPD que, si procede, deba
  realizar cada clínica como responsable del tratamiento frente a sus
  propios pacientes — sí le sirve de insumo técnico principal.

### 1.3 Categorías de interesados

- Pacientes de las clínicas clientes (identidad + contenido clínico).
- Personal de las clínicas clientes: administradores y audioprotesistas
  (cuentas de usuario, identidad profesional — nunca datos de salud
  propios).

### 1.4 Categorías de datos

| Categoría | Dato | Tabla | Sensibilidad |
|---|---|---|---|
| Identidad del paciente | Nombre para mostrar, año de nacimiento, código interno | `patients` | Personal — deliberadamente **sin** DNI, NSS, dirección, teléfono ni email del paciente (ver [privacy-and-security.md](privacy-and-security.md) §2) |
| Contenido clínico | Audio de la sesión | `audio_recordings` (blob) | Categoría especial (art. 9 RGPD, dato de salud por naturaleza de la conversación) |
| Contenido clínico | Transcripción, resumen, resumen para paciente, anamnesis, información ausente | `ai_artifact_versions.content` | Categoría especial |
| Contenido clínico (futuro, no implementado aún) | Señales de alerta / motivos de derivación | `clinical_flags` | Categoría especial |
| Consentimiento | Grabación / procesamiento IA / almacenamiento, versión de política aceptada | `consents` | Personal |
| Identidad del personal de clínica | Nombre, email, rol, hash de contraseña (`bcrypt`) | `users` | Personal |
| Trazabilidad | Quién hizo qué, cuándo, sobre qué entidad (nunca el valor del dato) | `audit_logs` | Personal (metadatos de actividad) |
| Telemetría técnica de IA | Proveedor, modelo, coste, tokens, latencia — nunca contenido salvo activación explícita | `ai_generation_runs` | Personal (indirectamente, por asociación a la sesión) |

### 1.5 Consentimiento del paciente

`consents` registra si el paciente consintió grabación de audio,
procesamiento por IA y almacenamiento, con la versión de política
aceptada (`consent_version`). Es un registro declarativo del
profesional, no una verificación contra un documento firmado externo —
limitación reconocida en §8. Desde el 2026-09-14,
`AI_PROCESSING_CONSENT_ENFORCED=true` en producción: generar contenido
de IA sin un consentimiento de `procesamiento_ia` vigente devuelve `409`
(ver [privacy-and-security.md](privacy-and-security.md) §7).

### 1.6 Ciclo de vida del dato

1. **Captura**: subida de audio, validado por tamaño/duración/formato
   antes de pasar a `ready`.
2. **Transcripción**: enviado a Deepgram (endpoint UE,
   `api.eu.deepgram.com`, `mip_opt_out=true` para excluir el uso del
   audio en el entrenamiento de sus modelos).
3. **Generación asistida por IA**: la transcripción (nunca el audio en
   sí) se envía a Anthropic (resumen de sesión) y OpenAI (resumen para
   paciente, información ausente) según el `artifact_type`.
4. **Revisión y aprobación humana**: obligatoria antes de que cualquier
   artefacto de IA pueda exportarse o considerarse parte del expediente
   (ver [clinical-safety.md](clinical-safety.md) §5).
5. **Almacenamiento**: base de datos PostgreSQL en Railway (Amsterdam,
   UE); audio en almacenamiento de objetos separado.
6. **Retención**: audio, 30 días por defecto (purgable antes o después
   según política de la clínica); contenido clínico (`ai_artifacts`,
   `clinical_sessions`), sin límite de purga automática — solo borrado
   lógico, salvo la purga definitiva bajo demanda del §1.7.
7. **Eliminación**: purga física manual y auditada de todo el contenido
   clínico de un paciente concreto
   (`RetentionCleanupService.purge_patient_clinical_data()`, ver
   [privacy-and-security.md](privacy-and-security.md) §8.2), o purga
   automática/manual del audio expirado por antigüedad (§8).
8. **Copia de seguridad**: `pg_dump` diario cifrado con `age` antes de
   salir del entorno, a un bucket S3-compatible en la UE (§1 de
   [privacy-and-security.md](privacy-and-security.md) §8.1).

### 1.7 Ejercicio de derechos del interesado

- **Acceso/rectificación**: vía la propia clínica (responsable del
  tratamiento frente al paciente), que edita los datos en la plataforma.
- **Supresión (art. 17 RGPD)**: hasta el 2026-09-18 no existía ningún
  camino técnico para borrar físicamente el contenido clínico de un
  paciente — solo borrado lógico indefinido. `purge_patient_clinical_data()`
  cerró esa parte ese día, pero **no** la identidad del paciente
  (`patients.display_name`/`birth_year`/`notes`/`internal_code`), que
  siguió intacta hasta el 2026-09-23 — una versión anterior de esta
  sección y el riesgo R6 de §5/§6 daban por cerrado el derecho de
  supresión completo citando solo la purga clínica, lo cual era
  impreciso: el art. 17 cubre todos los datos personales, no solo el
  contenido clínico. Desde 2026-09-23, la misma operación también
  anonimiza in-place la identidad (ver
  [privacy-and-security.md](privacy-and-security.md) §8.2) — ahora sí es
  una purga atómica, admin-only, con doble confirmación y entrada de
  auditoría que sobrevive al borrado, cubriendo identidad y contenido
  clínico en la misma transacción. **Importante**: la decisión de
  *cuándo* procede legalmente borrar (p. ej. tras el plazo mínimo de
  conservación de la historia clínica en España — 5 años desde el alta,
  art. 17 Ley 41/2002) es un juicio de la clínica caso por caso, no un
  temporizador automático del sistema. **Límite que sigue sin cubrir**:
  ni los backups ya tomados (§8.1/§8.2 de
  [privacy-and-security.md](privacy-and-security.md)) ni los
  subencargados externos (Deepgram, OpenAI, Anthropic — §2.2 más abajo)
  purgan retroactivamente los datos de un paciente ya anonimizado.
- **Portabilidad/oposición**: sin mecanismo dedicado todavía — pendiente
  de valorar junto con el DPA/ToS propio de Audiology AI Assistant.

## 2. Actores que intervienen en el tratamiento

### 2.1 Responsables y encargados

| Rol RGPD | Actor |
|---|---|
| Responsable del tratamiento (frente al paciente) | La clínica cliente |
| Encargado del tratamiento (frente a la clínica) | Audiology AI Assistant (Gerard Abelló Falcó) |
| Subencargados (frente a Audiology AI Assistant) | Ver tabla siguiente |

### 2.2 Subencargados con acceso a datos clínicos reales

Estado verificado en [privacy-and-security.md](privacy-and-security.md)
§9, a fecha 2026-09-18:

| Proveedor | Rol | Datos que recibe | Ubicación / transferencia internacional | DPA |
|---|---|---|---|---|
| Deepgram, Inc. | Transcripción de audio | Audio de la sesión | Endpoint UE (`api.eu.deepgram.com`) | **Firmado** 2026-09-15, incluye SCC + UK Addendum |
| Anthropic | Generación LLM (`summary`) | Transcripción de la sesión (texto) | EE. UU. (Commercial Terms, SCC incorporadas) | **Incorporado automáticamente** a los Commercial Terms of Service |
| OpenAI | Generación LLM (`patient_summary`, `missing_information`) | Transcripción de la sesión (texto) | EE. UU. (Services Agreement, SCC incorporadas) | **Incorporado automáticamente**; copia firmada aparte recomendada y pendiente de obtener por Gerard para su propio archivo |
| Railway Corporation | Hosting (backend, frontend, PostgreSQL) | Todo el contenido clínico y de identidad — es donde reside la base de datos completa | UE, región `ams` (Amsterdam) | **Firmado** 2026-09-15, incluye SCC + UK Addendum |
| Cloudflare (bucket R2) | Almacenamiento de copias de seguridad cifradas | `pg_dump` completo, pero cifrado en cliente con `age` antes de salir — Cloudflare solo ve blobs opacos, no puede descifrarlos | UE (jurisdicción EU del bucket) | **Incorporado automáticamente** al Self-Serve Subscription Agreement |
| Brevo (Sendinblue SAS) | Email transaccional | Solo datos de contacto del **personal de clínica** (nombre, email de registro/invitación) — **nunca** datos de paciente | No especificado explícitamente en la documentación del proyecto — pendiente de verificar para el registro de actividades de tratamiento | **Incorporado automáticamente** (Anexo 2 de sus Términos de Servicio) |
| Sentry | Error tracking | Ningún contenido clínico (cuerpo de petición, variables de traceback y cabeceras no esenciales eliminados antes del envío); solo un UUID opaco de usuario | No verificado en la documentación del proyecto | **No documentado** — pendiente de confirmar si Sentry trata datos personales (el UUID de usuario podría considerarse dato personal pseudonimizado) y, si es así, obtener/confirmar su DPA |

Los cinco proveedores con acceso a datos clínicos reales (Deepgram,
Anthropic, OpenAI, Railway, Cloudflare) tenían su DPA resuelto a fecha
2026-09-15, condición que el propio proyecto se impuso antes de dar de
alta el primer paciente real. **Pendiente de esta EIPD**: cerrar el
estado de Sentry y confirmar la jurisdicción del DPA de Brevo (filas
sombreadas arriba).

**Propagación de borrado hacia estos subencargados — investigado
2026-09-23, alimenta la TIA pendiente (ver
[antes-del-primer-cliente]).** Cuando `purge_patient_clinical_data()`
anonimiza a un paciente (§1.7), el audio/transcripción que ya se envió a
estos proveedores para procesarlo **no se borra retroactivamente en su
lado** — la plataforma no reenvía ninguna solicitud de supresión aguas
abajo hoy. Estado confirmado por proveedor contra fuente oficial:

- **Anthropic**: confirmado explícitamente que **no** ofrece borrado bajo
  demanda a clientes de pago de la API — "For paid API customers, we do
  not support ad hoc deletion" ([Anthropic Privacy Center — Can you
  delete data that I sent via
  API?](https://privacy.claude.com/en/articles/7996875-can-you-delete-data-that-i-sent-via-api)).
  Los datos expiran según su política de retención estándar, no por
  solicitud individual.
- **OpenAI**: los logs de monitorización de abuso se retienen hasta 30
  días por defecto; existe un control de "Zero Data Retention" pero
  requiere aprobación previa de OpenAI y es prospectivo (se aplica a
  peticiones futuras, no borra retroactivamente lo ya enviado); algunos
  endpoints quedan excluidos de ZDR ([OpenAI — Data controls in the
  OpenAI platform](https://developers.openai.com/api/docs/guides/your-data)).
  No se documenta un procedimiento de borrado retroactivo a petición.
- **Deepgram**: no se pudo confirmar con una fuente oficial el plazo de
  retención de audio ni un mecanismo de borrado a petición — su propia
  documentación remite a una sección "Your Data at Deepgram" no accesible
  públicamente; pendiente de pedirlo directamente al equipo de cuenta de
  Deepgram (tienen DPA firmado, es el canal natural para preguntarlo).

**Conclusión para la TIA y el DPA/RAT/ToS con la clínica**: el
compromiso de "eliminamos tus datos cuando lo pidas" que la plataforma
le pueda hacer a una clínica solo puede cubrir, hoy, lo que vive en la
infraestructura propia (Railway) — no lo ya enviado a Anthropic/OpenAI
para generación de contenido. Esto debe quedar explícito en el DPA (plazo
de devolución/eliminación de datos, uno de los `[PLACEHOLDER]`
pendientes) en vez de prometer un borrado total que hoy no es técnicamente
posible.

### 2.3 Política de no entrenamiento de modelos

Decisión de negocio explícita y verificada proveedor por proveedor
(2026-09-16): ningún dato de paciente se usa para entrenar o mejorar
modelos de un proveedor externo. Deepgram requería una acción técnica
activa (`mip_opt_out=true`, opt-out y no opt-in) que ya estaba
implementada y cubierta por tests dedicados; Anthropic y OpenAI no usan
datos de la API para entrenamiento por defecto. Detalle completo en
[privacy-and-security.md](privacy-and-security.md) §9.1.

## 3. ¿Es obligatoria una EIPD para este tratamiento?

Según el listado orientativo de la AEPD (basado en las directrices
WP248), un tratamiento requiere EIPD cuando cumple **dos o más** de once
criterios. Este tratamiento cumple, como mínimo, dos:

1. **Tratamiento a gran escala de categorías especiales de datos (art.
   9 RGPD)**: el audio y el contenido clínico derivado son, por
   naturaleza, datos de salud de los pacientes de todas las clínicas
   cliente de la plataforma.
2. **Uso de nuevas tecnologías o un uso innovador**: generación de
   contenido clínico mediante modelos de lenguaje de terceros
   (Anthropic, OpenAI) sobre transcripciones de sesiones sanitarias.

Adicionalmente, podría discutirse un tercer criterio parcial
(perfilado/evaluación) por el checklist de señales de alerta —
actualmente sin implementar, ver §8 — que en todo caso quedaría
mitigado por no existir todavía y, si se implementa, por requerir
siempre revisión humana antes de tener ningún efecto (nunca decisión
automatizada en el sentido del art. 22 RGPD, ver
[clinical-safety.md](clinical-safety.md) §5).

**Conclusión**: la EIPD es obligatoria para este tratamiento. Este
documento la desarrolla.

## 4. Necesidad y proporcionalidad

- **Minimización**: `patients` almacena deliberadamente el mínimo
  necesario para distinguir a un paciente en la interfaz — nombre para
  mostrar, año de nacimiento, código interno — sin DNI, NSS, dirección,
  teléfono ni email del paciente (ver
  [privacy-and-security.md](privacy-and-security.md) §2). Cada campo del
  modelo de datos tiene un uso identificado y documentado en
  [data-model.md](data-model.md).
- **Separación identidad/contenido clínico**: estructural desde el
  diseño (§3 de [privacy-and-security.md](privacy-and-security.md)),
  permite en el futuro aplicar controles distintos, o purgar/anonimizar
  un conjunto sin afectar al otro.
- **Limitación de la finalidad**: el modelo de IA no calcula ni sugiere
  grados de pérdida auditiva, no recomienda productos ni tratamientos, no
  prioriza pacientes ni genera alertas de urgencia — solo apoyo
  documental sujeto a revisión (ver
  [clinical-safety.md](clinical-safety.md) §8).
- **Idoneidad**: la transcripción y generación asistida reducen la carga
  administrativa del audioprotesista sin sustituir su criterio clínico —
  ningún artefacto de IA es válido ni exportable sin aprobación humana
  explícita.
- **Necesidad frente a alternativas menos invasivas**: se valoró
  consolidar a un único proveedor de LLM por simplicidad de DPA, y se
  descartó explícitamente (decisión de Gerard, 2026-09-17) — el reparto
  actual (Anthropic para `summary`, OpenAI para el resto) se mantiene por
  motivos de producto, no de minimización, lo que amplía ligeramente la
  superficie de subencargados frente a la alternativa de un único
  proveedor; compensado por el DPA propio y verificado de cada uno (§2.2).

## 5. Identificación y valoración de riesgos

Metodología: para cada amenaza se valora probabilidad e impacto
**antes** de aplicar medidas (riesgo inherente) sobre una escala
cualitativa baja/media/alta, siguiendo el enfoque de la guía AEPD de
gestión del riesgo (véase §0).

| # | Amenaza | Origen | Probabilidad inherente | Impacto inherente | Riesgo inherente |
|---|---|---|---|---|---|
| R1 | Acceso no autorizado a contenido clínico de otra clínica | Externo/interno | Media | Alto | Alto |
| R2 | Fuga de identidad de paciente vía logs, trazas de error o mensajes de excepción | Interno (fallo de diseño) | Media | Alto | Alto |
| R3 | Envío de datos clínicos reales a un proveedor de IA sin acuerdo de tratamiento vigente | Interno (error de configuración) | Baja | Alto | Medio |
| R4 | Uso de datos de paciente por un proveedor externo para entrenar sus modelos | Externo (proveedor) | Baja (tras mitigación técnica) | Alto | Medio |
| R5 | Pérdida irrecuperable de contenido clínico (fallo de infraestructura, borrado accidental) | Externo/interno | Baja | Alto | Medio |
| R6 | Imposibilidad de honrar una solicitud de supresión del paciente (art. 17 RGPD) | Interno (ausencia de funcionalidad) | — (materializado hasta 2026-09-18) | Alto | Alto (histórico) |
| R7 | Uso de un artefacto de IA no revisado como si fuera contenido clínico validado | Interno/usuario | Media | Alto (riesgo para la salud, no solo para el dato) | Alto |
| R8 | Suplantación de un usuario del personal de clínica (acceso con credenciales ajenas o sin autenticación real) | Externo | Media (mientras no haya pantalla de login ni MFA) | Alto | Alto |
| R9 | Exposición de contenido clínico en texto plano en caso de acceso no autorizado a la base de datos (sin cifrado a nivel de columna) | Interno (infraestructura) | Baja | Alto | Medio |
| R10 | Denegación de servicio o degradación por ausencia de límites de tasa efectivos en despliegue multi-réplica | Externo | Baja (mientras haya una sola réplica) | Medio | Bajo |
| R11 | Uso de un checklist de señales de alerta no validado clínicamente como si fuera fiable | Interno (producto) | — (funcionalidad no implementada todavía) | Alto (riesgo para la salud) | Medio (potencial, si se activa sin las salvaguardas de §8) |

## 6. Medidas de mitigación aplicadas

| Riesgo | Medidas ya implementadas | Riesgo residual |
|---|---|---|
| R1 | Aislamiento por clínica estructural (`clinic_id` derivado siempre de `current_user`, nunca del cliente); RBAC centralizado en `core/authorization.py`; recurso de otra clínica devuelve `404`, nunca `403` (no revela ni su existencia); auditado exhaustivamente en el hito 8.1 (ver [privacy-and-security.md](privacy-and-security.md) §5 y §13) | Bajo |
| R2 | Identidad separada del contenido clínico; `audit_logs.metadata` nunca contiene valores de campos, solo sus nombres; Sentry con scrubbing de cuerpo/cabeceras/variables antes de cualquier envío, `scope.user` limitado a UUID opaco | Bajo |
| R3 | Hasta la Fase 10, únicamente implementaciones `Mock*` disponibles para LLM — activar un proveedor real requiere cambio explícito de configuración; los cinco proveedores con acceso a datos clínicos reales tenían DPA resuelto antes de la primera activación en producción (2026-09-14/15) | Bajo |
| R4 | `mip_opt_out=true` incondicional en toda petición a Deepgram, verificado con tests de compliance dedicados; Anthropic/OpenAI no usan datos de API para entrenamiento por defecto, sin opt-in activado | Bajo |
| R5 | Tres capas de backup (snapshots de volumen, PITR ~4 semanas, `pg_dump` cifrado externo a bucket UE que sobrevive a la pérdida total de Railway); clave de cifrado `age` custodiada offline por Gerard, nunca en Railway; runbook de restore verificado dos veces contra dumps reales (2026-09-14 y 2026-09-18) — **corregido 2026-09-18**: una versión anterior de esta EIPD lo daba por pendiente citando `privacy-and-security.md` §8.1, que a su vez remitía a `development-plan.md`, donde ya constaba cerrado desde el 2026-09-14; no verificado contra el documento correcto antes de escribirlo | Bajo |
| R6 | `purge_patient_clinical_data()` (2026-09-18, ampliado 2026-09-23): purga física atómica, admin-only, doble confirmación, con entrada de auditoría que sobrevive al borrado — cubre contenido clínico **y**, desde el 2026-09-23, anonimización in-place de la identidad del paciente (`display_name`/`birth_year`/`notes`/`internal_code`); antes de esa fecha esta fila calificaba el riesgo de "Bajo" citando solo la purga clínica, lo cual era optimista frente al alcance real del art. 17 — ver §1.7 | Bajo — residual: backups ya tomados y subencargados externos (Deepgram/OpenAI/Anthropic) no purgan retroactivamente, ver §1.7 |
| R7 | Lenguaje no diagnóstico obligatorio y validado por tests; aviso obligatorio en toda respuesta de API y exportación; aprobación humana explícita antes de exportar o considerar un artefacto parte del expediente; ninguna transición a `approved` puede depender de `confidence` | Medio — depende en última instancia de que el profesional respete el flujo de revisión; no hay control técnico que impida a un usuario ignorar el aviso |
| R8 | Autenticación real por JWT + `bcrypt` obligatoria en producción (`RealCurrentUserProvider`), rate limiting en login (5/min), pantalla de login real en el frontend (`LoginForm.tsx`/`AuthContext.tsx`, hito 9.2) que bloquea todas las rutas sin token válido — **corregido 2026-09-18**: una versión anterior de esta EIPD daba esto por pendiente basándose en `privacy-and-security.md` §12, que estaba desactualizado; verificado directamente contra `frontend/src/App.tsx` (función `RealAuthApp`), el hito ya estaba implementado y mergeado | Medio — sin MFA, tokens de 8h de vida (revocables en servidor desde 2026-09-24: logout y reset de contraseña incrementan `token_version`, hallazgo D1 del red team); pendiente confirmar que `VITE_AUTH_MODE` de producción esté en `real` en la configuración real de Railway (no verificable desde el código) — aunque la barrera real está en el backend, no en el frontend |
| R9 | Cifrado a nivel de aplicación (columna) implementado — **corregido 2026-09-18**: AES-256-GCM (autenticado) sobre `patients.display_name`/`birth_year`, `ai_artifact_versions.content` y `ai_generation_runs.rendered_system_prompt`/`rendered_user_prompt`/`raw_response`, con claves versionadas/rotables desde el diseño inicial (`app/core/field_encryption.py`, `docs/privacy-and-security.md` §4) | Bajo — el contenido clínico más sensible ya no depende únicamente del cifrado en reposo del proveedor de infraestructura; residual: las claves viven como variables de entorno en Railway, no en un HSM/KMS gestionado, lo cual es proporcional a la escala actual (un proveedor, sin equipo de seguridad dedicado) pero debería revisarse si el volumen de clínicas crece significativamente |
| R10 | `SecurityHeadersMiddleware`, rate limiting con `slowapi`, límites de tamaño de subida | Bajo mientras el despliegue sea de una sola réplica (limitación conocida y aceptada, documentada) |
| R11 | Checklist aislado detrás de una interfaz sustituible (`ClinicalFlagsGenerator`); doble aviso obligatorio ("checklist de demostración, no validado clínicamente, no apto para uso con pacientes reales") cuando exista; lenguaje no diagnóstico; ligado a fragmento de transcripción | Medio — la funcionalidad no está implementada todavía (§13 de [privacy-and-security.md](privacy-and-security.md)); si se implementa, no debe activarse para pacientes reales sin validación clínica y legal previa, tal y como ya reconoce el propio [clinical-safety.md](clinical-safety.md) §7 |

## 7. Riesgo residual y necesidad de consulta previa (art. 36 RGPD)

Tras las medidas aplicadas, **todos los riesgos identificados quedan en
un nivel bajo o medio** — a fecha 2026-09-18, ningún riesgo de los
identificados en §5/§6 queda en residual alto.

(Dos correcciones respecto a versiones anteriores de este documento,
ambas por la misma causa — dar por pendiente algo que ya estaba resuelto
en el código, basándose en documentación desactualizada, en vez de
verificar contra el código real:

- **R8 (autenticación)**: se consideraba alto por una lectura de
  `privacy-and-security.md` que resultó estar desactualizada — la
  pantalla de login real ya existe y está en producción; queda en
  riesgo medio por la falta de MFA y de revocación de tokens, no en
  alto.
- **R9 (cifrado en reposo)**: se consideraba alto porque el cifrado a
  nivel de columna todavía no estaba implementado. **Ya está
  implementado** (ver §6 y `docs/privacy-and-security.md` §4) — queda en
  riesgo bajo, con la salvedad de la gestión de claves vía variables de
  entorno señalada en §6, no en alto.)

Ninguno de los riesgos residuales identificados alcanza, a día de hoy,
el umbral de "riesgo residual alto e ineludible" que obligaría a una
consulta previa a la AEPD conforme al art. 36 RGPD. **Esta conclusión
debe confirmarla el abogado/DPO que revise este documento**, no darse
por definitiva solo por constar aquí.

## 8. Brechas y recomendaciones pendientes

Por orden de prioridad, a criterio de quien redacta este borrador. Tres
elementos que figuraban aquí en versiones anteriores de este documento —
cifrado a nivel de columna, confirmación de `VITE_AUTH_MODE` en
producción, y el runbook de restore de backups — ya están resueltos (ver
§6/§7, y el runbook en particular en
[development-plan.md](development-plan.md) §Fase 11, verificado dos
veces: 2026-09-14 y 2026-09-18) y se retiran de esta lista, no se dejan
tachados: mantener algo resuelto en la lista de pendientes invitaría a
confundir "ya resuelto" con "todavía por hacer" en una lectura rápida
del documento.

1. **Confirmar el estado de DPA de Sentry** y la jurisdicción exacta del
   DPA de Brevo (§2.2) para poder dar el registro de subencargados por
   completo y verificado.
2. **MFA** para las cuentas de personal de clínica (la revocación de
   tokens en servidor quedó cerrada el 2026-09-24, hallazgo D1) — no bloqueante para el riesgo actual (bajo volumen,
   primer cliente), pero recomendable antes de escalar a varias clínicas.
3. **No activar `clinical_flags`** para pacientes reales hasta contar con
   una validación clínica y legal del ruleset (ya reconocido en
   [clinical-safety.md](clinical-safety.md) §7); mientras tanto, la
   funcionalidad sigue sin implementar, lo cual es, en sí, la mitigación
   correcta.
4. **Revisar el toggle "Rate chats" en Anthropic Console** (Organization
   settings → Data and Privacy) como defensa en profundidad — acción
   pendiente de Gerard, no ejecutable desde el propio sistema (ya
   señalada en [privacy-and-security.md](privacy-and-security.md) §9.1).
5. **Redactar el DPA/RAT/ToS propio de Audiology AI Assistant** hacia sus
   clínicas clientes, reflejando el reparto dual de proveedores de LLM
   con su alcance real (nunca como proveedor de respaldo) y la política
   de no entrenamiento — siguiente paso ya previsto en la hoja de ruta
   ([fase-13-rfc.md](fase-13-rfc.md)).
6. **Rotar la clave de cifrado de campo de ejemplo** que vive en
   `.env.example`/`backend/tests/conftest.py` si alguna vez se llega a
   copiar tal cual a un entorno real — es una clave pública (está en el
   repositorio), pensada solo para desarrollo y tests locales; Railway
   debe tener siempre una `FIELD_ENCRYPTION_KEYS` generada aparte, nunca
   esa (ver el runbook de `app/core/field_encryption_cli.py` si hiciera
   falta rotarla).

## 9. Revisión de esta EIPD

Esta evaluación debe revisarse, como mínimo, cuando ocurra cualquiera de
estos eventos — no en una fecha fija:

- Se incorpore un nuevo subencargado con acceso a datos clínicos o de
  identidad (nuevo proveedor de IA, de hosting, de comunicaciones, etc.).
- Se implemente `clinical_flags` u otra funcionalidad de IA nueva sobre
  contenido clínico.
- Se resuelva alguna de las brechas de §8 (para reflejar el riesgo
  residual actualizado, no solo para tacharla de la lista).
- Se amplíe el tratamiento a un volumen significativamente mayor de
  clínicas o pacientes (cambio de escala).
- Cambie la normativa aplicable (RGPD, LOPDGDD, Ley 41/2002) o la
  interpretación de la AEPD sobre IA generativa y datos de salud.

## 10. Aviso legal (repetido por claridad)

Este documento es un insumo técnico, no un dictamen jurídico. Antes de
tratarlo como la EIPD oficial de Audiology AI Assistant o de cualquier
clínica cliente, debe revisarlo un abogado o DPO cualificado en
protección de datos y derecho sanitario español/europeo — en particular
las conclusiones de §3 (obligatoriedad), §7 (riesgo residual y consulta
previa) y §8 (prioridad real de las brechas pendientes).
