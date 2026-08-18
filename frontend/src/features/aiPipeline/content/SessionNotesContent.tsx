import { SESSION_NOTES_BLOCK_LABELS, SESSION_NOTES_BLOCK_ORDER } from '../labels'

interface SessionNotesBlockData {
  text: string
  source_excerpt: string | null
}

interface Props {
  content: Record<string, unknown>
}

/** Los 4 bloques cerrados de SESSION_NOTES (ver
 * backend/app/integrations/domain/session_notes_generator.py). Un bloque
 * sin contenido (`text === ''`) se representa explícitamente como "sin
 * información registrada" — nunca se omite el bloque ni se inventa
 * continuidad con el resto de la nota. `source_excerpt` se muestra igual
 * que en `ClinicalFlagsContent`/`AnamnesisContent` — mismo patrón en los
 * tres tipos que lo llevan en `content`. */
export function SessionNotesContent({ content }: Props) {
  return (
    <div className="artifact-session-notes">
      {SESSION_NOTES_BLOCK_ORDER.map((blockName) => {
        const block = content[blockName] as SessionNotesBlockData | undefined
        const text = block?.text ?? ''
        const sourceExcerpt = block?.source_excerpt ?? null

        return (
          <div key={blockName} className="artifact-session-notes-block">
            <p>
              <strong>{SESSION_NOTES_BLOCK_LABELS[blockName]}</strong>
            </p>
            {text ? (
              <>
                <p>{text}</p>
                {sourceExcerpt && (
                  <p>
                    <em>Fragmento de origen:</em> «{sourceExcerpt}»
                  </p>
                )}
              </>
            ) : (
              <p>Sin información registrada en esta sesión para este bloque.</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
