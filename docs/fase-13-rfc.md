# RFC — Fase 13: Facturación / Stripe (ciclo comercial)

## 0. Método, estado real y reconciliación de alcance

### 0.1 Reconciliación con `product-requirements.md` y `development-plan.md`

- [product-requirements.md](product-requirements.md) §4 excluye
  explícitamente del MVP "Gestión de facturación, citas o flujos
  administrativos ajenos a la documentación clínica".
- [development-plan.md](development-plan.md) "Fuera de las fases del MVP"
  exige un nuevo ciclo de análisis de alcance antes de planificar
  cualquier ampliación de este tipo — este documento es ese ciclo, mismo
  patrón que [fase-12-rfc.md](fase-12-rfc.md) lo fue para el onboarding
  multi-clínica: una ampliación explícita de alcance, formalizada por
  escrito antes de tocar código.
- [fase-12-rfc.md](fase-12-rfc.md) §0.2 dejó dicho explícitamente:
  "Facturación/suscripción (Stripe u otra) queda explícitamente FUERA de
  este ciclo — las primeras clínicas se gestionan con acuerdo/factura
  manual mientras se valida el flujo de onboarding en sí." Ese onboarding
  ya está cerrado e implementado (hitos 12.0-12.4); este RFC recoge el
  testigo donde lo dejó.

### 0.2 Contexto ya resuelto por otro camino (2026-09-15/16)

Antes de este RFC ya se prepararon, fuera de este ciclo técnico, los tres
documentos legales que la relación comercial con una clínica externa
requiere (ver [legal/](legal/), no versionados en git por criterio ya
establecido):

- **DPA** (Contrato de Encargado del Tratamiento, art. 28 RGPD) — cubre el
  tratamiento de datos de **pacientes**. Stripe no aparece ni debe
  aparecer en su Anexo I de subencargados: Stripe nunca toca datos de
  pacientes, solo datos del propio Cliente (clínica) como sujeto de la
  relación comercial — ver §2.3 más abajo.
- **ToS / Acuerdo de Cliente** — su apartado 4 ("Tarifas y facturación")
  quedó explícitamente en placeholder porque este módulo no existía.
  **Es el documento que hay que reescribir de verdad cuando este RFC se
  cierre y el modelo de precios esté decidido** (ver §9).
- **RAT** — registra la actividad de tratamiento por cuenta de los
  Responsables (clínicas); no cambia por Stripe salvo, indirectamente, en
  su Anexo II si Stripe llegara a tratar algún dato de paciente (no
  debería, ver §2.3).

### 0.3 Estado real confirmado (auditoría de código, 2026-09-16)

- `ClinicORM` (`app/clinics/infrastructure/orm.py`) tiene hoy `id`, `name`,
  `code`, `is_active`, `created_at`, `updated_at` — **ningún campo de
  facturación** (sin `stripe_customer_id`, sin `subscription_status`, sin
  `plan`).
- Existe ya seguimiento de coste de IA por ejecución:
  `GenerationRun.estimated_cost_usd` (`app/ai_pipeline/infrastructure/
  orm.py`), más los límites globales de gasto `LLM_COST_LIMIT_ENFORCED` /
  `MAX_LLM_COST_PER_SESSION_USD` (`app/core/config.py`) — pensados como
  **freno de seguridad interno** (evitar una factura de IA descontrolada),
  no como sistema de medición para cobrar a la clínica. Es la pieza que
  más se acerca a una base de facturación por uso si en el futuro se
  quisiera ir en esa dirección (ver §4.3).
- No existe ningún módulo `app/billing/` ni equivalente, ni integración
  con Stripe (ni SDK en `pyproject.toml`, ni variables `STRIPE_*` en
  `config.py`/`.env.example`/`.railway/railway.ts`).
- Patrón arquitectónico ya establecido y reutilizable tal cual
  (`domain/infrastructure/api/service.py`, "autoriza → opera → audita →
  commit", ver [architecture.md](architecture.md)) y matriz de roles ya
  definida (`app/core/authorization.py`: `ADMIN`/`AUDIOLOGIST`/`VIEWER`) —
  igual que en la Fase 12, las operaciones de facturación (ver plan,
  cambiar de plan, abrir el portal de cliente) deberían quedar
  restringidas a `ADMIN`, mismo criterio que las invitaciones.
- Patrón ya establecido para autenticar llamadas entrantes de un tercero
  sin `CurrentUser` (`X-{Servicio}-Cron-Secret` + `secrets.compare_digest`,
  usado en retención y en la limpieza de onboarding) — **no aplica
  directamente al webhook de Stripe**, que usa su propio mecanismo de
  firma (`Stripe-Signature` + secreto de webhook), pero confirma que el
  proyecto ya tiene el hábito correcto (secreto dedicado, nunca
  comparación con `==`) para este tipo de endpoint no autenticado por JWT.

## 1. Objetivos y no objetivos

### 1.1 Objetivos

- Que una clínica pueda pasar de "gestionada a mano por Gerard" a "cliente
  de pago recurrente" sin que Gerard tenga que emitir facturas ni
  gestionar cobros manualmente.
- Que el estado de la suscripción (al día / impagada / cancelada)
  controle el acceso real a la plataforma, sin intervención manual.
- Dejar decidido y documentado el modelo de precios antes de escribir
  código de facturación (mismo criterio que toda ampliación de alcance en
  este proyecto).
- Mantener separados, con claridad legal, los datos de facturación de la
  clínica (gestionados por Stripe) de los datos clínicos de los pacientes
  (nunca tocados por Stripe) — ver §2.3.

### 1.2 No objetivos (fuera de este ciclo)

**Corrección (2026-09-18, cierre del RFC)**: dos puntos que esta sección
daba por fuera de alcance entraron finalmente en el ciclo, a petición
explícita de Gerard — se explican en su decisión correspondiente más
abajo en vez de repetirse aquí: facturación consolidada de una
cadena/empresa con varias clínicas bajo un mismo pagador (§3.3, sí en
alcance — pero sin panel de gestión centralizado, ver más abajo) y
descuento por pago anual (§3.2, sí en alcance).

- **Panel de sede central** (una cuenta que vea/gestione varias clínicas
  de una misma cadena desde un solo login) — sigue fuera de alcance de
  esta fase. A diferencia de la facturación consolidada (que no toca el
  modelo de datos), esto exige un concepto nuevo en el dominio
  (agrupar `Clinic`s bajo una entidad de organización) y revisar la
  autorización que hoy asume `current_user.clinic_id` único en al menos
  10 puntos del backend — tamaño de una fase propia, no un añadido de
  Stripe. Decisión explícita de Gerard (2026-09-18): se retoma como fase
  dedicada una vez el programa ya esté lanzado con facturación
  funcionando, ver [development-plan.md](development-plan.md).
- Marketplace/Connect (Gerard no revende el servicio de terceros ni paga
  a terceros a través de Stripe) — el modelo es SaaS directo, no
  plataforma multi-vendedor, así que **Stripe Connect no aplica**, solo
  Stripe Billing/Checkout estándar.
- Cupones, referidos — quedan como incremento posterior (§8), Stripe los
  soporta nativamente cuando se decida usarlos.
- Anti-abuso del signup público (CAPTCHA, dominios desechables) — ya
  implementado el 2026-09-18 (hito 12.4 ampliado), antes de cerrar este
  RFC, no después como se preveía originalmente aquí.

## 2. Implicaciones legales y fiscales (gestión de Gerard, no solo técnica)

### 2.1 Relación con el ToS ya redactado

El ToS entregado (ver §0.2) ya prevé este momento: su cláusula 4 dice
literalmente que "debe reescribirse por completo cuando se implemente la
suscripción de pago, incluyendo: precio, periodicidad, forma de pago,
consecuencias del impago y política de reembolso." Este RFC es el paso
previo que deja esas decisiones tomadas por escrito; la reescritura real
del ToS (y, si aplica, del RAT) se hace en cuanto este RFC se cierre —
Gerard ya ha pedido explícitamente que esto se haga sin que se le tenga
que recordar (2026-09-16).

### 2.2 IVA / fiscalidad (clientes empresa, no consumidor final)

Las clínicas son el Cliente en el ToS (personas jurídicas, no
consumidores), por lo que aplica el régimen de **IVA entre empresas
(B2B)**, no el de consumo:

- Cliente español → IVA español estándar (21%) en la factura.
- Cliente de otro país de la UE con NIF-IVA intracomunitario válido →
  inversión del sujeto pasivo ("reverse charge", 0% en la factura de
  Gerard, el cliente autoliquida su propio IVA) — requiere validar el
  NIF-IVA del cliente (VIES) antes de aplicar el 0%.
- Cliente de otro país de la UE sin NIF-IVA válido, o fuera de la UE →
  caso a resolver con más detalle cuando aparezca (no bloqueante con
  cero clientes reales hoy).
- **Stripe Tax** automatiza este cálculo (determina el tipo aplicable
  según la ubicación y el NIF-IVA del cliente, incluida la inversión del
  sujeto pasivo) a cambio de una comisión por transacción — evita que
  Gerard tenga que programar esta lógica a mano, pero exige configurar el
  domicilio fiscal de origen y decidir en qué países hay obligación de
  registro antes de activarlo.
**Decisión cerrada (2026-09-18)**: gestión de IVA a mano al principio
(factura simple con IVA español estándar, sin reverse charge) mientras
los clientes sean pocos y mayoritariamente españoles. Activar Stripe Tax
más adelante en cuanto haya clientes reales en otros países de la UE —
mismo criterio ya aplicado al DPD (no resolver con infraestructura antes
de tener el volumen que la justifique). Excepción: cualquier cliente
"Cadena/Empresa" (§3.3) fuera de España se revisa caso a caso antes de
facturarlo, dado que ahí sí hay negociación directa con Gerard.

### 2.3 Qué datos ve Stripe (y por qué no toca el DPA de pacientes)

Stripe, como procesador de pagos, trata: nombre y email de la persona de
contacto de facturación de la clínica, datos de la tarjeta (nunca
almacenados por Gerard — Stripe Checkout es hosted, la tarjeta no pasa
por el backend de Audiology AI Assistant), y el histórico de facturas.
Ninguno de esos datos es un dato de paciente. Por tanto:

- **No entra en el Anexo I del DPA** (ese Anexo lista subencargados que
  tratan datos de pacientes por cuenta de la clínica — Anthropic, OpenAI,
  Deepgram/AssemblyAI, Railway, Cloudflare).
- **Sí es un proveedor de Gerard como Responsable de sus propios datos de
  contacto comercial** (igual que Brevo para los emails de onboarding) —
  corresponde añadirlo a [privacy-and-security.md](privacy-and-security.md)
  §9/§10 cuando se active, no al DPA que Gerard ofrece a sus clientes.
- Stripe es sub-processor certificado con SCCs + participación en el
  marco EU-US Data Privacy Framework para sus operaciones fuera de la UE
  (a confirmar con el mismo nivel de detalle que se hizo con Anthropic
  antes de citarlo como definitivo en cualquier documento legal).

## 3. Modelo de negocio propuesto

### 3.1 Opciones comparadas

| Modelo | Cómo se cobra | Ventajas | Inconvenientes |
|---|---|---|---|
| **A — Suscripción plana por clínica, por niveles (recomendado para el primer incremento)** | Precio fijo mensual/anual por clínica, cada nivel con un tope de uso incluido (p. ej. nº de sesiones/mes) | Sencillo de implementar con Stripe Billing estándar (un `Price` por nivel); factura predecible para el cliente y para Gerard; encaja con `Clinic` como unidad de facturación ya existente | El precio no sigue el coste real de IA con precisión; una clínica que se pase de nivel sin darse cuenta genera fricción hasta que se defina qué pasa (bloquear, cobrar overage, avisar) |
| **B — Por usuario (asiento)** | Precio por usuario activo de la clínica (`ADMIN`/`AUDIOLOGIST`/`VIEWER`) | Encaja con el modelo de invitaciones ya implementado (Fase 12); fácil de entender ("X€/usuario/mes"); Stripe soporta cantidad variable de forma nativa | No refleja el coste real de IA (una clínica con 2 usuarios muy activos puede costar más que una con 5 usuarios pasivos); exige sincronizar la cantidad de la suscripción cada vez que se invita/desactiva un usuario |
| **C — Medido por uso real (metered billing sobre `estimated_cost_usd`)** | Se reporta a Stripe el consumo real de IA de cada clínica y se cobra sobre eso, con o sin un mínimo | La más justa técnicamente; reutiliza directamente el tracking de coste ya existente en `ai_pipeline` | Factura variable e impredecible para el cliente (mala fricción comercial en un sector poco acostumbrado a SaaS); requiere reportar uso a Stripe de forma fiable (colas, reintentos) — complejidad que no se justifica sin datos reales de uso todavía |
| **D — Híbrido: base plana + overage medido** | Igual que A, más cobro adicional por Stripe metered billing si se supera el tope incluido | El más robusto a medio plazo — combina predictibilidad con captura de valor real | Es A y C a la vez: más superficie de código y de UI para el primer incremento del proyecto |

### 3.2 Decisión cerrada (2026-09-18)

Gerard eligió el **modelo D** (base plana por niveles + overage medido
sobre `estimated_cost_usd`, hasta un techo de seguridad — no el modelo A
recomendado originalmente): más superficie de código que el modelo A,
pero evita la fricción de bloquear a una clínica que se pasa del tope por
poco, sin dejar el gasto totalmente sin límite.

**Niveles y precios** (mensual / anual con descuento de 2 meses — pagas
10, no 12):

| Nivel | Tope incluido | Precio/mes | Precio/año | Para quién (aprox.) |
|---|---|---|---|---|
| Básico | 40 sesiones/mes | 39€ | 390€ | 1 profesional, uso selectivo de la IA (~2 sesiones/día) — autónomo o consulta muy pequeña |
| Profesional | 150 sesiones/mes | 109€ | 1.090€ | Clínica de 2-3 profesionales, uso habitual |
| Clínica grande | 400 sesiones/mes | 249€ | 2.490€ | 5-8 profesionales, o varios puntos de atención bajo un mismo centro |
| Cadena/Empresa | por clínica, ver §3.3 | 89€/clínica (2-5) · 75€/clínica (6-15) | mismo descuento de 2 meses | Cadenas con varios centros bajo un mismo pagador (tipo GAES, Soloptical) — más de 15 clínicas, presupuesto a medida negociado directamente |

Precios de partida, no un estudio de mercado — a revisar con datos reales
de conversión/abandono en cuanto haya clientes de pago reales.

**Overage** (modelo D): al superar el tope incluido, el exceso se cobra
automáticamente vía Stripe metered billing sobre `estimated_cost_usd`
real, hasta un techo de seguridad fijado en el doble del tope incluido de
cada nivel (p. ej. Básico: cobro automático hasta 80 sesiones/mes). Por
encima de ese techo, se bloquea el acceso (ver §5, gate de suscripción) y
se sugiere explícitamente subir de nivel — evita tanto la fricción de
bloquear por un exceso pequeño como una factura descontrolada por un uso
muy por encima de lo esperado.

**Periodo de prueba**: 14 días gratuitos, con tarjeta pedida desde el
alta (reduce abuso de pruebas, coherente con el anti-abuso ya existente
en el signup).

**Descuento por pago anual**: sí, equivalente a 2 meses gratis (pagas 10
meses de una vez en vez de 12 mensualidades) — ver tabla arriba.

### 3.3 Nivel Cadena/Empresa

Añadido el 2026-09-18 a petición de Gerard, pensando en cadenas grandes
(GAES, Soloptical y similares) con muchas clínicas abiertas en el mismo
país. Alcance de esta fase, deliberadamente acotado a solo
**facturación consolidada** — un único pagador (`stripe_customer_id`) con
una suscripción de cantidad variable (`quantity` = nº de clínicas de la
cadena) y precio por volumen, mientras cada `Clinic` de la cadena sigue
funcionando exactamente igual que hoy: aislada, con su propio `admin` y
usuarios, sin visibilidad cruzada entre clínicas de la misma cadena. No
incluye ningún panel de gestión centralizado — ver §1.2 para esa
decisión, aplazada explícitamente a una fase futura dedicada.

Alta de una cadena, en este primer incremento: **gestionada
semi-manualmente por Gerard** (no self-service) — estas ventas se
negocian directamente, no llegan por el formulario público de signup. El
modelo de datos no necesita ningún cambio: basta con poder asociar el
mismo `stripe_customer_id` a varias filas de `Clinic` en vez de asumir
1:1 clínica↔pagador (ver §5).

## 4. Flujo resultante

### 4.1 Alta de facturación de una clínica ya existente (o nueva)

1. El admin de la clínica, desde un nuevo apartado "Facturación" del
   panel (frontend), inicia el alta → `POST /billing/checkout-session`
   (nuevo, autenticado, solo `ADMIN`) crea una Stripe Checkout Session en
   modo `subscription` para el nivel elegido y redirige al Checkout
   alojado por Stripe.
2. El admin introduce sus datos de pago en la página de Stripe (nunca en
   la plataforma de Gerard) y confirma.
3. Stripe redirige de vuelta a una URL de éxito/cancelación propia del
   frontend; el estado real de la suscripción no se confía a ese
   redirect, sino al webhook (paso 4) — mismo criterio de no fiarse de lo
   que dice el cliente, solo de lo que confirma el servidor.
4. Webhook `POST /billing/webhook` (nuevo, sin `CurrentUser`, verificado
   con la firma `Stripe-Signature` + `STRIPE_WEBHOOK_SECRET`) recibe
   `checkout.session.completed`, asocia `stripe_customer_id` y
   `stripe_subscription_id` a la `Clinic`, y fija su `subscription_status`.

### 4.2 Vida de la suscripción

- `customer.subscription.updated` / `invoice.paid` / `invoice.payment_failed`
  / `customer.subscription.deleted` — el webhook mantiene
  `Clinic.subscription_status` sincronizado (`active`, `past_due`,
  `canceled`, etc.) como única fuente de verdad para decidir acceso (ver
  §5.3).
- El admin gestiona su propio método de pago, ve facturas pasadas y
  cancela/cambia de nivel desde el **Stripe Customer Portal** (enlace
  generado por `POST /billing/portal-session`, autenticado, `ADMIN`) — no
  hace falta construir esa UI a mano, Stripe la aloja.

### 4.3 Uso de `estimated_cost_usd` en este ciclo

**Actualizado (2026-09-18)**: al confirmarse el modelo D (§3.2), esta
pieza sí se activa en este ciclo — no queda aplazada. `estimated_cost_usd`
(ya trackeado por `ai_pipeline`, mismo campo que alimenta el benchmark de
proveedores) es la base para reportar el overage medido a Stripe cuando
una clínica supera el tope de sesiones incluido en su nivel, hasta el
techo de seguridad de §3.2. Sigue existiendo además, sin cambios, como
freno de seguridad interno (`LLM_COST_LIMIT_ENFORCED`) — son dos
mecanismos distintos: uno factura, el otro corta en seco un coste por
sesión disparado.

## 5. Arquitectura técnica propuesta

- Nuevo módulo `app/billing/` (mismo patrón `domain/infrastructure/api/
  service.py` que el resto del proyecto):
  - `domain/entities.py`: no hace falta una entidad nueva más allá de
    extender `Clinic` con `stripe_customer_id: str | None`,
    `stripe_subscription_id: str | None`, `subscription_status: str
    | None`, `plan: str | None`, `sessions_used_this_period: int`
    (migración Alembic). `stripe_customer_id` puede repetirse entre varias
    filas de `Clinic` — es lo único que necesita el nivel Cadena/Empresa
    (§3.3), sin tabla ni entidad nueva.
  - `service.py` (`BillingService`): `create_checkout_session`,
    `create_portal_session`, `handle_webhook_event`, `report_overage_usage`
    (nuevo, reporta a Stripe metered billing cuando se supera el tope
    incluido, hasta el techo de seguridad de §3.2) — autoriza (`ADMIN`
    para las dos primeras; el webhook no tiene usuario, se autentica por
    firma) → opera → audita → commit, mismo criterio que el resto.
  - `api/router.py`: `POST /billing/checkout-session`, `POST /billing/
    portal-session` (autenticados), `POST /billing/webhook` (no
    autenticado por JWT, verificado por firma de Stripe).
- SDK oficial `stripe` (Python) como nueva dependencia de producción en
  `backend/pyproject.toml`.
- Variables de entorno nuevas (`.env.example`, `config.py`,
  `.railway/railway.ts`, mismo patrón `preserve()` ya usado para el resto
  de secretos): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
  `STRIPE_PRICE_ID_<NIVEL>` (uno por nivel de precio, incluido el precio
  por volumen de Cadena/Empresa), `STRIPE_METERED_PRICE_ID_<NIVEL>`
  (overage).
- **Gate de acceso por estado de suscripción**: nueva dependencia FastAPI
  (parecida a `get_current_user_provider`) que bloquee (403, no 401 — el
  usuario sí está autenticado, es su clínica la que no está al día) los
  endpoints de negocio cuando `Clinic.subscription_status` no sea
  `active`/`trialing`, o cuando el uso del periodo supere el techo de
  seguridad de overage (§3.2). **Decisión cerrada (2026-09-18)**: periodo
  de gracia = el que ya gestiona Stripe con sus reintentos de cobro
  ("dunning") — no se bloquea en el primer `past_due`, solo cuando Stripe
  marca la suscripción como definitivamente impagada
  (`unpaid`/`canceled`). Evita bloquear a una clínica por un fallo de
  cobro puntual (tarjeta caducada ese mismo día, por ejemplo) mientras
  Stripe todavía está reintentando.
- Idempotencia del webhook: Stripe puede reenviar el mismo evento más de
  una vez — el handler debe ser idempotente (comprobar
  `stripe_event.id` ya procesado antes de aplicar el cambio), mismo
  espíritu que ya se aplica en otros procesos automáticos del proyecto
  (los cron de limpieza son idempotentes por diseño).

## 6. Riesgos y mitigaciones

- **Webhook falsificado**: mitigado por la verificación obligatoria de
  `Stripe-Signature` con `STRIPE_WEBHOOK_SECRET` — nunca confiar en el
  cuerpo del request sin verificar la firma primero.
- **Reintentos duplicados del webhook**: mitigado por idempotencia por
  `stripe_event.id` (ver §5).
- **Suscripción cancelada pero la clínica sigue con acceso** (webhook
  perdido/caído temporalmente): mitigado por una comprobación periódica
  de reconciliación (cron, mismo patrón que retención/limpieza) que
  contraste el estado real en Stripe con `Clinic.subscription_status` al
  menos una vez al día — no depender solo del webhook para el caso
  extremo.
- **Impago silencioso sin que el admin se entere**: Stripe ya envía sus
  propios emails de dunning/impago al método de contacto de facturación;
  valorar un aviso adicional dentro de la propia plataforma cuando
  `subscription_status` pase a `past_due` (no bloqueante para el primer
  incremento).
- **Fuga de datos de tarjeta**: no aplica — Stripe Checkout es hosted, la
  tarjeta nunca pasa por el backend de Gerard (evita todo el alcance de
  cumplimiento PCI-DSS más allá del nivel más bajo, "SAQ A").
- **SCA/PSD2** (autenticación reforzada del titular de la tarjeta,
  obligatoria para pagos en la UE): la gestiona Stripe Checkout de forma
  automática (3D Secure cuando el banco emisor lo exige) — no requiere
  lógica propia.

## 7. Roadmap de implementación propuesto (hitos, nada implementado todavía)

- **13.0** — Alineación documental (este RFC) + decisiones comerciales de
  Gerard (§3.2) + cuenta de Stripe creada (modo test) + reescritura real
  del ToS §4 con precios definitivos.
- **13.1** — Modelo de datos (`Clinic` + migración) + `BillingService` +
  `POST /billing/checkout-session` + webhook con los eventos de alta.
- **13.2** — Webhooks del resto del ciclo de vida (impago, cancelación,
  actualización) + gate de acceso por `subscription_status` + cron de
  reconciliación diaria.
- **13.3** — `POST /billing/portal-session` (Customer Portal) + apartado
  "Facturación" en el frontend (estado del plan, botón a Checkout/Portal).
- **13.4** — Paso de producción: cuenta de Stripe en modo live, IVA
  decidido (§2.2), migración de las clínicas piloto gestionadas a mano
  (si Gerard quiere pasarlas a cobro automático) o convivencia de ambas
  formas mientras dure la transición.

## 8. Cuestiones futuras, no bloqueantes (quedan fuera de este ciclo)

- **Panel de sede central** para el nivel Cadena/Empresa (§3.3) — ver
  §1.2, fase propia dedicada, a retomar una vez el programa esté lanzado
  con Stripe funcionando.
- Cupones, programa de referidos — Stripe los soporta nativamente cuando
  se decida usarlos.
- Activación de Stripe Tax (ver §2.2) — aplazado hasta tener clientes
  reales fuera de España.
- Clasificación de errores CRÍTICO/MAYOR/MENOR del benchmark de
  transcripción (Fase 5.3) — nota cruzada, sin relación con facturación,
  dejada aquí solo porque comparte el mismo criterio de "backlog
  explícito, no bloqueante".

## 9. Cierre de este RFC

**Cerrado el 2026-09-18.** Decisiones tomadas con Gerard:

- Modelo de negocio: **D** (base plana por niveles + overage medido con
  techo de seguridad) — no el modelo A recomendado originalmente (§3.2).
- Niveles, precios (mensual/anual) y a quién va dirigido cada uno: ver
  tabla de §3.2.
- Nivel nuevo **Cadena/Empresa**, no contemplado en la versión original de
  este RFC: facturación consolidada por volumen, sin panel de gestión
  centralizado (§3.3).
- IVA: gestión manual al principio, Stripe Tax cuando haya clientes reales
  fuera de España (§2.2).
- Periodo de prueba: 14 días, con tarjeta desde el alta (§3.2).
- Qué pasa al superar el tope: cobro automático del exceso hasta un techo
  de seguridad, bloqueo solo por encima de ese techo o por impago
  definitivo confirmado por Stripe, nunca por el primer `past_due` (§3.2,
  §5).

Con el RFC cerrado, quedan dos documentos legales por actualizar con
estas cifras definitivas: el **ToS** (cláusula 4, tarifas — reescritura
completa, hecha el mismo día) y, solo si la fiscalidad elegida en §2.2 lo
llega a requerir más adelante,
[privacy-and-security.md](privacy-and-security.md) (nueva entrada para
Stripe como proveedor de Gerard, no del DPA de sus clientes — pendiente,
se añade cuando se active Stripe de verdad, no antes). El hito 13.1
(código) puede empezar en cuanto Gerard lo pida — este RFC ya no es un
bloqueante.
