import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART_INK, SEQUENTIAL_BLUE } from './chartTheme'

export interface BarChartItem {
  label: string
  value: number
}

interface Props {
  items: BarChartItem[]
  emptyMessage: string
  /** Alto por fila en px — el gráfico crece con el número de categorías en
   * vez de comprimirlas todas en una altura fija. */
  rowHeight?: number
}

/** Barra horizontal de una sola serie — comparación de magnitud entre
 * categorías con nombre (desglose de sesiones por estado, actividad por
 * profesional). Un solo hue secuencial: aquí las categorías no son la
 * identidad de la historia, solo su magnitud relativa (ver
 * choosing-a-form.md del skill de dataviz) — nunca un color distinto por
 * categoría, eso es para cuando la identidad de cada serie importa. */
export function HorizontalBarChart({ items, emptyMessage, rowHeight = 36 }: Props) {
  if (items.length === 0 || items.every((item) => item.value === 0)) {
    return <p>{emptyMessage}</p>
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(items.length * rowHeight, 80)}>
      <BarChart data={items} layout="vertical" margin={{ top: 4, right: 24, left: 0, bottom: 4 }}>
        <CartesianGrid stroke={CHART_INK.gridline} horizontal={false} />
        <XAxis
          type="number"
          allowDecimals={false}
          stroke={CHART_INK.baseline}
          tick={{ fill: CHART_INK.muted, fontSize: 12 }}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={140}
          stroke={CHART_INK.baseline}
          tick={{ fill: CHART_INK.primary, fontSize: 12 }}
        />
        <Tooltip formatter={(value) => [String(value ?? 0), 'Total']} />
        <Bar
          dataKey="value"
          fill={SEQUENTIAL_BLUE}
          radius={[0, 4, 4, 0]}
          maxBarSize={24}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
