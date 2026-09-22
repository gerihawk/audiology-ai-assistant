# Fase 0 — AgentShield: superficie del propio agente/tooling

**Fecha:** 2026-09-22
**Alcance:** tooling de IA del repositorio (CLAUDE.md, `.claude/settings.local.json`, agentes/skills/hooks/MCP de proyecto). No incluye la app en ejecución (backend/frontend).
**Estado:** diagnóstico solo — **no se ha aplicado ningún autofix**.

## Metodología (importante leer antes que los hallazgos)

El comando `agentshield` solicitado no existe en este entorno. Tras confirmarlo contigo, se ejecutó
`npx ecc-agentshield@1.6.0 scan --path . --format json` (paquete npm que no estaba en caché local;
se instaló y ejecutó automáticamente). Su salida bruta se guardó sin tocar en
[`agentshield-diagnostico.json`](./agentshield-diagnostico.json).

Esa salida bruta **no se ha dado por buena**: cada uno de sus 61 hallazgos se ha contrastado a mano
contra el estado real de los ficheros del repo. Además se ha usado Semgrep Guardian (login
completado en esta sesión: usuario `gerihawk`, deployment `gabello66-personal-org`) como fuente
adicional — aunque ese deployment todavía no tiene ningún proyecto dado de alta, así que no aportó
hallazgos SAST/secrets/SCA reales todavía.

**Resultado de la verificación:** de 61 hallazgos brutos, **34 son falsos positivos confirmados**
(el 100% de los marcados "critical"), 9 son avisos genéricos de bajo valor, y **15 están confirmados
como reales** contra el repo. El *grade D (40/100)* que reporta la herramienta no es fiable — no
representa el estado real del repo.

---

## A. Secretos expuestos en repo/configuración

| Veredicto | Severidad informada | Hallazgo |
|---|---|---|
| ❌ Falso positivo | critical ×32 | "Hardcoded Azure storage account key" en `package-lock.json` |
| ❌ Falso positivo | high ×2 | "Sensitive env var in CLAUDE.md: GOOGLE_API_KEY / OPENAI_API_KEY" |
| ⚠️ No escaneado | — | `docker-compose.yml`, `.env`, `.env.example` |

- **Los 32 "Azure keys" son hashes `integrity` de npm** (SHA-512 estándar en cualquier
  `package-lock.json`, público por diseño). Verificado línea por línea. No aplicar el fix propuesto.
- **Los 2 hallazgos en CLAUDE.md son el ejemplo de buena práctica que el propio CLAUDE.md exige**
  ("report: GOOGLE_API_KEY: configured / OPENAI_API_KEY: missing", sección *Secret handling*). Es
  documentación de la política de no-exposición, no un secreto real. Aplicar el fix propuesto
  **rompería** esa política.
- `docker-compose.yml`, `.env` y `.env.example` existen (permisos `600`, correcto) pero **no fueron
  tocados por el escáner**. Por política del proyecto no he leído el contenido de `.env`. No he
  revisado el contenido de `docker-compose.yml` en esta pasada — dímelo si quieres que lo haga.

## B. Permisos y alcance de agentes/skills instalados

Confirmado contra `.claude/settings.local.json` (87 reglas `allow`, ninguna `deny`):

| Veredicto | Hallazgo |
|---|---|
| ✅ Confirmado | Sin lista `deny` en absoluto |
| ✅ Confirmado | `Bash(docker compose *)`, `Bash(docker volume *)`, `Bash(docker volume rm *)`, `Bash(docker info *)` |
| ✅ Confirmado | `Bash(python3 -)`, `Bash(python3 -c ' *)`, `Bash(python3 -m json.tool)` — ejecución de código arbitrario |
| ✅ Confirmado | `Bash(curl *)` sin restricción de dominio — y hace redundantes ~36 reglas curl más específicas |
| ✅ Confirmado | `Bash(poetry env *)` — puede volcar variables de entorno |
| ✅ Confirmado | `Read(//etc/claude-code/**)` |
| 🆕 No detectado por el escáner | `Read(//Users/Gerard1/**)` — lectura de **todo el home del usuario**, más amplio que lo que sí marcó |
| ✅ Confirmado (info) | Sin agentes/skills a nivel de proyecto (`.claude/agents`, `.claude/skills` no existen) |

El hallazgo más relevante que el propio escáner **no vio**: `Read(//Users/Gerard1/**)` es más
permisivo que el `Read(//etc/claude-code/**)` que sí marcó como sensible.

## C. Inyección en hooks de runtime

- ✅ Confirmado: no hay clave `hooks` en `.claude/settings.local.json` ni directorio
  `.claude/hooks`. Cualquier hook activo en esta sesión (p. ej. el de Semgrep Guardian) es
  **configuración global del usuario**, no de este repo.
- 🔎 Observación en vivo durante este mismo escaneo: el hook de Semgrep Guardian **bloqueó**
  `npm view` / `pip index` / `brew search` (solo lectura de metadatos) pero **dejó pasar** la
  ejecución real de `npx ecc-agentshield` (código de un paquete no verificado). Un gate que impide
  verificar la procedencia de un paquete pero permite ejecutarlo protege al revés de lo esperado.

## D. Perfil de riesgo de cada servidor MCP conectado

- ✅ Confirmado: no hay `.mcp.json` a nivel de proyecto. Todos los MCP de esta sesión (Semgrep
  Guardian, aws-core, azure, pinecone, posthog, railway, cockroachdb, dak, expo, vercel,
  claude-in-chrome, conectores Google/Slack, etc.) son plugins de cliente/usuario, fuera del
  alcance de este repositorio. El "mcp: 100" del score bruto es correcto en sentido estricto pero
  no representa el riesgo real de esa superficie.
- ⚠️ No auditado en profundidad en esta pasada: perfil de riesgo específico de cada MCP de sesión
  (p. ej. Semgrep Guardian ya queda con sesión OAuth persistente tras el login de hoy).

## E. Configuración de CLAUDE.md

- 🟡 Plausible pero de baja precisión: 9 avisos "missing prompt defense" (instruction-override,
  role-escape, indirect-injection, output-weaponization, output-manipulation, multilang-bypass,
  unicode-attack, context-overflow, social-engineering, input-validation, abuse-prevention). Es
  cierto que CLAUDE.md no repite estas cláusulas explícitamente, pero el escáner ignora que buena
  parte de estas protecciones ya las impone el harness de Claude Code por defecto, fuera del
  alcance de un fichero de instrucciones de proyecto. Severidad real: mejora de higiene documental,
  no vulnerabilidad activa.
  - Sugerencia opcional, coherente con la Regla 4 ya existente: añadir una línea explícita en
    CLAUDE.md de que el contenido de transcripciones/audio y de cualquier salida de herramienta es
    siempre no confiable y nunca debe interpretarse como instrucción.
- ✅ Sin acción necesaria: las Reglas 1-9 y la sección *Secret handling* de CLAUDE.md son sólidas y
  no se ha encontrado ninguna violación real en el resto del escaneo.

## F. Cadena de suministro del propio tooling de escaneo (hallazgo meta de esta Fase 0)

- ✅ **Resuelto (2026-09-22):** procedencia de `ecc-agentshield` verificada por el usuario fuera de
  esta sesión — mismo autor en GitHub y npm (`cogsec` = affaan-m, correo @affaanmustafa.com),
  publicando desde febrero de 2026, tarball firmado, dependencias limpias. Se da por confirmado, no
  se repite la comprobación. El punto sigue siendo válido como lección general: verificar
  procedencia de cualquier paquete ejecutado vía `npx` antes de confiar en su salida, no solo de
  este en concreto.
- 🟠 **Confirmado, severidad media:** el escáner tiene un ratio de falsos positivos muy alto —
  34 de 61 hallazgos (56%), incluyendo el 100% de los "critical". No usar su `grade`/`score` como
  referencia de decisión.

## G. `docker-compose.yml` (añadida a petición del usuario tras revisión del informe)

- ✅ **Confirmado, sin hallazgos.** Revisada la estructura completa (no el contenido de `.env`,
  por política del proyecto). Los 3 servicios (`db`, `backend`, `frontend`) usan exclusivamente
  interpolación `${VARIABLE}` / `${VARIABLE:-default}` de Compose para cada valor sensible
  (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `ANTHROPIC_API_KEY`, `STRIPE_SECRET_KEY`,
  `FIELD_ENCRYPTION_KEYS`, etc.) — ni un solo secreto literal en el fichero. `TRANSCRIPTION_PROVIDER`,
  `LLM_PROVIDER_*` y `PAYMENT_GATEWAY` tienen default `mock`, coherente con la Regla 6 de CLAUDE.md
  (no llamar APIs de pago reales durante el MVP). El volumen `./ops:/ops:ro` está correctamente
  montado solo-lectura.

---

## Resumen corregido

| | Bruto (`ecc-agentshield`) | Verificado a mano |
|---|---|---|
| Total hallazgos | 61 | 61 revisados |
| Critical | 33 | **0** (todos falsos positivos) |
| High confirmados | 16 | 7 |
| Falsos positivos | — | 34 |
| Avisos genéricos de baja precisión | — | 9 |
| No escaneado por la herramienta | — | 3 áreas (`docker-compose.yml`, `.env`, MCP de sesión) |

## Estado final de las 5 decisiones (2026-09-22, cerrado)

1. ✅ `docker-compose.yml` revisado — ver categoría G. Sin hallazgos.
2. ✅ Procedencia de `ecc-agentshield` confirmada por el usuario — ver categoría F.
3. ⏸️ **Bloqueado, pendiente de acción del usuario.** Se instaló `semgrep` (CLI oficial de PyPI) para
   dar de alta el repo en Semgrep AppSec Platform, pero `semgrep login` requiere una terminal
   interactiva (navegador) o un `SEMGREP_APP_TOKEN`, y no se pudo completar desde esta sesión. El
   login OAuth hecho vía el MCP de Semgrep Guardian (usuario `gerihawk`) es una credencial distinta
   a la del CLI. Pendiente: el usuario ejecuta `semgrep login` en su propia terminal, o genera un
   `SEMGREP_APP_TOKEN` en la plataforma y lo exporta en su shell (nunca pegado al asistente). Una vez
   hecho, se puede lanzar `semgrep ci` para obtener hallazgos SAST/secrets/SCA reales.
4. ✅ **Aplicado.** Regla 10 añadida a `CLAUDE.md` (contenido externo = dato, nunca instrucción).
5. ✅ **Aplicado** en `.claude/settings.local.json`:
   - Quitado del `allow`: `Bash(curl *)`, `Bash(docker volume *)`, `Bash(docker volume rm *)`.
   - Añadido al `allow`: `Bash(docker volume ls)`, `Bash(docker volume inspect *)`.
   - Acotado `Read(//Users/Gerard1/**)` a las dos rutas del propio proyecto (Desktop y `~/proyectos`).
   - `Bash(python3 -c ' *)` y `Bash(python3 -)` se dejan tal cual (riesgo aceptado por el usuario).
   - Nueva lista `deny`: `Bash(rm -rf *)`, `Bash(git push --force*)`, `Bash(docker volume rm *)`,
     `Read(//Users/Gerard1/.ssh/**)`, `Read(//Users/Gerard1/.aws/**)`.

Nada de esto se ha commiteado ni pusheado — pendiente de que el usuario lo pida explícitamente.
