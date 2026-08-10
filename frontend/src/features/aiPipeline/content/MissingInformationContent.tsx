interface MissingInfoItemData {
  topic: string
  suggested_question: string
}

interface Props {
  content: Record<string, unknown>
}

/** Formato checklist, deliberadamente no editable: son sugerencias de
 * seguimiento para el profesional, no un formulario. */
export function MissingInformationContent({ content }: Props) {
  const items = Array.isArray(content.items) ? (content.items as MissingInfoItemData[]) : []

  if (items.length === 0) {
    return <p>No se ha sugerido información adicional que ampliar.</p>
  }

  return (
    <ul className="artifact-checklist">
      {items.map((item) => (
        <li key={item.topic} className="artifact-checklist-item">
          <label>
            <input type="checkbox" disabled checked={false} aria-readonly="true" />
            {item.suggested_question}
          </label>
        </li>
      ))}
    </ul>
  )
}
