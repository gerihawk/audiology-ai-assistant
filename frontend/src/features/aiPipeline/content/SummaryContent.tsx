interface Props {
  content: Record<string, unknown>
}

/** Muestra el resumen como documento de lectura (no como bloque de código
 * ni JSON crudo). */
export function SummaryContent({ content }: Props) {
  const text = typeof content.text === 'string' ? content.text : ''

  return (
    <article>
      <p>{text || 'Sin contenido.'}</p>
    </article>
  )
}
