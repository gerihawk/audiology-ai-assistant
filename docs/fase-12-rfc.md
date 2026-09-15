# RFC — Fase 12: Onboarding self-service multi-clínica

## 0. Método, estado real y reconciliación de alcance

### 0.1 Reconciliación con `product-requirements.md` y `development-plan.md`

- [product-requirements.md](product-requirements.md) §4 excluye explícitamente
  del MVP "Multi-tenant / multi-clínica (se asume una única organización)".
- [development-plan.md](development-plan.md) "Fuera de las fases del MVP"
  exige un "nuevo ciclo de análisis de alcance" antes de planificar
  multi-tenant — este documento es ese ciclo, mismo patrón que
  [fase-6-rfc.md](fase-6-rfc.md) lo fue para IA real y que la Fase 5.3 lo
  fue para activar Deepgram: una ampliación explícita de alcance,
  formalizada por escrito antes de tocar código.
- **Confirmado por auditoría de código (2026-09-15)**: el modelo de datos
  YA es multi-tenant a nivel de esquema — decisión tomada explícitamente en
  la Fase 2 ("Multi-clínica desde el modelo, mono-clínica en el MVP",
  [data-model.md](data-model.md) §1) — pero existe **cero superficie de
  onboarding**: no hay `POST /clinics`, ni invitación de usuarios, ni
  registro público. La única vía de creación de `Clinic`/`User` hoy es
  `app/seed.py`, que se niega a ejecutarse si `ENVIRONMENT=production`.

### 0.2 Decisiones ya tomadas con Gerard (2026-09-15)

- **Onboarding público de autoservicio**: cualquiera puede registrarse,
  crear su clínica y quedar como su primer usuario admin, sin intervención
  manual de Gerard.
- **Facturación/suscripción (Stripe u otra) queda explícitamente FUERA de
  este ciclo** — las primeras clínicas se gestionan con acuerdo/factura
  manual mientras se valida el flujo de onboarding en sí.

## 1. Objetivos y no objetivos

### 1.1 Objetivos

- Permitir que una clínica nueva se dé de alta sin intervención de Gerard:
  formulario público → crea `Clinic` + primer `User` (rol `admin`) →
  verificación de email → login normal ya existente (`POST /auth/login`,
  sin cambios).
- Permitir que el admin de una clínica invite a más usuarios de su propia
  clínica (`audiologist`/`viewer`) sin tocar la base de datos ni el seed.
- Mantener intacto el aislamiento por `clinic_id` ya existente en el resto
  del sistema — este ciclo **no** toca `patients`/`clinical_sessions`/etc.,
  solo añade la puerta de entrada.

### 1.2 No objetivos (fuera de este ciclo)

- Facturación/suscripción de pago (Stripe) — decisión explícita, ver §0.2.
- Gestión avanzada de organización (múltiples sedes bajo una misma
  clínica, roles personalizados, SSO/SAML).
- Re-onboardear la clínica de producción actual de Gerard — sigue
  existiendo con los datos ya creados, no necesita pasar por este flujo.
- Panel de administración global (para Gerard) de todas las clínicas dadas
  de alta — deseable pero no bloqueante; candidato a un incremento
  posterior (ver §8).

## 2. Implicación legal — cambio de rol de Gerard (gestión suya, no solo técnica)

Esto es lo que más cambia respecto a todo lo ya resuelto en DPA/GDPR
([privacy-and-security.md](privacy-and-security.md) §9). Hasta hoy Gerard
es el **Controller** de sus propios pacientes, y Anthropic/OpenAI/
Deepgram/Railway/Cloudflare son sus **Processors** — esa cadena ya está
cubierta y firmada.

En cuanto una clínica externa se da de alta y sube datos de **sus**
pacientes, esa clínica pasa a ser la Controller de esos datos, y la
empresa de Gerard pasa a ser el **Processor** (con Anthropic/OpenAI/
Deepgram como sub-processors *de Gerard* frente a ese nuevo cliente). Antes
de que una clínica externa real firme (no antes de programar el
onboarding técnico), Gerard necesitará:

- **Su propio DPA** — plantilla que ofrecer a cada clínica cliente como
  Controller, listando a sus sub-processors (Anthropic, OpenAI, Deepgram,
  Railway, Cloudflare, y el proveedor de email transaccional que se elija
  en §5) — el mismo papel que Railway/Deepgram jugaron frente a él, ahora
  en el lado del Processor.
- **Términos de Servicio / Acuerdo de Cliente** que cubran la relación
  comercial (SLA, límites de responsabilidad, terminación) — hoy no
  existen.
- Revisar si debe registrarse como responsable/encargado del tratamiento
  ante la AEPD (o autoridad correspondiente) al pasar de "una sola
  organización" a "prestador de servicios para terceros".
- SCCs propias si algún cliente queda fuera de la UE/EEE (el objetivo
  declarado es vender en Europa, pero conviene dejarlo decidido por
  escrito).

Nada de esto bloquea programar el onboarding técnico de este RFC — sí
bloquea activarlo con una clínica externa real. Se documenta aquí porque
es exactamente el tipo de trámite (legal, no solo IA/GDPR) que se pidió
señalar aparte en cuanto apareciera.

## 3. Estado real confirmado (auditoría de código, 2026-09-15)

- `clinics`, `users`, `patients`, `clinical_sessions`, `audit_logs` — todos
  con `clinic_id`, índices compuestos y unicidad por clínica
  (`UNIQUE(clinic_id, internal_code)`, etc.) — ver
  [data-model.md](data-model.md) §1, §7, §9.
- `CurrentUser.clinic_id` ya viaja en cada request autenticada (JWT o
  `X-Dev-User-Id`) y toda query de negocio filtra por él —
  `core/current_user.py`, `core/deps.py`.
- Roles ya definidos con matriz de permisos centralizada por recurso
  (`core/authorization.py`): `ADMIN`/`AUDIOLOGIST`/`VIEWER` — reutilizable
  tal cual para el primer usuario de una clínica nueva (admin) y para las
  invitaciones (el admin decide el rol del invitado).
- `POST /auth/login` (Fase 9) es el único endpoint de autenticación —
  sin registro, sin recuperación de contraseña, sin invitación.
- `ClinicRepository.add()`/`UserRepository.add()` solo se usan desde
  `app/seed.py` (bloqueado en production) — cero superficie API para crear
  ninguno de los dos hoy.
- No existe tabla ni concepto de "invitación" en el esquema actual — es
  una entidad nueva a diseñar en este ciclo.
- Frontend: no auditado en detalle en este ciclo (alcance de esta revisión
  = backend); asumir que hoy solo existe pantalla de login, sin registro —
  a confirmar antes de planificar el roadmap de frontend (§7).

## 4. Flujo de usuario resultante

### 4.1 Alta de una clínica nueva (self-service)

1. Formulario público (`/signup` en frontend): nombre de la clínica,
   nombre y email del primer usuario, contraseña.
2. `POST /clinics/signup` (nuevo, sin autenticación previa, mismo patrón
   que `/auth/login`): crea `Clinic` (código generado automáticamente,
   único) + `User` con rol `admin`, `is_active=False` hasta verificar
   email.
3. Email de verificación (primer uso de envío de email transaccional en el
   proyecto — ver §5 sobre el proveedor a elegir).
4. Al verificar, `is_active=True` → login normal ya existente, sin
   cambios en `POST /auth/login`.

### 4.2 Invitar a un compañero de la misma clínica

1. Admin ya autenticado: `POST /clinics/{id}/invitations` con email + rol
   propuesto (`audiologist`/`viewer`; nunca `admin` desde este endpoint,
   para evitar escalada de privilegios — promover a un segundo admin es
   una acción aparte, ya cubierta por `authorize_*`).
2. Email de invitación con enlace de un solo uso y caducidad (p. ej. 7
   días).
3. `POST /invitations/{token}/accept` (sin autenticación previa): fija
   contraseña, crea `User` en esa `clinic_id` con el rol propuesto,
   `is_active=True`.

## 5. Arquitectura propuesta

- Nuevo módulo (`app/onboarding/`, o extender `app/clinics/` y
  `app/users/` con su propio `api/`) — a decidir en implementación, mismo
  criterio arquitectónico que el resto (`domain/infrastructure/api/
  service.py`).
- Nueva entidad `Invitation` (`id`, `clinic_id`, `email`, `role`,
  `token_hash`, `expires_at`, `accepted_at`, `created_by`).
- Generación del `code` de clínica: slug a partir del nombre + sufijo
  aleatorio si colisiona — nunca elegido libremente por el usuario, para
  evitar enumeración/typosquatting entre clínicas.
- **Proveedor de email transaccional: decidido el 2026-09-15 — Brevo**
  (antes Sendinblue). Comparado contra Resend y Postmark (ver tabla
  abajo); se elige Brevo por ser empresa europea con hosting de datos en
  Francia/Alemania — mejor discurso frente a clínicas clientes europeas,
  aunque los emails de este ciclo son de personal (nombre/email de quien
  se registra o es invitado), nunca datos de pacientes. DPA autoservicio
  (Anexo 2 de sus Términos de Servicio, se acepta junto con la cuenta,
  mismo patrón que Anthropic/OpenAI) — **acción pendiente cuando se
  implemente 12.1**: crear la cuenta de Brevo y confirmar/archivar el DPA
  igual que se hizo con Railway/Deepgram, luego añadir la entrada
  correspondiente en
  [privacy-and-security.md](privacy-and-security.md) §9.

  | Proveedor | Sede / hosting | DPA | Precio orientativo | Motivo de descarte |
  |---|---|---|---|---|
  | **Brevo (elegido)** | Francia — servidores UE (Francia/Alemania) | Autoservicio (Anexo 2 ToS) | ~$9/mes por 5.000 emails, plan gratis 300/día | — |
  | Resend | EE. UU., sin residencia UE (SCCs) | Autoservicio, se acepta al crear cuenta | Gratis hasta 3.000/mes, $20/mes por 50.000 | Mejor DX y precio, pero sin historia de residencia UE de cara a clientes |
  | Postmark | EE. UU. (AWS + Deft), sin residencia UE (SCCs) | Autoservicio desde dic. 2024 | $15-18/mes por 10.000 | Mejor entregabilidad transaccional pura, pero mismo punto débil que Resend en residencia UE |
  | Amazon SES | Multi-región, EU disponible (`eu-west-1`) | Automático, incorporado al AWS Customer Agreement | Desde $0,10/1.000 (el más barato a escala) | Descartado: exige más operación propia (verificación de dominio, salir de sandbox, gestión de bounces/quejas vía SNS) para un volumen bajo (solo verificación + invitaciones) — sobra complejidad para este incremento |
- Rate limiting propio en `/clinics/signup` y `/invitations/*/accept`
  (mismo patrón que `/auth/login`, 5/minute) — es superficie no
  autenticada, mismo riesgo de fuerza bruta/abuso.
- CAPTCHA o verificación equivalente en el formulario público de signup —
  a valorar; no bloqueante para un primer incremento con tráfico bajo.

## 6. Riesgos y mitigaciones

- **Abuso del signup público** (bots creando clínicas basura): mitigado
  por rate limiting + verificación de email obligatoria antes de activar;
  CAPTCHA como mitigación adicional si el abuso real lo justifica.
- **Emails desechables**: valorar lista de dominios bloqueados en el
  registro (no bloqueante para el primer incremento).
- **Enumeración de emails vía invitación** (¿existe ya esa cuenta?):
  responder siempre el mismo mensaje de éxito, igual que
  `AuthService.login` ya hace con `_INVALID_CREDENTIALS_MESSAGE` — mismo
  criterio de no revelar por canal lateral.
- **Clínicas fantasma sin verificar** acumulando basura en la base de
  datos: TTL de limpieza (p. ej. borrar clínicas `is_active=False` sin
  verificar tras N días) — mismo espíritu que `RetentionCleanupService`
  ya existente para audio.
- **Colisión de nombre/marca entre clínicas**: el `code` es interno y
  generado automáticamente (ver §5), el `name` no necesita ser único
  globalmente — sin conflicto legal esperado a este nivel.

## 7. Roadmap de implementación propuesto (hitos, nada implementado todavía)

- **12.0** — Alineación documental (este RFC, cerrado el 2026-09-15) +
  cuenta de Brevo creada y DPA confirmado/archivado.
- **12.1** — Dominio `Invitation` + `POST /clinics/signup` + verificación
  de email **+ recuperación de contraseña** ("olvidé mi contraseña",
  decidido el 2026-09-15: entra en este hito por compartir la misma
  infraestructura de email/token que la verificación, evitando que un
  admin bloqueado dependa de una intervención manual de Gerard en la
  base de datos).
- **12.2** — `POST /clinics/{id}/invitations` + `POST /invitations/
  {token}/accept`.
- **12.3** — Frontend: pantalla de signup, pantalla de aceptar invitación,
  pantalla de "olvidé mi contraseña", pantalla de gestión de usuarios de
  la clínica (vista admin).
- **12.4** — Rate limiting + anti-abuso + limpieza de clínicas no
  verificadas.

## 8. Cuestiones futuras, no bloqueantes (aplazadas explícitamente el 2026-09-15)

- Facturación/Stripe — explícitamente fuera de este ciclo (§0.2).
- Panel global de Gerard sobre todas las clínicas dadas de alta — no
  necesario mientras el número de clínicas piloto sea manejable a mano.
- Baja de una clínica / exportación-portabilidad de sus datos si deja de
  usar el servicio — relevante para el derecho de portabilidad del propio
  Controller-cliente frente a Gerard como Processor, pero gestionable de
  forma manual (los endpoints de exportación de `clinical_record` ya
  existen, acotados por clínica) mientras el volumen sea bajo.

## 9. Cierre de este RFC

**Cerrado el 2026-09-15.** Decisiones tomadas: (a) proveedor de email
transaccional = Brevo, DPA autoservicio pendiente de confirmar al crear
la cuenta (§5); (b) recuperación de contraseña entra en el primer
incremento (12.1), el resto de §8 queda aplazado. A partir de aquí puede
empezar a implementarse el hito 12.1 — ningún código de este ciclo se ha
escrito todavía, por diseño.
