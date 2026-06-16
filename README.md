# Donna

Agente personal con memoria y criterio, con la personalidad de Donna Paulsen (*Suits*).
No un tracker con bot encima: te conoce, recuerda, infiere y aconseja.

> Plan: [Plan_Donna_v5.md](Plan_Donna_v5.md) · Runbook: [Plan_Construccion_ClaudeCode_v2.md](Plan_Construccion_ClaudeCode_v2.md)

## Arquitectura (Fase 1)

Monolito simple, un proceso. El **núcleo** (carácter cacheado + memoria + inferencia +
brief/cierre + evals) es estable; los **módulos** se enchufan por la interfaz sin tocarlo.

```
Telegram (texto · voz · foto)
        │
        ▼
   main.py ──► brain.py  ── agentic loop, constitución CACHEADA (prompt caching),
        │                    presupuesto de contexto, compactación, registro de tools
        │                         │
        │                         ├─ memory.py   Supabase + contextual retrieval (Voyage)
        │                         ├─ agenda.py   agenda del día (Calendar)
        │                         └─ modules/    finanzas (fin_*) · salud (salud_*)
        │                                        señal destilada + Vision en contexto aislado
   scheduler.py  brief 8:00 / cierre 22:00 con resiliencia ante reinicios
   evals.py      set de comportamiento + deriva + selección de tool
```

## Estructura

```
config.py        memory.py     brain.py      evals.py
sheets.py        agenda.py     voice.py      scheduler.py     flows.py     main.py
prompts/         constitution.md  anchors.md          # el carácter (se sirve cacheado)
modules/         finanzas.py      salud.py            # tools fin_* / salud_*
evals/           casos.yaml                           # casos de evaluación (crecen por fase)
migrations/      001..005 .sql                        # 4 tablas + RLS
```

## Memoria (4 tablas)

`perfil` · `memoria` (texto + contexto + embedding) · `inferencias` · `compromisos`.
Contextual retrieval: cada nota se embebe con su etiqueta de contexto, así se recupera
la memoria *correcta*, no solo la parecida. Embeddings con **Voyage AI** (1024 dims).

## Setup

1. **Llaves** (Fase 0): `cp .env.example .env` y rellenar Telegram, Anthropic, Supabase
   (service_role), Voyage, OpenAI/Whisper, Google (service account + Sheet + Calendar).
2. **Dependencias**: `pip install -r requirements.txt`
3. **Base de datos**: correr en orden `migrations/001..005` en el SQL editor de Supabase.
   - Proyecto Supabase de Donna: `https://bmwbtrfgtttgbsanxnxi.supabase.co`
   - Con RLS (005), Donna **debe** usar la service_role key.
4. **Google**: descargar el JSON del service account → `credentials.json`; compartir el
   Sheet y el Calendar con el email del service account.
5. **Correr**: `python main.py`

## Evals

```bash
python evals.py     # ningún cambio se da por bueno hasta que pasan
```

## Deploy

Railway desde GitHub. `Procfile` → `web: python main.py`. Cargar todas las variables del
`.env` en el dashboard. Correr los evals contra producción al cerrar cada fase.

## Roadmap

Fase 1 (núcleo + Finanzas + Salud + evals) → +Proyectos → +Noomi → +Proactividad/Aprendizaje.
Cada módulo: contrato de módulo (no toca núcleo, tools con prefijo, señal destilada,
contexto aislado, degradación elegante) y agrega sus casos a los evals.
```
