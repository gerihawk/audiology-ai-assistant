import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { SessionsTrendPoint } from '../../shared/api/types'
import { CHART_INK, SEQUENTIAL_BLUE, SEQUENTIAL_BLUE_AREA_FILL } from './chartTheme'

interface Props {
  data: SessionsTrendPoint[]
}

const DAY_FORMATTER = new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: '2-digit' })

function formatDay(day: string): string {
  return DAY_FORMATTER.format(new Date(`${day}T00:00:00`))
}

/** Tendencia de sesiones por día — una única serie de magnitud a lo largo
 * del tiempo: área con un solo hue secuencial (ver choosing-a-form.md del
 * skill de dataviz), sin leyenda (una sola serie no la necesita, el
 * título del bloque ya dice qué se representa). */
export function SessionsTrendChart({ data }: Props) {
  if (data.length === 0) {
    return <p>No hay sesiones registradas en este periodo.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={CHART_INK.gridline} vertical={false} />
        <XAxis
          dataKey="day"
          tickFormatter={formatDay}
          stroke={CHART_INK.baseline}
          tick={{ fill: CHART_INK.muted, fontSize: 12 }}
        />
        <YAxis
          allowDecimals={false}
          stroke={CHART_INK.baseline}
          tick={{ fill: CHART_INK.muted, fontSize: 12 }}
        />
        <Tooltip
          labelFormatter={(day) => formatDay(String(day))}
          formatter={(value) => [String(value ?? 0), 'Sesiones']}
        />
        <Area
          type="monotone"
          dataKey="count"
          name="Sesiones"
          stroke={SEQUENTIAL_BLUE}
          strokeWidth={2}
          fill={SEQUENTIAL_BLUE_AREA_FILL}
          dot={false}
          activeDot={{ r: 4 }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
