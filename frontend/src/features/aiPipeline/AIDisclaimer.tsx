interface Props {
  /** Texto tal cual lo devuelve la API (`ai_disclaimer` en la respuesta de
   * cada artefacto) — nunca se hardcodea en el frontend, así coincide
   * siempre con la constante única del backend (`core/messages/es.py`). */
  text: string
}

export function AIDisclaimer({ text }: Props) {
  return (
    <p className="ai-disclaimer" role="note">
      {text}
    </p>
  )
}
