> ⚠️ **ARCHIVADO (histórico) — 2026-07-04.** Runbook E0–E7 (ya ejecutados) + E8–E12 (cuyo detalle vive ahora en [`../Spec_Herramientas_Nuevas.md`](../Spec_Herramientas_Nuevas.md) y las fichas del [`../Roadmap_Modular.md`](../Roadmap_Modular.md)). El marco "8 brechas" quedó reemplazado por la secuencia de 8 módulos + Fase 0. Consúltalo solo por los prompts de build; el estado vigente está en el Roadmap.

# Plan de Construcción Donna v7.2 — Runbook de EXTENSIÓN para Claude Code

**Para:** Nico
**Compañero:** `Plan_Donna_v7.md` (el qué y el porqué) · `Alineacion_Donna.md` (las 8 brechas) · `CLAUDE.md` (contrato del repo).
**Cambio de marco (importante):** Donna.zip **ya está ~80% construida** (núcleo, salud, finanzas, digest, memoria, voz, agenda, proactividad, aprendizaje). Este runbook **NO reconstruye**: extiende el repo existente para cerrar las 8 brechas hacia el canon. No tocas lo que ya calza.
**Regla de oro:** ningún paso está terminado hasta que **su eval pasa** y está **deployado en Railway**. No avanzas si el "LISTO CUANDO" no se cumple.
**Stack (ya montado):** Python (monolito) · Telegram · Supabase + pgvector · Anthropic SDK (caching) · Voyage · Whisper · Google Sheets API · Gmail API · Railway.
**Cómo usar:** copia el bloque "PROMPT" de cada paso, pégalo en Claude Code, no marques hecho hasta el "LISTO CUANDO". Trabaja sobre el repo de Donna.zip (sácale antes `.env` y `credentials.json` del control de versiones).

---

## FASE E0 — Verificación y esquema (antes de tocar lógica)

> **PROMPT:**
> Estás extendiendo un bot existente (repo Donna). Primero **no escribas lógica nueva**: (1) corre el repo local y confirma que `/start`, el brief y el cierre arrancan; (2) lista qué módulos existen en `modules/` y `core/` y reporta cuáles están vivos. Luego **re-sincroniza el esquema de hojas**: actualiza `setup_sheets.py` para que los tabs y headers calcen **exactamente** con `Donna_Canonico.xlsx` (Diario 12 col; Recordatorios con `Estado`/`Posposiciones`/`Ultima_Accion` y tipo `unica`; tab nuevo `Reconciliacion`; `Semanal` con columnas de tiempo-por-frente + `Factor_Optimismo`; `Config` con filas de módulos ON/OFF). NO borres datos existentes: solo agrega tabs/columnas que falten.

**LISTO CUANDO:** el bot arranca y responde; `setup_sheets.py` deja la planilla con los tabs/headers del `Donna_Canonico.xlsx` sin perder filas; reportaste el inventario de módulos vivos.

---

## FASE E1 — Recordatorios: escalera ⭐

> **PROMPT:**
> Extiende `modules/recordatorios.py` (prefijo `rec_`) a la **escalera** (hoy es básico). El tab `Recordatorios` ahora tiene tipo **mensual/anual/única**, `Estado` (pendiente/hecho/pospuesto), `Posposiciones`, `Ultima_Accion`. Implementa:
> - `rec_semana()` → todos los de los próximos 7 días, en un bloque (preview del domingo).
> - `rec_proximos()` → los que disparan **hoy**: T-2 (2 días antes) y T-0 (el día); el T-0 con acción **✅ Hecho**.
> - `rec_marcar_hecho(id)` → `Estado=hecho`; si es recurrente, agenda la próxima; si es única, cierra.
> - `rec_posponer(id, hasta)` → exige **día concreto**; incrementa `Posposiciones`. Tras 3, marca el patrón para que Donna lo nombre.
> - `rec_vencidos()` → pendientes con fecha pasada (alimenta la escalada del scheduler, E-siguiente).
> - `rec_agregar(texto)` → parsea recurrente **y único** ("el IVA el 12" / "dentista el viernes 3pm"). Anti-duplicado con `Tareas`: con fecha + persigue = recordatorio; backlog sin fecha = tarea.
> Ver spec detallado en `Spec_Herramientas_Nuevas.md §rec_`.

**LISTO CUANDO:** `rec_semana()` lista los 7 días; `rec_proximos()` dispara T-2 y T-0; ✅ Hecho cierra y reagenda si recurrente; posponer sin fecha se rechaza; un vencido aparece en `rec_vencidos()`.

---

## FASE E2 — Correo: invariante "jamás borra" + triage 3 buckets ⭐

> **PROMPT:**
> Dos arreglos sobre `core/correo.py` + `modules/spam.py`:
> **(A) Invariante duro:** el manejo de spam HOY manda a la papelera ("Borrar todo"). Cámbialo: spam/bulk → aplica etiqueta `Donna/Archivado` y **quita `INBOX`**, **nunca `trash`/`delete`**. Quita toda ruta de borrado. El botón pasa a "🗄️ Archivar todo" / "✋ Conservar".
> **(B) Triage de 3 buckets:** además de gasto + spam, clasifica TODO el inbox en **spam/bulk → archivar · importante → resumen brief · financiero → digest**. Pipeline por costo: Gmail spam (gratis) → reglas (`List-Unsubscribe`, `no-reply`, allowlist financiera, allowlist importantes) → LLM **solo el residuo, una llamada, `{remitente, asunto, snippet}`, nunca el cuerpo**. Agrega `cor_resumen_brief()` (conteo por bucket + 1 línea por importante, solo lectura) y `cor_reconciliar()` (diario, sin LLM: lo rescatado de `Donna/Archivado` sube a importante en tabla `remitentes`).
> Ver `Spec_Herramientas_Nuevas.md §cor_`.

**LISTO CUANDO:** corres el triage sobre tu inbox real; los 3 buckets salen con conteos correctos; un marketing se archiva (etiqueta puesta, `INBOX` quitado) y **assert: ninguna acción llamó a trash/delete**; rescatas uno y al otro día su remitente entra como importante.

---

## FASE E3 — Correo dedicado financiero

> **PROMPT (manual + código):**
> **Manual (una vez):** casilla `finanzas.nico@…`, redirige ahí los avisos de bancos/servicios, da lectura a Donna (OAuth/service account). **Crítico:** deja la allowlist del inbox viejo corriendo **en paralelo** hasta confirmar que el nuevo recibe todo.
> **Código:** en `modules/finanzas.py`, agrega la casilla dedicada como **segunda fuente** de `fin_procesar_correo`. Dentro de ella, igual filtra: transacción = monto + palabra clave (`compra`/`cargo`/`transferencia`/`giro`); marketing = `List-Unsubscribe` → archivar. En `⚙️ Config`, `Correo Outlook = OFF` (no se usa).

**LISTO CUANDO:** una alerta real al correo dedicado entra al digest; marketing del mismo banco se archiva; el inbox viejo sigue cubierto en paralelo.

---

## FASE E4 — Reconciliación nocturna (opción 1, con delta) ⭐

> **PROMPT:**
> Scope nuevo, prefijo `prod_`. En el **cierre 22:00** (extiende `core/scheduler.py`), tras el digest, agrega el flujo de reconciliación SIN tocar el brief:
> - `prod_bloques_hoy()` → lee de `core/agenda.py` los bloques/eventos del Google Calendar de hoy.
> - Panel de toques: "✅ Hice todo" (un toque si el día salió) **o** tocas solo los que no; por cada bloque, ⏱️ **Menos / Igual / Más** de lo que pusiste. Mismo patrón "aceptar todo / corrige excepciones" del digest.
> - `prod_guardar_reconciliacion(items)` → escribe en el tab `Reconciliacion` (Fecha, Bloque, Frente∈{Tesis,Noomi,Delivery,Hijo,Personal}, Min planeados, ¿Hecho?, Delta, Min reales). El frente se infiere del evento (etiqueta/keyword) y se confirma con toque si dudoso.
> - El Semanal del domingo suma `Min reales` por frente → columnas h Tesis/Noomi/Delivery/Hijo. **El brief queda intacto.**
> Ver `Spec_Herramientas_Nuevas.md §prod_`.

**LISTO CUANDO:** simulas el cierre con 3 bloques en Calendar; "Hice todo" los marca hechos con su duración; corriges uno a "Menos"; el tab `Reconciliacion` queda escrito; el Semanal del domingo muestra horas por frente. El brief de la mañana no cambió.

---

## FASE E5 — Factor de optimismo (sobre aprendizaje) ⭐

> **PROMPT:**
> Extiende `modules/aprendizaje.py` (prefijo `apr_`). Usando lo que escribe la reconciliación (E4):
> - `apr_factor_optimismo(frente)` → ratio plan-vs-real por frente sobre las últimas N semanas (reference class forecasting personal): si planeas 5h de tesis y haces 3h, factor ≈ 0,6. **Persiste el modelo aprendido en Supabase (tabla `aprendizaje`, migración 007)**; en el `Semanal` escribe SOLO el resultado legible `Factor_Optimismo`.
> - `apr_observador(plan_propuesto)` → cuando planificas de más, devuelve la señal de observador externo: "dijiste 5 bloques de tesis; tu promedio real es 3 — ¿bajamos esto?". Requiere ≥2-3 semanas de datos antes de hablar; mientras tanto, calla.
> Inferencia validada: el factor SIEMPRE viene con el dato (semanas y promedio) que lo respalda. **Capa de datos:** registros en Sheets (`Reconciliacion`), aprendizaje en Supabase — nunca al revés. Ver `Spec_Herramientas_Nuevas.md §apr_`.

**LISTO CUANDO:** con 3 semanas de datos simulados, `apr_factor_optimismo('Tesis')` da un ratio coherente y queda persistido en Supabase; `apr_observador` frena un plan inflado mostrando el promedio real; con <2 semanas, se queda callado.

---

## FASE E6 — Poda: productividad simple

> **PROMPT:**
> Alinea la capa de productividad al canon **simple**:
> - `⚙️ Config`: `Módulo Tiempo (log diario) = OFF`. Deja `modules/tiempo.py` en el repo pero **desconectado del scheduler** (dormido; se promueve después si el sistema lleva semanas vivo).
> - Simplifica el tab/uso de `Tareas`: de "fases de proyecto" a **tareas sueltas** (Creada, Descripción, Proyecto, Tipo, Fecha objetivo, Estado, Completada, Notas), como en `Donna_Canonico.xlsx`.
> - `metas.py`: o se pliega al `Semanal` o queda dormido; no debe pedir input diario.
> - El tiempo-por-frente NO viene de un log diario, viene de la reconciliación (E4).

**LISTO CUANDO:** el scheduler no llama a `tiempo.py` ni pide log de tiempo; `Tareas` funciona como tareas sueltas; `Config` refleja Tiempo OFF, Outlook OFF, Aprendizaje ON, Proactividad ON.

---

## FASE E7 — Evals nuevos + redeploy

> **PROMPT:**
> Agrega a `tests/evals.py` (y `tests/casos.yaml`) los casos del canon: (1) **correo jamás borra** — assert que ninguna acción llama a trash/delete; (2) **triage** — bucketing correcto sobre un set fijo; (3) **escalera** — T-2/T-0/vencido disparan cuando deben; (4) **posponer** — sin fecha se rechaza; tras 3, nombra el patrón; (5) **reconciliación** — "Hice todo" escribe duraciones; un "Menos" baja los minutos reales; (6) **factor de optimismo** — con <2 semanas calla, con ≥3 frena un plan inflado con su dato. Mantén los evals previos (deriva, digest, freno de deuda). Corre `pytest`, redeploy a Railway, confirma brief + cierre + reconciliación reales en producción.

**LISTO CUANDO:** `pytest tests/evals.py` pasa todo (viejos + nuevos); el bot corre 24h en Railway; recibiste brief, cierre y reconciliación reales.

---

## Fases añadidas (mejoras del roadmap de 8 módulos)

> Estas fases extienden el canon tras la sesión de revisión de las propuestas externas. Mapean a los módulos del `Roadmap_Modular.md`: **E8 → Salud (M2)**, **E9 → Compras (M3, nuevo)**, **E10 → Familia (M8, nuevo)**, **E11 → Finanzas v2 (M1)**. Misma regla: una a la vez, eval verde + deploy + 7 días estable antes de promover. **No se construye código en este paso documental**; aquí queda el runbook para cuando a cada módulo le toque su turno.

### FASE E8 — Salud v2: nutrición, ventanas, peso, score, eventos ⭐

> **PROMPT:**
> Extiende `modules/salud.py` (prefijo `sal_`), `core/scheduler.py` (cierre), `core/flows.py` (panel) y `setup_sheets.py`. **Schema:** agrega a `Diario` (al final, merge aditivo) `Primera_Comida`, `Hora_Despertar`, `Agua`, `Proteina`, `Peso`; agrega a `Semanal` `Score_Habitos`, `Ventana_Comida`, `Ventana_Sueno`, `Peso`. Implementa:
> - Toques en el cierre: **agua** sí/no y **proteína** sí/no (mismo patrón de `marcar_habito`); hora **1ª comida**, **última comida** (ya existe `Ultima_Comida`), hora **despertar** (ya existe `Hora_Dormi`).
> - `sal_peso(kg)` → escribe `Peso` en la fila del día; se **pide los domingos** (no diario).
> - `sal_resumen_ventanas(semana)` → mediana de ventana de comida (1ª→última) y de sueño (dormir→despertar), **semana vs fin de semana**. **Solo mide y muestra**; sin meta ni empuje (espera 2-3 semanas de baseline — canon "calla hasta tener datos").
> - `sal_score_semana()` → % de hábitos cumplidos en la semana (default: sueño 7h, ejercicio, meditación, agua, proteína); escribe `Score_Habitos` en `Semanal` (es una lectura).
> - **Eventos contextuales:** en el cierre, pregunta *"¿hubo algo hoy fuera de tu control que te bajó el ánimo o no te dejó hacer lo planeado?"* → texto libre → `core/memory` con tag `evento_externo`. El correlador lee ese tag y trata el día como **contexto, no patrón**.
> Ver `Spec_Herramientas_Nuevas.md §sal_`.

**LISTO CUANDO:** los toques de agua/proteína/comidas escriben en `Diario`; `sal_peso` registra el domingo; `sal_resumen_ventanas` da medianas coherentes (semana vs finde); `Score_Habitos` cuadra con los toques; un evento contextual queda en `memoria` y el correlador no lo cuenta como patrón.

### FASE E9 — Compras: lista del súper (módulo nuevo `cmp_`, Fase 1) ⭐

> **PROMPT:**
> Crea `modules/compras.py` (prefijo `cmp_`, sin solapamiento), tab nuevo `Compras` en `setup_sheets.py` (`Item · Estado(pendiente|comprado) · Fecha_Agregado · Fecha_Comprado · Categoria`), e intents en `core/brain.py`/`main.py`. Implementa **solo Fase 1 (lista manual)**:
> - `cmp_agregar(item)` → reconoce "Donna falta toalla nova", "queda poco arroz, anótalo a la lista" → agrega `Estado=pendiente`, `Fecha_Agregado=hoy`; anti-duplicado por nombre normalizado.
> - `cmp_lista()` → "Donna dame la lista del súper" → devuelve **exactamente** los `pendiente`.
> - `cmp_marcar_comprado(item)` → `Estado=comprado`, `Fecha_Comprado=hoy`; lo saca de la lista. (Toque o texto.)
> - Degrada elegante si Sheets falla. **Fase 2 NO se construye aquí** (motor de frecuencia + alertas), pero la Fase 1 ya **siembra la fecha de cada compra** para que la inferencia futura tenga historial.
> En `⚙️ Config` agrega `modulo_compras = ON`. Ver `Spec_Herramientas_Nuevas.md §cmp_`.

**LISTO CUANDO:** "falta X" agrega sin duplicar; "dame la lista" devuelve solo lo pendiente; marcar comprado lo saca y registra `Fecha_Comprado`; nada de Fase 2 todavía.

### FASE E10 — Familia (módulo nuevo `fam_`, opción B) ⭐

> **PROMPT:**
> Crea `modules/familia.py` (prefijo `fam_`), agrega a `Diario` (merge aditivo) `Fam_Emilio`, `Fam_Pareja`, `Fam_Cena`; en `core/scheduler.py` (cierre) suma 3 toques sí/no. Implementa:
> - `fam_marcar(campo, valor)` → escribe el toque en la fila del día (reusa el patrón de `sal_marcar_habito`).
> - `fam_senal()` → señal destilada hacia arriba (racha de días con/sin tiempo de calidad).
> - **Espina:** escribe inferencias propias a Supabase; el correlador cruza **familia↔ánimo↔sueño** con su dato.
> - **Nudge propio** (vía Proactividad, módulo 7): "llevas N días sin tiempo con Emilio" — respeta el tope 1/día.
> En `⚙️ Config` agrega `modulo_familia = ON`. Ver `Spec_Herramientas_Nuevas.md §fam_`.

**LISTO CUANDO:** los 3 toques escriben en `Diario`; `fam_senal` da una racha coherente; el correlador cruza familia con ánimo con su dato; el nudge dispara tras una racha sin tiempo de calidad.

### FASE E11 — Finanzas v2: intención del gasto + metas ⭐

> **PROMPT:**
> Extiende `modules/finanzas.py` (prefijo `fin_`) y `setup_sheets.py`. **Schema:** agrega `Intencion` a `Transacciones` (merge aditivo) y crea tab `Metas` (`Meta · Objetivo · Actual · Progreso · Notas`). Implementa:
> - **Intención del gasto:** el extractor (`procesar_correo`/`procesar_foto`) propone `Intencion ∈ {Necesario, Inversion, Deseo}`; se **confirma en el digest** junto con la categoría (mismo "aceptar todo / corrige excepciones", sin fricción nueva). Resumen mensual por intención.
> - **Metas con progreso:** `fin_metas()` lee `Metas` y calcula `Progreso = Actual/Objetivo`; 2-3 metas (fondo de emergencia, pagar TC). Se muestran en el `Semanal`/digest. **Sin input diario.**
> - **Alerta presupuesto 90%** (gatillo de Proactividad, módulo 7): cuando una categoría llega al 90% de su `Presupuesto`, un nudge (tope 1/día).
> **No** construyas cuentas con saldos auto / doble-entrada (descartado: rompe "registro sin fricción"). Ver `Spec_Herramientas_Nuevas.md §fin_`.

**LISTO CUANDO:** la intención se infiere y se corrige en el digest; el resumen mensual por intención cuadra; una meta muestra su % de avance; la alerta de presupuesto salta al 90% real.

### FASE E12 — Finanzas v3: detalle de compra (ítems) + correlación foto↔correo + captura al momento ⭐

> **Contexto:** la predicción de Compras (Fase 2) necesita saber **qué** compraste, no solo cuánto gastaste. Esta fase enriquece la captura de Finanzas para producir ese detalle, sin doble conteo y sin fricción. Es **Finanzas la que escribe el detalle**; **Compras solo lo lee** (sin solapar tools).

> **PROMPT:**
> Extiende `modules/finanzas.py` (`fin_`), `setup_sheets.py`, `core/flows.py` y el ciclo de ingesta. **Schema:** crea el tab `Compras_Detalle` (`Fecha · Comercio · Item · Cantidad · Precio · Categoria · Predecible(si|no) · ID_Tx · Fuente(foto|desglose|lista)`); agrega un flag `es_compras` a las reglas de comercio (Supabase, `memory.get_comercios`) para saber qué cargos disparan la pregunta. Implementa:
> - **Foto ítem-a-ítem:** cambia `procesar_foto` para extraer `items[]` (item, cantidad, precio) + `total` (hoy devuelve un solo total). Escribe **una** transacción en `Transacciones` (total) + N líneas en `Compras_Detalle` con `ID_Tx = ID_Unico` de la transacción. La suma de `Precio` debe **cuadrar al total** (línea "resto/varios" si falta).
> - **Correlación foto↔correo:** `fin_correlacionar(buffer)` aparea la entrada de **foto** con la de **correo** del mismo gasto por **monto total + fecha (±1-2 días) + comercio** (fuzzy / vía reglas; resuelve "ALMACEN SAN VALENTIN" vs "MERCADOPAGO*SANVA"). El **correo es el total canónico** (medio + monto bancario); la **foto aporta los ítems**. Resultado: **una** transacción, **jamás dos** (extiende el anti-duplicado actual `_id_unico`/`_planificar_digest`, que hoy solo dedup por id exacto).
> - **Captura al momento:** cuando la ingesta detecta un cargo de un comercio `es_compras=true` **sin detalle**, Donna manda un **prompt transaccional** por Telegram: *"vi $X en San Valentín — ¿qué compraste?"* con `📷 foto` / `✍️ desglosar` / `⏭️ después`. **No** cuenta contra el tope 1/día de Proactividad (es captura, no insight). Requiere que `ingerir_gastos_email` corra en **cadencia diurna** (poll periódico), no solo en el cierre. **El brief de las 8:00 no se toca.**
> - **Desglose por categoría:** `fin_desglose(texto, total)` parsea "gasté 2000 en chanchería y el resto fue pan" → `[{cat: Chanchería, monto: 2000}, {cat: Pan, monto: total-2000}]` (el "resto" cuadra al total); cada línea → `Compras_Detalle`.
> - **Filtro de predicción:** marca `Predecible` por categoría — **sí** = despensa/reposición (arroz, atún, fideos, aceite, azúcar, papel, limpieza); **no** = perecible/cotidiano (pan, chanchería, verdura, comida preparada). Solo `Predecible=sí` lo consumirá Compras Fase 2.
> Ver `Spec_Herramientas_Nuevas.md §fin_` (detalle/correlación) y `§cmp_` (Fase 2 lee el detalle).

**LISTO CUANDO:** una foto deja ítems con precio + total en `Compras_Detalle`; foto + correo del mismo gasto = **una** transacción (no dos); un cargo de comercio "de compras" sin detalle dispara el prompt al momento; "2000 chanchería, resto pan" cuadra al total; arroz/atún quedan `Predecible=sí` y pan/chanchería `no`; el detalle no rompe el total de `Transacciones`.

### Propagación de schema y evals (transversal a E8–E12)

- `setup_sheets.py` — nuevas columnas (`Diario` +5, `Semanal` +4, `Transacciones` +`Intencion`), nuevos tabs (`Compras`, `Metas`, `Compras_Detalle`), `CONFIG_SEED` +`modulo_salud`/`modulo_compras`/`modulo_familia`. **Merge aditivo:** respeta el orden existente, agrega faltantes al final; no borra filas.
- `Donna_Canonico.xlsx` — refleja el mismo esquema (es la fuente de verdad del schema; `setup_sheets.py` debe calzar con él).
- Supabase — flag `es_compras` en reglas de comercio; el historial de compras predecibles (item, fecha) que consume el predictor vive en `aprendizaje` (no en el Sheet).
- `tests/evals.py` + `tests/casos.yaml` — casos nuevos: ventanas/score (E8), lista de compras agregar/listar/marcar (E9), checks de familia + cruce con ánimo (E10), intención del gasto + meta con progreso (E11), **correlación foto↔correo sin doble conteo + desglose que cuadra + filtro predecible (E12)**.

---

## Reglas para Claude Code (en cada paso)
- **No reconstruyas lo que ya calza** (ver `Alineacion_Donna.md` §3 "calza fuerte"). Extiende, no reescribas.
- Respeta el contrato: prefijos `sal_`/`fin_`/`rec_`/`cor_`/`prod_`/`apr_`, sin solapamiento, señal destilada hacia arriba, trabajo pesado aislado, degradación elegante.
- **Invariantes duros:** Donna jamás borra correo (solo etiqueta). Jamás escribe a Sheets sin tu OK (digest/reconciliación). Jamás afirma sin el dato (inferencia validada).
- Toques > texto; el cierre es **un** panel; el brief es **solo lectura** (nada de reconciliación en la mañana).
- Al final de cada paso: corre su eval y haz commit.

---

*El próximo artefacto no es un v8. Es la Fase E1 cerrada y commiteada en el repo de Donna.*
