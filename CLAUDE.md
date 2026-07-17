# CLAUDE.md — Donna (instrucciones de repo para Claude Code)

Lee esto al empezar cada sesión. Es el contrato del proyecto. Si algo que te piden choca con esto, párate y pregunta.

## Qué es Donna
Agente personal de Nico (chief-of-staff modelado en Donna Paulsen de *Suits*). Orquestador + subagentes. Dos touchpoints diarios: **brief 8:00 (solo lectura)** y **cierre 22:00 (panel de toques + digest)**; revisión los domingos. Interfaz: **Telegram** (toques > texto). Estado: **~80% construida** — extiendes, no reconstruyes.

## Stack
Python monolito · `python-telegram-bot` · Supabase + pgvector · Anthropic SDK (prompt caching) · Voyage (embeddings) · Whisper (voz) · Google Sheets API · Gmail API · Google Calendar · Railway. Modelos: cerebro `claude-sonnet-4-6`; tareas livianas `claude-haiku-4-5-20251001`.

## Mapa del repo
- `core/`: `brain` (carácter cacheado + inferencia validada), `memory` (Supabase), `sheets`, `scheduler` (brief/cierre), `voice` (Whisper), `agenda` (Calendar), `correo` + `email_gmail`, `flows`.
- `modules/` (un prefijo por módulo): `salud` (`sal_`), `finanzas` (`fin_`), `compras` (`cmp_`), `recordatorios` (`rec_`), `correo`/`spam` (`cor_`), productividad/reconciliación (`prod_`), `aprendizaje` (`apr_`), `proactividad`, `familia` (`fam_`), `proyectos`, `archivista` (`arc_`, F3-lite — ver abajo). Dormidos: `tiempo` (`metas` puede despertar para las metas financieras de `fin_`).
- `migrations/` 001–011 · `prompts/` (constitution, anchors, capacidades) · `tests/` (evals.py, casos.yaml) · `setup_sheets.py`.

## Dos sombreros, dos planillas (canon v8)
Donna trabaja con **dos sombreros**, cada uno en su propia planilla de Google Sheets:
- **Sombrero Donna (vida)** — planilla `GOOGLE_SHEET_ID`: recordatorios, salud, familia, correo, productividad y compras. Hojas: Diario, Tareas, Proyectos, Recordatorios, Reconciliacion, Semanal, Compras, Ideas, ⚙️ Config.
- **Sombrero Louis (plata)** — planilla `GOOGLE_SHEET_ID_LOUIS`: finanzas + estados de cuenta. Hojas: Transacciones, Categorias, Tarjetas y Deuda, Dashboard, Comparativo, Metas, Compras_Detalle, Deuda_Mensual.

En el código: todo lo de vida usa el id por defecto (`sheets.vida_id()`); finanzas y estados de cuenta pasan **siempre** `sheets.fin_id()` (Louis). Si `GOOGLE_SHEET_ID_LOUIS` está vacío, `fin_id()` cae a la planilla Donna (modo single-workbook) — nada se rompe antes de migrar. `setup_sheets.py` asegura `TABS_DONNA` contra Donna y `TABS_LOUIS` contra Louis. **Cable cruzado a vigilar:** `Compras_Detalle` lo escribe Louis (finanzas) y lo leerá **Compras Fase 2** — esa lectura debe pasar `sheet_id=sheets.fin_id()` explícito (cruza de Donna a Louis).

## Dos capas de datos (NO las mezcles)
Ortogonal a los dos sombreros: cada planilla es "registros"; Supabase es "aprendizaje".
- **Google Sheets = los registros (lo que pasó y lo que Nico ve/edita).** Repartidos en las dos planillas de arriba (Donna + Louis). Estado y registros, legibles para Nico. **La fuente de verdad del esquema es doble:** la planilla real en el Drive de Nico (viva) y, en el código, `setup_sheets.py` (`TABS_DONNA`/`TABS_LOUIS`) — que debe calzar con ella. *(El viejo `Donna_Canonico.xlsx` se retiró del repo el 2026-07-17 por estar desactualizado.)*
- **Supabase = lo que Donna APRENDE de esos registros.** `perfil`, `memoria` episódica (+ embeddings Voyage/pgvector), `inferencias`, `compromisos`, `aprendizaje` (calibración, factor de optimismo, lookup de correcciones). No es legible para Nico ni reemplaza los registros.

**Flujo (una sola dirección para aprender):** registros en Sheets → Donna lee → infiere/calibra → **guarda el aprendizaje en Supabase** → aconseja usando esa memoria. Regla dura: el aprendizaje (patrones, ratios, inferencias) **se persiste en Supabase, nunca en el Sheet**. El Sheet puede mostrar un *resultado* (p. ej. `Factor_Optimismo` en `Semanal` es una lectura), pero el modelo que lo produce vive en Supabase. Y al revés: los registros crudos viven en Sheets, no en Supabase.

## Memoria viva — la espina (cruza todos los módulos)
Donna aprende de Nico cruzando dominios; la memoria NO es un módulo, es una espina. **Cada módulo, como parte de su definición de "completo", escribe a Supabase** sus inferencias y episodios. Cinco tipos: `perfil` (estable: quién es, frentes, pros/contras), `memoria` (episódica), `inferencias` (patrones, cada uno con su dato), `compromisos`, `aprendizaje` (calibración).
- **Correlador:** se enciende con ≥2 módulos vivos. Propone cruces entre dominios (sueño↔ánimo↔gasto↔tiempo), **valida cada uno contra el dato**, descarta los espurios (N chico, semana atípica → usa mediana) y guarda los que aguantan. Guardia anti-patrones-falsos: ante la duda, no afirma.
- **Vista editable `/perfil` ("lo que sé de ti"):** muestra perfil + inferencias top, cada una con su dato. Nico puede corregir ("eso no es así" baja/borra; "esto importa" fija); sus correcciones entran a la calibración.
- **Cómo se muestra:** bajo demanda + resumen suave los domingos + **proactivo solo cuando un patrón es accionable ahora** (máx 1/día, vive en el módulo Proactividad). Siempre con el dato; nunca etiqueta de carácter ("planificas de más", no "eres desordenado"); patrones revisables, no permanentes.

## Archivista (`arc_`, F3-lite — 2026-07-16)
Donna escribe en Córtex (el segundo cerebro de Nico) con `arc_guardar`, importando
`cortex_core` **vendorizado como copia** en `cortex_core/` (mismo patrón que sugiere
`cortex/README.md` §4: "Agrega cortex_core/ al proyecto — submódulo git o copia del
paquete"). Es la rebanada delgada de F3 del [[Roadmap-Holding]]: solo captura vía
Telegram. **NO incluye** la síntesis matinal en el brief ni el cron del loop nocturno
en Railway — eso sigue siendo F3 completo, semana 4.
- **Local:** `CORTEX_VAULT` apunta directo al vault en disco (probado end-to-end
  2026-07-16: escribe, hace pull/commit/push con el git ambiente de la máquina).
- **Railway:** el contenedor es efímero. `scripts/start.sh` clona el repo completo de
  Córtex (código + vault) al arrancar si `CORTEX_GITHUB_TOKEN` está seteado, y expone
  `CORTEX_VAULT` apuntando al clon. Variables Railway nuevas: `CORTEX_GITHUB_TOKEN`
  (PAT con scope `repo`), `CORTEX_AUTOR=donna`, `CORTEX_GIT_AUTO=1` (opcional:
  `CORTEX_LOCAL_PATH` si no quieres `/app/_cortex`). **Pendiente de que Nico las
  configure en Railway** — sin ellas, `arc_guardar` degrada solo (avisa, no rompe).
- Si `cortex_core` no importa o el vault no está disponible, el tool degrada
  (contrato de módulo #4): responde sin cortar la conversación, nunca truena a Donna.

## Contrato de módulo (no negociable)
1. Un módulo **nunca toca el núcleo**; habla solo por su interfaz.
2. Entrega **señal destilada** hacia arriba (una frase/estructura corta), no datos crudos.
3. El trabajo pesado corre **aislado** (contexto separado, p. ej. Vision/parseo por ítem).
4. **Degrada elegante:** si una herramienta falla (Sheets/Calendar/memoria), sigue sin ella.
5. Prefijo propio, **sin solapamiento** de tools entre módulos.

## Invariantes duros (jamás los rompas)
- **Correo: JAMÁS borra.** Spam → etiqueta `Donna/Archivado` + quita `INBOX`. Nada de `trash`/`delete`. Recuperable de un clic.
- **Sheets: nunca escribe sin OK de Nico.** Gastos (digest) y reconciliación se confirman con toque antes de persistir.
- **Inferencia validada:** nunca afirma un patrón sin mostrar el dato que lo respalda.
- **Privacidad:** "off the record" no se guarda; "olvida X" borra. Del correo solo mira lo justo (gasto + triage), no manda correos a terceros.
- **Memoria:** solo pasa la barra de relevancia; lo trivial no se guarda.

## Canon vigente (decisiones cerradas)
- Productividad **simple** (Tareas sueltas + Proyectos + Semanal de rachas). Sin log de tiempo diario.
- **Tiempo por frente** vía **reconciliación nocturna** (opción 1, con delta Menos/Igual/Más) en el cierre → alimenta el Semanal. **El brief no se toca.**
- **Factor de optimismo** sobre `aprendizaje`: aprende tu ratio plan-vs-real por frente y te frena al planificar de más (reference class forecasting). Calla hasta tener ≥2-3 semanas de datos.
- **Recordatorios: escalera** (domingo + T-2 + T-0 con ✅ Hecho; vencido → push propio diario). Estado pendiente/hecho/pospuesto; tipos mensual/anual/única; posponer exige fecha; tras 3 posposiciones, nombra el patrón.
- **Correo: triage 3 buckets** (spam→archivar, importante→resumen brief, financiero→digest) + correo dedicado financiero.
- **Salud (ampliada):** ventanas de ayuno + sueño (`Primera_Comida`/`Ultima_Comida`, `Hora_Dormi`/`Hora_Despertar`) → **resumen semanal de ventanas, solo medir** (sin meta hasta 2-3 semanas de baseline); peso se pregunta **cada cierre** (kg); **score % semanal de hábitos** en `Semanal` (ejercicio, meditación, sueño 7h+); **eventos contextuales** = pregunta en el cierre por lo que no controlaste → `memoria` con tag `evento_externo` (el correlador lo trata como contexto, no patrón). Nutrición (agua/proteína) se retiró del cierre — las columnas quedan como legado sin capturar.
- **Compras (`cmp_`, módulo nuevo, posición 3):** lista del súper por voz/texto ("Donna falta X" / "dame la lista"). **Fase 1 = lista manual**; **Fase 2 (diferida)** = motor de frecuencia que infiere reposición ("puede que toque comprar arroz") vía Proactividad. La Fase 2 aprende de dos fuentes: la lista Fase 1 (ítems `comprado`) + las líneas `Predecible=sí` de `Compras_Detalle`. **Predicción solo para despensa/reposición** (arroz, atún, fideos, limpieza); **nunca lo cotidiano/perecible** (pan, chanchería) — fuera del predictor por diseño.
- **Familia (`fam_`, módulo nuevo, último):** 3 toques en el cierre (Emilio / pareja / cena juntos) con inferencias y nudge propios; el correlador cruza familia↔ánimo↔sueño.
- **Extras:** Aprendizaje ON · Proactividad 12:00 (máx 1/día) ON · Salud ON · **Compras Fase 1 ON / Fase 2 diferida** · **Familia ON** (al final del roadmap) · **Tiempo log OFF** (dormido) · **Outlook OFF**.
- **Finanzas:** deuda real **incluye la línea**. Faro: Deuda total real ~**$2.297.966** (dato vivo de la planilla; Finanzas v4 corrigió el $2.028.091 histórico), Intereses muertos **$48.236/mes**. *(No hardcodear la cifra como assert de eval — es dato vivo; el eval verifica que el faro calce con `Tarjetas y Deuda` B4:B8.)* **v2:** intención del gasto (Necesario/Inversión/Deseo en `Transacciones`, se confirma en el digest) + metas financieras con progreso (tab `Metas`, sin input diario). **No** se agregan cuentas con saldos auto / doble-entrada (rompe "registro sin fricción").
- **Captura de compras (Finanzas v3, alimenta a Compras):** la boleta se lee **ítem por ítem** (foto → ítem+precio+total) y va a `Compras_Detalle`. **Foto y correo del mismo gasto se correlacionan por monto+fecha(+comercio) → una sola transacción, jamás doble conteo** (el correo es el total canónico; la foto aporta los ítems). Para **comercios "de compras"** (súper, almacén, San Valentín) sin detalle, Donna pregunta **al momento** "¿qué compraste?" → foto o desglose por categoría ("2000 chanchería, resto pan", el resto cuadra al total); es prompt **transaccional**, no cuenta contra el tope 1/día. Cada línea se marca `Predecible` (sí = despensa/reposición; no = perecible/cotidiano) y **solo `Predecible=sí` alimenta el predictor de Compras Fase 2**.

## Reglas de trabajo
- **Entrega modular: un módulo a la vez.** Completo + deployado + 7 días estable + evals verdes antes de empezar el siguiente. Orden y fichas en `Roadmap_Modular.md`. No construyes el módulo N+1 hasta que N pasa su semana.
- No reconstruyas lo que ya calza. El trabajo pendiente y el estado real por módulo viven en el tablero de `Roadmap_Modular.md`; el detalle de tools en `Spec_Herramientas_Nuevas.md`. (El marco histórico de "8 brechas E0–E12" y la auditoría original quedaron en `docs/archivo/` — `Plan_Construccion_v7.md` y `Alineacion_Donna.md` —, superados por el Roadmap.)
- Ningún paso está hecho hasta que **su eval pasa** y está **deployado**. Corre `pytest tests/evals.py`.
- Commit por paso. Mensajes en español, concretos.
- `.env` y `credentials.json` **nunca** al control de versiones.
- Costo: las llamadas LLM se reservan para el residuo (lo determinista —Gmail, reglas, lookup— va primero).

## Carácter (no se ablanda)
Cálida pero filosa, te lee como rayos X, se anticipa, no sumisa, memoria total. Marcas: "te conozco", "ya lo resolví", "no me vengas con eso". Eje #1: **el sueño**. Línea madre: *"a la cama a las 23:00, te conozco."* Detalle en `prompts/constitution.md` y `prompts/anchors.md`.
