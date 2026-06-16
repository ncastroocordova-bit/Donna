# Donna — Guía de construcción por fases v2 (para Claude Code)

**Alineada con el Plan Donna v5 (final).** Cambios respecto a la v1: se agrega la **capa de evals** como entregable de la Fase 1, **prompt caching** del carácter, **contextual retrieval** en la memoria, **tools con prefijo de módulo** sin solapamiento, **aislamiento de contexto** de los módulos pesados, **política de qué guardar** y **resiliencia** del brief/cierre.

**Cómo usar:** una fase a la vez. Cada paso trae (a) herramientas, (b) paso a paso, (c) prompt para pegarle a Claude Code, (d) "listo cuando". **Regla nueva v2: ninguna fase está lista hasta que sus evals pasan.**

**Base:** scaffold del skill `agent-builder` (Telegram + Claude + Sheets + Railway) + **Supabase (pgvector)** como cerebro de memoria. Monolito simple, un proceso, no sobreingenierizar.

---

## Stack (igual que v1, con dos matices)
| Herramienta | Para qué |
|---|---|
| Claude Code | El constructor |
| Python 3.11+ / GitHub / Railway | Lenguaje, repo, deploy |
| Telegram + BotFather | Canal de Donna |
| **Anthropic API** | Cerebro (`claude-sonnet-4-6`) + ops baratas (`claude-haiku-4-5`). **Usa prompt caching** para el prefijo estable (constitución+anclas) — sin setup extra, es un parámetro de la API |
| Google Cloud + Sheets | Datos de los módulos (Finanzas, Salud, Proyectos) |
| Supabase (pgvector) | Memoria de Donna |
| **Voyage AI** | Embeddings **con contextual retrieval** |
| Whisper (OpenAI) | Transcribir notas de voz |

---

## Estructura de archivos (objetivo Fase 1)
```
donna/
├── config.py
├── sheets.py
├── memory.py        # Supabase + contextual retrieval + política de guardado
├── brain.py         # agentic loop + constitución CACHEADA + presupuesto de contexto
├── evals.py         # NUEVO v2: set de comportamiento + deriva + selección de tool
├── voice.py         # Whisper
├── scheduler.py     # brief/cierre con resiliencia
├── modules/
│   ├── finanzas.py  # tools fin_*  (Vision en contexto aislado)
│   └── salud.py     # tools salud_*
├── flows.py
├── main.py
├── prompts/
│   ├── constitution.md
│   └── anchors.md
├── evals/
│   └── casos.yaml   # los casos de evaluación (se va llenando por fase)
├── requirements.txt
├── Procfile
└── .env.example
```

---

## FASE 0 — Setup de cuentas y llaves
**Pasos:** (1) Bot en @BotFather → `TELEGRAM_TOKEN`. (2) `ANTHROPIC_API_KEY` en platform.claude.com. (3) Google Cloud: service account + Sheets API + Drive API → `GOOGLE_CREDENTIALS_JSON`; crear workbook y compartirlo → `GOOGLE_SHEET_ID`. (4) Supabase: proyecto + `create extension vector;` → `SUPABASE_URL`, `SUPABASE_KEY`. (5) `VOYAGE_API_KEY` y `OPENAI_API_KEY` (Whisper). (6) Repo `donna` en GitHub. (7) Railway listo para deploy from GitHub.
**Listo cuando:** todas las llaves en un `.env` local (no subir a GitHub).

---

## FASE 1 — Núcleo + Finanzas + Salud + Evals (la primera Donna real)

### 1.1 — Repo + scaffold
**Pasos:** clonar el scaffold de `agent-builder` (config.py, sheets.py, flows.py, main.py, requirements, Procfile). Agregar a requirements: `supabase`, `voyageai`, `openai`, `pgvector`. Crear `prompts/` y `evals/`.
**Prompt Claude Code:** *"Arma el proyecto `donna` sobre el scaffold del skill agent-builder, con la estructura de archivos de esta guía. config.py con todas las variables del stack. Modelo cerebro claude-sonnet-4-6, barato claude-haiku-4-5. No reinventes el agentic loop ni la conexión a Sheets."*
**Listo cuando:** `/start` responde local.

### 1.2 — Memoria + contextual retrieval (`memory.py`)
**Pasos:** 4 tablas (`perfil`, `memoria` con columnas `texto`, `contexto`, `embedding vector`; `inferencias`; `compromisos`). En `guardar_memoria`: antes de embeber, anteponer una **etiqueta de contexto** (fecha, dominio, qué estaba pasando) al texto, y embeber esa versión contextualizada con Voyage. Aplicar **política de guardado**: solo guardar lo que pasa una barra de relevancia. `buscar_memoria(consulta, k=5)` por similitud (opcional: híbrido embedding + palabra clave). CRUD de inferencias y compromisos.
**Prompt Claude Code:** *"Crea memory.py con Supabase. Implementa contextual retrieval: cada nota se guarda con una etiqueta de contexto (fecha/dominio/situación) y se embebe esa versión combinada con Voyage. Agrega una política de guardado que descarte lo trivial. buscar_memoria top-k por similitud. Dame el SQL de las 4 tablas."*
**Listo cuando:** guardas dos notas parecidas pero de contextos distintos y `buscar_memoria` trae la correcta.

### 1.3 — Carácter + cerebro + prompt caching (`prompts/`, `brain.py`)
**Pasos:** escribir `constitution.md` (carácter, sección 2 del plan v5) y `anchors.md` (3–5 líneas oro). En `brain.py`: agentic loop con `claude-sonnet-4-6`; el system prompt = constitución + anclas, marcadas con **prompt caching** (`cache_control` en ese prefijo estable) para que se re-inyecten completas pero baratas. Armar contexto con **presupuesto**: prefijo cacheado + datos del día + top-k memorias relevantes. Implementar **compactación** del historial largo. Registrar las tools del núcleo.
**Prompt Claude Code:** *"Crea brain.py. System prompt = prompts/constitution.md + prompts/anchors.md, servido con prompt caching (cache_control) como prefijo estable, re-inyectado completo en cada llamada. Antes de responder, arma contexto: prefijo cacheado + datos del día + top-5 memorias de buscar_memoria. Compactación cuando el historial supere N tokens. Registra las tools del núcleo (buscar/guardar memoria, leer_agenda, inferencias, compromisos)."*
**Listo cuando:** Donna conversa con su voz, recuerda de una sesión previa, y el caching está activo (se ve en el uso de tokens).

### 1.4 — Set de evals base (`evals.py`, `evals/casos.yaml`)  ← NUEVO v2
**Pasos:** crear ~10 casos en `casos.yaml`: una nota de voz desahogándose, una pregunta de plata, marcar un hábito, una excusa para saltarse el gym, un "off the record", etc., cada uno con el comportamiento esperado. `evals.py` corre los casos contra el brain y reporta pasa/falla. Incluir el **test de deriva** (¿la voz sigue filosa y no genérica?) y dejar el hueco para **selección de tool** (se llena al agregar módulos).
**Prompt Claude Code:** *"Crea evals.py que lea evals/casos.yaml y corra cada caso contra brain.py, comparando con el comportamiento esperado (usando un Claude evaluador para los de criterio cualitativo como el sabor de la voz). Incluye el test de deriva. Dame 10 casos base en casos.yaml."*
**Listo cuando:** corres `python evals.py` y obtienes un reporte pasa/falla. **Desde aquí, cada cambio se valida con esto.**

### 1.5 — Módulo Finanzas (`modules/finanzas.py`)
**Pasos:** hojas CATEGORIAS, GASTOS, INGRESOS, TARJETAS (esquemas del skill agent-builder, variante finanzas). Tools con prefijo: `fin_registrar_gasto`, `fin_registrar_ingreso`, `fin_get_balance`, `fin_get_pagos_proximos`, `fin_procesar_imagen`. La **imagen (Vision) corre en una llamada con contexto aislado** y devuelve solo el dato extraído. `senal_finanzas()` devuelve la conclusión destilada para el brief. Flujo de botones para registrar gasto. **Agregar casos de Finanzas al set de evals.**
**Prompt Claude Code:** *"Crea modules/finanzas.py respetando el contrato de módulo: no toca el núcleo, tools con prefijo fin_, descripciones sin solapamiento. fin_procesar_imagen corre Vision en una llamada aislada y devuelve solo lo extraído. senal_finanzas() resume el estado para el brief. Usa los esquemas de Sheets del skill agent-builder. Agrega 3 casos de Finanzas a evals/casos.yaml."*
**Listo cuando:** registras un gasto por botón y por foto, Donna da el balance, **y los evals (incluido selección de tool) pasan.**

### 1.6 — Módulo Salud (`modules/salud.py`)
**Pasos:** hojas HABITOS, REGISTROS. Tools con prefijo: `salud_marcar_habito`, `salud_get_racha`, `salud_resumen_semana`. Botones de un toque para ejercicio/meditación/ayuno/sueño. `senal_salud()` con rachas y caídas. **Agregar casos de Salud al set de evals.**
**Prompt Claude Code:** *"Crea modules/salud.py, mismo contrato, tools con prefijo salud_. Botones de un toque para los 4 hábitos. senal_salud() resume rachas/caídas para brief y cierre. Agrega 2 casos de Salud a evals/casos.yaml."*
**Listo cuando:** marcas un hábito de un toque, Donna muestra la racha, **y los evals pasan.**

### 1.7 — Brief/Cierre con resiliencia (`scheduler.py`)
**Pasos:** JobQueue de PTB. `brief_matutino()` 8:00 = agenda (Calendar) + senal_finanzas + senal_salud + insight opcional. `cierre_nocturno()` 22:00 = cierre + máximo una inferencia para validar (botones). **Resiliencia:** al arrancar, chequear si el brief/cierre de hoy ya salió; si no, mandarlo. Zona horaria America/Santiago.
**Prompt Claude Code:** *"Crea scheduler.py con JobQueue: brief 8:00 y cierre 22:00 con señales destiladas. Al iniciar el proceso, chequear si el toque de hoy ya se envió y, si no, enviarlo (resiliencia ante reinicios de Railway)."*
**Listo cuando:** recibes brief y cierre a la hora, y si reinicias el proceso no se pierde el toque del día.

### 1.8 — Voz + Deploy Railway (`voice.py`, deploy)
**Pasos:** `voice.py` descarga la nota de voz, transcribe con Whisper, pasa el texto al brain. Subir a GitHub. Railway: deploy from GitHub, cargar TODAS las variables, `Procfile` = `web: python main.py`, revisar logs. **Correr los evals contra producción.**
**Prompt Claude Code:** *"Crea voice.py (Telegram voice → Whisper → brain), conéctalo en main.py, y dame el checklist de deploy en Railway con todas las variables. Deja un comando para correr los evals contra el bot deployado."*
**Listo cuando (Fase 1 completa):** Donna deployada; texto y voz; registra plata y hábitos; brief y cierre resilientes; recuerda entre sesiones; suena como Donna; **el set de evals completo pasa.**

---

## FASE 2 — Módulo Proyectos
`modules/proyectos.py`, contrato de módulo, tools `proy_*`. `proy_registrar_avance`, `proy_get_estado`, `proy_bloquear_tiempo` (Calendar). `senal_proyectos()` avisa semanas en cero y entregas. **Agregar casos de Proyectos a los evals.**
**Prompt Claude Code:** *"Crea modules/proyectos.py para tesis y proyectos, tools con prefijo proy_, contrato de módulo, senal_proyectos() para el brief. Agrega casos a evals/casos.yaml. No tocar núcleo ni otros módulos."*
**Listo cuando:** Donna avisa si la tesis lleva semanas detenida, sin tocar Finanzas/Salud, y los evals pasan.

## FASE 3 — Conexión Noomi
`modules/noomi.py`: solo lee una **señal destilada** del bot de Noomi (propuestas sin respuesta, follow-ups) y la entrega a Donna para el brief. Sin tocar la lógica de Noomi.
**Listo cuando:** Donna menciona un follow-up de Noomi pendiente.

## FASE 4 — Proactividad + Aprendizaje avanzado
`modules/proactividad.py` (mensaje espontáneo, máx 1/día, presupuesto de preguntas) y `modules/aprendizaje.py` (tablas `patrones` y `calibracion`, jobs de decay, aprendizaje en 3 niveles, guardia anti-patrones-falsos). La calibración **alimenta el eval de calibración** del plan v5.
**Listo cuando:** Donna calla las inferencias que suele errar, afina las que acierta, y rompe el silencio solo cuando vale la pena.

---

## Reglas que Claude Code debe respetar siempre
1. **Monolito simple, un proceso.**
2. **Contrato de módulo:** no toca el núcleo; interfaz; señal destilada; trabajo pesado en contexto aislado; degradación elegante; **tools con prefijo de módulo y sin solapamiento.**
3. **Presupuesto de contexto:** prefijo (constitución+anclas) **cacheado** y siempre; memoria just-in-time top-k con **contextual retrieval**; compactar lo largo.
4. **Política de memoria:** guardar solo lo relevante; "off the record" no se guarda.
5. **Evals primero:** ninguna fase está lista hasta que sus evals pasan; cada módulo agrega sus casos.
6. **Deploy + evals al final de cada fase** antes de seguir.

---

*v2 del runbook: cada fase deja algo deployado, medido por evals, y listo para que el siguiente módulo se enchufe sin romper nada.*
