# CLAUDE.md — Donna (instrucciones de repo para Claude Code)

Lee esto al empezar cada sesión. Es el contrato del proyecto. Si algo que te piden choca con esto, párate y pregunta.

## Qué es Donna
Agente personal de Nico (chief-of-staff modelado en Donna Paulsen de *Suits*). Orquestador + subagentes. Dos touchpoints diarios: **brief 8:00 (solo lectura)** y **cierre 22:00 (panel de toques + digest)**; revisión los domingos. Interfaz: **Telegram** (toques > texto). Estado: **~80% construida** — extiendes, no reconstruyes.

## Stack
Python monolito · `python-telegram-bot` · Supabase + pgvector · Anthropic SDK (prompt caching) · Voyage (embeddings) · Whisper (voz) · Google Sheets API · Gmail API · Google Calendar · Railway. Modelos: cerebro `claude-sonnet-4-6`; tareas livianas `claude-haiku-4-5-20251001`.

## Mapa del repo
- `core/`: `brain` (carácter cacheado + inferencia validada), `memory` (Supabase), `sheets`, `scheduler` (brief/cierre), `voice` (Whisper), `agenda` (Calendar), `correo` + `email_gmail`, `flows`.
- `modules/` (un prefijo por módulo): `salud` (`sal_`), `finanzas` (`fin_`), `recordatorios` (`rec_`), `correo`/`spam` (`cor_`), productividad/reconciliación (`prod_`), `aprendizaje` (`apr_`), `proactividad`, `proyectos`. Dormidos: `tiempo`, `metas`.
- `migrations/` 001–011 · `prompts/` (constitution, anchors, capacidades) · `tests/` (evals.py, casos.yaml) · `setup_sheets.py`.

## Fuentes de verdad de datos
Un workbook **Donna** (ver `Donna_Canonico.xlsx`): hojas de vida (Diario, Tareas, Proyectos, Recordatorios, Reconciliacion, Semanal, Config) + finanzas (Transacciones, Categorias, Tarjetas y Deuda, Dashboard, Comparativo). Donna lee/escribe ahí; Nico casi no la toca. El esquema canónico lo fija `Donna_Canonico.xlsx`; `setup_sheets.py` debe calzar con él.

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
- **Extras:** Aprendizaje ON · Proactividad 12:00 (máx 1/día) ON · **Tiempo log OFF** (dormido) · **Outlook OFF**.
- **Finanzas:** deuda real **incluye la línea**. Faro: Deuda total real **$2.028.091**, Intereses muertos **$48.236/mes**.

## Reglas de trabajo
- No reconstruyas lo que ya calza (ver `Alineacion_Donna.md`). El trabajo pendiente son las **8 brechas** del `Plan_Construccion_v7.md`.
- Ningún paso está hecho hasta que **su eval pasa** y está **deployado**. Corre `pytest tests/evals.py`.
- Commit por paso. Mensajes en español, concretos.
- `.env` y `credentials.json` **nunca** al control de versiones.
- Costo: las llamadas LLM se reservan para el residuo (lo determinista —Gmail, reglas, lookup— va primero).

## Carácter (no se ablanda)
Cálida pero filosa, te lee como rayos X, se anticipa, no sumisa, memoria total. Marcas: "te conozco", "ya lo resolví", "no me vengas con eso". Eje #1: **el sueño**. Línea madre: *"a la cama a las 23:00, te conozco."* Detalle en `prompts/constitution.md` y `prompts/anchors.md`.
