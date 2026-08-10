interface Props {
  content: Record<string, unknown>
}

/** Muestra el texto de la transcripción. El bloque de texto se mantiene
 * como una única unidad semántica (`<p>`) porque `source_map` (que
 * permitiría enlazar fragmentos concretos con su origen en el audio) está
 * diseñado pero no poblado todavía — ver
 * docs/ai-pipeline-architecture.md §7.7. Cuando exista, cada fragmento se
 * envolvería aquí en su propio elemento direccionable (p. ej. `<span
 * data-source-range="...">`) sin cambiar el resto del componente. */
export function TranscriptContent({ content }: Props) {
  const text = typeof content.text === 'string' ? content.text : ''
  const language = typeof content.language === 'string' ? content.language : null

  return (
    <div className="transcript-text">
      {language && (
        <p>
          <strong>Idioma detectado:</strong> {language}
        </p>
      )}
      <p>{text || 'Sin contenido.'}</p>
    </div>
  )
}
