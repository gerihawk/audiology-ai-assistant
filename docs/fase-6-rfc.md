# RFC — Fase 6: Exportación, documentación clínica completa e IA real

**Versión**: 2.0.  
**Estado**: diseño cerrado, listo para implementación.  
**Alcance**: producto y arquitectura; no incluye código.  
**Documentos normativos relacionados**: `docs/development-plan.md`,
`docs/ai-pipeline-architecture.md`, `docs/clinical-safety.md`,
`docs/privacy-and-security.md`, `docs/api-specification.md` y
`docs/data-model.md`.

Este RFC sustituye íntegramente la versión 1. Mantiene el núcleo del AI
Pipeline definido en Fase 4 y cierra las decisiones necesarias para ejecutar
la Fase 6 sin reinterpretaciones durante la implementación.

---

## 0. Método, estado real y reconciliación de alcance

La propuesta parte del estado verificado del repositorio, no de un modelo
idealizado:

- `AIArtifact`/`AIArtifactVersion`, el grafo declarado mediante
  `depends_on()` y los ejes independientes de ejecución y disposición humana
  siguen siendo la base; no se rediseñan.
- `SessionType` **ya existe y está cableado de extremo a extremo**. Sus seis
  valores son `INITIAL_ASSESSMENT`, `FOLLOW_UP`, `HEARING_AID_FITTING`,
  `HEARING_AID_ADJUSTMENT`, `REVIEW` y `OTHER`. El gap real es que el AI
  Pipeline todavía no lo utiliza.
- `PromptTemplateRepository`, `LanguageModelProvider`, `HUMAN_EDITED`,
  `AIArtifact.deleted_by` y `AIArtifact.deleted_at` están diseñados total o
  parcialmente, pero no todos están activados en el flujo real.
- La lista canónica de anamnesis es la lista de **20 campos implementada en
  `ANAMNESIS_FIELDS`**. Esta fase no introduce una supuesta variante de 22
  campos. La documentación que aún diga 22 debe corregirse como deuda
  documental, no convertirse en una decisión de producto.

### 0.1 Reconciliación con `development-plan.md`

El alcance original de Fase 6 es exportación: `DocumentExporter`,
`PdfDocumentExporter`, `TextDocumentExporter`, endpoints y la aceptación de
que un artefacto aprobado pueda exportarse en PDF y texto plano. Este RFC
conserva íntegramente ese compromiso y declara una **ampliación explícita de
alcance**, equivalente a la ya declarada en Fase 5:

1. activación controlada de un proveedor LLM real;
2. guardarraíles de seguridad y grounding en runtime;
3. edición humana real y borrado lógico auditado como precondiciones;
4. nuevos artefactos `PATIENT_SUMMARY` y `SESSION_NOTES`;
5. actualización explícita y acotada de anamnesis;
6. vista longitudinal de solo lectura mediante `clinical_record`.

Noah/HIMSA **no es un entregable de Fase 6**. Aquí solo se preservan las
decisiones conceptuales que evitan cerrar puertas. La interfaz, el mock y la
integración pertenecen a Fase 7 salvo que `development-plan.md` se modifique
expresamente mediante otro RFC.

### 0.2 Principios no negociables

- Un artefacto representa un propósito, una audiencia y un ciclo de revisión.
- Ningún contenido clínico generado por IA se convierte automáticamente en
  hecho clínico aprobado.
- Un step declara tanto sus dependencias intra-sesión como sus requisitos de
  contexto externo; no realiza lecturas laterales ocultas.
- Solo se exportan versiones aprobadas, vigentes y no eliminadas.
- La producción usa integración directa con el proveedor LLM elegido.
  OpenRouter queda limitado al benchmark comparativo.
- Seguridad, grounding, esquema y coste se validan programáticamente; el
  prompt nunca es el único control.

---

## 1. Objetivos y no objetivos

### 1.1 Objetivos

1. Cumplir el alcance de exportación de `development-plan.md` con PDF y texto
   plano, control de permisos y auditoría.
2. Activar generación LLM real sin relajar `clinical-safety.md`.
3. Mantener trazabilidad campo a campo entre contenido generado y
   transcripción mediante `source_excerpt` y `source_map`.
4. Separar el resumen técnico del resumen dirigido al paciente para que
   ambos puedan editarse y aprobarse independientemente.
5. Documentar visitas posteriores sin forzar una anamnesis inicial en cada
   sesión y permitir completar lagunas de la anamnesis sin sobrescrituras
   silenciosas.
6. Ofrecer continuidad longitudinal por paciente sin duplicar datos ni
   convertir `patients` en propietario de información clínica.
7. Medir calidad, latencia y coste con un benchmark reproducible antes de
   seleccionar el proveedor de producción.

### 1.2 No objetivos

- Integración, XML o mock Noah/HIMSA en Fase 6.
- Calendario, facturación, envío de cartas o write-back a sistemas externos.
- Diagnóstico automático, recomendación terapéutica o decisión clínica.
- Cola distribuida o worker asíncrono en esta fase.
- Entidad o tabla propia para la historia clínica longitudinal.
- Certificación regulatoria del producto.

---

## 2. Flujo clínico resultante

| Momento | Capacidad | Regla principal |
|---|---|---|
| Preconsulta | `clinical_record` agrega sesiones y artefactos aprobados | Solo lectura, aislamiento por clínica |
| Primera documentación | `ANAMNESIS` cuando no existe una aprobada | La necesidad clínica prevalece sobre `session_type` |
| Visita posterior | `SESSION_NOTES` cuando existe anamnesis aprobada | Evidencia de la sesión actual, no copia del histórico |
| Información nueva posterior | `AnamnesisUpdateStep` explícito | Solo completa lagunas salvo evidencia nueva explícita |
| Explicación al paciente | `PATIENT_SUMMARY` independiente | Ciclo de edición/aprobación propio |
| Revisión | versión `HUMAN_EDITED` antes de aprobar cuando sea necesario | Toda edición queda versionada y auditada |
| Salida | PDF o texto plano | Solo contenido aprobado, vigente y no eliminado |

`session_type` conserva valor clínico, de filtrado y de presentación, y se
incluye como contexto de prompts y exportaciones. No se usa como interruptor
binario `ANAMNESIS` frente a `SESSION_NOTES`, porque los seis tipos reales no
representan mutuamente esos dos estados y `HEARING_AID_FITTING` es un caso
híbrido legítimo.

---

## 3. Arquitectura propuesta

```text
ClinicalSession (SessionType existente, incluidos None/legacy)
        │
        ▼
PipelineContext
  ├── outputs intra-sesión
  ├── session / patient / clinic
  └── patient_context declarado y cargado por el orquestador
        │
        ▼
PipelineStep
  ├── depends_on()
  ├── patient_context_requirements()
  └── applies_to(context) -> bool
        │
        ├── ANAMNESIS si no existe anamnesis aprobada
        ├── SESSION_NOTES si existe anamnesis aprobada
        ├── PATIENT_SUMMARY independiente de SUMMARY
        └── AnamnesisUpdateStep solo por acción explícita
        │
        ▼
Proveedor directo → parseo/schema → Grounding → Safety → coste
        │
        ▼
AIArtifactVersion + source_map + resultado/fallo tipado
        │
        ▼
HUMAN_EDITED → approved → DocumentExporter (PDF | TEXT)
        │
        └── clinical_record (agregación de solo lectura)
```

### 3.1 Extensión de `PipelineStep`

El protocolo incorpora:

- `applies_to(context) -> bool`, con implementación por defecto `True` para
  preservar el comportamiento de los steps existentes;
- `patient_context_requirements()`, vacío por defecto, que declara lecturas
  cross-sesión necesarias.

El orquestador evalúa los requisitos, carga el contexto mediante servicios
públicos y después ejecuta `applies_to()`. Si devuelve `False`, registra el
step como omitido con un `skipped_reason` estable; no lo registra como fallo.
`produce()` no puede consultar repositorios de otros módulos por su cuenta.

### 3.2 Reglas de aplicabilidad

- `AnamnesisStep.applies_to()`: `True` si el paciente no tiene una
  `ANAMNESIS` aprobada, vigente y no eliminada en la clínica actual.
- `SessionNotesStep.applies_to()`: `True` si sí existe dicha anamnesis.
- Un `HEARING_AID_FITTING` puede generar `SESSION_NOTES` y, por acción
  profesional separada, una actualización de anamnesis.
- `PATIENT_SUMMARY` puede configurarse en el catálogo de pipeline sin quedar
  embebido en `SUMMARY`.
- Los steps restantes mantienen `True`, sujeto a sus dependencias actuales.

### 3.3 `session_type=None`

`None` es válido para datos legacy o sesiones incompletas y no provoca un
error del pipeline. La selección Anamnesis/Session Notes sigue dependiendo de
la existencia de anamnesis aprobada. En prompts y exportaciones se representa
como `unspecified`, nunca se infiere un valor. La API conserva `null`; la UI
muestra “Sin especificar”. Las métricas contabilizan estos casos para poder
sanear datos, pero no bloquean generación ni exportación.

### 3.4 Módulos y dependencias

- `ai_pipeline/domain/steps/base.py`: wrapper común de ejecución y
  `SafetyValidator` en el chokepoint previo a persistencia.
- `ai_pipeline/domain/grounding.py`: primitiva compartida de normalización y
  verificación de extractos.
- `ai_pipeline/domain/safety.py`: constante compartida y resultado tipado de
  seguridad, si separar el fichero evita ciclos; el wrapper sigue invocándose
  desde `steps/base.py`.
- `export`: módulo independiente con `DocumentExporter`, implementaciones PDF
  y texto, servicio y router.
- `clinical_record`: módulo independiente de agregación de solo lectura, sin
  ORM, tabla ni entidad persistida.

`clinical_record` usa los servicios públicos de `patients`,
`clinical_sessions` y `ai_pipeline`; en particular, obtiene artefactos mediante
`AIPipelineService.list_artifacts`, no leyendo sus tablas. Ningún módulo de
origen depende de `clinical_record`.

---

## 4. Pipeline IA por artefacto

### 4.1 Transcript

Se mantiene sin cambios. Se añade al golden dataset audio corto de seguimiento
para validar el flujo que alimenta `SESSION_NOTES`.

### 4.2 Summary

- Entrada: `TRANSCRIPT`.
- Salida: `{"text": str}`; no contiene texto para el paciente.
- Dependencia: `TRANSCRIPT`.
- Validación: esquema estricto, lenguaje prohibido y comprobaciones de
  contenido cuantitativo no respaldado.
- Revisión/aprobación: ciclo propio existente.

### 4.3 Patient Summary

Nuevo `AIArtifactType.PATIENT_SUMMARY`:

- Entrada: `TRANSCRIPT` y, cuando esté disponible en la ejecución, `SUMMARY`.
- Salida: `{"text": str}` en lenguaje llano.
- Propósito/audiencia: comunicación con el paciente, distinta del resumen
  técnico.
- Revisión, edición y aprobación: independientes de `SUMMARY`.
- Seguridad: no transforma señales, sospechas o incertidumbre en diagnósticos
  ni recomendaciones.
- Exportación: puede exportarse solo si su propia versión está aprobada.

### 4.4 Clinical Flags

Sigue siendo rule-based. Antes de ampliar reglas a visitas de adaptación se
corrige el `source_excerpt` actual: no puede usar `transcript[:200]`; debe
capturar la ventana real que contiene la coincidencia que disparó la regla y
validarla con la misma primitiva de grounding.

### 4.5 Missing Information

La lista se genera contra un esquema objetivo explícito:

- si se ejecutará `ANAMNESIS`, contra `ANAMNESIS_FIELDS`;
- si se ejecutará `SESSION_NOTES`, contra sus cuatro bloques;
- si ninguno aplica, el step se omite con razón tipada.

Cada elemento referencia una clave válida del esquema cerrado. Temperatura
0–0.1 y rechazo de claves inventadas.

### 4.6 Anamnesis

La forma canónica conserva los 20 campos de `ANAMNESIS_FIELDS` y los cuatro
estados existentes. Todo campo `informado` o `negado_explicitamente` exige un
`source_excerpt` válido. Sin evidencia válida se degrada a
`no_determinado`; nunca se promueve por inferencia.

La anamnesis inicial no depende exclusivamente de
`INITIAL_ASSESSMENT`: se genera cuando falta una anamnesis aprobada para el
paciente en esa clínica.

### 4.7 Session Notes

Nuevo `AIArtifactType.SESSION_NOTES`:

```json
{
  "changes_since_last_visit": {"text": "...", "source_excerpt": "..."},
  "device_adjustments": {"text": "...", "source_excerpt": "..."},
  "patient_reported_issues": {"text": "...", "source_excerpt": "..."},
  "next_steps": {"text": "...", "source_excerpt": "..."}
}
```

- Dependencia intra-sesión: `TRANSCRIPT`.
- Requisito declarado de contexto: última anamnesis aprobada, vigente y no
  eliminada del paciente.
- El contexto previo ayuda a interpretar referencias, pero no es evidencia de
  que algo se haya dicho en la sesión actual.
- Todos los extractos deben pertenecer al transcript actual.
- Los bloques sin contenido quedan explícitamente vacíos/no determinados; el
  modelo no rellena texto de continuidad por cortesía.

### 4.8 Anamnesis Update

`AnamnesisUpdateStep` entra en el diseño como operación explícita, no como
parte automática de cada ejecución:

1. el profesional solicita “proponer actualización de anamnesis” desde una
   sesión concreta;
2. el step recibe la última anamnesis aprobada y el transcript actual;
3. por defecto solo propone cambios en campos `no_determinado` o
   `no_preguntado`;
4. un campo `informado` o `negado_explicitamente` solo puede cambiar si el
   transcript actual contiene **evidencia nueva explícita**, entendida como
   una declaración atribuible al paciente/profesional que contradice o
   corrige directamente el valor previo, no una omisión, inferencia o cambio
   de contexto;
5. todo cambio incluye valor anterior, propuesta, `source_excerpt` actual y
   motivo tipado `fills_gap` o `explicit_correction`;
6. el resultado es una nueva versión propuesta de `ANAMNESIS`, nunca una
   mutación in-place, y exige revisión humana antes de aprobación.

La acción requiere permiso clínico de edición y genera auditoría específica.

---

## 5. Guardarraíles, grounding y estados de fallo

### 5.1 Orden obligatorio de validación

Para todo step LLM:

1. invocar proveedor;
2. parsear respuesta;
3. validar JSON/schema y detectar respuesta evasiva o metacomentario;
4. ejecutar validación estructural específica del artefacto;
5. validar grounding donde corresponda;
6. construir `source_map`;
7. ejecutar `SafetyValidator` sobre todos los textos terminales;
8. comprobar el coste acumulado de la sesión;
9. persistir la versión o el fallo tipado.

Una salida que no supera la secuencia nunca queda disponible como borrador
clínico revisable.

### 5.2 SafetyValidator

Vive en el wrapper común de `ai_pipeline/domain/steps/base.py`, junto a
`run_provider_step`, para que ningún step LLM pueda omitirlo. Se ejecuta antes
de persistir una versión correcta.

La lista de lenguaje prohibido se crea como constante compartida única,
por ejemplo `FORBIDDEN_CLINICAL_LANGUAGE`, en dominio. Producción y tests
importan esa misma constante; queda prohibida la duplicación inline hoy
existente en tests. La constante contiene inicialmente las expresiones
normativas de `clinical-safety.md`, incluidas “el paciente tiene”,
“diagnóstico confirmado” y “tratamiento recomendado”, y evoluciona mediante
cambio revisado en ese único punto.

El validador devuelve coincidencias estructuradas (regla, texto, ubicación),
no solo booleano, sin almacenar innecesariamente contenido clínico en logs.

### 5.3 GroundingValidator

La primitiva compartida vive en `ai_pipeline/domain/grounding.py` y recibe
`(excerpt, transcript) -> resultado`. Reutiliza una única normalización
equivalente a `benchmark/metrics/text_normalize.py`; la implementación debe
extraer esa normalización a una utilidad compartida o garantizar mediante
tests contractuales que ambas no divergen.

La primitiva es genérica, pero cada step recorre su propia estructura y decide
qué campos exigen evidencia. Un extracto debe corresponder al transcript de
la sesión que produce el artefacto. No se acepta un fragmento del contexto
longitudinal como grounding actual.

### 5.4 `source_excerpt` y `source_map`

Son mecanismos distintos:

- `source_excerpt` vive dentro de `content` y aporta evidencia localizada por
  campo o bloque;
- `source_map` es el JSONB top-level de `AIArtifactVersion` y agrega
  automáticamente los extractos validados, con la ruta del campo y, cuando
  pueda resolverse de forma determinista, offsets normalizados/originales.

`source_map` se construye después de validar los extractos; no lo suministra
el LLM como autoridad. Permite consultar toda la trazabilidad sin reparsear
`content`. Un artefacto con campos que requieren evidencia y carece de mapa
válido no puede persistirse como generación exitosa.

### 5.5 Fallos distinguibles y retries

Se conserva el eje de ejecución existente; no se crea un tercer eje. Se añade
un motivo tipado de fallo, al menos:

- `provider_timeout`
- `provider_rate_limited`
- `provider_unavailable`
- `invalid_response_format`
- `schema_validation_failed`
- `evasive_or_meta_response`
- `grounding_failed`
- `safety_policy_failed`
- `cost_limit_exceeded`
- `unexpected_internal_error`

Política de reintento:

- máximo 2 reintentos automáticos (3 intentos totales) solo para timeout,
  rate limit, indisponibilidad transitoria, formato inválido, schema o
  respuesta evasiva;
- backoff acotado con jitter para fallos transitorios;
- en formato/schema/evasiva, un único reintento correctivo puede incluir el
  error de validación sin incluir nuevos datos clínicos;
- `grounding_failed` y `safety_policy_failed` admiten como máximo un reintento
  regenerativo con instrucciones reforzadas; si se repiten, el step falla;
- `cost_limit_exceeded` no se reintenta;
- una reejecución manual crea un nuevo run y conserva los intentos anteriores.

El API/UI distingue “proveedor temporalmente no disponible”, “salida inválida”,
“evidencia insuficiente”, “bloqueado por seguridad” y “límite de coste”, sin
mostrar detalles sensibles ni convertirlos todos en un `FAILED` opaco.

---

## 6. Estrategia LLM y benchmark de generación

### 6.1 Proveedor de producción

La producción implementa `LanguageModelProvider` directamente contra el
proveedor/modelo ganador. Esto reduce intermediación, superficie contractual,
latencia y ambigüedad sobre tratamiento de datos. El proveedor debe cumplir
residencia/transferencias, DPA, retención y no entrenamiento exigidos por
`privacy-and-security.md` antes de procesar datos reales.

OpenRouter se usa **solo en el benchmark** para ejecutar candidatos con una
interfaz uniforme. No recibe tráfico clínico de producción.

### 6.2 Benchmark programático

El benchmark es un comando reproducible, no una evaluación manual. Usa un
golden dataset versionado con casos sintéticos o debidamente autorizados,
incluidos español, sesiones breves, fitting híbrido, negaciones, correcciones
explícitas, referencias ambiguas y `session_type=None`.

Para cada modelo/prompt registra:

- validez JSON/schema;
- precisión/recall/F1 por campo o bloque;
- exactitud de los cuatro estados de anamnesis;
- tasa de `source_excerpt` verificable;
- tasa de degradación a `no_determinado`;
- violaciones de seguridad;
- respuestas evasivas/meta;
- omisiones y contenido no sustentado;
- latencia p50/p95;
- tokens y coste por artefacto/sesión;
- tasa de éxito y número de retries.

Las ejecuciones fijan dataset, versión de prompt, proveedor/modelo y
parámetros. La salida es JSON/CSV machine-readable y un informe comparativo.
Los umbrales de aceptación se almacenan junto al benchmark y bloquean la
selección de un modelo que incumpla seguridad o grounding aunque sea más
barato.

### 6.3 Límite duro de coste

Existe una constante/configuración central por entorno
`MAX_LLM_COST_PER_SESSION`, expresada en moneda y calculada con una tabla de
precios versionada. Antes de cada llamada se estima el peor coste razonable
de entrada+salida; después se registra el coste real devuelto/calculado.

Si el acumulado más la siguiente llamada puede superar el límite, el step no
se invoca y falla con `cost_limit_exceeded`. Los retries cuentan contra el
mismo presupuesto. No existe override automático; solo un usuario autorizado
puede reejecutar con un override auditado y acotado.

### 6.4 Ejecución síncrona en Fase 6

Decisión cerrada: el backend ejecuta la generación de forma **síncrona** en
esta fase. No se implementan cola, jobs ni polling. La aceptación de esta
decisión exige benchmark de latencia y timeouts explícitos por proveedor.

Si p95 del pipeline completo supera el presupuesto operativo definido durante
6.3, o si las tasas de timeout hacen inviable la petición HTTP, se abre un RFC
posterior para jobs asíncronos y polling. Los estados/runs existentes se
diseñan sin asumir que la conexión HTTP permanece abierta, para que esa
migración no cambie el modelo clínico.

---

## 7. Exportación

### 7.1 Contrato único

`export/domain` define `DocumentExporter`; no se introduce el nombre
competidor `ClinicalRecordExporter`.

- `PdfDocumentExporter`: salida PDF legible, no JSON crudo.
- `TextDocumentExporter`: UTF-8 text/plain con estructura estable y legible.

Ambas implementaciones consumen un DTO canónico preparado por el servicio de
exportación. Ninguna consulta repositorios directamente ni genera
`AIArtifact`.

### 7.2 Alcances

- `scope=session`: una sesión y selección de artefactos aprobados.
- `scope=patient`: el DTO agregado por `clinical_record`, separado por sesión
  y ordenado cronológicamente.

El alcance paciente solo se habilita después de implementar el módulo de
§8; no anticipa joins dentro de `export`.

### 7.3 Elegibilidad y soft-delete

Solo es exportable una versión que sea:

- aprobada;
- la versión aprobada vigente según las reglas existentes;
- perteneciente a la clínica/alcance solicitado;
- asociada a un artefacto no eliminado lógicamente.

La activación del borrado lógico de `AIArtifact` es precondición de la
exportación: endpoint/servicio autorizado, `deleted_by`, `deleted_at`, evento
de auditoría y exclusión por defecto de listas, contexto longitudinal y
exports. No se implementa hard-delete. Un intento de exportar contenido
eliminado responde como recurso no disponible, sin filtrar su existencia a
roles no autorizados.

### 7.4 Contenido y auditoría

PDF y texto incluyen clínica, paciente mínimo necesario, sesión,
`session_type` o “Sin especificar”, artefacto, versión, aprobación humana,
fecha y hash de contenido. Nunca presentan JSON crudo. El PDF usa plantilla
visual; texto mantiene encabezados deterministas.

Cada descarga registra `document.exported` con actor, clínica, paciente,
scope, formato, tipos y versiones. El binario se genera on-demand y no se
persiste en PostgreSQL.

### 7.5 Permisos

Exportar requiere un permiso explícito `clinical_document:export`, además de
acceso al paciente y clínica. La exportación longitudinal requiere además
`clinical_record:read`. La autorización se valida en servicio, no solo en el
router o frontend. Los roles sin permiso pueden revisar según sus permisos,
pero no descargar. Toda exportación masiva queda fuera de alcance.

Respuestas:

- `403` si el actor carece de permiso;
- `404` si el recurso no pertenece a su tenant o está eliminado;
- `409` si existe pero no hay versión aprobada elegible;
- `422` si faltan datos imprescindibles para renderizar.

---

## 8. Historia clínica longitudinal

`clinical_record` es un módulo independiente de solo lectura. No vive dentro
de `patients`, no posee datos y no tiene tabla. Su servicio:

1. valida clínica, paciente y permisos;
2. pagina `ClinicalSession` del paciente;
3. obtiene artefactos mediante servicios públicos de `ai_pipeline`;
4. excluye borradores, rechazados y eliminados;
5. devuelve un DTO cronológico para UI o `DocumentExporter`.

La vista registra `clinical_record.viewed`; la exportación registra el evento
de §7.4. La paginación es obligatoria en API. Para generación de un DTO de
exportación completo se aplica un límite configurable de sesiones y tamaño;
superarlo exige segmentar la exportación, no cargar historial ilimitado.

El contexto para `SessionNotes` y `AnamnesisUpdateStep` utiliza la misma
lógica de selección aprobada, pero mediante una consulta mínima específica,
no cargando el expediente completo.

---

## 9. Prerrequisitos, riesgos y mitigaciones

### 9.1 Prerrequisitos bloqueantes

1. Activar edición humana versionada (`HUMAN_EDITED`).
2. Activar soft-delete auditado de `AIArtifact`.
3. Crear constante compartida de lenguaje prohibido y migrar los tests.
4. Corregir el excerpt decorativo de Clinical Flags.
5. Bloquear LLM real si falta consentimiento válido de procesamiento IA.
6. Definir permiso de exportación y aplicarlo en servicio.
7. Configurar límite duro de coste.

### 9.2 Riesgos

| Riesgo | Mitigación |
|---|---|
| Alucinación u omisión | Grounding, golden dataset y revisión humana |
| Lenguaje clínico prohibido | SafetyValidator común y constante única |
| Respuesta evasiva/no parseable | Validación tipada y retry acotado |
| Mezcla de sesiones | Contexto declarado; evidencia solo del transcript actual |
| Sobrescritura de anamnesis | Update explícito, diff y aprobación |
| Coste variable | Límite duro por sesión y accounting de retries |
| Fuga a terceros | Proveedor directo aprobado, consentimiento y DPA |
| Exportación indebida | Permiso explícito, tenant isolation y auditoría |
| Documento obsoleto | Versión/hash visibles |
| Histórico excesivo | Paginación y límites de exportación |
| Latencia síncrona | Benchmark p95 y criterio de RFC async posterior |

---

## 10. Roadmap de implementación

Los hitos se ordenan por dependencias y cada uno es entregable verificable.

### 6.0 — Alineación documental y precondiciones

- reconciliar `data-model.md` con los 20 `ANAMNESIS_FIELDS`;
- declarar la ampliación de Fase 6 en `development-plan.md`;
- implementar edición humana y soft-delete auditados;
- añadir permisos de exportación y consentimiento bloqueante;
- crear constante compartida y corregir Clinical Flags grounding.

**Aceptación**: ninguna ruta de exportación/LLM puede ignorar edición,
eliminación, permiso, consentimiento o constante de seguridad.

### 6.1 — Infraestructura de validación y costes

- `SafetyValidator`, grounding compartido, validación schema/evasiva;
- fallos tipados, retries y límite duro de coste;
- activación de `PromptTemplateRepository`.

**Aceptación**: tests unitarios/contractuales cubren orden, fallos y límites
sin depender de un proveedor real.

### 6.2 — Benchmark programático de generación

- golden dataset y runner reproducible vía OpenRouter;
- evaluación de modelos para cada step;
- informe de calidad, latencia y coste.

**Aceptación**: resultados machine-readable reproducibles y proveedor/modelo
ganador que supera umbrales de seguridad y grounding.

### 6.3 — Proveedor LLM directo y steps de menor riesgo

- implementación directa del ganador;
- `SUMMARY`, `PATIENT_SUMMARY` y `MISSING_INFORMATION`;
- ejecución síncrona con timeouts medidos.

**Aceptación**: datos reales solo con consentimiento; p95 dentro del
presupuesto; fallos visibles y distinguibles; coste acotado.

### 6.4 — Aplicabilidad y documentación clínica

- `applies_to()` y requisitos de contexto;
- `ANAMNESIS` con grounding real;
- `SESSION_NOTES`;
- comportamiento `session_type=None`.

**Aceptación**: casos primera visita, follow-up, fitting híbrido, legacy null y
cross-sesión pasan tests sin lecturas laterales ocultas.

### 6.5 — Actualización de anamnesis

- acción explícita, diff, evidencia nueva y nueva versión revisable.

**Aceptación**: completa lagunas; no sobrescribe hechos previos sin corrección
explícita; nunca muta una versión aprobada.

### 6.6 — Exportación individual

- `DocumentExporter`, `PdfDocumentExporter`, `TextDocumentExporter`;
- endpoints, permisos y auditoría para `scope=session`.

**Aceptación alineada con `development-plan.md`**: un artefacto aprobado,
vigente y no eliminado se exporta en PDF y texto plano; cualquier otro queda
bloqueado con respuesta correcta.

### 6.7 — `clinical_record` y exportación longitudinal

- servicio/API paginados de solo lectura;
- `scope=patient` para PDF y texto.

**Aceptación**: aislamiento por clínica, solo aprobados/no eliminados, límites
de tamaño y auditoría de vista/exportación.

### Fase 7 — Integraciones externas

Noah/HIMSA, calendario y otras integraciones conservan su ubicación en
`development-plan.md`. Antes de implementar Noah se seleccionará partner y
contrato real; solo entonces se diseñarán puerto, mock, formato y write-back.

---

## 11. Decisiones cerradas y cuestiones futuras

### 11.1 Decisiones cerradas por este RFC

1. `session_type` existe con seis valores y puede ser `None`; no se migra a
   un enum de tres valores.
2. Selección de steps mediante `applies_to()`, no mediante exclusión binaria.
3. Contexto cross-sesión declarado y cargado por el orquestador.
4. `PATIENT_SUMMARY` es artefacto independiente.
5. La anamnesis canónica tiene 20 campos implementados.
6. `AnamnesisUpdateStep` es explícito, versionado y revisable.
7. Safety común en `steps/base.py`; grounding primitivo en
   `domain/grounding.py`.
8. Constante única de lenguaje prohibido compartida por runtime y tests.
9. `source_map` se deriva de `source_excerpt` ya validado.
10. Fallos tipados dentro del eje de ejecución existente.
11. Máximo de retries acotado y límite duro de coste por sesión.
12. Proveedor directo en producción; OpenRouter solo benchmark.
13. Generación síncrona en Fase 6; async/polling requiere RFC posterior.
14. `DocumentExporter` es el único nombre de contrato y soporta PDF/texto.
15. `clinical_record` es módulo independiente de solo lectura.
16. Noah vuelve a Fase 7.
17. Soft-delete, edición humana, consentimiento y permisos son precondiciones.

### 11.2 Cuestiones futuras, no bloqueantes

- proveedor/modelo podrá cambiar si un benchmark posterior supera al actual;
- pricing comercial al cliente;
- oferta self-hosted/Ollama;
- certificación regulatoria;
- umbral operativo que activará el RFC asíncrono;
- partner Noah/HIMSA de Fase 7.

---

## Anexo A — Matriz mínima de pruebas de aceptación

| Caso | Resultado esperado |
|---|---|
| Paciente sin anamnesis, cualquier `SessionType` | Aplica Anamnesis; no Session Notes |
| Paciente con anamnesis, `HEARING_AID_FITTING` | Aplica Session Notes; update solo explícito |
| `session_type=None` | Flujo válido; etiqueta sin especificar |
| Excerpt ausente o falso | Degradación/fallo de grounding según artefacto |
| Frase prohibida | Fallo `safety_policy_failed` |
| Respuesta “soy una IA” | `evasive_or_meta_response`, retry acotado |
| Coste potencial excede máximo | No se llama al proveedor |
| Artefacto draft/rechazado/eliminado | No exportable |
| Usuario sin permiso | `403`, sin descarga |
| Recurso de otra clínica | `404`, sin filtración |
| PDF/texto aprobado | Versión, hash, aprobación y auditoría presentes |
| Update contradice valor sin evidencia explícita | Rechazado |
| Contexto previo citado como evidencia actual | Rechazado por grounding |

---

## Anexo B — Trazabilidad frente al alcance original

| Compromiso de `development-plan.md` | Cobertura |
|---|---|
| `DocumentExporter` | §7.1, hito 6.6 |
| `PdfDocumentExporter` | §7.1–§7.4, hito 6.6 |
| `TextDocumentExporter` | §7.1–§7.4, hito 6.6 |
| Endpoints de exportación | §7.2–§7.5, hito 6.6 |
| Solo artefactos aprobados | §7.3 |
| PDF y texto plano | §7.1, aceptación 6.6 |
| Integraciones externas en Fase 7 | §0.1, roadmap Fase 7 |

La ampliación declarada en §0.1 no sustituye estos compromisos ni permite
considerar Fase 6 completada sin satisfacer primero el criterio original de
exportación.
