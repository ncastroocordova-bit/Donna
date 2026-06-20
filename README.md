# Donna

Agente personal con memoria y criterio, con la personalidad de Donna Paulsen (*Suits*).
No un tracker con bot encima: te conoce, recuerda, infiere y aconseja. Eje de medición:
**salud · orden · productividad**.

> Plan: [Plan_Donna_v7.md](Plan_Donna_v7.md) · Runbook: [Plan_Construccion_v7.md](Plan_Construccion_v7.md)
> · Diccionario: [Guia_Ingreso_Datos_Donna.md](Guia_Ingreso_Datos_Donna.md)

## Qué trae v7

El delta de v7 sobre v6 es **el digest financiero nocturno** + el faro de deuda como freno:

- **Captura pasiva** durante el día (fotos de boleta vía Vision, correos pegados) → buffer, en
  contexto aislado, con `ID_Único` anti-duplicado. No escribe a la planilla todavía.
- **Cierre 22:00**: panel de toques (hábitos/ánimo/MIT) + MITs de mañana por voz + el **digest**
  pre-categorizado ("✅ Aceptar todo" o tap por línea) → recién ahí escribe a `Transacciones`.
- **Freno de deuda**: antes de cualquier compra en cuotas, Donna muestra el costo real (intereses
  muertos del mes) leído de la planilla.
- **Correo (Gmail + Outlook personal)**: lee avisos de gasto de **Banco de Chile, Mach, Copec Pay
  y MercadoPago** → al digest nocturno; y un **digest de spam diario** que borras con un toque (a
  papelera). Gmail vía API OAuth, Outlook vía Microsoft Graph. Degrada solo si no hay credenciales.

## Arquitectura (Fase 1)

Monolito simple, un proceso. El **núcleo** (`core/`) es estable; los **módulos** se enchufan por
la interfaz sin tocarlo (tools con prefijo, señal destilada, trabajo pesado aislado, degradación elegante).

```
Telegram (texto · voz · foto)
        │
        ▼
   main.py ──► core/brain.py ── agentic loop, constitución CACHEADA (prompt caching),
        │                        presupuesto de contexto, compactación, registro de tools
        │           ├─ core/memory.py   Supabase + contextual retrieval (Voyage) + buffer + jobs_log
        │           ├─ core/agenda.py   agenda del día (Calendar)
        │           ├─ core/sheets.py   dos planillas: Vida_v6 + Finanzas_vigente
        │           ├─ core/voice.py    Whisper (MITs por voz)
        │           ├─ core/correo.py   Gmail (API) + Outlook (Graph): gastos por mail + spam
        │           ├─ core/flows.py    paneles de toque + digest financiero + digest de spam
        │           └─ modules/         finanzas (fin_*) · salud (sal_*) · recordatorios (rec_*) · spam (spam_*)
        │                               + proyectos/tareas · tiempo · metas · proactividad · aprendizaje
   core/scheduler.py  brief 8:00 (read-only) / cierre 22:00 (panel + digest) con resiliencia (jobs_log)
   tests/evals.py     comportamiento + deriva + selección de tool (incluye freno y digest)
```

## Estructura

```
config.py        main.py        Procfile        requirements.txt        auth_email.py
core/            brain.py  memory.py  agenda.py  sheets.py  voice.py  scheduler.py  flows.py
                 correo.py  email_gmail.py  email_outlook.py            # gastos por mail + spam
modules/         finanzas.py  salud.py  recordatorios.py  spam.py  proyectos.py  tiempo.py  metas.py
                 proactividad.py  aprendizaje.py
prompts/         constitution.md  anchors.md  capacidades.md     # el carácter (se sirve cacheado)
tests/           evals.py  casos.yaml                            # casos de evaluación (crecen por fase)
migrations/      001..011 .sql                                   # 4 tablas + RLS + buffer/jobs_log/correos
setup_sheets.py  asegura los tabs de entrada en las dos planillas
```

## Memoria (Supabase)

`perfil` · `memoria` (texto + contexto + embedding) · `inferencias` · `compromisos`
+ `buffer_transacciones` (alimenta el digest) + `jobs_log` (resiliencia) + `correos_vistos`
(anti-reproceso de mail) + `calibracion`/`patrones`.
Contextual retrieval: cada nota se embebe con su etiqueta de contexto. Embeddings **Voyage AI** (1024 dims).

## Setup

1. **Llaves** (Fase 0): `cp .env.example .env` y rellenar Telegram, Anthropic, Supabase
   (service_role), Voyage, OpenAI/Whisper, Google. v7 usa **dos** Sheet IDs:
   `GOOGLE_SHEET_ID_VIDA` y `GOOGLE_SHEET_ID_FINANZAS` (comparte ambas con el service account).
2. **Dependencias**: `pip install -r requirements.txt`
3. **Base de datos**: correr en orden `migrations/001..011` en el SQL editor de Supabase.
   Con RLS, Donna **debe** usar la service_role key.
4. **Sheets**: `python setup_sheets.py` asegura los tabs de entrada. Las pestañas con fórmulas
   (Dashboard, Comparativo, 'Tarjetas de Crédito') ya existen y no se tocan.
5. **Correo** (opcional): rellena `GMAIL_CLIENT_ID/SECRET` y `OUTLOOK_CLIENT_ID` en `.env`, corre
   `python auth_email.py` y pega los `*_REFRESH_TOKEN` que imprime. Sin esto, Donna corre igual,
   solo sin gastos por mail ni digest de spam.
6. **Correr**: `python main.py`

## Evals

```bash
python -m tests.evals      # ningún paso se da por bueno hasta que pasan
python -m tests.evals --comparar   # Sonnet 4.6 vs Opus 4.8 (potencia + costo)
pytest tests/evals.py      # mismo set vía pytest (se salta sin API key)
```

## Deploy

Railway desde GitHub. `Procfile` → `worker: python main.py`. Cargar todas las variables del
`.env` en el dashboard. Ninguna fase está terminada hasta que sus evals pasan **y** está deployada.

## Roadmap (Plan v7 §9)

Fase 1 (núcleo + Salud + Finanzas con digest + Recordatorios + evals) → +Productividad → +Noomi
→ +Proactividad → +Aprendizaje avanzado. Cada módulo bajo el mismo contrato, con su paso y su eval.
