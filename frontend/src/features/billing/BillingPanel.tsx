import { useCallback, useEffect, useState } from 'react'
import {
  createCheckoutSession,
  createPortalSession,
  getBillingStatus,
} from '../../shared/api/billing'
import { describeActionError } from '../../shared/apiErrorMessage'
import type { BillingStatus, Plan, Role } from '../../shared/api/types'
import { canManageBilling } from './permissions'

type LoadState = 'loading' | 'ready' | 'error'

interface Props {
  devUserId: string
  role: Role | undefined
}

/** Un nivel por fila — nombre visible + slug (`Plan`) que viaja al
 * backend. Precios/topes son los cerrados en docs/fase-13-rfc.md §3.2;
 * viven solo en el texto de esta pantalla (no hay endpoint que los
 * exponga, ver docs/fase-13-rfc.md §5: los Price de Stripe son la fuente
 * de verdad del precio real). */
const PLANS: { slug: Plan; label: string; description: string }[] = [
  { slug: 'basico', label: 'Básico', description: '40 sesiones/mes — 39€/mes' },
  { slug: 'profesional', label: 'Profesional', description: '150 sesiones/mes — 109€/mes' },
  { slug: 'clinica_grande', label: 'Clínica grande', description: '400 sesiones/mes — 249€/mes' },
  {
    slug: 'cadena_empresa',
    label: 'Cadena/Empresa',
    description: 'Facturación consolidada por volumen — precio a medida, contacta con Gerard',
  },
]

const PLAN_LABELS: Record<Plan, string> = {
  basico: 'Básico',
  profesional: 'Profesional',
  clinica_grande: 'Clínica grande',
  cadena_empresa: 'Cadena/Empresa',
}

/** Apartado "Facturación" (Fase 13, hito 13.3) — estado de la suscripción
 * de la clínica, botón a Stripe Checkout por nivel y botón al Stripe
 * Customer Portal. Recibe `devUserId`/`role` por props en vez de leer
 * `useDevUser()` directamente — mismo patrón que
 * `IntegrationsList`/`InvitationsList`, para que `BillingPage` sea solo el
 * gate y esto sea testeable con props fijas. */
export function BillingPanel({ devUserId, role }: Props) {
  const [billingStatus, setBillingStatus] = useState<BillingStatus | null>(null)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [redirecting, setRedirecting] = useState<Plan | 'portal' | null>(null)

  const canManage = canManageBilling(role)

  const load = useCallback(() => {
    setLoadState('loading')
    setErrorMessage(null)
    getBillingStatus(devUserId)
      .then((response) => {
        setBillingStatus(response)
        setLoadState('ready')
      })
      .catch((error: unknown) => {
        const described = describeActionError(error)
        setErrorMessage(`${described.label}: ${described.message}`)
        setLoadState('error')
      })
  }, [devUserId])

  useEffect(() => {
    if (canManage) load()
  }, [canManage, load])

  if (!canManage) return null

  async function handleCheckout(plan: Plan) {
    setRedirecting(plan)
    setErrorMessage(null)
    try {
      const result = await createCheckoutSession(plan, devUserId)
      window.location.href = result.checkout_url
    } catch (error) {
      const described = describeActionError(error)
      setErrorMessage(`${described.label}: ${described.message}`)
      setRedirecting(null)
    }
  }

  async function handlePortal() {
    setRedirecting('portal')
    setErrorMessage(null)
    try {
      const result = await createPortalSession(devUserId)
      window.location.href = result.portal_url
    } catch (error) {
      const described = describeActionError(error)
      setErrorMessage(`${described.label}: ${described.message}`)
      setRedirecting(null)
    }
  }

  return (
    <div>
      <h2>Facturación</h2>

      {errorMessage && <p role="alert">{errorMessage}</p>}

      {loadState === 'loading' && <p role="status">Cargando estado de facturación…</p>}

      {loadState === 'ready' && billingStatus && (
        <section aria-label="Estado actual">
          <h3>Estado actual</h3>
          {billingStatus.plan === null ? (
            <p>Esta clínica todavía no tiene un plan de Stripe contratado (gestión manual).</p>
          ) : (
            <>
              <p>
                Nivel: <strong>{PLAN_LABELS[billingStatus.plan]}</strong> — estado:{' '}
                <strong>{billingStatus.subscription_status ?? 'desconocido'}</strong>
              </p>
              {billingStatus.included_sessions !== null && (
                <p>
                  Uso de este periodo: {billingStatus.sessions_used_this_period} /{' '}
                  {billingStatus.included_sessions} sesiones incluidas
                  {billingStatus.safety_cap_sessions !== null &&
                    billingStatus.sessions_used_this_period > billingStatus.included_sessions &&
                    billingStatus.sessions_used_this_period <=
                      billingStatus.safety_cap_sessions && (
                      <>
                        {' '}
                        (en overage, facturado automáticamente hasta{' '}
                        {billingStatus.safety_cap_sessions})
                      </>
                    )}
                </p>
              )}
              {billingStatus.safety_cap_sessions !== null &&
                billingStatus.sessions_used_this_period > billingStatus.safety_cap_sessions && (
                  <p role="alert">
                    Se ha superado el techo de uso incluido en el nivel contratado — el pipeline de
                    IA está bloqueado hasta subir de nivel.
                  </p>
                )}
            </>
          )}
          <button
            type="button"
            onClick={() => void handlePortal()}
            disabled={!billingStatus.has_stripe_customer || redirecting !== null}
          >
            {redirecting === 'portal' ? 'Abriendo…' : 'Gestionar método de pago / facturas'}
          </button>
        </section>
      )}

      <section aria-label="Niveles disponibles">
        <h3>Niveles disponibles</h3>
        <ul>
          {PLANS.map((plan) => (
            <li key={plan.slug}>
              <strong>{plan.label}</strong> — {plan.description}{' '}
              <button
                type="button"
                onClick={() => void handleCheckout(plan.slug)}
                disabled={redirecting !== null}
              >
                {redirecting === plan.slug
                  ? 'Abriendo…'
                  : billingStatus?.plan === plan.slug
                    ? 'Nivel actual'
                    : 'Contratar'}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
