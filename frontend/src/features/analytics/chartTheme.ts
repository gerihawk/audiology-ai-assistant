/** Constantes de color para los gráficos de la Fase 15 — subconjunto de
 * la paleta validada del skill de dataviz (references/palette.md), solo
 * en modo claro: el resto de la aplicación no tiene modo oscuro todavía,
 * así que introducir uno solo para este panel sería inconsistente. Si en
 * el futuro se añade modo oscuro a toda la app, estos valores se
 * sustituyen por los equivalentes de la columna "Dark" de esa misma
 * referencia. */

/** Hue secuencial por defecto (azul) — para una única serie de magnitud
 * (tendencia de sesiones por día) y para comparaciones de magnitud entre
 * categorías (desglose por estado, actividad por profesional): "un solo
 * hue, más oscuro = más alto" es el valor seguro por defecto cuando las
 * categorías no son la propia identidad de la historia. */
export const SEQUENTIAL_BLUE = '#2a78d6'
export const SEQUENTIAL_BLUE_AREA_FILL = 'rgba(42, 120, 214, 0.1)' // ~10% opacidad, ver marks-and-anatomy.md

/** Paleta de estado fija (nunca se tematiza) — usada solo para el
 * desglose de artefactos de IA por estado, donde las tres categorías SÍ
 * son estados con una lectura de buen/mal resultado natural (aprobado =
 * bien, pendiente = atención, rechazado = mal). Nunca reutilizada para
 * "serie 4" de ningún otro gráfico. */
export const STATUS_COLORS = {
  good: '#0ca30c',
  warning: '#fab219',
  critical: '#d03b3b',
} as const

export const CHART_INK = {
  primary: '#0b0b0b',
  secondary: '#52514e',
  muted: '#898781',
  gridline: '#e1e0d9',
  baseline: '#c3c2b7',
  surface: '#fcfcfb',
} as const
