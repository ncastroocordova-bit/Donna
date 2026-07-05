# Ficha — Autodiagnóstico (solo diagnóstico) + Variedad de textos

**Fecha:** 2026-07-03 · **Para:** una sesión de Claude Code que lo ejecute después.
**Decisiones de Nico que fijan el alcance (no reabrir):**
- Donna **NO se arregla sola**. Ni parches de código, ni retry con LLM, ni deploy. Solo: detectar → diagnosticar → contárselo a Nico en su voz → dejar el incidente empaquetado para arreglarlo fácil con Claude Code.
- Costo **moderado**: lo determinista (validaciones, verificación de escrituras, watchdog) es gratis y va primero; el LLM (Haiku) solo diagnostica incidentes NUEVOS (dedup por firma).
- Los errores viven en **Supabase** (espina de aprendizaje), no en el repo.
- Prioridades de dolor: escrituras a Sheets > elección de tools > calidad conversacional.
- **Parte 2:** Donna recuerda los textos que ya emitió (saludos, brief, cierre) y varía — no más fórmulas repetidas.

**Prerequisito:** Fase 0 del roadmap cerrada (bugs activos de `Plan_Reparacion_Bugs_y_Datos.md`). No montar diagnóstico sobre tools que corrompen columnas: primero se arreglan, después se vigilan.

**Reglas de ejecución:** las mismas del plan de reparación (rama propia `feat/autodiagnostico`, commit por paso en español, `pytest tests/ -q` verde con los tests nuevos, invariantes de CLAUDE.md intactos).

---

# PARTE 1 — Autodiagnóstico

## 1.1 Datos: tabla `incidentes` (migración `migrations/012_incidentes.sql`)

```sql
create table if not exists incidentes (
  id          bigserial primary key,
  creado      timestamptz not null default now(),
  firma       text not null,            -- hash corto de (tool, tipo, causa_raiz_normalizada) para dedup
  tool        text not null,            -- 'rec_agregar', 'job_brief', 'sheets.append', '-'
  tipo        text not null,            -- ver taxonomía 1.2
  resumen     text not null,            -- 1 frase para humanos
  causa_probable text,                  -- lo escribe el diagnóstico Haiku
  prompt_reparacion text,               -- AUTOCONTENIDO: para pegar en Claude Code (ver 1.4)
  input_json  jsonb,                    -- input de la tool al fallar (sin datos off-record)
  error_texto text,                     -- excepción/diff de verificación, truncado a 2000 chars
  frecuencia  int not null default 1,   -- repeticiones de la misma firma
  ultimo_visto timestamptz not null default now(),
  estado      text not null default 'abierto',  -- abierto | cerrado
  cerrado_en  timestamptz
);
create unique index if not exists incidentes_firma_abierto
  on incidentes (firma) where estado = 'abierto';
```

Dedup: si llega un incidente con firma ya abierta → `frecuencia += 1`, `ultimo_visto = now()`, **sin** nueva llamada LLM. El diagnóstico Haiku corre solo la primera vez por firma (tope duro: 5 diagnósticos LLM/día; el resto se registra sin causa y se diagnostica al día siguiente).

## 1.2 Taxonomía de tipos (cerrada — no inventar más sobre la marcha)

| `tipo` | Detector | Ejemplo |
|---|---|---|
| `tool_excepcion` | wrapper de `_ejecutar_tool` | `tarea_completar` tira `ValueError: 'Descripcion' not in list` |
| `schema_sheets` | verificación de headers al boot | la hoja `Recordatorios` no tiene la columna que el código espera |
| `verificacion_escritura` | write-then-verify | se escribió una fila y al releerla los valores no calzan con lo enviado |
| `job_no_corrio` | watchdog del scheduler | son las 23:00 y `job_ya_corrio("brief")` es falso |
| `api_externa` | wrapper de Sheets/Gmail/Calendar/Supabase | 429/500 persistente tras los retries del SDK |
| `correccion_nico` | flujos existentes de corrección | Nico corrige una categoría en el digest / "eso no es así" en /perfil |

`correccion_nico` es **señal, no falla**: se registra con frecuencia (para detectar patrones "Donna siempre categoriza mal X") pero no genera prompt de reparación salvo que se repita ≥3 veces la misma firma.

## 1.3 Módulo nuevo `core/diagnostico.py` (interfaces exactas)

```python
TIPOS = ("tool_excepcion", "schema_sheets", "verificacion_escritura",
         "job_no_corrio", "api_externa", "correccion_nico")

def _firma(tool: str, tipo: str, error_texto: str) -> str:
    """hash sha1[:10] de tool + tipo + primera línea del error normalizada
    (sin números de fila/fecha/montos — regex \\d+ → '#') para que el mismo bug dedupe."""

async def registrar(tool: str, tipo: str, resumen: str, *,
                    input_json: dict | None = None, error_texto: str = "") -> dict:
    """Upsert por firma (dedup). Si es firma NUEVA → llama _diagnosticar() (Haiku) y
    guarda causa_probable + prompt_reparacion. Devuelve la fila (con id y frecuencia).
    DEGRADA ELEGANTE: si Supabase falla, loguea y devuelve un dict mínimo — el
    diagnóstico jamás puede tumbar la respuesta a Nico (contrato §4)."""

async def _diagnosticar(tool, tipo, resumen, input_json, error_texto) -> dict:
    """UNA llamada a settings.model_cheap con output_config.format (JSON schema estricto):
    {causa_probable: str, archivo_sospechoso: str, prompt_reparacion: str}.
    El system incluye el mapa del repo (módulos/prefijos) para que apunte a archivo:línea."""

def texto_para_nico(inc: dict, contexto_accion: str) -> str:
    """La respuesta EN CARÁCTER cuando algo falla (ver 1.5). Determinista, sin LLM."""

async def pendientes() -> list[dict]:      # abiertos, orden frecuencia desc
async def cerrar(incidente_id: int) -> bool
async def resumen_semanal() -> str          # para el domingo: "3 incidentes, el más repetido: ..."
```

## 1.4 El `prompt_reparacion` (el contrato con Claude Code)

Formato fijo, autocontenido, mismo estándar que `Plan_Reparacion_Bugs_y_Datos.md`:

```
## Incidente #<id> — <resumen>  (visto <frecuencia>x, último <fecha>)
**Tipo:** <tipo> · **Tool:** <tool> · **Archivo sospechoso:** <modules/x.py>
**Error:** <error_texto>
**Input que lo gatilló:** <input_json>
**Causa probable:** <causa_probable>
**Cómo reproducir:** <llamada de tool o job concreto>
**Definición de arreglado:** la tool responde sin excepción con este input +
test de regresión agregado en tests/ + pytest verde.
Contexto obligatorio: leer CLAUDE.md; el schema real de las hojas está en setup_sheets.py TABS.
```

**Puente al repo — `scripts/incidentes.py`** (CLI, usa las creds de `.env` como el resto del código):
- `python scripts/incidentes.py` → lista abiertos (id, resumen, frecuencia).
- `--prompt <id>` → imprime el `prompt_reparacion` para pegar/pipe a Claude Code.
- `--cerrar <id>` → marca cerrado (lo corre la sesión de Claude Code al terminar el fix).

Flujo completo: Donna registra → te avisa → tú (cuando quieras) abres Claude Code y le dices "arregla el incidente 12" → la sesión corre el script, lee el prompt, arregla, testea, cierra. **Donna nunca toca el código.**

## 1.5 Cómo responde Donna cuando algo se rompe (en carácter, sin LLM extra)

`texto_para_nico()` compone determinista:

> «No pude {acción} — {causa en una frase}. Ya lo dejé diagnosticado (#{id}{, va {N} veces}); cuando quieras lo arreglamos con Claude Code. Mientras tanto {alternativa o "sigo con el resto"}.»

Ejemplos del tono esperado (calibrar con `prompts/anchors.md`):
- «No pude anotar el recordatorio — la hoja tiene otras columnas de las que espero (#12). Anótalo tú por ahora, y ese bug ya está diagnosticado para Claude Code.»
- «El brief de hoy no salió a las 8 — me di cuenta sola y quedó registrado (#15). Aquí va ahora.»

Reglas: máx 1 mención del mismo incidente por día (si la firma ya se reportó hoy, la respuesta solo dice "es el mismo problema de esta mañana"); jamás stacktrace en el chat; el resumen técnico vive en Supabase.

## 1.6 Puntos de enganche (dónde se instala cada detector)

1. **`core/brain.py:_ejecutar_tool` (línea ~186)** — envolver la llamada al handler:
   `except Exception as e:` → `inc = await diagnostico.registrar(name, "tool_excepcion", ..., input_json=inp, error_texto=repr(e))` → devolver `texto_para_nico(inc, ...)` como tool_result (así el LLM del loop se lo transmite a Nico en contexto). Los handlers hoy tragan sus propias excepciones con mensajes genéricos ("No pude crear la tarea ahora") — **quitar esos try/except genéricos módulo por módulo** para que la excepción real suba al wrapper (empezar por recordatorios/proyectos/salud; commit por módulo).
2. **`core/sheets.py` — dos helpers nuevos:**
   - `async def verificar_headers(esperados: dict[str, list[str]]) -> list[str]`: compara headers reales vs esperados por hoja (reusar `_fila_headers`). Se corre en el arranque (`main.py`) con un dict `HOJAS_CRITICAS` declarado por cada módulo; cada mismatch → incidente `schema_sheets`. **Este detector habría atrapado los bugs de la auditoría el día uno.**
   - `async def append_row_verificado(hoja, valores, verificar_cols: list[int])`: append + releer la última fila + comparar las posiciones indicadas; mismatch → incidente `verificacion_escritura` (la escritura NO se revierte — solo se reporta; revertir sería auto-arreglo). Migrar a este helper las escrituras de finanzas/salud/recordatorios (una por commit).
3. **`core/scheduler.py` — watchdog:** job diario 23:15 que revisa `job_ya_corrio` para brief/cierre (+ spam si correo activo) → incidente `job_no_corrio` por cada uno que falte. Además `job_resumen_semanal` agrega `diagnostico.resumen_semanal()` al texto del domingo.
4. **Correcciones de Nico:** en el fix del digest (categoría corregida) y en /perfil ("eso no es así") ya hay handlers — agregar `registrar(tool, "correccion_nico", ...)` sin LLM.
5. **Tool nueva `diag_estado`** (registrada en el brain, prefijo `diag_`): «OBLIGATORIO cuando Nico pregunta qué se ha roto, qué errores has tenido o si estás funcionando bien» → lista `pendientes()` en 1 línea por incidente.

## 1.7 Tests (`tests/test_diagnostico.py`)

(a) misma excepción 2 veces → 1 fila, frecuencia 2, **1 sola** llamada al mock de Haiku; (b) excepción distinta → firma distinta; (c) Supabase caído → `registrar` no lanza y la tool devuelve texto igual; (d) `verificar_headers` con columna faltante → incidente `schema_sheets` con la hoja y columna en el resumen; (e) `append_row_verificado` con fila releída distinta → incidente con el diff; (f) watchdog con `job_ya_corrio=False` → incidente `job_no_corrio`; (g) `texto_para_nico` no contiene "Traceback" ni saltos de stacktrace; (h) mismo incidente reportado 2 veces el mismo día → segunda respuesta abreviada; (i) `scripts/incidentes.py --prompt` imprime el bloque con "Cómo reproducir".

---

# PARTE 2 — Memoria de textos: que Donna no se repita

**Problema:** los saludos e intros del brief/cierre los genera el LLM sin memoria de qué dijo ayer (cae en las mismas fórmulas), y varios textos son strings fijos hardcodeados (`scheduler.py:52` «¿Cuánto dormiste?», el pedido de MITs por voz, la pregunta de evento contextual, el peso del domingo).

## 2.1 Datos: tabla `textos_emitidos` (migración `migrations/013_textos_emitidos.sql`)

```sql
create table if not exists textos_emitidos (
  id bigserial primary key,
  touchpoint text not null,   -- 'brief_intro' | 'cierre_intro' | 'proactividad' | 'sueno_pregunta' | ...
  texto text not null,
  creado timestamptz not null default now()
);
```
Retención: al insertar, borrar los > últimos 15 por touchpoint (función en `core/memory.py`).

## 2.2 Textos generados por LLM (brief/cierre/proactividad) — costo cero extra

En `core/brain.py:generar()` agregar parámetro `touchpoint: str | None = None`:
1. Si viene, leer los últimos 5 textos de ese touchpoint y **anexar al prompt del usuario** (nunca al system — no romper el prefijo cacheado):
   > «Tus últimas {n} aperturas fueron: {lista}. No repitas esas fórmulas ni su estructura: cambia el arranque, el ángulo y el remate. Mismo carácter, otra letra.»
2. Tras generar, guardar el texto emitido en `textos_emitidos`.
3. Llamadas a actualizar: `scheduler._texto_brief()` → `touchpoint="brief_intro"`, `_texto_cierre()` → `"cierre_intro"`, `job_proactividad` → `"proactividad"`.

Son solo tokens de contexto extra (~100/llamada) + 2 queries a Supabase. Degrada elegante: si la lectura falla, genera sin la lista.

## 2.3 Textos fijos — módulo nuevo `core/frases.py` (determinista, gratis)

```python
POOLS = {
  "sueno_pregunta":  ["¿Cuánto dormiste?", "¿Y ese sueño? ¿7 horas o ni cerca?",
                      "Primero lo primero: ¿dormiste tus 7?", "¿Cómo amaneció el sueño hoy?"],
  "mits_voz":        [...4-6 variantes...],
  "evento_contextual":[...],
  "peso_domingo":    [...],
}
async def frase(key: str) -> str:
    """Elige del pool evitando las últimas 2 usadas (lee textos_emitidos), registra la elegida."""
```
Redactar los pools **en la voz de Donna** (revisar contra `prompts/anchors.md`; las variantes del eje sueño pueden dejar caer la línea madre a veces, no siempre). Reemplazar los strings fijos en `scheduler.py` líneas 52, 83, 87, 91 por `await frases.frase(...)`.

**Nota semántica:** los `callback_data` de los botones NO cambian (solo el texto de la pregunta varía) — cero impacto en `on_callback`.

## 2.4 Tests (`tests/test_frases.py` + casos en `test_salud.py` si toca)

(a) `frase()` nunca devuelve la misma variante 2 veces seguidas para el mismo key; (b) `generar(touchpoint=...)` incluye los textos previos en el prompt (mock del cliente Anthropic capturando `messages`) y NO en `system`; (c) el texto generado queda guardado; (d) Supabase caído → `frase()` devuelve una variante igual (fallback aleatorio) y `generar` funciona sin la lista; (e) retención: nunca más de 15 filas por touchpoint.

---

## Orden de ejecución y commits

1. `feat(diagnostico): tabla incidentes + core/diagnostico.py con dedup por firma` (1.1–1.3 + tests a/b/c)
2. `feat(diagnostico): wrapper de tools + destape de excepciones en recordatorios/proyectos/salud` (1.6.1)
3. `feat(diagnostico): verificar_headers al boot + append_row_verificado` (1.6.2 + tests d/e)
4. `feat(diagnostico): watchdog de jobs + resumen dominical + tool diag_estado` (1.6.3–1.6.5)
5. `feat(diagnostico): scripts/incidentes.py (puente a Claude Code)` (1.4 + test i)
6. `feat(variedad): textos_emitidos + generar(touchpoint) en brief/cierre/proactividad` (2.1–2.2)
7. `feat(variedad): core/frases.py y pools para los textos fijos del cierre/brief` (2.3)

Gate de salida: pytest verde · 1 incidente provocado a mano (romper un header en una copia de prueba) produce fila en Supabase + respuesta en carácter + prompt reparación imprimible · 3 días seguidos de brief con aperturas distintas.

## Qué queda explícitamente FUERA (decisión de Nico 2026-07-03)

- Retry con LLM, auto-corrección de escrituras, revertir filas, auto-parche de código, botón "lanzar arreglo", deploy automático. Si más adelante se quiere subir la ambición, esta ficha es la base — pero hoy: **Donna diagnostica y avisa; Claude Code arregla; Nico decide.**
