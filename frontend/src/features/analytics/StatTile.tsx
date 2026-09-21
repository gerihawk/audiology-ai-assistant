interface Props {
  label: string
  value: string | number
  /** Solo para cifras con una lectura de estado natural (p. ej. artefactos
   * aprobados/rechazados) — ver references/marks-and-anatomy.md del skill
   * de dataviz: el color nunca es la única señal, siempre va acompañado
   * de `label`. */
  accentColor?: string
}

/** Tarjeta de una cifra agregada — "KPI row de stat tiles" para un
 * puñado de números de cabecera (ver choosing-a-form.md del skill de
 * dataviz), nunca una gráfica de una sola barra. `label` en minúscula
 * inicial sin dos puntos, `value` en semibold con cifras proporcionales
 * (nunca tabulares: esto no es una columna que deba alinear con otras). */
export function StatTile({ label, value, accentColor }: Props) {
  return (
    <div className="analytics-stat-tile">
      <p className="analytics-stat-tile__label">{label}</p>
      <p
        className="analytics-stat-tile__value"
        style={accentColor ? { color: accentColor } : undefined}
      >
        {value}
      </p>
    </div>
  )
}
