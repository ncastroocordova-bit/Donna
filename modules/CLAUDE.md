# CLAUDE.md — Donna (instrucciones de repo para Claude Code)

Lee esto al empezar cada sesión. Es el contrato del proyecto. Si algo que te piden choca con esto, párate y pregunta.

## Qué es Donna
Agente personal de Nico (chief-of-staff modelado en Donna Paulsen de *Suits*). Orquestador + subagentes. Dos touchpoints diarios: **brief 8:00 (solo lectura)** y **cierre 22:00 (panel de toques + digest)**; revisión los domingos. Interfaz: **Telegram** (toques > texto). Estado: **~80% construida** — extiendes, no reconstruyes.

## Stack
Python monolito · `python-telegram-bot` · Supabase + pgvector · Anthropic SDK (prompt caching) · Voyage (embeddings) · Whisper (voz) · Google Sheets API · Gmail API · Google Calendar · Railway. Modelos: cerebro `claude-sonnet-4-6`; tareas livianas `claude-haiku-4-5-20251001`.

## Mapa del repo
- `core/`: `brain` (carácter cacheado + inferencia validada), `memory` (Supabase), `sheets`, `scheduler` (brief/cierre), `voice` (Whisper), `agenda` (Calendar), `correo` + `email_gmail`, `flows`.
- `modules/` (un prefijo por módulo): `salud` (`sal_`), `finanzas` (`fin_`), `compras` (`cmp_`), `recordatorios` (`rec_`), `correo`/`spam` (`cor_`), productividad/reconciliación (`prod_`), `aprendizaje` (`apr_`), `proactividad`, `familia` (`fam_`), `proyectos`, `archivista` (`arc_` — escribe en Córtex vía `cortex_core` vendorizado; ver `CLAUDE.md` raíz §Archivista). Dormidos: `tiempo` (`metas` puede despertar para las metas financieras de `fin_`).
- `migrations/` 001–011 · `prompts/` (constitution, anchors, capacidades) · `tests/` (evals.py, casos.yaml) · `setup_sheets.py`.

## Fuentes de verdad de datos
**Dos sombreros, dos planillas (canon v8):** **Donna (vida)** `GOOGLE_SHEET_ID` — Diario, Tareas, Proyectos, Recordatorios, Reconciliacion, Semanal, Compras, Ideas, ⚙️ Config; **Louis (plata)** `GOOGLE_SHEET_ID_LOUIS` — Transacciones, Categorias, Tarjetas y Deuda, Dashboard, Comparativo, Metas, Compras_Detalle, Deuda_Mensual. Donna lee/escribe ahí; Nico casi no las toca. **Fuente de verdad del esquema:** la planilla real en el Drive de Nico + `setup_sheets.py` (`TABS_DONNA`/`TABS_LOUIS`) en código. *(El `Donna_Canonico.xlsx` se retiró del repo el 2026-07-17.)* Ver [`docs/Sombreros_Donna_Louis.md`](../docs/Sombreros_Donna_Louis.md).

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
- **Finanzas:** deuda real **incluye la línea**. Faro: Deuda total real **$2.028.091**, Intereses muertos **$48.236/mes**. **v2:** intención del gasto (Necesario/Inversión/Deseo en `Transacciones`, se confirma en el digest) + metas financieras con progreso (tab `Metas`, sin input diario). **No** se agregan cuentas con saldos auto / doble-entrada (rompe "registro sin fricción").
- **Captura de compras (Finanzas v3, alimenta a Compras):** la boleta se lee **ítem por ítem** (foto → ítem+precio+total) y va a `Compras_Detalle`. **Foto y correo del mismo gasto se correlacionan por monto+fecha(+comercio) → una sola transacción, jamás doble conteo** (el correo es el total canónico; la foto aporta los ítems). Para **comercios "de compras"** (súper, almacén, San Valentín) sin detalle, Donna pregunta **al momento** "¿qué compraste?" → foto o desglose por categoría ("2000 chanchería, resto pan", el resto cuadra al total); es prompt **transaccional**, no cuenta contra el tope 1/día. Cada línea se marca `Predecible` (sí = despensa/reposición; no = perecible/cotidiano) y **solo `Predecible=sí` alimenta el predictor de Compras Fase 2**.

## Reglas de trabajo
- No reconstruyas lo que ya calza (ver `Alineacion_Donna.md`). El trabajo pendiente son las brechas del `Plan_Construccion_v7.md` (las 8 originales E0–E7 + las fases añadidas: Salud-v2, Compras, Familia, Finanzas-v2).
- Ningún paso está hecho hasta que **su eval pasa** y está **deployado**. Corre `pytest tests/evals.py`.
- Commit por paso. Mensajes en español, concretos.
- `.env` y `credentials.json` **nunca** al control de versiones.
- Costo: las llamadas LLM se reservan para el residuo (lo determinista —Gmail, reglas, lookup— va primero).

## Carácter (no se ablanda)
Cálida pero filosa, te lee como rayos X, se anticipa, no sumisa, memoria total. Marcas: "te conozco", "ya lo resolví", "no me vengas con eso". Eje #1: **el sueño**. Línea madre: *"a la cama a las 23:00, te conozco."* Detalle en `prompts/constitution.md` y `prompts/anchors.md`.
