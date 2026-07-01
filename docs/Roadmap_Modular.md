# Roadmap Modular — Donna

**Para:** Nico
**Qué es:** la re-secuencia de la entrega. Un módulo a la vez, completo, probado 1 semana, antes del siguiente. La memoria de Donna (la espina) crece con cada módulo.
**Acompaña a:** `CLAUDE.md` (contrato + invariantes), `Plan_Construccion_v7.md` (pasos de build por brecha), `Spec_Herramientas_Nuevas.md` (detalle de tools), `Donna_Canonico.xlsx` (esquema de datos).

---

## Regla madre
Un solo Donna (un repo). Se construye y prueba **un módulo a la vez**. No empiezas el siguiente hasta que el actual pase su semana.
**Gate de promoción:** deployado + corre estable 7 días + sus evals en verde.

## Cadencia (cómo se trabaja cada módulo)
1. Rama git `modulo/<nombre>`.
2. Sesión nueva de Claude Code, contexto limpio, apuntando a `CLAUDE.md` + la ficha del módulo. (Una sesión por módulo = dejas de perder info entre frentes.)
3. En `Config`, el módulo en construcción es el único **ON**; el resto dormido (para que no escriban basura).
4. Construir hasta "completo" (ver ficha) → correr su eval → merge a `main` + deploy.
5. Empieza la **semana de prueba**: tu único trabajo es usarlo y anotar lo que se rompe. **No construyes el siguiente.**
6. 7 días estable + evals verdes → **promovido**. Recién ahí, módulo siguiente.

## La espina de memoria (transversal — ver CLAUDE.md)
No es un módulo: es una espina que cruza todo. Cada módulo, como parte de "completo", **escribe sus inferencias y episodios a Supabase**. Cinco tipos: `perfil` (estable), `memoria` (episódica), `inferencias` (con dato), `compromisos`, `aprendizaje` (calibración).
- **Correlador:** se enciende con ≥2 módulos vivos (o sea, desde Salud). Propone cruces, los valida contra el dato, descarta los espurios, guarda los que aguantan.
- **Vista `/perfil` editable ("lo que sé de ti"):** se construye en el Módulo 1 (vacía, crece con cada módulo). Muestra perfil + inferencias top con su dato; corriges y eso calibra.
- **Surfacing:** bajo demanda + resumen domingo + **proactivo cuando es accionable** (esto último aterriza en el Módulo 7).

## Ficha de módulo (plantilla — se rellena igual cada vez)
> Objetivo · Scope ("completo") · Prefijo · Datos (hojas + Supabase) · Aporte a la espina · Eval que lo gatilla · Semana cumplida.

---

## Los 8 módulos

### 1. Finanzas `fin_`
- **Objetivo:** capturar tu plata sin fricción y mostrarte la verdad de tu deuda.
- **Scope completo:** foto + manual + categorización + faro de deuda (con línea) + dashboard + digest nocturno en el cierre. **Correo NO** (va en Módulo 5).
- **Scope v2 (añadido):** **intención del gasto** — columna `Intencion` (Necesario/Inversión/Deseo) en `Transacciones`, la infiere el extractor y la confirmas en el digest (sin fricción nueva); resumen mensual por intención. **Metas financieras con progreso** — tab `Metas` (`Meta · Objetivo · Actual · Progreso`), 2-3 metas (fondo de emergencia, pagar TC), leídas en el `Semanal`/digest. **Sin input diario.** *(No entra: cuentas con saldos auto / doble-entrada — rompe "registro sin fricción".)*
- **Scope v3 (detalle de compra — alimenta la predicción de Compras):** la boleta deja de ser un solo total y se vuelve **ítem por ítem**.
  - **Foto ítem-a-ítem:** `procesar_foto` lee cada ítem + precio + total → escribe el detalle en la hoja nueva `Compras_Detalle` (`Fecha · Comercio · Item · Cantidad · Precio · Categoria · Predecible · ID_Tx · Fuente`).
  - **Correlación foto↔correo (jamás doble conteo):** el correo del banco es el **total canónico** (medio + monto confirmado); la foto aporta los **ítems**. Se aparean por **monto total + fecha (±1-2 días) + comercio** (fuzzy / vía reglas de comercio) → **una** transacción en `Transacciones` + sus líneas en `Compras_Detalle`. Hoy se contarían dos veces porque la foto lee "ALMACEN SAN VALENTIN" y el correo "MERCADOPAGO*SANVA"; el matcher lo resuelve por monto+fecha.
  - **Captura al momento:** cuando entra un cargo de un **comercio marcado "de compras"** (súper, almacén, San Valentín) **sin detalle**, Donna pregunta en el momento *"vi $X en San Valentín — ¿qué compraste?"* → respondes con **foto** (→ ítems) o con **desglose por categoría** ("2000 en chanchería, el resto pan" → 2000 Chanchería + resto Pan, el "resto" cuadra al total). Es un prompt **transaccional**, no cuenta contra el tope 1/día de Proactividad.
  - **Filtro de predicción:** cada línea se marca `Predecible` = **sí solo para despensa/reposición** (arroz, atún, fideos, aceite, azúcar, papel, limpieza) y **no para lo cotidiano/perecible** (pan, chanchería, verdura, comida preparada). **Solo las `Predecible=sí` alimentan el predictor de Compras Fase 2.**
- **Datos:** Sheets `Transacciones`/`Categorias`/`Tarjetas y Deuda`/`Dashboard`/`Metas`/`Compras_Detalle`; Supabase `inferencias`.
- **Espina:** nace mínima. Siembra `perfil` con lo que ya sabemos de ti; escribe inferencias de gasto/deuda. **Se construye la vista `/perfil` (aún corta).** Sin correlación todavía.
- **Eval:** foto→categoría correcta · "aceptar todo" escribe sin duplicar · faro da $2.028.091 y $48.236 · el freno muestra la deuda antes de una cuota · la intención se infiere y se corrige en el digest · una meta muestra su % de avance · foto+correo del mismo gasto = **una** transacción (no dos) · un desglose "2000 chanchería, resto pan" cuadra al total · arroz/atún quedan `Predecible=sí`, pan/chanchería `no`.
- **Semana:** 7 días registrando gastos reales, estable, evals verdes.

### 2. Salud `sal_`
- **Objetivo:** el eje #1 (sueño) + hábitos, ánimo, nutrición y ritmo diario.
- **Scope completo:** `Diario` (ejercicio, meditación, sueño 7h, ánimo 1-4, hora dormí, MITs) + brief 8:00 (lectura) + cierre 22:00 (toques) + señal sueño×ánimo.
- **Scope ampliado (añadido):**
  - **Nutrición:** toques de **agua** sí/no y **proteína** sí/no en el cierre (`Diario` +`Agua`, +`Proteina`).
  - **Ventanas (ayuno + sueño):** `Diario` +`Primera_Comida`, +`Hora_Despertar` (ya existen `Ultima_Comida` y `Hora_Dormi`) → **resumen semanal de ventanas**: mediana de la ventana de comida (1ª→última) y de sueño (dormir→despertar), semana vs fin de semana. **Solo medir, sin meta todavía** (cuando haya 2-3 semanas de baseline, recién ahí se propone ventana objetivo — canon "calla hasta tener datos").
  - **Peso:** `Diario` +`Peso` (kg), pedido **semanal** (domingo), no diario; muestra tendencia.
  - **Score % semanal de hábitos:** número único calculado el domingo en `Semanal` (`Score_Habitos`). Composición default (revisable): sueño 7h, ejercicio, meditación, agua, proteína.
  - **Eventos contextuales:** pregunta en el cierre — *"¿hubo algo hoy fuera de tu control que te bajó el ánimo o no te dejó hacer lo planeado?"* → texto libre → `memoria` episódica con tag `evento_externo`. **El correlador trata ese día como contexto, no como patrón** (guardia anti-patrón-falso).
- **Datos:** Sheets `Diario`/`Semanal`; Supabase `inferencias`/`memoria`.
- **Espina:** **se enciende el correlador** (2º dominio). Primeros cruces: sueño↔ánimo; con finanzas, sueño↔gasto; y ahora ventana/nutrición↔ánimo.
- **Eval:** marcas hábitos por botón → fila correcta · señal coherente · el cruce sueño↔ánimo aparece con su dato · el resumen de ventanas da medianas coherentes · el score % cuadra con los toques de la semana · un evento contextual marca el día como contexto.
- **Semana:** 7 días de cierre real, estable, evals verdes.

### 3. Compras `cmp_`  ⟵ NUEVO
- **Objetivo:** que no se te olvide qué comprar; lo dices suelto y Donna lo guarda.
- **Scope completo (Fase 1 — lista manual):** `cmp_agregar` ("Donna falta toalla nova" / "queda poco arroz, anótalo") → guarda en la lista; `cmp_lista` ("Donna dame la lista del súper") → devuelve **exactamente** lo pendiente; marcar comprado por toque → sale de la lista. Hoja nueva `Compras` (`Item · Estado(pendiente|comprado) · Fecha_Agregado · Fecha_Comprado · Categoria`).
- **Fase 2 (DIFERIDA — no en este módulo):** motor de frecuencia. **Lee dos fuentes** de eventos de compra (item, fecha): (a) la **lista Fase 1** (ítems marcados `comprado`) y (b) las líneas **`Predecible=sí`** de `Compras_Detalle` que escribe Finanzas v3 (foto + desglose). Calcula el intervalo medio por ítem → infiere reposición → alerta *"puede que toque comprar arroz"* (sale por **Proactividad**). Se persiste en Supabase (`aprendizaje`). **Solo despensa/reposición** (arroz, atún, fideos, limpieza); **nunca lo cotidiano/perecible** (pan, chanchería) — esos quedan fuera del predictor por diseño.
- **Datos:** Sheets `Compras` (Fase 1) + `Compras_Detalle` (lee, lo escribe Finanzas); Supabase `aprendizaje` (recién en Fase 2).
- **Espina:** Fase 1 siembra el historial de compras con fecha; Fase 2 lo cruza con el detalle predecible de las boletas (insumo del predictor).
- **Eval:** "falta X" agrega sin duplicar · "dame la lista" devuelve solo lo pendiente · marcar comprado lo saca y registra la fecha.
- **Semana:** 7 días usándolo de verdad (agregar al vuelo + pedir la lista antes de ir al súper).

### 4. Recordatorios / Calendario `rec_`
- **Objetivo:** que no se te olvide nada y que el calendario esté a la vista.
- **Scope completo:** escalera (domingo + T-2 + T-0 con ✅ Hecho + vencido-insiste) + estados (pendiente/hecho/pospuesto) + tipos (mensual/anual/única) + posponer con fecha; lectura del Google Calendar en el brief.
- **Datos:** Sheets `Recordatorios`; Calendar (lectura).
- **Espina:** inferencias de cumplimiento ("pospones el IVA seguido") → un "contra" con dato.
- **Eval:** T-2/T-0/vencido disparan cuando deben · posponer sin fecha se rechaza · tras 3 posposiciones, nombra el patrón.
- **Semana:** idem.

### 5. Correo `cor_`
- **Objetivo:** triage del inbox sin que tengas que mirarlo, y que **jamás borre**.
- **Scope completo:** inbox dedicado financiero + triage 3 buckets (spam→archivar · importante→resumen brief · financiero→digest) + jamás borra (etiqueta). Enchufa al digest de Finanzas (ya estable).
- **Datos:** Gmail; alimenta `Transacciones` vía `fin_`; Supabase `remitentes`/`aprendizaje`.
- **Espina:** aprende qué remitentes te importan (de tus rescates de `Donna/Archivado`).
- **Eval:** 3 buckets correctos · **assert: ninguna acción borra** · rescatar promueve al remitente.
- **Semana:** idem. *(Es el más delicado; por eso va con Finanzas ya recibiendo su señal.)*

### 6. Productividad `prod_` / `apr_`
- **Objetivo:** saber en qué se te va el tiempo y frenarte cuando planificas de más.
- **Scope completo:** reconciliación nocturna (con delta) + tiempo por frente en `Semanal` + factor de optimismo (observador externo). **El brief no se toca.**
- **Refinamiento (añadido):** **horas profundas por frente** — las horas por frente ya existen (`Reconciliacion`→`Semanal h_Tesis/h_Noomi/h_Delivery/h_Hijo`); el refinamiento es asegurar que tesis/Ñoomi/delivery se capturen como **trabajo profundo (producir)** distinguible de "estar ocupado", no agregar variables nuevas.
- **Datos:** Calendar; Sheets `Reconciliacion`/`Semanal`; Supabase `aprendizaje`.
- **Espina:** el factor de optimismo es tu primer "contra" duro con dato; cruces tiempo↔ánimo↔gasto.
- **Eval:** "hice todo" escribe duraciones · con ≥3 semanas frena un plan inflado con su dato · con <2 calla.
- **Semana:** idem.

### 7. Proactividad `pro_`
- **Objetivo:** que Donna hable sola, máx 1/día, **solo cuando un patrón es accionable ahora**.
- **Scope completo:** 1 mensaje espontáneo/día, gatillado por la espina (un cruce accionable). Acá vive tu decisión de "proactivo cuando es accionable".
- **Scope ampliado (añadido):** salidas concretas que se enchufan a medida que los módulos se encienden — **alerta de presupuesto al 90%** (de Finanzas v2), **nudge de familia** ("llevas N días sin tiempo con Emilio", de Módulo 8) y, cuando exista, **alertas de Compras Fase 2** ("puede que toque comprar X"). Todas respetan el tope 1/día.
- **Datos:** Supabase (`inferencias` top); sin escritura nueva.
- **Espina:** es el **brazo de salida** de la espina — convierte lo aprendido en un aviso oportuno.
- **Eval:** dispara solo con señal real · respeta el tope 1/día · calla si nada mueve la aguja · la alerta de presupuesto salta al 90% real.
- **Semana:** idem.

### 8. Familia `fam_`  ⟵ NUEVO (opción B: módulo propio)
- **Objetivo:** que el tiempo con Emilio y tu pareja esté medido y no se diluya.
- **Scope completo:** 3 toques en el cierre — tiempo con **Emilio** / tiempo con **pareja** / **cena juntos** (sí/no); `Diario` +`Fam_Emilio`, +`Fam_Pareja`, +`Fam_Cena`. **Inferencias propias** en Supabase y **nudge propio** vía Proactividad ("llevas 5 días sin tiempo con Emilio").
- **Datos:** Sheets `Diario`; Supabase `inferencias`/`memoria`.
- **Espina:** nuevo dominio del correlador — cruces **familia↔ánimo↔sueño**.
- **Eval:** los 3 toques escriben en la fila del día · el correlador cruza familia con ánimo con su dato · el nudge dispara tras una racha de días sin tiempo de calidad.
- **Semana:** 7 días marcando los 3 toques en el cierre.

---

## Tablero (una línea por módulo)
**Actualizado 2026-07-02 por auditoría de código** (qué existe y está enganchado en `brain`/`scheduler`/`flows`,
no telemetría de producción — el repo no dice si algo lleva sus 7 días estables en Railway).

Estados: ⬜ pendiente · 🔨 construido (scope de la ficha completo) · 🔶 parcial (falta scope de la ficha) ·
🧪 prueba sem X/7 · ✅ promovido · ⚠️ riesgo (viola un invariante duro de `CLAUDE.md`, o el código
escribe/lee mal contra el schema real de la planilla — más grave que "falta scope")

**Nota importante:** la regla madre de este documento ("un módulo a la vez, 7 días estable antes del
siguiente") ya no se está siguiendo — el código de casi todos los módulos existe en paralelo. Este tablero
registra ese hecho en vez de fingir que la secuencia se respetó.

1. **Finanzas** `fin_` — 🔨 completo (v1 + v2 intención/metas + v3 detalle ítem-a-ítem/correlación). 39/39
   evals unitarios verdes (`tests/test_finanzas.py`). Semana de 7 días estable: **sin confirmar** (no es
   verificable desde el repo).
2. **Salud** `sal_` — 🔨 completo (base + v2/E8: nutrición, ventanas, peso, score, eventos). El correlador
   ya está **encendido** (`core/correlador.py`, cruza sueño↔ánimo↔gasto en el cierre) y ahora respeta la
   guardia de eventos contextuales (un día con evento_externo no ensucia el patrón). MITs rediseñados:
   ya no son texto libre en `Diario` — un MIT no resuelto se crea como fila en `Tareas` (`Tipo=MIT`) y
   queda pendiente sin límite hasta marcarlo hecho; el cierre los muestra todos (hoy + acumulados) y el
   brief de las 8:00 los separa en "de hoy" vs "acumulados" (solo lectura). **Riesgo cruzado con
   Productividad:** esos MITs viven en la misma hoja `Tareas` que usa `modules/proyectos.py` — si Nico
   interactúa con un MIT a través de `tarea_listar`/`tarea_completar` (no del panel del cierre), pisa el
   bug de columnas de Productividad (ver ítem 6 abajo) y puede no encontrarlo o mostrarlo mal. 35 evals
   unitarios verdes (`tests/test_salud.py`) + `Semanal` se genera por primera vez (job domingo 22:30).
   Semana de 7 días estable: **sin confirmar**.
3. **Compras** `cmp_` — ⬜ pendiente. Sin `modules/compras.py`; ni Fase 1 (lista manual) tiene código.
4. **Recordatorios/Calendario** `rec_` — ⚠️ **riesgo, más que parcial**. `modules/recordatorios.py` lee
   `Dia_Fecha`/`Monto_Aprox`/`Ultimo_Aviso` — ninguna existe en la planilla real (`Día / Fecha`, `Monto
   aprox`, `Última acción`). Efecto real: **`rec_proximos` siempre devuelve "no hay recordatorios"**, sin
   importar lo que tengas cargado — el brief nunca te avisa un pago. Y `rec_agregar` escribe **7 valores
   en una hoja de 8 columnas con nombres distintos**: `aviso_dias` termina en la columna `Estado` y `"Sí"`
   en `Posposiciones` — cada recordatorio nuevo que crees por chat queda con esas dos columnas corrompidas.
   **No uses `rec_agregar` hasta que esto se arregle.** Tampoco está la escalera (domingo + T-2 + T-0 con
   ✅Hecho), el posponer-exige-fecha, ni el "nombra el patrón" tras 3 posposiciones — pero el bug de
   columnas es más urgente que el scope faltante: hoy el módulo no hace lo que ya dice que hace.
5. **Correo** `cor_` — 🔶 parcial. `modules/spam.py` + `core/correo.py` construidos y enganchados
   (digest de spam, archivar/conservar por toque — Gmail etiqueta `Donna/Archivado` + quita `INBOX`,
   Outlook mueve a la carpeta `Donna Archivado`; ninguno de los dos borra). El bucket "importante→resumen
   brief" todavía no es visible en el código; el bucket financiero ya lo cubre Finanzas
   (`ingerir_gastos_email`, Gmail-only, Outlook OFF por canon).
6. **Productividad** `prod_`/`apr_` — ⚠️ **riesgo, más que parcial**. `modules/proyectos.py` tiene el mismo
   patrón de bug que Recordatorios: `Proyectos` real no tiene columna `ID` (`_buscar_proyecto`/`_avance`
   quedan comparando contra `""` siempre → **todos los proyectos activos muestran el mismo avance,
   contando TODAS las tareas de la hoja**, no las suyas — el número que ves está mal, no solo incompleto).
   `tarea_listar` lee `Descripcion`/`Prioridad` (sin tilde / columna que no existe) → **muestra "None" en
   vez de la descripción real de la tarea**. `tarea_crear` escribe **11 valores en una hoja de 8
   columnas** → cada tarea nueva por chat queda con las columnas corridas (mezcla ID/prioridad en celdas
   equivocadas). `tarea_completar` busca la columna `Descripcion` (sin tilde) con `headers.index(...)` →
   no la encuentra, tira excepción, siempre falla con "no pude completar la tarea". **No uses
   `tarea_crear`/`tarea_completar`/`proy_listar` hasta que esto se arregle** — y ojo: los MITs de Salud
   (`Tipo=MIT`) viven en esta misma hoja `Tareas`; si los tocas con estas tools rotas en vez del panel del
   cierre, te vas a topar con el mismo problema. La reconciliación nocturna, el tiempo-por-frente en
   `Semanal` y el factor de optimismo **tampoco están construidos**; `modules/tiempo.py` sigue dormido
   como manda el canon.
7. **Proactividad** `pro_` — 🔨 completo el scope base. `modules/proactividad.py` prioriza compromiso
   vencido > proyecto en riesgo > meta atrasada; el tope de 1/día está enforced en `core/scheduler.py`
   (`job_ya_corrio("proactividad")`). El scope ampliado (alerta de presupuesto al 90%, nudge de familia,
   alertas de Compras Fase 2) depende de módulos que aún no existen (Familia, Compras Fase 2), así que
   sigue pendiente.
8. **Familia** `fam_` — ⬜ pendiente. Sin `modules/familia.py`.

**Transversal (la espina):** `modules/aprendizaje.py` construido (calibración por dominio, patrones con
decay, guardia anti-patrones-falsos) y el correlador ya corre con 2 dominios vivos (Finanzas + Salud), antes
de lo que sugiere la secuencia del roadmap.

## Auditoría contra la planilla real (2026-07-01, actualizada 2026-07-02)

Se descargó y comparó el workbook "Donna" real de Google Drive contra el código. Estado actual:

**Ya resuelto desde la primera auditoría** (no repetir el trabajo):
- Tab `Metas` — creado (`setup_sheets.py` corrido contra la planilla real).
- Tab `Ideas` — creado (idem).
- `⚙️ Config` — `setup_sheets.py` ya referencia el nombre real (con el emoji); no hay riesgo de tab
  duplicado. Sigue siendo decorativo (ningún módulo lo lee), pero eso es una decisión de diseño, no un bug.
- Correo — `trash`/`delete` reemplazados por etiquetar/mover (ver ficha de Correo). Invariante cumplido.

**Calza (verificado con datos reales):**
- El faro de deuda da exacto $2.028.091 / $48.236 en las celdas ya calculadas.
- Las fechas de `Diario`/`Transacciones` están en `yyyy-mm-dd` — calzan con lo que el código busca.
- La Intención del gasto (Finanzas v2) se está escribiendo en las transacciones recientes.

**⚠️ Nuevo, el más grave de todos — Recordatorios y Productividad escriben sobre el schema real
equivocado, y no es "falta scope", es corrupción de datos activa:**
- `modules/recordatorios.py` lee `Dia_Fecha`/`Monto_Aprox`/`Ultimo_Aviso`; la planilla real tiene
  `Día / Fecha`/`Monto aprox`/`Última acción`. Resultado: **`rec_proximos` siempre da "no hay
  recordatorios"** — el aviso de un pago nunca sale, aunque esté cargado. Y `rec_agregar` escribe 7
  valores en una hoja de 8 columnas reales → **cada recordatorio nuevo por chat corrompe `Estado` y
  `Posposiciones`** (les mete `aviso_dias` y `"Sí"` en vez de lo que corresponde).
- `modules/proyectos.py` (Proyectos + Tareas): `Proyectos` real no tiene columna `ID` → `_avance()`
  siempre compara contra `""`, así que **todos los proyectos activos muestran el mismo conteo, sumando
  TODAS las tareas de la hoja** (no las suyas — el número está mal, no solo ausente). `tarea_listar` lee
  `Descripcion`/`Prioridad` (sin tilde / no existen) → **muestra "None" en vez del texto real de la
  tarea**. `tarea_crear` escribe 11 valores en una hoja de 8 columnas → **cada tarea nueva por chat
  corrompe las columnas** (ID y prioridad terminan en celdas equivocadas). `tarea_completar` busca
  `headers.index("Descripcion")` (sin tilde) → no la encuentra, tira excepción, siempre falla.
- **Consecuencia directa para Salud:** los MITs (`Tipo=MIT`) ahora viven en esta misma hoja `Tareas`. Los
  que crea/marca el panel del cierre usan las columnas correctas (por eso funcionan), pero si tocas un
  MIT vía `tarea_listar`/`tarea_completar` en vez del panel, te vas a topar con este mismo bug.
- **Mientras no se arregle:** evita `rec_agregar`, `tarea_crear`, `tarea_completar` y no confíes en el
  avance que muestra `proy_listar` — todo lo demás de esos dos módulos (lectura de `Estado`/`Completada`
  para filtrar pendientes, por ejemplo) sí usa columnas reales y funciona bien.

**Gaps más chicos, siguen abiertos:**
- **Colisión de nombres:** `modules/metas.py` (legacy, tab `MetasSemanales` que tampoco existe en la
  planilla real) sigue con `metas_get_semana`/`metas_actualizar` registradas junto a `fin_metas`/
  `fin_aportar_meta` — descripciones casi idénticas, riesgo de que el LLM llame la equivocada.
- **`Categorias` real tiene 14 categorías** (incluye GGCC, Hijo, Tecnología, Ropa, Educación,
  Entretenimiento, Tarjeta Crédito) pero el mapeador por palabra clave de `finanzas.py` solo cubre 6 y
  cae a `"Otros"` — categoría que ni existe como fila real (ahí el cajón default es `"Otro Gasto"`).
- `Recordatorios` real todavía tiene la fila placeholder `"(verifica tu 9° recordatorio de Vida_v6)"` sin
  limpiar, y `⚙️ Config` tiene `Telegram Chat ID = "(llenar)"` sin llenar (inofensivo, nada lo lee).

---

*El gate "un módulo a la vez" ya lo decidiste (lo llevas junto con arreglos puntuales a lo construido,
no en secuencia estricta). Lo único pendiente de decidir: cuándo entra Productividad/Recordatorios a
arreglarse — hoy tienen bugs de escritura activos, no solo scope incompleto.*
