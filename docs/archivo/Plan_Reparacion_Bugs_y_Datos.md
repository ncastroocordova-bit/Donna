# Plan de Reparación — bugs activos del agente + problemas de datos del Sheets

> ⚠️ **ARCHIVADO (histórico) — 2026-07-17. Ejecutado: Fase 0 completa.** Todos los ítems A1–A2, B1–B2 y
> C1–C6 se cerraron y deployaron (ver `Roadmap_Modular.md` §Fase 0). Se conserva por trazabilidad del
> razonamiento (2 opciones por ítem, output esperado). El estado real vive en el tablero del Roadmap;
> este doc ya no es trabajo pendiente.

**Fecha del diagnóstico:** 2026-07-01 (auditoría de código + planilla real de Drive).
**Para quién:** una sesión de Claude Code (u otra IA) que ejecute los fixes más tarde.
**Prerequisito del ejecutor:** leer `CLAUDE.md` completo antes de tocar nada. Este plan NO reemplaza el contrato del repo; lo aplica.

---

## Reglas de ejecución (aplican a todos los ítems)

1. **Invariantes duros vigentes** (de `CLAUDE.md`): Sheets nunca se escribe sin OK de Nico (los fixes de *código* no escriben nada por sí solos; los scripts de *limpieza de datos* corren en dry-run primero y piden confirmación); correo jamás borra; inferencias siempre con dato.
2. **Una rama por grupo:** `fix/recordatorios-schema`, `fix/proyectos-schema`, `fix/tools-legacy`, `fix/categorias`, `fix/cierre-fecha-ancla`. Commit por paso, mensajes en español, concretos.
3. **Ningún fix está hecho hasta que sus tests pasan**: `python -m pytest tests/ -q` debe quedar en verde (hoy: 91 passed). Cada fix agrega sus propios tests siguiendo el patrón de mocking de `tests/test_salud.py` (monkeypatch sobre `core.sheets.get_dicts` / `get_rows` / `append_row` / `set_cell` / `upsert_por_clave`).
4. **Headers reales = fuente de verdad.** El schema real de la planilla (verificado 2026-07-01 contra el workbook "Donna" en Drive, id `1jhOvZGo-hoGqMadywYqsk0cTMv9TYK8Z1h2UeUhxpy4`) ya está transcrito en `setup_sheets.py` TABS. Ante cualquier duda de nombre de columna, esa lista manda — no el docstring del módulo.
5. **Orden de ejecución sugerido:** A1 → A2 → B1 → B2 → C2 → C1 → C3 → C4 → C5 → C6. A1/A2 primero porque son corrupción activa; C6 al final porque requiere observar un cierre real.
6. Infraestructura disponible (no reinventar): `core/sheets.py` expone `get_dicts(hoja)` (dicts por header real, salta el banner de fila 1), `get_rows`, `append_row(hoja, valores)` (posicional desde columna A), `set_cell(hoja, fila_1based, col_0based, valor)`, `upsert_por_clave(hoja, clave_col, clave_val, set_col, valor)` (falla con "columna desconocida" si el header no existe — por eso los nombres deben ser EXACTOS, con tildes y espacios).

---

# PARTE A — Bugs activos del agente (corrupción de datos)

## A1. Recordatorios: el módulo lee/escribe un schema que no existe

**Causa raíz.** `modules/recordatorios.py` fue escrito contra un schema planeado ("Guía Parte B": `Dia_Fecha · Monto_Aprox · Aviso_Dias · Ultimo_Aviso`) que nunca se materializó. La hoja real tiene:

```
Recordatorio · Tipo · Día / Fecha · Monto aprox · Estado · Posposiciones · Última acción · Activo
```

Evidencia en código:
- `recordatorios.py:43` — `rec.get("Dia_Fecha")` → siempre `""` → `_dias_hasta()` devuelve `None` → `rec_proximos` filtra TODO → "no hay recordatorios" siempre.
- `recordatorios.py:87` — `rec.get("Aviso_Dias")` → columna inexistente.
- `recordatorios.py:96` — `upsert_por_clave(..., "Ultimo_Aviso", ...)` → devuelve "columna desconocida", nunca marca.
- `recordatorios.py:147-150` — `append_row` con **7 valores posicionales** `[rec, tipo, dia_fecha, monto, aviso_dias, "Sí", ""]` contra una hoja de **8 columnas con otro orden**: `aviso_dias` cae en `Estado`, `"Sí"` cae en `Posposiciones`, `Activo` queda vacío.

Consecuencia real ya observada: "Revisión técnica camioneta" venció el 2026-06-30 y Donna nunca avisó.

### Opción A (recomendada): adaptar el código al schema real

El schema real es MEJOR que el planeado: tiene `Estado`/`Posposiciones`/`Última acción`, que son exactamente lo que la escalera del canon necesita (pendiente/hecho/pospuesto, "tras 3 posposiciones nombra el patrón"). Adaptarse a él deja el terreno listo para construir la escalera después sin migrar nada.

**Instrucciones técnicas:**

1. En `modules/recordatorios.py`, agregar un dict de columnas (mismo patrón que `salud.COLS`):
   ```python
   COLS = {
       "recordatorio": "Recordatorio", "tipo": "Tipo", "dia_fecha": "Día / Fecha",
       "monto": "Monto aprox", "estado": "Estado", "posposiciones": "Posposiciones",
       "ultima_accion": "Última acción", "activo": "Activo",
   }
   ```
   Reemplazar TODOS los accesos a claves viejas por `COLS[...]`. Actualizar el docstring del módulo (líneas 3-10) al schema real.
2. `_dias_hasta()` (línea 39): leer `rec.get(COLS["dia_fecha"], "")`. Además soportar `Tipo = "Única"/"única"` (existe en los datos reales: la camioneta): parsear `YYYY-MM-DD` y devolver `(d - hoy).days` **sin** rollover de año — puede ser negativo (= vencido). Para `Anual`, mantener el rollover actual.
3. `proximos()` (línea 77): eliminar `Aviso_Dias` (no existe) — la ventana es solo el parámetro `dias`. Agregar dos filtros nuevos: saltar filas con `Estado` que empiece con "hecho" (case-insensitive), e **incluir** los vencidos (`falta < 0`) marcándolos con `r["_falta"] = falta` (negativo). `texto_proximos()` debe renderizarlos como `"X venció hace N días"`.
4. `texto_proximos()` (línea 115): `_num(r.get(COLS["monto"]))`.
5. `_marcar_avisado()` (línea 96): `upsert_por_clave(HOJA, COLS["recordatorio"], recordatorio, COLS["ultima_accion"], f"avisado {fecha}")`.
6. `_t_agregar()` (líneas 138-150): en el prompt del extractor LLM, eliminar `aviso_dias` y agregar `tipo: 'única' si es una fecha que no se repite`. El append pasa a **8 valores en el orden real**:
   ```python
   await sheets.append_row(HOJA, [
       d.get("recordatorio", texto), d.get("tipo", "mensual"), str(d.get("dia_fecha", "")),
       d.get("monto_aprox", 0) or "", "Pendiente", 0, "", "Sí",
   ])
   ```
7. **Tests nuevos** `tests/test_recordatorios.py` (mock de `sheets.get_dicts`/`append_row`/`upsert_por_clave` con los headers reales): (a) mensual día 1 con hoy=2026-07-01 → `_falta == 0` y aparece; (b) anual `2026-05-26` → rollover a 2027; (c) única `2026-06-30` con hoy=2026-07-01 → `_falta == -1` y el texto dice "venció"; (d) `Estado="Hecho"` → excluido; (e) `Activo="No"` → excluido; (f) `rec_agregar` llama `append_row` con exactamente 8 valores y `Estado=="Pendiente"`, `Activo=="Sí"` en las posiciones 4 y 7.
8. Commit sugerido: `fix(recordatorios): lee y escribe el schema real de la planilla (Día / Fecha, Estado, Posposiciones)`.

**Output esperado (Opción A):**
- `rec_proximos` devuelve los recordatorios reales: con los datos de hoy diría "Pago contadora hoy; Pago IVA hoy; Cumple mes pareja mañana; Revisión técnica camioneta venció hace 1 día".
- `rec_agregar` crea filas limpias con las 8 columnas correctas; `Estado`/`Posposiciones` dejan de corromperse.
- El brief vuelve a avisar pagos. Cero cambios en la planilla, cero migración.
- Queda pendiente (fuera de este fix, ficha del Módulo 4): escalera T-2/T-0/✅Hecho, posponer-con-fecha, patrón tras 3 posposiciones. El schema ya lo soporta.

### Opción B: migrar la planilla al schema del código

Renombrar en la hoja real `Día / Fecha`→`Dia_Fecha`, `Monto aprox`→`Monto_Aprox`, `Última acción`→`Ultimo_Aviso`, y agregar columna `Aviso_Dias`; actualizar `setup_sheets.py` TABS["Recordatorios"] y `Donna_Canonico.xlsx`.

**Instrucciones técnicas:** editar la fila de headers (fila 2) de la hoja `Recordatorios` vía `values().update`; agregar `Aviso_Dias` al final; poblar `Aviso_Dias=2` en las 9 filas; en el código solo arreglar el orden del append (el bug posicional existe igual: 7 valores, y con `Aviso_Dias` al final serían 9 columnas). Actualizar `setup_sheets.py:33` y regenerar `Donna_Canonico.xlsx`.

**Output esperado (Opción B):** el código lee bien, PERO: (1) se pierden `Estado`/`Posposiciones` o quedan huérfanas — la escalera del canon las necesita, así que en el Módulo 4 habría que **volver a migrar**; (2) `Donna_Canonico.xlsx` y `setup_sheets.py` divergen del workbook que Nico ya usa; (3) hay que tocar datos productivos a mano. Más trabajo total y contradice el canon. **No recomendada.**

---

## A2. Proyectos/Tareas: schema fantasma de IDs y fases

**Causa raíz.** `modules/proyectos.py` asume un schema legacy con `ID`/`ID_Proy`/`Fase`/`Num`/`Sem_Inicio`/`Sem_Fin`/`Prioridad`/`Descripcion` (sin tilde). Las hojas reales:

```
Proyectos: Proyecto · Estado · Foco actual · Próxima acción · % Avance · Última act. · Notas
Tareas:    Creada · Descripción · Proyecto · Tipo · Fecha objetivo · Estado · Completada · Notas
```

Evidencia:
- `proyectos.py:30` — busca columna `ID` en Proyectos (no existe).
- `proyectos.py:40` — `_avance()` filtra Tareas por `ID_Proy` (no existe) → compara `"" == ""` → **todos** los proyectos "poseen" **todas** las tareas → mismo avance falso para todos.
- `proyectos.py:121` — `t.get('Descripcion')` (sin tilde) → imprime `None`; `Prioridad` no existe.
- `proyectos.py:139-143` — `append_row` con **11 valores** contra 8 columnas reales → toda tarea creada por chat corrompe la fila.
- `proyectos.py:156` — `headers.index("Descripcion")` → `ValueError` → `tarea_completar` falla siempre.
- `proyectos.py:72-75` — `proy_crear` escribe 8 valores con orden legacy (ID primero) contra 7 columnas reales.

**Restricción de consistencia:** los MITs de Salud viven en la MISMA hoja `Tareas` y ya usan el schema real correctamente (`salud.py:135` appendea `[_hoy(), item, "—", "MIT", manana, "Pendiente", "", ""]`; `salud.py:145-149` define `COLS_TAREAS`; `salud.marcar_mit` marca `Completada="Sí"`). Cualquier fix debe quedar consistente con ese escritor.

### Opción A (recomendada): eliminar los IDs, operar por nombre sobre el schema real

Con 5 frentes fijos y tareas sueltas, un ID sintético no aporta nada; el nombre del proyecto ES la clave (así ya lo usa Salud con `Proyecto="—"`).

**Instrucciones técnicas:**

1. Definir en `proyectos.py` un dict `COLS_TAREAS` idéntico al de `salud.py:145-149` y uno `COLS_PROY` (`{"proyecto": "Proyecto", "estado": "Estado", "foco": "Foco actual", "proxima": "Próxima acción", "avance": "% Avance", "ultima": "Última act.", "notas": "Notas"}`). No importar desde `salud` (contrato de módulo: sin acoplamiento entre módulos); duplicar el literal con un comentario `# = salud.COLS_TAREAS, mismo canon`.
2. `_buscar_proyecto()` (línea 26): eliminar el match por `ID`; queda solo el match por substring sobre `Proyecto`.
3. `_avance(nombre_proy)` (línea 38): firma pasa a recibir el **nombre**; filtra `t.get("Proyecto","")` con igualdad case-insensitive contra el nombre. Excluir filas `Tipo == "MIT"` del conteo de avance de proyectos (los MITs de Salud usan `Proyecto="—"`, así que en la práctica no colisionan, pero el filtro explícito blinda el caso de un MIT asociado a proyecto en el futuro).
4. `_proy_listar()` (línea 47): `_avance(p.get("Proyecto",""))`; eliminar `Prioridad` del output (no existe); mostrar en su lugar `Foco actual`. Formato sugerido: `[Activo] Tesis — 2/5 tareas (40%) · foco: Pruebas de laboratorio`.
5. `_proy_crear()` (línea 64): eliminar la generación de ID. Append de **7 valores en el orden real**:
   ```python
   await sheets.append_row("Proyectos", [
       nombre, "Activo", inp.get("descripcion", ""), inp.get("proxima_accion", "(define tu próxima acción)"),
       "0%", _hoy(), inp.get("notas", ""),
   ])
   ```
   Actualizar el `input_schema` del tool: fuera `sem_estimadas`/`prioridad`, entra `proxima_accion` (opcional).
6. `_proy_actualizar()`/`_proy_cerrar()` (líneas 82-107): `upsert_por_clave("Proyectos", "Proyecto", p["Proyecto"], ...)`. Campos actualizables: `estado→Estado`, `foco→Foco actual`, `proxima_accion→Próxima acción`, `notas→Notas`. Eliminar `prioridad` (sin columna). Tras cualquier update, setear también `Última act.` = `_hoy()` (mismo `upsert_por_clave`).
7. `_tarea_listar()` (línea 112): claves `Descripción` (con tilde) y `Fecha objetivo`; filtro por proyecto vía columna `Proyecto` (eliminar `ID_Proy`). Formato: `[Pendiente] Tesis · Escribir capítulo 2 (para 2026-07-10)`. Considerar excluir `Tipo=MIT` del listado general o marcarlos `[MIT]` — decisión menor, sugerido: mostrarlos con etiqueta, no ocultarlos.
8. `_tarea_crear()` (línea 128): append de **8 valores en el orden real** (idéntico patrón a `salud.py:135`):
   ```python
   await sheets.append_row("Tareas", [
       _hoy(), desc, (p["Proyecto"] if p else (query or "—")), inp.get("tipo", "Tarea"),
       inp.get("fecha_objetivo", ""), "Pendiente", "", inp.get("notas", ""),
   ])
   ```
   `input_schema`: fuera `fase`/`prioridad`; entra `fecha_objetivo` (string YYYY-MM-DD, opcional).
9. `_tarea_completar()` (línea 150): `headers.index("Descripción")` (con tilde) — o mejor, replicar el patrón robusto de `salud._fila_mit` (`salud.py:197-216`) que arma `idx = {c: headers.index(v) ...}` desde el dict COLS y tolera filas cortas. Escribir `Estado="Completada"` **y** `Completada="Sí"` (mantiene compatibles los dos filtros existentes: el propio `_tarea_listar` y `salud.mits_pendientes`).
10. `senal_proyectos()` (línea 170): eliminar el filtro por `Prioridad` (no existe); alerta = proyecto `Activo` con `tot > 0 and h == 0`.
11. **Tests nuevos** `tests/test_proyectos.py`: (a) `_avance` con 2 proyectos y 3 tareas mezcladas cuenta solo las del proyecto pedido; (b) `_avance` ignora filas `Tipo=MIT`; (c) `tarea_listar` muestra el texto real de `Descripción` (regresión del "None"); (d) `tarea_crear` appendea exactamente 8 valores y `Estado=="Pendiente"` en posición 5; (e) `tarea_completar` sobre headers reales marca `Estado` y `Completada` en la fila correcta (mock de `get_rows`+`set_cell` registrando llamadas); (f) `proy_crear` appendea 7 valores.
12. Commit: `fix(proyectos): opera por nombre sobre el schema real de Proyectos/Tareas (sin IDs fantasma)`.

**Output esperado (Opción A):**
- `proy_listar` muestra avance **por proyecto** (hoy todos mostrarían "sin tareas", correcto: solo hay 1 tarea de ejemplo).
- `tarea_listar` muestra el texto real de cada tarea; `tarea_crear` produce filas idénticas en forma a las de los MITs de Salud; `tarea_completar` funciona por primera vez.
- Desaparece el riesgo cruzado sobre los MITs: ambos escritores de `Tareas` usan el mismo schema.
- La planilla no se toca.

### Opción B: agregar las columnas de ID a la planilla

Agregar `ID` a `Proyectos` e `ID_Proy`/`Fase`/`Num`/`Sem_Inicio`/`Sem_Fin`/`Prioridad` a `Tareas` (merge aditivo de `setup_sheets.py`: quedarían AL FINAL de cada hoja), poblar IDs retroactivos (P001..P005), y actualizar `Donna_Canonico.xlsx`.

**Instrucciones técnicas (resumen honesto):** además de la migración de datos, **igual hay que reescribir los appends** — `tarea_crear` escribe 11 valores posicionales desde la columna A asumiendo `ID_Proy` primero, pero el merge aditivo deja las columnas nuevas al FINAL; habría que pasar a escritura por nombre de columna. También hay que enseñar a los MITs de Salud a poblar (o tolerar) las columnas nuevas, y `Donna_Canonico.xlsx` + `setup_sheets.py` + la Guía divergen del diseño "productividad simple" del canon.

**Output esperado (Opción B):** IDs disponibles para futuras features (sub-referencias estables si algún día hay decenas de proyectos), a cambio de: migración manual de datos productivos, reescritura del módulo de todos modos, doble escritor (Salud) que tocar, y contradicción con el canon "productividad simple — Tareas sueltas + Proyectos". **No recomendada.**

---

# PARTE B — Hallazgos adicionales del agente

## B1. `metas.py` legacy registrado junto a `fin_metas` (colisión de tools)

**Causa raíz.** `core/brain.py:15,177,182` importa y registra `metas.TOOLS` (`metas_get_semana`/`metas_actualizar`), que operan sobre la hoja `MetasSemanales` — **no existe** en el workbook real. Conviven con `fin_metas`/`fin_aportar_meta` (hoja `Metas`, la vigente) con descripciones casi idénticas ("cuando Nico pregunta por sus metas..."). Riesgo: el LLM llama la equivocada; si llama `metas_actualizar`, `upsert_por_clave` sobre una hoja inexistente lanza excepción de la API de Sheets.

### Opción A (recomendada): desregistrar del brain, conservar el archivo dormido

**Instrucciones técnicas:**
1. En `core/brain.py`: quitar `metas` del import (línea 15), quitar `+ metas.TOOLS` de `ALL_TOOLS` (línea 177-178) y `**metas.HANDLERS` de `_HANDLERS` (línea 181-182).
2. `grep -rn "metas\." core/ main.py tests/` para confirmar que nada más lo usa (verificado hoy: `scheduler.py` NO lo importa; el único punto es `brain.py`; `senal_metas` no se llama desde el brief). Si algún test lo referencia, actualizarlo.
3. Agregar al docstring de `modules/metas.py`: `"""LEGACY — dormido. Hoja MetasSemanales no existe en el workbook Donna; las metas vigentes son fin_metas (modules/finanzas.py). No registrar en brain sin migrarlo."""`.
4. Commit: `fix(brain): desregistra metas legacy (MetasSemanales no existe; colisiona con fin_metas)`.

**Output esperado:** 2 tools menos en `ALL_TOOLS`; imposible que el LLM confunda `metas_*` con `fin_metas`; el archivo queda como referencia si algún día se quiere resucitar. Reversible en 3 líneas.

### Opción B: borrar `modules/metas.py` del repo

Mismo paso 1-2, más `git rm modules/metas.py`.

**Output esperado:** −115 LOC, repo más limpio, cero ambigüedad futura. A cambio se pierde el código de referencia (recuperable por git history). Válida si se decide que las metas semanales jamás vuelven en esa forma; el canon actual sugiere que su reemplazo real es `Semanal` + `fin_metas`, así que es defendible. Elegir B solo con OK explícito de Nico.

## B2. `tiempo.TOOLS` expuesto al LLM aunque el módulo está dormido (canon: Tiempo log OFF)

**Causa raíz.** `core/brain.py:177` registra `tiempo.TOOLS` (`tiempo_registrar`/`tiempo_resumen`) que escriben/leen la hoja `Tiempo` — **no existe** en el workbook. Config dice `Módulo Tiempo (log diario) = OFF`, pero nada lee ese flag: si Nico dice "trabajé 3 horas en la tesis", el LLM tiene un tool "OBLIGATORIO" que va a llamar y va a reventar contra la API (o peor, `append_row` a una hoja inexistente lanza error 400 y Donna responde "no pude").

### Opción A (recomendada): desregistrar igual que B1

**Instrucciones técnicas:** idéntico patrón a B1 (quitar de import/ALL_TOOLS/_HANDLERS en `brain.py`; docstring "DORMIDO por canon — Tiempo log OFF; el tiempo por frente vigente es la reconciliación nocturna"). Commit: `fix(brain): desregistra tiempo (dormido por canon, hoja Tiempo no existe)`.

**Output esperado:** el LLM ya no puede intentar registrar horas; "trabajé 3h en tesis" cae en conversación normal (y en el futuro, en la reconciliación nocturna del Módulo 6, que es el diseño canónico). Despertar el módulo = re-agregar 3 referencias + crear la hoja.

### Opción B: gate dinámico por Config (los flags de módulo se vuelven reales)

Hacer que `brain.py` construya `ALL_TOOLS`/`_HANDLERS` en función de flags leídos al arrancar.

**Instrucciones técnicas:** (1) en `config.py` agregar `modulos_off: set[str]` poblado al inicio desde la hoja `⚙️ Config` (leer con `sheets.get_dicts("⚙️ Config")`, filas `Parámetro` que empiecen con "Módulo" y `Valor == "OFF"`) con fallback a `{"tiempo"}` si Sheets no responde (degradación elegante); (2) en `brain.py`, registro declarativo `MODULOS = {"finanzas": finanzas, "salud": salud, ..., "tiempo": tiempo, "metas": metas}` y comprensión que arma `ALL_TOOLS` excluyendo los OFF; (3) cachear al boot (no leer Sheets por mensaje). Nota: `ALL_TOOLS` hoy es un literal a nivel de módulo; moverlo a una función `_construir_tools()` llamada en el arranque de `main.py`.

**Output esperado:** `⚙️ Config` deja de ser decorativo — apagar/prender módulos sin deploy (alineado con la cadencia del Roadmap: "el módulo en construcción es el único ON"). Costo: ~40 LOC en el núcleo + una lectura de Sheets al boot + tests del gate. Es la solución "bien hecha" pero toca el núcleo; si se elige, hacerla como paso propio con sus tests, no colada dentro de otro fix.

---

# PARTE C — Problemas de datos del Google Sheets

## C1. Categorías de `Transacciones` no calzan con la hoja `Categorias`

**Causa raíz (doble).** (1) El mapeador determinista `finanzas.py:236-251` (`_CATEGORIAS_KW`) cubre 6 categorías y su fallback es `"Otros"`, que **no existe** en `Categorias` (el cajón real es `"Otro Gasto"`). (2) El extractor LLM (`procesar_correo`) propone categoría libre sin validar contra la lista real. Resultado en los datos (22 transacciones jun-18→30): tres grafías de Chanchería (`Chanchería/Chancheria/chancheria`), y categorías huérfanas `Supermercado`, `Negocio`, `Cosas casa`, `Software`, `Otros`, `Transferencias`, `transferencia a mi mismo`. El Dashboard suma por categoría exacta → de $239.152 de gasto, ~$100k quedan fuera de todo presupuesto.

Las 18 categorías reales (verificadas): **Gasto:** Alimentación, Chanchería, Transporte, Salud, Hijo, Entretenimiento, Suscripciones, Ropa, Hogar, GGCC, Educación, Tecnología, Tarjeta Crédito, Otro Gasto. **Ingreso:** Freelance, Ayuda Familiar, Uber Eats, Clases.

### Opción A (recomendada): validar contra `Categorias` en el código + limpieza única de datos con OK

**Instrucciones técnicas — código (`modules/finanzas.py`):**
1. Cambiar el fallback de `_categoria_de()` (línea 251) de `"Otros"` a `"Otro Gasto"`. Revisar `_categoria_item()` (línea 320-324) que compara contra `"Otros"` — actualizar la comparación al nuevo fallback.
2. Nueva función de normalización + validación:
   ```python
   import unicodedata
   def _norm(s: str) -> str:
       s = unicodedata.normalize("NFD", str(s or ""))
       return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()

   _cache_categorias: dict | None = None  # {norm: nombre_canonico}
   async def _categorias_reales() -> dict:
       # lee la hoja Categorias 1 vez por proceso (refrescar en cada digest es aceptable);
       # degradación elegante: si Sheets falla, devuelve {} y no se valida (no bloquear el flujo).
   async def _validar_categoria(cat: str) -> tuple[str, bool]:
       """Devuelve (categoria_canonica, era_valida). 'chancheria' → ('Chanchería', True);
       'Cosas casa' → ('Otro Gasto', False)."""
   ```
3. Aplicar `_validar_categoria` en `normalizar_gasto` (zona de `finanzas.py:204-218`, donde ya se aplican reglas de comercio): si `era_valida is False`, forzar `dudosa=True` con `motivo_duda=f"¿'{cat_original}' → qué categoría real?"` — así el digest se lo pregunta a Nico con toque en vez de escribir silencioso (respeta "Sheets con OK").
4. Ampliar `_CATEGORIAS_KW` con lo aprendido de los datos reales (mínimo): `("Tecnología", ["anthropic", "openai", "github", "railway", "google one"])` — ojo: mover "openai"/"claude" desde Suscripciones o dejarlos donde Nico prefiera, marcar `dudosa` si ambiguo; `("Hogar", [..., "super ganga"])`; `("Alimentación", [..., "san vale", "sanva", "agroconcepcio"])`. Las reglas por comercio persistentes viven en Supabase (`_aplicar_reglas_comercio`, línea 180) — las correcciones de Nico en el digest ya las alimentan; no duplicar ahí.
5. **Tests**: en `tests/test_finanzas.py` agregar casos: `_validar_categoria("chancheria")` → `("Chanchería", True)` con mock de Categorias; `"Cosas casa"` → `("Otro Gasto", False)`; fallback del mapeador == `"Otro Gasto"`; Sheets caído → passthrough sin excepción.
6. Commit: `fix(finanzas): valida categorías contra la hoja Categorias; fallback Otro Gasto`.

**Instrucciones técnicas — limpieza de datos (script único `scripts/normalizar_categorias.py`):**
7. Leer `Transacciones` con `get_rows` (para conocer nº de fila) + `_fila_headers`. Tabla de mapeo propuesta (imprimirla y **pedir OK antes de escribir** — invariante):
   `Chancheria|chancheria → Chanchería` · `Supermercado → Alimentación` · `Negocio → Alimentación` · `Cosas casa → Hogar` · `Software → Tecnología` · `Otros → Otro Gasto` · `Transferencias|transferencia a mi mismo → (DECISIÓN DE NICO, ver abajo)`.
8. Modo `--dry-run` (default): imprime `fila N: 'X' → 'Y'` sin tocar nada. Modo `--aplicar`: `set_cell("Transacciones", n, idx_categoria, nuevo)` por fila afectada.
9. **Decisión que el script debe dejar planteada, no resolver:** las 2 transferencias a sí mismo ($8.000 + $5.000) hoy inflan "Gastos del mes". Opciones para Nico: crear categoría `Transferencias` en `Categorias` (fila nueva, Tipo=`Gasto`, presupuesto `-`) o recategorizarlas a `Otro Gasto`. El script acepta `--transferencias=crear|otro`.

**Output esperado (Opción A):** grafías unificadas; toda categoría escrita en adelante existe en `Categorias` o pasa por toque de Nico; el Dashboard por categoría vuelve a sumar ≈ el total del mes; el % de presupuesto usado se vuelve confiable.

### Opción B: ampliar `Categorias` para aceptar lo que ya se escribe

Agregar filas `Supermercado`, `Negocio`, `Cosas casa`, `Software`, `Transferencias`, `Otros` a la hoja `Categorias` (con presupuesto `-`), y en datos solo unificar las 3 grafías de Chanchería.

**Instrucciones técnicas:** 6 `append_row` a `Categorias` (con OK de Nico) + el mini-fix de grafías del paso 7-8 de la Opción A (solo Chanchería). Sin cambios de código obligatorios, aunque el fallback `"Otros"` pasaría a ser una categoría real (agregar la fila `Otros` la legitima).

**Output esperado (Opción B):** el Dashboard vuelve a cuadrar rápido y con mínimo esfuerzo, PERO el presupuesto queda fragmentado (Supermercado y Alimentación compiten por el mismo gasto real de $250.000; `Otros` y `Otro Gasto` coexisten como dos cajones), y el problema regenera: el extractor LLM seguirá inventando categorías nuevas que tampoco existirán. Parche, no fix. **No recomendada salvo como alivio temporal.**

## C2. `⚙️ Config`: `Mes activo = 6` (hoy es julio) — Dashboard/Comparativo miran el mes viejo

**Causa raíz.** `Mes activo`/`Año activo` filtran el Dashboard por fórmulas; los actualiza Nico a mano y nadie (ni código ni recordatorio) lo empuja.

### Opción A: arreglo manual hoy + recordatorio mensual (cero código)

**Instrucciones técnicas:** (1) Nico edita `⚙️ Config` → `Mes activo` = `7` (celda B de esa fila). (2) Tras el fix A1, crear un recordatorio real: fila en `Recordatorios` = `["Actualizar Mes activo del Dashboard", "Mensual", 1, "", "Pendiente", 0, "", "Sí"]` (puede crearse por chat con `rec_agregar` ya arreglado, o a mano).

**Output esperado:** el Dashboard muestra julio desde ya; cada día 1, el brief avisa "Actualizar Mes activo hoy". Sigue siendo un paso manual mensual (~10 segundos), con red de seguridad.

### Opción B (recomendada a mediano plazo): toque de confirmación automático el día 1

**Instrucciones técnicas:**
1. En `core/scheduler.py`, dentro de `job_brief` (línea 48), al inicio: si `datetime.now(settings.tz).day == 1`, leer `sheets.get_dicts("⚙️ Config")`, ubicar `Parámetro == "Mes activo"`; si `int(Valor) != mes_actual`, mandar mensaje con botón inline `InlineKeyboardButton("✅ Sí, actualiza", callback_data=f"cfg:mes:{mes_actual}")` (patrón de teclados en `core/flows.py:56-58`). En enero, incluir también `cfg:anio:{año}`.
2. En `core/flows.py` `on_callback` (línea 234), rama `tipo == "cfg"`: `await sheets.upsert_por_clave("⚙️ Config", "Parámetro", "Mes activo", "Valor", int(valor))` — los headers reales de Config son `Parámetro · Valor · Nota`, así que `upsert_por_clave` funciona directo. Responder "Dashboard apuntando a {mes}. Ya lo resolví."
3. **Invariante respetado:** la escritura ocurre solo tras el toque de Nico.
4. Test: mock de Config con `Mes activo=6` y fecha 1-jul → el brief incluye el botón; callback `cfg:mes:7` → `upsert_por_clave` llamado con `("⚙️ Config","Parámetro","Mes activo","Valor",7)`.
5. Commit: `feat(scheduler): toque de actualización de Mes activo el día 1`.

**Output esperado:** nunca más un Dashboard mirando el mes anterior; un toque el día 1 y listo. Costo: ~30 LOC + test.

## C3. El eje #1 no se mide: `Hora dormí`, `Hora desperté`, `Primera comida` vacías (12/12 días)

**Causa raíz.** La captura de esas horas existe solo por chat (`sal_registrar_sueno` con `hora_dormi` opcional — `salud.py:119-123` — y `sal_set_hora` para `CAMPOS_HORA`), pero ningún flujo las pregunta con toque. El brief pregunta solo el binario "¿Dormiste 7h+?" (`flows.py:56-58`). Evidencia de que el diseño no funciona: 12 días de datos, 0 horas capturadas. Sin esas columnas, el resumen semanal de ventanas (`salud.py:378`, job del domingo) va a escribir vacío para siempre.

### Opción A (recomendada): chips de hora en los flujos existentes

**Instrucciones técnicas:**
1. **Hora dormí + Hora desperté → en el brief** (es cuando Nico lo sabe). En `core/flows.py`, tras responder el botón de sueño (`sueno:si|no` en `on_callback`), encadenar dos teclados de chips:
   - `"¿A qué hora te dormiste?"` → chips `22:30 · 23:00 · 00:00 · 01:00 · 02:00` con `callback_data="sh:d:{hora}"`.
   - `"¿Y a qué hora despertaste?"` → chips `06:30 · 07:00 · 07:30 · 08:00 · 09:00` con `callback_data="sh:w:{hora}"`.
   Patrón de chips ya existente: `CHIPS_COMIDA` (`flows.py:43-44`). Handler: `sh:d` → `salud.registrar_sueno("", hora)` o directamente `salud._set("hora_dormi", hora)` vía una función pública nueva `salud.registrar_hora("hora_dormi", hora)` — **ya existe** (`tests/test_salud.py:184` la usa); `sh:w` → `salud.registrar_hora("hora_despertar", hora)`. Semántica de fila: se escribe en la fila de HOY (la mañana), consistente con cómo ya se registra `Sueño 7h+`.
2. **Primera comida → en el cierre.** En `teclado_cierre` (`flows.py:35-45`), agregar una fila de chips `🍳 Primera comida: 08:00 · 09:00 · 10:00 · 12:00` con `callback_data="pc:{h}"` → `salud.registrar_hora("primera_comida", h)`. (La última comida ya tiene chips.)
3. Mantener los chips como *atajo*, no obligación: si Nico no toca, queda vacío (igual que hoy); el dato fino sigue entrando por chat/voz si él dice "me dormí 1:40".
4. Tests: los callbacks nuevos rutean al campo correcto de `salud.COLS`; el teclado del brief encadena tras `sueno:*`.
5. Commit: `feat(salud): chips de hora dormí/desperté en el brief y primera comida en el cierre (ventanas E8)`.

**Output esperado:** desde el primer día deployado, las 3 columnas se llenan con un toque cada una; en 2-3 semanas hay baseline real y el resumen de ventanas del domingo deja de salir vacío — que es la condición del canon para recién proponer una ventana objetivo. El eje #1 (sueño) pasa de un binario a hora real.

### Opción B: sin código nuevo — reforzar el prompt de los touchpoints

**Instrucciones técnicas:** en `scheduler.py` cambiar el segundo mensaje del brief (línea 52) a `"¿Cuánto dormiste? Y dime a qué hora te dormiste y despertaste (ej: 'me dormí 00:30, desperté 7:15')"` — el LLM ya tiene los tools (`sal_registrar_sueno`, `sal_set_hora`) para persistir la respuesta en texto libre. Análogo en el texto del cierre para primera comida.

**Output esperado:** cero código estructural (solo strings), PERO exige que Nico escriba/dicte cada mañana. La evidencia de 12 días vacíos con los tools ya disponibles sugiere que va a seguir vacío — la interfaz del proyecto es "toques > texto" por diseño. Aceptable solo como paso intermedio si no hay tiempo para la Opción A.

## C4. Recordatorio vencido sin gestionar: "Revisión técnica camioneta" (venció 2026-06-30)

**Causa raíz.** Consecuencia directa del bug A1 — Donna nunca avisó. Además el canon exige "vencido → push propio diario", que no está construido.

### Opción A (recomendada): se resuelve con A1 + un paso del canon (vencido-insiste)

**Instrucciones técnicas:** con A1-Opción-A los vencidos ya salen en `rec_proximos` (paso 3). Agregar el push: en `scheduler.job_brief`, si `texto_proximos` contiene vencidos, incluirlos SIEMPRE (no marcar `Última acción` para vencidos → insiste a diario hasta que cambie `Estado`). Botón `✅ Hecho` por recordatorio vencido: `callback_data=f"rec:hecho:{nombre}"` → `upsert_por_clave("Recordatorios", "Recordatorio", nombre, "Estado", "Hecho")` + `upsert` de `Última acción` = `hecho {fecha}`. Tests: vencido aparece N días seguidos; toque Hecho lo silencia.

**Output esperado:** la camioneta aparece en el brief de mañana como "venció hace N días" con botón ✅, y todo vencido futuro insiste solo. Primer peldaño real de la escalera del Módulo 4.

### Opción B: gestión manual del dato, escalera para después

**Instrucciones técnicas:** Nico marca en la planilla `Estado = "Hecho"` (si ya hizo la revisión) o corre la fecha (`Día / Fecha = 2026-07-15`). Nada de código más allá de A1.

**Output esperado:** el dato queda limpio hoy, pero el "vencido insiste" no existe: el próximo vencido volverá a depender de que Nico mire la planilla — exactamente lo que Donna debía evitar. Válido como triage inmediato mientras se construye la Opción A.

## C5. Higiene menor de la planilla

**Ítems:** (1) fila placeholder `"(verifica tu 9° recordatorio de Vida_v6)"` en `Recordatorios` (sin fecha → con A1 arreglado será ruido que `_dias_hasta` descarta, pero ensucia); (2) `Telegram Chat ID = "(llenar)"` en Config (inofensivo — nada lo lee, el id real vive en `.env` `NICO_TELEGRAM_ID`); (3) `Proyectos.% Avance` mezcla formatos (`0.1` vs `5.0%`) y `Última act.` congelada al 2026-06-12.

### Opción A (recomendada): checklist manual de Nico (5 minutos)

**Instrucciones técnicas:** (1) borrar la fila placeholder (o completarla si de verdad falta el 9° recordatorio de Vida_v6 — decisión de Nico); (2) poner el chat id real o `N/A (vive en .env)` en la Nota; (3) unificar `% Avance` a formato `N%` (decidir si `0.1` de Sistema Personal significa 10%) y actualizar `Última act.`. Nadie más que Nico sabe los valores verdaderos de (3) — por eso manual.

**Output esperado:** planilla limpia, cero riesgo, cero código. La ambigüedad de `0.1` la resuelve el único que sabe qué significa.

### Opción B: script de limpieza asistida

**Instrucciones técnicas:** `scripts/limpieza_higiene.py` con dry-run + OK: borra la fila placeholder vía `spreadsheets().batchUpdate` con `DeleteDimensionRequest` (requiere `sheetId` numérico: obtenerlo de `ss.get()` metadata, no confundir con el nombre del tab); escribe el Chat ID desde `settings.nico_telegram_id`; normaliza `% Avance` parseando `0.1 → 10%` **solo con confirmación explícita por fila** (la interpretación es ambigua).

**Output esperado:** mismo resultado, con la complejidad extra de `DeleteDimensionRequest` y el riesgo de interpretar mal `0.1`. Solo tiene sentido si esta limpieza se va a repetir (no parece: es deuda de migración de una sola vez). **Recomendada la A.**

## C6. Alternancia sospechosa en `Diario` (jun 20–29): hipótesis del cruce de medianoche

**Síntoma.** Del 20 al 29 de junio las filas alternan: un día tiene hábitos+ánimo (sin sueño), el siguiente solo sueño+Brief✓+Cierre✓. Desde el 30 salen completas.

**Hipótesis mecánica (verificada como plausible en el código, no confirmada con logs):** el panel del cierre sale 22:00 y `salud.marcar_cierre()` estampa `Cierre ✓` con la fecha del envío (`scheduler.py:107`), pero cada toque de hábito escribe con `_hoy()` **al momento del tap** (`flows.py:35-45` → `callback_data="hab:ejercicio:si"` sin fecha → `salud.marcar_habito` → `_set(campo, valor)` → `fecha = _hoy()`, `salud.py:94-96`). Nico se duerme ~1:00: si responde el panel después de medianoche, sus hábitos del día N caen en la fila del día N+1. Nota: `_set` **ya acepta** `fecha` opcional — el fix es solo transportarla.

### Opción A (recomendada): anclar la fecha del panel en el `callback_data` (fix estructural)

**Instrucciones técnicas:**
1. En `core/flows.py`, el builder del panel (`teclado_cierre`) recibe `fecha: str` (la fecha del ENVÍO, calculada en `enviar_panel_cierre`) y la appendea a cada callback: `f"hab:ejercicio:si:{fecha}"`, `f"comida:{h}:{fecha}"`, `f"animo:{n}:{fecha}"`. Límite de Telegram: 64 bytes por `callback_data` — `"hab:meditacion:no:2026-07-01"` = 28 bytes, holgado.
2. En `on_callback` (`flows.py:234`): parsear el 4° segmento si existe (`partes = data.split(":")`; para `comida` ojo que la hora contiene `:` → usar `rsplit(":", 1)` para extraer la fecha, o cambiar el separador de fecha a `|`: `f"comida:{h}|{fecha}"` — elegir UNA convención y aplicarla a los tres tipos; sugerido: sufijo `|fecha` en todos, así el parseo es `data, _, fecha = data.partition("|")`). Fallback: sin fecha → `_hoy()` (compatibilidad con paneles ya enviados antes del deploy).
3. Threading: `salud.marcar_habito(campo, valor, fecha=None)` y `salud.registrar_animo(valor, fecha=None)` ganan el parámetro y lo pasan a `_set(campo, valor, fecha)` (que ya lo soporta). El re-render del teclado tras cada tap debe conservar la misma fecha (el estado `e` del panel guarda `e["fecha"]`).
4. Elegir `callback_data` y NO `bot_data` como transporte: sobrevive reinicios del bot en Railway entre las 22:00 y el tap (patrón `esperando_mits` usa `bot_data` y tiene esa fragilidad).
5. Tests: tap con `|2026-07-01` a las 00:30 del 02 → `upsert_por_clave` recibe `Fecha="2026-07-01"`; tap sin sufijo → usa hoy.
6. Commit: `fix(flows): el panel del cierre ancla su fecha — los toques post-medianoche caen en el día correcto`.

**Output esperado:** los hábitos del día N siempre aterrizan en la fila N aunque Nico responda a la 1:00; el score semanal y las rachas dejan de tener huecos alternados; el correlador cruza sueño↔ánimo con filas completas.

### Opción B: solo diagnóstico primero (una semana de logs)

**Instrucciones técnicas:** agregar en `salud._set` un `logger.info("Diario._set campo=%s valor=%s fecha=%s (tap a las %s)", campo, valor, fecha, datetime.now(settings.tz).isoformat())`; deploy; revisar los logs de Railway tras 3-7 cierres buscando taps con timestamp > 00:00 cuya fecha destino ≠ día del panel.

**Output esperado:** confirmación empírica de la hipótesis antes de tocar el flujo de callbacks (que es el corazón de la UX). Costo: si la hipótesis es cierta, una semana más de filas partidas. Razonable si se quiere certeza; la Opción A es de bajo riesgo igual (tiene fallback), así que también es defendible ir directo. Pueden combinarse: log + fix en el mismo deploy, y el log valida el fix.

---

## Verificación global (al terminar cualquier subconjunto)

1. `python -m pytest tests/ -q` → todo verde (91 base + los nuevos).
2. Smoke manual por Telegram tras deploy: `"¿qué recordatorios tengo?"` (debe listar los reales, incluida la camioneta vencida hasta marcarla), `"tarea: probar fix de tareas"` → verificar en la planilla que la fila quedó en las 8 columnas correctas → `"terminé la tarea de probar"` → `Estado=Completada` y `Completada=Sí`.
3. Revisar en la planilla real que NINGUNA fila nueva tenga valores corridos de columna.
4. Actualizar el tablero de `docs/Roadmap_Modular.md` (ítems 4 y 6: de ⚠️ a 🔶/🔨 según lo que se haya cerrado) y la sección "Auditoría contra la planilla real".
5. Deploy a Railway; los fixes A1/A2 no cambian schema, así que no requieren `setup_sheets.py`.

## Decisiones que quedan en manos de Nico (no las tome la IA ejecutora)

- **Por ítem: qué opción (A/B) se ejecuta.** Este plan recomienda: A1-A, A2-A, B1-A, B2-A (B como mejora futura), C1-A, C2-B (con A como triage inmediato), C3-A, C4-A (B como triage), C5-A, C6-A.
- C1: **DECIDIDO (2026-07-04):** validar contra `Categorias` + fallback `Otro Gasto`; las 2 transferencias
  a sí mismo → categoría **`Transferencias`** (crear la fila en `Categorias`); **"Negocio/San Vale" →
  `Alimentación`** por defecto, pero **a veces `Chanchería`** → cuando el detalle no lo aclare, marcar
  `dudosa=True` para que el digest lo pregunte, no adivinar en silencio.
- C5: valores reales de `% Avance` (¿`0.1` = 10%?) y si existe el 9° recordatorio de Vida_v6.
- B1-B (borrar `metas.py`): solo con OK explícito.
