# Seguridad clínica — Audiology AI Assistant

## 1. Principio rector

Esta aplicación **no diagnostica** ni sustituye el juicio clínico del
audioprotesista. Todo lo que genera la IA es un borrador de apoyo
documental sujeto a revisión y aprobación humana explícita. Esta regla es
la más importante del proyecto y prevalece sobre cualquier otra
consideración de producto o de arquitectura.

## 2. Lenguaje obligatorio

`AnamnesisGenerator`, `SummaryGenerator` y `ClinicalFlagsGenerator`
(incluidos los mocks — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6) y
cualquier texto generado automáticamente en `ai_artifact_versions.content`
debe usar exclusivamente expresiones no diagnósticas, entre ellas:

- "señal que requiere valoración profesional";
- "información que convendría ampliar";
- "posible motivo de derivación según el protocolo configurado";
- "hipótesis no diagnóstica".

## 3. Lenguaje prohibido

Nunca debe aparecer en contenido generado por IA (ni en plantillas, ni en
mensajes de UI que describan ese contenido):

- "el paciente tiene…";
- "diagnóstico confirmado";
- "tratamiento recomendado automáticamente";
- cualquier formulación que presente una inferencia de la IA como hecho
  clínico establecido.

Esto se valida en dos niveles:
1. **Diseño de las plantillas** en `prompt_templates` (ver
   [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.4),
   incluidas las usadas por los mocks, que deben servir de ejemplo
   correcto desde el primer commit.
2. **Tests automatizados** que comprueben que las plantillas de salida no
   contienen las expresiones prohibidas (lista mantenida como constante
   compartida, no duplicada entre backend y tests).

## 4. Aviso obligatorio

Todo contenido generado por IA que se muestre al profesional —en API y en
UI— debe ir acompañado, sin excepción, del texto:

> "Contenido generado mediante IA. Debe ser revisado y aprobado por un
> profesional cualificado antes de incorporarse al expediente."

Este aviso se implementa como constante única (backend,
`core/messages/es.py` — ver [architecture.md](architecture.md) §8)
reutilizada tanto en las respuestas de API (`ai_disclaimer`) como en la
exportación PDF/texto mientras el artefacto no esté `approved`. Una vez
aprobado, el artefacto exportado indica en su lugar quién lo aprobó y
cuándo, conservando el histórico de que el borrador se originó con IA
(visible en `ai_artifact_versions`/auditoría, no oculto).

## 5. Aprobación humana explícita

- Ningún artefacto de IA (`ai_artifacts` — transcripción, resumen,
  señales de alerta, información ausente, anamnesis) puede exportarse ni
  considerarse parte del "expediente" sin pasar por `status = approved`.
- La aprobación es una acción explícita del profesional (`POST
  .../approve`), distinta de simplemente guardar una edición. Guardar una
  edición deja el artefacto en `review_pending`, nunca lo aprueba
  implícitamente.
- La aprobación registra `approved_by` y `approved_at`; no existe
  aprobación automática ni por inactividad. Tampoco existe aprobación
  automática por `confidence`: ese valor nunca decide una transición de
  estado, solo orienta la revisión humana — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §8.
- **Decisión cerrada**: si el profesional edita un artefacto ya aprobado
  (o rechazado), el sistema devuelve automáticamente su estado a
  `review_pending` y exige una nueva aprobación explícita antes de
  permitir de nuevo su exportación. Ver
  [data-model.md](data-model.md) §10.

## 6. Estados de campo en la anamnesis

Para evitar que un campo vacío se confunda con "no hay nada que
declarar", cada campo de la anamnesis lleva un estado independiente de su
valor de texto (ver [data-model.md](data-model.md)):

- `informado`: el paciente proporcionó información sobre este punto.
- `negado_explicitamente`: se preguntó y el paciente lo negó explícitamente.
- `no_preguntado`: no hay evidencia en la transcripción de que se abordara.
- `no_determinado`: se mencionó pero no de forma suficientemente clara
  para clasificarlo.

`AnamnesisGenerator` nunca debe asignar `informado` o
`negado_explicitamente` sin un fragmento de la transcripción que lo
respalde. Ante la duda, el estado correcto es `no_determinado`.

## 7. Señales de alerta / motivos de derivación — checklist de demostración

**Decisión cerrada**: el MVP usa un checklist genérico de demostración
(`MockClinicalFlagsGenerator`, ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6.1 y §6.4)
para generar `clinical_flags` (p. ej. pérdida asimétrica, otalgia,
otorrea). Este checklist:

- **no está validado clínicamente**;
- **no es apto para uso real** con pacientes;
- existe únicamente para probar el flujo de datos (transcripción →
  detección de señal → revisión humana → confirmación/descarte).

Todo lugar donde se muestren o exporten `clinical_flags` — API y UI — debe
incluir, además del `ai_disclaimer` general, un segundo aviso específico:

> "Checklist de demostración. No validado clínicamente. No apto para uso
> con pacientes reales."

Cada señal generada se redacta en lenguaje no diagnóstico (§2), queda
ligada a un fragmento de la transcripción (`source_excerpt`) cuando sea
posible, y registra qué ruleset la produjo (`ruleset_name`, ver
[data-model.md](data-model.md)) para poder auditar qué reglas estuvieron
activas en cada sesión.

**Aislamiento obligatorio**: la lógica del checklist vive exclusivamente
detrás de la interfaz `ClinicalFlagsGenerator` (`integrations/domain/` —
ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6.1;
sustituye a la antigua interfaz `ClinicalFlagRuleset`, misma lógica y
mismas salvaguardas, nombre unificado con el resto del AI Pipeline).
Ningún otro módulo (API, `ai_pipeline`) contiene reglas de detección
embebidas. Esto permite sustituir `MockClinicalFlagsGenerator` por un
protocolo clínico validado en el futuro sin tocar el resto del sistema —
sustitución que, en todo caso, requerirá validación clínica y legal
previa, fuera del alcance de este MVP.

## 8. Límites explícitos de la IA en este producto

- No calcula ni sugiere grados de pérdida auditiva.
- No recomienda productos, ajustes de audífono ni tratamientos.
- No prioriza pacientes ni genera alertas de urgencia — señala
  posibles motivos de derivación para que el profesional decida.
- No accede a fuentes externas de conocimiento clínico en el MVP (el mock
  trabaja únicamente sobre el texto de la transcripción).

## 9. Responsabilidad

El documento final del expediente es responsabilidad del profesional que
lo aprueba. El sistema no debe presentarse, en ningún texto de UI, como
responsable de la exactitud clínica del contenido — solo como herramienta
de apoyo documental.
