# Roadmap Modular — Donna

**Para:** Nico
**Qué es:** la re-secuencia de la entrega. Un módulo a la vez, completo, probado 1 semana, antes del siguiente. La memoria de Donna (la espina) crece con cada módulo.
**Acompaña a:** `CLAUDE.md` (contrato + invariantes), `Plan_Construccion_v7.md` (pasos de build por brecha), `Spec_Herramientas_Nuevas.md` (detalle de tools). **Después de los 8 módulos:** la expansión a negocios/contenido está en `Vision_Donna_Ampliada.md` (fases N1–N5, escalera de autonomía).

**Nota (2026-07-17):** `Donna_Canonico.xlsx` se borró del repo (estaba desactualizado). La versión
vigente del esquema de datos vive en el Google Drive de Nico, fuera del repo — no hay copia local que
mantener sincronizada.

---

## Regla madre
Un solo Donna (un repo). Se construye y prueba **un módulo a la vez**. No empiezas el siguiente hasta que el actual pase su semana.

**Gate en dos estados (híbrido — decidido 2026-07-17):**
- **🔨 construido** = scope de la ficha completo + deployado + **todos sus tests manuales de
  `Tests_Aceptacion_Manual.md` en verde** (+ evals de `tests/` verdes). Esto es lo que habilita
  empezar a *usarlo* de verdad.
- **✅ promovido** = además **7 días corriendo estable** en producción. Recién ahí, módulo siguiente.

(Mientras no haya telemetría real de producción, "construido" se apoya en los tests manuales; los
"7 días estables" siguen siendo el sello final de "promovido". Los dos docs —este y
`Tests_Aceptacion_Manual.md`— ahora usan esta misma definición.)

## Cadencia (cómo se trabaja cada módulo)
1. Rama git `modulo/<nombre>`.
2. Sesión nueva de Claude Code, contexto limpio, apuntando a `CLAUDE.md` + la ficha del módulo. (Una sesión por módulo = dejas de perder info entre frentes.)
3. En `Config`, el módulo en construcción es el único **ON**; el resto dormido (para que no escriban basura).
4. Construir hasta "completo" (ver ficha) → correr su eval → merge a `main` + deploy.
5. **Actualizar los docs con lo nuevo construido** (ver "Al cerrar un módulo" abajo). Parte del "completo", no opcional.
6. Empieza la **semana de prueba**: tu único trabajo es usarlo y anotar lo que se rompe. **No construyes el siguiente.**
7. 7 días estable + evals verdes → **promovido**. Recién ahí, módulo siguiente.

## Al cerrar un módulo: actualizar los docs (obligatorio, parte de "completo")
Ningún módulo se da por cerrado hasta que los documentos vivos reflejen lo que se construyó. En la
**misma sesión/PR** en que se termina o se extiende un módulo, actualiza:
- **`docs/Tests_Aceptacion_Manual.md`** — agrega/reescribe la sección del módulo con los tests físicos
  que Nico debe correr, listando las **tools reales** cableadas, los **comandos** y los **botones**
  tal como quedaron en el código (no como estaban en la ficha). Si un flujo cambió (ej. un botón que
  se reemplazó por chips), corrige el test viejo en vez de dejar el obsoleto. Marca el estado en el
  índice (✅/🔶/⬜).
- **El tablero de este archivo** (`Roadmap_Modular.md`) — mueve el módulo de estado y anota, con fecha,
  qué se agregó y cuántos evals quedaron verdes.
- **`docs/Spec_Herramientas_Nuevas.md`** — si se agregaron/cambiaron tools, deja su ficha al día.
- **`CLAUDE.md`** (canon) — solo si la decisión de diseño cambió algo del contrato o los invariantes.

Regla práctica: si tocaste `TOOLS`/`HANDLERS`, un teclado de `flows.py`, un `CommandHandler` de
`main.py` o un job de `scheduler.py`, algo en `Tests_Aceptacion_Manual.md` casi seguro quedó desfasado
— revísalo antes de cerrar. Un doc desactualizado cuenta como trabajo sin terminar.

## La espina de memoria (transversal — ver CLAUDE.md)
No es un módulo: es una espina que cruza todo. Cada módulo, como parte de "completo", **escribe sus inferencias y episodios a Supabase**. Cinco tipos: `perfil` (estable), `memoria` (episódica), `inferencias` (con dato), `compromisos`, `aprendizaje` (calibración).
- **Correlador:** se enciende con ≥2 módulos vivos (o sea, desde Salud). Propone cruces, los valida contra el dato, descarta los espurios, guarda los que aguantan.
- **Vista `/perfil` editable ("lo que sé de ti"):** se construye en el Módulo 1 (vacía, crece con cada módulo). Muestra perfil + inferencias top con su dato; corriges y eso calibra.
- **Surfacing:** bajo demanda + resumen domingo + **proactivo cuando es accionable** (esto último aterriza en el Módulo 7).

## Ficha de módulo (plantilla — se rellena igual cada vez)
> Objetivo · Scope ("completo") · Prefijo · Datos (hojas + Supabase) · Aporte a la espina · Eval que lo gatilla · **Docs actualizados** (tests manuales + tablero + spec de tools) · Semana cumplida.

---

## Los 8 módulos

### 1. Finanzas `fin_`
- **Objetivo:** capturar tu plata sin fricción y mostrarte la verdad de tu deuda.
- **Scope completo:** foto + manual + categorización + faro de deuda (con línea) + dashboard + digest nocturno en el cierre. **Correo NO** (va en Módulo 5).
- **Scope v2 (añadido):** **intención del gasto** — columna `Intencion` (Necesario/Inversión/Deseo) en `Transacciones`, la infiere el extractor y la confirmas en el digest (sin fricción nueva); resumen mensual por intención. **Metas financieras con progreso** — tab `Metas` (`Meta · Objetivo · Actual · Progreso`), 2-3 metas (fondo de emergencia, pagar TC), leídas en el `Semanal`/digest. **Sin input diario.** *(No entra: cuentas con saldos auto / doble-entrada — rompe "registro sin fricción".)*
- **Scope v3 (detalle de compra — alimenta la predicción de Compras):** la boleta deja de ser un solo total y se vuelve **ítem por ítem**.
  - **Foto ítem-a-ítem:** `procesar_foto` lee cada ítem + precio + total → escribe el detalle en la hoja nueva `Compras_Detalle` (`Fecha · Comercio · Item · Precio · Categoria · Predecible · ID_Tx` — 7 columnas desde la auditoría del 2026-07-24; ver el tablero).
  - **Correlación foto↔correo (jamás doble conteo):** el correo del banco es el **total canónico** (medio + monto confirmado); la foto aporta los **ítems**. Se aparean por **monto total + fecha (±1-2 días) + comercio** (fuzzy / vía reglas de comercio) → **una** transacción en `Transacciones` + sus líneas en `Compras_Detalle`. Hoy se contarían dos veces porque la foto lee "ALMACEN SAN VALENTIN" y el correo "MERCADOPAGO*SANVA"; el matcher lo resuelve por monto+fecha.
  - **Captura al momento:** cuando entra un cargo de un **comercio marcado "de compras"** (súper, almacén, San Valentín) **sin detalle**, Donna pregunta en el momento *"vi $X en San Valentín — ¿qué compraste?"* → respondes con **foto** (→ ítems) o con **desglose por categoría** ("2000 en chanchería, el resto pan" → 2000 Chanchería + resto Pan, el "resto" cuadra al total). Es un prompt **transaccional**, no cuenta contra el tope 1/día de Proactividad.
  - **Filtro de predicción:** cada línea se marca `Predecible` = **sí solo para despensa/reposición** (arroz, atún, fideos, aceite, azúcar, papel, limpieza) y **no para lo cotidiano/perecible** (pan, chanchería, verdura, comida preparada). **Solo las `Predecible=sí` alimentan el predictor de Compras Fase 2.**
- **Datos:** Sheets `Transacciones`/`Categorias`/`Tarjetas y Deuda`/`Dashboard`/`Metas`/`Compras_Detalle`; Supabase `inferencias`.
- **Espina:** nace mínima. Siembra `perfil` con lo que ya sabemos de ti; escribe inferencias de gasto/deuda. **Se construye la vista `/perfil` (aún corta).** Sin correlación todavía.
- **Eval:** foto→categoría correcta · "aceptar todo" escribe sin duplicar · faro **calza con `Tarjetas y Deuda` B4:B8** (cifra viva, no hardcodeada; ~$2.297.966 tras v4) e intereses muertos $48.236 · el freno muestra la deuda antes de una cuota · la intención se infiere y se corrige en el digest · una meta muestra su % de avance · foto+correo del mismo gasto = **una** transacción (no dos) · un desglose "2000 chanchería, resto pan" cuadra al total · arroz/atún quedan `Predecible=sí`, pan/chanchería `no`.
- **Semana:** 7 días registrando gastos reales, estable, evals verdes.

### 2. Salud `sal_`
- **Objetivo:** el eje #1 (sueño) + hábitos, ánimo, nutrición y ritmo diario.
- **Scope completo:** `Diario` (ejercicio, meditación, sueño 7h, ánimo 1-4, hora dormí, MITs) + brief 8:00 (lectura) + cierre 22:00 (toques) + señal sueño×ánimo.
- **Scope ampliado (añadido):**
  - **Nutrición (retirada del cierre):** los toques de **agua**/**proteína** se sacaron del panel del cierre; `Diario` +`Agua`, +`Proteina` quedan como columnas legado sin capturar.
  - **Ventanas (ayuno + sueño):** `Diario` +`Primera_Comida`, +`Hora_Despertar` (ya existen `Ultima_Comida` y `Hora_Dormi`) → **resumen semanal de ventanas**: mediana de la ventana de comida (1ª→última) y de sueño (dormir→despertar), semana vs fin de semana. **Solo medir, sin meta todavía** (cuando haya 2-3 semanas de baseline, recién ahí se propone ventana objetivo — canon "calla hasta tener datos").
  - **Peso:** `Diario` +`Peso` (kg), pedido **cada cierre** (22:00), no solo domingo; muestra tendencia.
  - **Score % semanal de hábitos:** número único calculado el domingo en `Semanal` (`Score_Habitos`). Composición default (revisable): sueño 7h, ejercicio, meditación.
  - **Eventos contextuales:** pregunta en el cierre — *"¿hubo algo hoy fuera de tu control que te bajó el ánimo o no te dejó hacer lo planeado?"* → texto libre → `memoria` episódica con tag `evento_externo`. **El correlador trata ese día como contexto, no como patrón** (guardia anti-patrón-falso).
  - **Revisión dominical (touchpoint visible):** domingo 22:30 Donna manda la revisión de la semana en su voz (score + ventanas + peso con tendencia) Y los cruces del correlador vigentes con botones *sí/no/corregir* — Nico puede reeditar hasta los ya confirmados si algo se ve raro. Escribe `Semanal` como antes; ahora además surfacing a Telegram. Registrado en `jobs_log` + recuperado por `check_pendientes` (antes se perdía mudo si Railway estaba caído a las 22:30).
- **Datos:** Sheets `Diario`/`Semanal`; Supabase `inferencias`/`memoria`.
- **Espina:** **se enciende el correlador** (2º dominio). Primeros cruces: sueño↔ánimo; con finanzas, sueño↔gasto; y ahora ventana/nutrición↔ánimo.
- **Eval:** marcas hábitos por botón → fila correcta · señal coherente · el cruce sueño↔ánimo aparece con su dato · el resumen de ventanas da medianas coherentes · el score % cuadra con los toques de la semana · un evento contextual marca el día como contexto · la revisión dominical llega con los números correctos y sus cruces editables.
- **Semana:** 7 días de cierre real, estable, evals verdes.

### 3. Compras `cmp_`  ⟵ NUEVO
- **Objetivo:** que no se te olvide qué comprar; lo dices suelto y Donna lo guarda.
- **Scope completo (Fase 1 — lista manual):** `cmp_agregar` ("Donna falta toalla nova" / "queda poco arroz, anótalo") → guarda en la lista; `cmp_lista` ("Donna dame la lista del súper") → devuelve **exactamente** lo pendiente; marcar comprado por toque → sale de la lista. Hoja nueva `Compras` (`Item · Estado(pendiente|comprado) · Fecha_Agregado · Fecha_Comprado · Categoria`).
- **Fase 2 (DIFERIDA — no en este módulo):** motor de frecuencia. **Lee dos fuentes** de eventos de compra (item, fecha): (a) la **lista Fase 1** (ítems marcados `comprado`) y (b) las líneas **`Predecible=sí`** de `Compras_Detalle` que escribe Finanzas v3 (foto + desglose). Calcula el intervalo medio por ítem → infiere reposición → alerta *"puede que toque comprar arroz"* (sale por **Proactividad**). Se persiste en Supabase (`aprendizaje`). **Solo despensa/reposición** (arroz, atún, fideos, limpieza); **nunca lo cotidiano/perecible** (pan, chanchería) — esos quedan fuera del predictor por diseño.
- **Datos:** Sheets `Compras` (Fase 1) + `Compras_Detalle` (lee, lo escribe Finanzas); Supabase `aprendizaje` (recién en Fase 2).
- **Espina:** Fase 1 siembra el historial de compras con fecha; Fase 2 lo cruza con el detalle predecible de las boletas (insumo del predictor).
- **Eval:** "falta X" agrega sin duplicar · "dame la lista" devuelve solo lo pendiente · marcar comprado lo saca y registra la fecha.
- **Semana:** 7 días usándolo de verdad (agregar al vuelo + pedir la lista antes de ir al súper).

### 4. Recordatorios + Calendario `rec_`  ⟵ **REDECIDIDO 2026-07-23: fusión real, es el siguiente en construirse**
- **Objetivo:** que no se te olvide nada, sin importar si vive en la hoja `Recordatorios` o en tu Google
  Calendar — una sola escalera que mira ambas fuentes.
- **Por qué se redecide ahora:** la ficha original ya traía "lectura del Google Calendar en el brief"
  como scope menor de Recordatorios. Se decidió subirlo de rango: **antes** de cerrar el scope pendiente
  de la escalera, se construye el módulo de Calendario en serio y se **fusionan** — no van a quedar como
  dos cosas separadas que Nico tiene que revisar por separado.
- **Scope completo (ampliado):**
  - Escalera (domingo + T-2 + T-0 con ✅ Hecho + vencido-insiste) + estados (pendiente/hecho/pospuesto) +
    tipos (mensual/anual/única) + posponer con fecha — **ya construido** (Fase 0, ver auditoría abajo).
  - **Lectura ampliada de Calendar:** `core/agenda.py` hoy solo tiene `eventos_de_hoy()` (usado por
    `leer_agenda`, solo hoy). Se extiende a un rango (próximos N días) para que la escalera pueda ver
    eventos con fecha próxima igual que ve filas de `Recordatorios`.
  - **Escritura real:** `agenda.crear_evento()` ya existe en el código (SCOPES ya en modo escritura) pero
    **no está conectado a ningún tool** — se cablea como tool real (ej. `rec_agendar`) para que "agéndame
    la reunión con X el jueves a las 5" cree el evento de verdad.
  - **Fusión (la pieza nueva):** un recordatorio con fecha (`rec_agregar`) también genera su evento en
    Calendar; un evento de Calendar que matchee el patrón de compromiso entra a la misma escalera de
    avisos T-2/T-0. Una sola fuente de "qué se viene" — no dos paneles que revisar por separado.
- **Prefijo:** `rec_` (agenda sigue siendo servicio `core/`, como `sheets`/`memory` — no es un módulo con
  prefijo propio, es infraestructura que este módulo consume).
- **Datos:** Sheets `Recordatorios`; Google Calendar (lectura ampliada + escritura vía service account).
- **Espina:** inferencias de cumplimiento ("pospones el IVA seguido") → un "contra" con dato; ahora
  también sobre eventos de calendario pospuestos/reagendados, no solo filas de `Recordatorios`.
- **Eval:** T-2/T-0/vencido disparan cuando deben (ya verde) · posponer sin fecha se rechaza (ya verde) ·
  tras 3 posposiciones, nombra el patrón (ya verde) · **nuevo:** un evento de Calendar con fecha próxima
  aparece en la escalera junto a los recordatorios de Sheets · crear un recordatorio con fecha genera el
  evento correspondiente en Calendar · "agéndame X el jueves a las 5" crea el evento real y devuelve el
  link.
- **Semana:** 7 días con la escalera fusionada corriendo (recordatorios + eventos en un solo lugar).

**Después de este módulo, el siguiente es Correo `cor_`** (cerrar el bucket "importante→resumen brief"
que falta — ver ficha 5). Productividad, Proactividad-ampliado y Familia quedan después de Correo.

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
**Addendum 2026-07-16/17:** canon v8 (dos sombreros/dos planillas) + Tanda 1 (esperas unificadas) + fixes
del brief (heartbeat de diagnóstico, `/brief` a demanda, fecha determinista) + cierre rediseñado (peso
cada noche, franjas de comida, MITs/evento por voz) + digest vivo (mensaje anclado, chips top-3, commit
único) — ver los ítems 1 y 2 del tablero y el bloque "Trabajo transversal reciente" abajo.

Estados: ⬜ pendiente · 🔨 construido (scope de la ficha completo) · 🔶 parcial (falta scope de la ficha) ·
🧪 prueba sem X/7 · ✅ promovido · ⚠️ riesgo (viola un invariante duro de `CLAUDE.md`, o el código
escribe/lee mal contra el schema real de la planilla — más grave que "falta scope")

**Nota importante:** la regla madre de este documento ("un módulo a la vez, 7 días estable antes del
siguiente") ya no se está siguiendo — el código de casi todos los módulos existe en paralelo. Este tablero
registra ese hecho en vez de fingir que la secuencia se respetó.

1. **Finanzas** `fin_` — 🔨 completo (v1 + v2 intención/metas + v3 detalle ítem-a-ítem/correlación) **+ v4
   NUEVO (2026-07-05): estados de cuenta automáticos.** `modules/estados_cuenta.py` baja del correo los
   PDF de Banco de Chile y Mach, los descifra (Mach con RUT, BCh con clave propia en `.env`), extrae con
   Haiku las cifras de deuda por producto, actualiza las celdas-input del faro (`Tarjetas y Deuda`, las
   fórmulas se recalculan solas), lleva el historial mes a mes en la hoja nueva `Deuda_Mensual`, reconcilia
   las compras del estado contra `Transacciones` (marca las que faltan, sin auto-escribir) y avisa a Nico
   cuando llegan estados nuevos con el detalle y el delta vs. el mes anterior. Tool `fin_progreso_deuda`.
   Job diario 9:30 (dedup interno → solo actúa ~mensual). Validado end-to-end contra los PDFs reales de
   Nico: corrigió el faro de $2.028.091 (desactualizado) a **$2.297.966** (real) y encontró 11 compras de
   junio sin registrar (ya agregadas con categoría, con nueva categoría `Regalo` creada de paso).
   46/46 evals unitarios verdes (`test_finanzas.py` + `test_estados_cuenta.py`). **+ digest vivo
   (2026-07-17):** el digest nocturno pasa de una serie de mensajes sueltos a **un solo mensaje anclado**
   que se edita en el lugar (`core/flows.py`) — deja de inundar el chat. Muestra **chips top-3 aprendidos**
   (categorías/comercios que Donna ya infirió con confianza, para confirmar con un toque en vez de
   tipear) e **ítems por excepción** (solo lo que no pudo clasificar solo). Escribe todo en **un commit
   único** a Sheets al cerrar, no fila por fila. 177 líneas de test nuevas (`tests/test_digest_vivo.py`).
   **+ Fase 4/5 (2026-07-27), a partir de feedback real de Nico:** tool nueva `fin_movimientos_recientes`
   ("muéstrame mis cargos"/"qué he gastado") — antes no existía ninguna forma de listar movimientos
   individuales, solo totales agregados (`fin_saldo_mes`). Y botón **✎** en la grilla de ítems del
   digest para corregir el NOMBRE de un ítem mal leído por foto/dictado — a diferencia de la
   categoría, esta corrección **se aprende** (tabla `items_nombres`, migración 016, mismo patrón que
   `items_predecibles`): la próxima vez que el mismo texto crudo aparezca, sale ya corregido.
   21 tests nuevos entre `test_finanzas.py`/`test_digest_vivo.py`/`test_brain_hints.py`.
   Semana de 7 días estable: **sin confirmar**.
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
   **+ cierre rediseñado (2026-07-16):** peso ahora se pide **cada cierre** (antes solo domingo);
   horas de comida capturadas en dos franjas fijas (`6-12` / `18-01`, antes una sola ventana ambigua);
   MITs y evento contextual del día ahora se capturan **por texto o por voz** indistintamente (antes solo
   por chip); y el panel completo pasó a **cadena de una pregunta a la vez** en vez de un formulario con
   todo junto — corta el abandono a mitad de cierre. `core/scheduler.py` + `core/frases.py` tocados;
   35+ tests nuevos entre `test_salud.py`/`test_scheduler.py`/`test_frases.py`/`test_ux_fase0.py`.
   **+ primera comida a mediodía (2026-07-27):** Nico reportó que nunca la contestaba en el
   cierre — a las 22:00 ya se le había olvidado lo que comió a las 8 de la mañana. Se sacó de
   `teclado_cierre` y ahora es un aviso propio a las 12:30 (`job_primera_comida`, no 12:00 para
   no chocar con Proactividad), que además **calla si Nico ya la contó por su cuenta** antes de
   esa hora (`salud.ya_registro_primera_comida`). 8 tests nuevos.
   Semana de 7 días estable: **sin confirmar**.
3. **Compras** `cmp_` — 🔨 **Fase 1 construida (2026-07-05).** `modules/compras.py`: lista manual del
   súper. `cmp_agregar` ("falta arroz", "queda poco atún, anótalo" → parser determinista, sin LLM, dedup
   por nombre), `cmp_lista` (devuelve lo pendiente), `cmp_comprado` ("ya lo compré / tacha el X"). Hoja
   nueva `Compras` (Item · Estado · Fecha_Agregado · Fecha_Comprado · Categoria). **Toque:** comando
   `/lista` manda la lista tocable (un ✅ por producto → lo saca y registra la fecha). Validado
   end-to-end contra la planilla real; 7 tests (`tests/test_compras.py`). **Fase 2 (predictor de
   reposición) sigue DIFERIDA** por canon — no se construyó.
   **Pista de aterrizaje de la Fase 2 (2026-07-24/25):** se auditó de dónde saldrían sus datos y no
   había ninguno (`Predecible=sí` en 0 de 65 líneas, lista Fase 1 en 0 filas). Los pasos 1-3 del
   plan ya están hechos (el chip 📦/🥖 aprende · el clasificador conoce la despensa real · la
   boleta se pide y se pega al cargo en las compras grandes); faltan el 4 (usar la lista, es
   conductual) y el 5 (el gate de datos). Ver la sección de más abajo — **la Fase 2 no se abre
   hasta que el gate del paso 5 dé verde**, y hoy da 0.
4. **Recordatorios/Calendario** `rec_` — 🔶 parcial (el bug de schema quedó **cerrado**, falta scope).
   **⟵ SIGUIENTE EN LA SECUENCIA (redecidido 2026-07-23, ver ficha 4 arriba): antes de cerrar el scope
   restante se construye Calendario en serio y se fusiona con Recordatorios en un solo módulo.**
   **Fase 0 · A1 hecho** (commit `fix(recordatorios): schema real`): `modules/recordatorios.py` ahora lee/
   escribe las columnas reales (`Día / Fecha`, `Monto aprox`, `Estado`, `Posposiciones`, `Última acción`,
   `Activo`), soporta tipo `única` (fechas que no se repiten, quedan negativas si vencen), incluye los
   vencidos en `rec_proximos` y appendea 8 valores en el orden correcto. `rec_agregar` ya no corrompe
   columnas; el brief vuelve a avisar pagos. **Fase 0 · C4 hecho:** `recordatorios.vencidos()` +
   `marcar_hecho()` — el brief empuja los vencidos a diario con botón ✅ Hecho hasta que se marcan.
   9 tests de regresión (`tests/test_recordatorios.py`). **Sigue pendiente el scope de la ficha:** la
   escalera completa (domingo + T-2 + T-0, ya construida) más lo **nuevo** de la fusión — `core/agenda.py`
   hoy solo lee eventos de hoy (`leer_agenda`) y tiene `crear_evento()` escrito pero sin conectar a
   ningún tool; falta ampliar la lectura a un rango de días, cablear la escritura, y fusionar
   recordatorio↔evento en una sola escalera.
5. **Correo** `cor_` — 🔶 parcial. `modules/spam.py` + `core/correo.py` construidos y enganchados
   (digest de spam, archivar/conservar por toque — Gmail etiqueta `Donna/Archivado` + quita `INBOX`,
   Outlook mueve a la carpeta `Donna Archivado`; ninguno de los dos borra). El bucket "importante→resumen
   brief" todavía no es visible en el código; el bucket financiero ya lo cubre Finanzas
   (`ingerir_gastos_email`, Gmail-only, Outlook OFF por canon).
6. **Productividad** `prod_`/`apr_` — 🔶 parcial (el bug de schema quedó **cerrado**, falta scope).
   **Fase 0 · A2 hecho** (commit `fix(proyectos): opera por nombre`): `modules/proyectos.py` opera por
   NOMBRE sobre el schema real, sin IDs fantasma. `_avance` cuenta solo las tareas del proyecto pedido
   (antes contaba TODAS) y excluye los MITs de Salud; `tarea_listar` muestra la `Descripción` real (no
   "None"); `tarea_crear` appendea 8 valores en el orden real (idéntico a como Salud crea un MIT);
   `tarea_completar` usa el patrón robusto de `salud._fila_mit` y por fin funciona. 7 tests de regresión
   (`tests/test_proyectos.py`). **Fase 0 · B1/B2 hecho:** `metas`/`tiempo` desregistrados del brain
   (hojas inexistentes; `tiempo.py` sigue dormido por canon). **Sigue pendiente el scope de la ficha:**
   reconciliación nocturna, tiempo-por-frente en `Semanal` y factor de optimismo **no están construidos**.
7. **Proactividad** `pro_` — 🔨 completo el scope base. `modules/proactividad.py` prioriza compromiso
   vencido > proyecto en riesgo > meta atrasada; el tope de 1/día está enforced en `core/scheduler.py`
   (`job_ya_corrio("proactividad")`). El scope ampliado (alerta de presupuesto al 90%, nudge de familia,
   alertas de Compras Fase 2) depende de módulos que aún no existen (Familia, Compras Fase 2), así que
   sigue pendiente.
8. **Familia** `fam_` — ⬜ pendiente. Sin `modules/familia.py`.

**Transversal (la espina):** `modules/aprendizaje.py` construido (calibración por dominio, patrones con
decay, guardia anti-patrones-falsos) y el correlador ya corre con 2 dominios vivos (Finanzas + Salud), antes
de lo que sugiere la secuencia del roadmap.

## Trabajo transversal reciente

### El brief mismo (touchpoint, no un módulo) — 2026-07-16

Tres commits seguidos sobre `core/scheduler.py`, ninguno es un módulo del roadmap: arreglan y amplían el
touchpoint de las 8:00 en sí.
- **Heartbeat de diagnóstico en el brief (F1):** `core/diagnostico.py` ahora empuja al brief si algo se
  rompió en las últimas 24h (antes solo se consultaba bajo demanda con `diag_estado`) — Donna avisa sola
  en vez de que Nico tenga que preguntar. 26 líneas de test nuevas.
- **Comando `/brief` a demanda (F1):** Nico puede pedir el brief en cualquier momento, de solo lectura —
  **no consume** el brief programado de las 8:00 (si lo pide a las 10:00, igual llega el de las 8:00 al
  día siguiente sin saltarse). `main.py` + `core/scheduler.py`.
- **Fix día/fecha deterministas + domingo silencioso:** el brief calculaba día de semana y fecha con
  lógica que podía desincronizarse; ahora es determinista. La revisión dominical (Módulo 2, ítem "Salud")
  **fallaba en silencio** si Railway estaba caído a las 22:30 — ahora, si no corrió, se detecta y no se
  pierde muda (mismo espíritu que `jobs_log`/`check_pendientes` ya documentado en el ítem 2 del tablero).

### El cierre y el cerebro, a partir de 3 bugs reales reportados por Nico (2026-07-27)

Nico reportó tres síntomas en una sola sesión: una inferencia repetida ~10 veces seguidas, el
digest financiero que un día no llegó, y Donna diciendo "Nico. Jueves." en un mensaje del cierre
de un domingo. Investigación en el código (no reproducido en vivo, sin acceso a logs de Railway)
encontró causas concretas para las tres, todas en `core/scheduler.py`/`core/brain.py`:

- **`job_cierre` resiliente por paso.** Antes encadenaba 6 pasos sin aislar errores (ingesta de
  correo → intro → panel → digest → inferencia) y solo marcaba `jobs_log` al final. Si un paso
  temprano tronaba (el candidato concreto: `fin_aplicar_correlacion()` sin proteger dentro de
  `ingerir_gastos_email`), todo lo que venía después se caía SIN marcar nada — así que un
  reinicio de Railway en esa ventana repetía el cierre completo desde cero: el digest nunca
  llegaba (se caía antes de esa línea) y lo que sí alcanzaba a mandarse antes del fallo se repetía
  en cada reintento. Ahora cada pieza visible (`cierre:ingesta`/`panel`/`digest`/`inferencia`)
  se marca por separado; un reintento solo repite lo que de verdad no salió.
- **Fecha real inyectada al cerebro.** El encabezado determinista de fecha (`📅 Domingo 26/07`)
  solo existía en el brief, antepuesto AL texto del LLM. En el cierre y en cualquier chat libre,
  el modelo nunca recibía la fecha real — podía inventar un día de la semana que no calzara.
  `brain._armar_contexto` ahora inyecta `_fecha_hoy()` (mismo criterio determinista) SIEMPRE,
  para brief, cierre, proactividad y chat por igual.

6 tests nuevos (`test_scheduler.py` + `test_brain_fecha.py` nuevo). Sin confirmar aún en
producción — pendiente de que Nico observe si el patrón no vuelve a repetirse.

### Canon v8 + Tanda 1 (2026-07-16 — cableado, aún sin commitear al abrir la sesión)

Dos piezas que cruzan módulos, no son un módulo del roadmap. Ambas con tests verdes (204/204 en total).

**1. Canon v8 — dos sombreros, dos planillas (Donna vida / Louis plata).** Finanzas y estados de cuenta
se separan a su propia planilla `GOOGLE_SHEET_ID_LOUIS`. **Cableado hecho:** `config.py`
(`sheet_finanzas` resuelve Louis → legacy Finanzas → Donna), `core/sheets.py` (`fin_id()` cae a Donna si
Louis vacío), `setup_sheets.py` (`TABS` partido en `TABS_DONNA`/`TABS_LOUIS`, asegura cada grupo contra
su planilla; `TABS` combinado se mantiene para el guardián de schema), `core/scheduler.py`
(`job_verificar_schema` chequea vida contra Donna y finanzas contra `fin_id()` — sin esto tiraría
incidentes falsos "columnas faltantes"). `CLAUDE.md` actualizado al canon v8. Detalle y pasos de
migración en [`docs/Sombreros_Donna_Louis.md`](Sombreros_Donna_Louis.md). **Degrada elegante:** con
`GOOGLE_SHEET_ID_LOUIS` vacío sigue en single-workbook, nada se rompe. **Migración confirmada activa
(verificado 2026-07-23):** la planilla "Louis" (`GOOGLE_SHEET_ID_LOUIS` en `.env`) existe desde
2026-07-18 y tiene transacciones reales escribiéndose hasta hoy — la separación ya está en producción,
no solo en código. **Cable cruzado a vigilar:** Compras Fase 2 leerá `Compras_Detalle` (ahora en
Louis) → deberá pasar `sheet_id=sheets.fin_id()` explícito.

**2. Tanda 1 — esperas unificadas (`core/espera.py` nuevo).** Antes cada corrección pendiente (categoría
de una línea del digest, categoría de un ítem, desglose de un cargo, corrección de una inferencia, monto
de un gasto sin cifra) vivía como una llave suelta en `user_data` que se tragaba el PRÓXIMO mensaje fuera
cual fuera — sin cancelar, sin validar forma, sin vencer nunca; y un error así se aprendía después como
regla permanente. Ahora hay **una sola pieza de estado por chat** con tres reglas parejas: se cancela
(«cancelar»/«olvídalo»), expira sola (TTL 15 min), y quien la resuelve **valida que la respuesta tenga
forma de tal** antes de darla por buena — si no calza, se suelta y el mensaje sigue normal al cerebro.
**Cableado:** `core/espera.py` (motor), `core/flows.py` (los 4 botones que abrían una espera ahora llaman
`espera.iniciar`), `main.py` (`_procesar_entrada` como punto único para texto y voz, con eco de voz solo
tras validar). El gasto sin monto legible es la excepción de forma (vive en un global de `finanzas.py`
porque el tool corre sin contexto de Telegram) pero sigue las mismas tres reglas: `parece_monto` rechaza
"recuérdame pagar el agua el 15" / "dormí 7 horas", cancelable y con TTL propio. 12 tests nuevos
(`tests/test_espera.py`) + 5 en `tests/test_finanzas.py`.

### Archivista (`arc_`) — fuera de los 8 módulos (F3-lite del [[Roadmap-Holding]])

**No es un módulo de este roadmap:** es la rebanada delgada de F3 del proyecto **Córtex** (el segundo
cerebro de Nico), que vive en el Roadmap-Holding, no en los 8 módulos personales. Se registra aquí solo
para no perderle la pista. **Estado (2026-07-17): construido, commiteado (`4e537aa` docs + `54e3259`
código) y pusheado a `origin/main`; token ya seteado en Railway — falta verificar el primer guardado real.**
- **Qué hace:** Donna escribe en Córtex con `arc_guardar`, importando `cortex_core` vendorizado como copia
  en `cortex_core/`. Solo **captura vía Telegram**. **NO incluye** la síntesis matinal en el brief ni el
  cron del loop nocturno — eso es F3 completo (semana 4 del Holding).
- **Cableado:** `modules/archivista.py` (nuevo), `cortex_core/` (vendor), cambios en `core/brain.py`,
  `Procfile`, `scripts/start.sh` (clona el repo de Córtex al arrancar en Railway), `CLAUDE.md` (sección
  Archivista) y `prompts/capacidades.md`. Probado end-to-end en local 2026-07-16.
- **Degrada elegante:** si `cortex_core` no importa o el vault no está disponible, el tool responde sin
  cortar la conversación (contrato de módulo #4). Dos mensajes distinguen la causa: *"Todavía no tengo el
  cerebro (Córtex) conectado…"* = token/clone falló (se evalúa al importar); *"No pude escribirlo en el
  cerebro ahora…"* = conectado pero la escritura/push falló.
- **Config de Railway:** ✅ **`CORTEX_GITHUB_TOKEN` seteado por Nico (2026-07-17).** `CORTEX_AUTOR` y
  `CORTEX_GIT_AUTO` ya traen default en `start.sh` (`donna` / `1`), así que el token era lo único
  imprescindible.
- **Pendiente de verificación (Nico):** (1) confirmar en los logs de Railway del deploy el mensaje
  `[start.sh] Clonando Córtex…`; (2) mandar una nota real por Telegram (*"anota en el cerebro: …"*) y ver
  que responde *"Guardado en el cerebro…"*; (3) confirmar el commit nuevo firmado por "Donna" en el repo
  `ncastroocordova-bit/cortex` (carpeta `vault/00-Inbox/`). **Prerrequisito a chequear:** que ese repo de
  Córtex exista en GitHub (el test local usó un vault en disco, no el clone).
- **Ficha de tool:** `Spec_Herramientas_Nuevas.md` §arc_.

## Auditoría de la planilla Louis (2026-07-23) — plan de realineamiento abierto

Se leyeron las 8 hojas de Louis vía Sheets API y se cruzaron contra el código. **21 hallazgos**, el más
grave: **el Dashboard y el Comparativo están muertos** (todo `#N/A`/`#REF!`) porque la migración al canon
v8 dejó las referencias entre hojas desatadas — Sheets ata por ID interno de hoja, no por nombre, y esos
IDs eran del workbook Donna. `Tarjetas y Deuda` sobrevivió porque solo se referencia a sí mismo.
Verificado: una fórmula idéntica escrita de cero funciona (los gastos de julio dan $514.992).

Otros hallazgos de peso: el faro **calcula** el interés en vez de usar el del estado de cuenta
(subreporta **$6.652/mes**; el real es ~$63.908, no $57.256) y mezcla meses (BCh de junio, Mach de julio);
el mes activo quedó congelado en junio; BCh está **$30.608 sobre el cupo** sin que el faro lo nombre;
`_categoria_item` inventa categorías fuera del catálogo; el matcher no cubre `dictado`↔`correo` (hay un
doble conteo de $4.340); y no hay **ni un ingreso registrado** en 69 filas.

**Plan completo con olas de ejecución y gate de salida:**
[`docs/Plan_Realineamiento_Louis.md`](Plan_Realineamiento_Louis.md).

**Estado (2026-07-23): las 6 olas ejecutadas, realineamiento cerrado.** 269 tests verdes (arrancó en
~91). Resumen por ola:
- **Ola 0** — Dashboard/Comparativo revividos (0 errores), mes activo en julio, categorías limpias.
- **Ola 1** — el faro usa el interés del ESTADO cuando lo trae (intereses muertos $57.256 → **$63.908**
  real), alerta de cupo excedido, `correo_dias` 2→14.
- **Ola 2** — `Compras_Detalle` deja de inventar categorías; 2ª pasada de correlación contra lo YA
  escrito en la planilla (el diagnóstico original decía "falta cubrir dictado" — **era otra causa**:
  la correlación solo miraba el buffer del día, que se vacía cada noche).
- **Ola 3** — 2 duplicados borrados + 5 traspasos recategorizados (**-$72.340 / -$40.500** del gasto
  de julio: $514.992 → $415.152). Modelo de datos **corregido a mitad de camino**: `Transacciones` es
  una fila por movimiento del banco (para reconciliar); `Compras_Detalle` es el detalle por ítem (de
  ahí salen las métricas) — no se parten filas ni se sufija `ID_Único`, al revés de lo que se había
  entendido primero. Nace la **regla del RUT propio**: un movimiento entre cuentas de Nico no es
  gasto ni ingreso.
- **Ola 4** — hoja `Metas` cargada (con un bug de fórmula evitado: `Objetivo=$0` para "deuda en cero"
  da división por cero); `Subcategoría`→`Detalle_Medio`; comercios normalizados.
- **Ola 5** — reconciliación de estados de cuenta (capacidad nueva, no reparación): cada estado/cartola
  se compara contra `Transacciones` y da un diferencial en plata; cubre tarjeta de crédito **y**
  cuenta corriente (débito); ingresos y saldo mensual (hoja `Saldos` nueva) desde los abonos de la
  cartola. **Encontró un bug sistémico en el camino:** `Fecha` se lee como número de serie de Sheets,
  no como texto — rompía en silencio la propia reconciliación de esta ola, la 2ª pasada de
  correlación de la Ola 2 (nunca funcionó en producción) y el correlador sueño↔gasto. Arreglado con
  un helper único (`sheets.fecha_iso()`). `CLAUDE.md` actualizado: excepción al canon de "no saldos
  automáticos" para el saldo mensual (sale gratis del documento, cero fricción para Nico).

**Plan completo, con los 4 bugs reales encontrados durante la construcción y su verificación contra
datos en vivo:** [`docs/Plan_Realineamiento_Louis.md`](Plan_Realineamiento_Louis.md).

**Pendiente de Nico:** confirmar `DUENO_NOMBRES` en Railway (además de local) y revisar el primer
digest real con candidatos de la Ola 5 (compras faltantes + ingresos detectados).

## Auditoría de columnas de `Transacciones` y `Compras_Detalle` (2026-07-24) — ejecutada

Pedida por Nico ("siento que algunas columnas no sirven para nada"). Se leyeron las dos hojas en
vivo (68 transacciones, 65 líneas de detalle) y se cruzó cada columna contra el código que la
escribe y la lee, y contra las fórmulas del Dashboard y el Comparativo.

**La integridad estaba impecable** (0 líneas huérfanas, 0 descuadres, 0 celdas en error): el
problema eran las columnas, no los datos.

- **`Transacciones` 10 → 9.** Se borró `Detalle_Medio`: **write-only en todo el código** y
  guardaba tres cosas en la misma celda (nº de tarjeta `****5502`, RUT del destino
  `Rut 19986903-5`, glosa libre `Transferencia a terceros`). Lo único que aportaba —distinguir
  débito de crédito— se rescató **normalizando `Medio`**, que tenía 8 valores mezclando tres ejes
  (`Banco de Chile` x18 sin decir el producto, `Tarjeta crédito` x11 sin decir el banco, `Mach`
  x8 que eran transferencias). Ahora son **5 valores de un solo eje** —de qué cuenta salió la
  plata— garantizados por `finanzas.normalizar_medio()`, que corre **al escribir**, no en cada
  parser: un parser nuevo ya no puede reintroducir una etiqueta suelta.
- **`Compras_Detalle` 10 → 7.** Se borraron `Cantidad` (**0 de 65 filas llenas**), `Intención` y
  `Fuente` (copias exactas del padre, recuperables por `ID_Tx`). **`Predecible` se mantuvo** pese
  a estar en `no` al 100%: está vacía por la misma causa que `Cantidad`, no por inútil.
- **La causa raíz de las tres columnas vacías:** `Fuente` solo tiene `correo` (57) y
  `estado_cuenta` (11). **Cero fotos, cero dictados** — la captura ítem-a-ítem de Finanzas v3
  nunca se ha usado en producción, y es la única vía que llena `Cantidad` y marca `Predecible=sí`.
  Solo 2 de 68 transacciones tienen desglose real. **El predictor de Compras Fase 2 nacería sin
  un solo dato**; mientras no entre una boleta por foto, esa fase no tiene insumo.
- **Bug latente cerrado de paso:** `_ids_transacciones` leía el rango `A:I` y ubicaba `ID_Único`
  por header — pero `ID_Único` estaba justo en la columna I. Una sola columna agregada a su
  izquierda lo empujaba a J, fuera del rango: la guardia anti-duplicados devolvía un set vacío,
  se apagaba sola y el digest habría escrito transacciones repetidas sin avisar. Ahora `A:Z`.
- **Verificación:** respaldo completo de las 9 hojas antes de tocar nada; las fórmulas del
  Dashboard y el Comparativo se reengancharon solas (`Transacciones!F`→`E`,
  `Compras_Detalle!E`→`D`, `!F`→`E`); **ningún número del Dashboard se movió** y las 9 hojas
  siguen con 0 errores. 276 tests verdes (3 nuevos sobre el vocabulario de `Medio`).
### Corrección al diagnóstico + pasos 1 y 2 del plan de Predecible (2026-07-24)

El "hallazgo de fondo" del párrafo anterior estaba **mal leído**. La columna `Fuente` no tiene
fotos, pero sí desgloses por texto, que es el otro camino de captura. El buffer de Supabase dice:
**Donna preguntó *"¿qué compraste?"* 8 veces y Nico respondió 7 (87%)**; hay 14 filas del buffer
con ítems reales. La captura funciona y Nico sí responde.

Y `Predecible=no` en 65/65 es **mayormente correcto**: lo que se compra en el almacén San Vale
(11 de 68 transacciones) es pan, chanchería y cervezas — perecible y cotidiano, que el canon
excluye del predictor a propósito. El clasificador acierta en el control (`arroz`, `atún`,
`detergente`, `papel higiénico` → sí). El predictor no está sin datos por un bug: está sin datos
porque la despensa no pasa por ese canal.

**Los tres huecos reales** (y qué se hizo con cada uno):
1. **El clasificador no sabía que Nico tiene un hijo.** `pañales emilio` × $29.340 salía `no` — el
   ítem de reposición por excelencia. ✅ **Hecho (paso 2):** se agregaron las familias que
   faltaban (guagua: pañal/toallita/fórmula/colado/mamadera; aseo recurrente) y se cambió el
   desempate a **la coincidencia más específica gana**, que de paso arregla los compuestos
   (`salsa de tomate` calzaba con `tomate` y salía `no`). 18/18 casos correctos.
2. **Las correcciones no se aprendían.** El chip 📦/🥖 existe desde v3 pero el toque moría en ese
   digest: Nico podía marcar "pañales" cada semana y Donna lo volvía a inferir mal. ✅ **Hecho
   (paso 1):** tabla `items_predecibles` (migración 015, aplicada), `memory.get_items_predecibles`
   / `upsert_item_predecible`, `finanzas.aprender_predecible` (aprende la palabra significativa,
   no la frase entera) y `_predecible` consulta el lookup **antes** que las keywords. Verificado
   en vivo contra Supabase: enseñar → releer → la corrección manda.
3. **La granularidad muere donde vive la despensa.** Los desgloses del almacén salen perfectos
   (`pan 2.500 + chanchería 1.840`); los del súper no — **$29.340 en Santa Isabel se respondió con
   un solo ítem**. Una compra de súper son 15 productos, y ahí está el arroz y el detergente.
   ✅ **Hecho (paso 3, 2026-07-25):** sobre `finanzas.UMBRAL_FOTO` ($15.000) en un comercio "de
   compras", Donna deja de preguntar abierto y **pide la boleta**: *"Vi $29.340 en Santa Isabel.
   Eso no es un ítem — mándame la boleta y la desgloso yo"*, con 📷 solo en su propia fila y el
   texto bajado a secundario. Bajo el umbral, la pregunta abierta de siempre.
   **Y se ató la foto al cargo:** el botón 📷 abre una espera `foto_cargo` y la siguiente foto va
   a ESE cargo. Antes solo se pedía la foto y se confiaba en que la correlación
   monto+fecha+comercio la juntara — que es justo la que falla cuando la boleta dice 'ALMACEN SAN
   VALENTIN' y el banco 'MERCADOPAGO*SANVA'. El total canónico sigue siendo el del banco: si la
   boleta suma menos, `_cuadrar_resto` completa. Si Nico responde por texto en vez de foto, vale
   como desglose del mismo cargo (sin esto la espera se descartaba y se perdía el vínculo).
   `finanzas.leer_boleta` se separó de `procesar_foto` para poder adjuntar sin bufferizar aparte.

### ⬜ Paso 4 — despertar la lista de Compras Fase 1 (el segundo feed)

**Qué pasa:** la hoja `Compras` (planilla Donna) tiene **0 filas desde que se construyó el
2026-07-05**. El módulo funciona —`cmp_agregar` / `cmp_lista` / `cmp_comprado` + el comando
`/lista` con sus toques—; simplemente no se usa.

**Por qué importa:** por canon, el predictor de Fase 2 aprende de **dos** fuentes, y esta es la
barata: un ítem marcado `comprado` da el par (ítem, fecha) **directo, sin OCR, sin LLM, sin
parseo**. La otra fuente (`Predecible=sí` en `Compras_Detalle`) depende de que llegue una boleta
con despensa. Con la lista viva, el predictor tiene datos aunque no se saque ni una foto.

**Es conductual, no código** — nada que construir. Lo que se necesita: usar *"Donna falta arroz"*
cuando se acaba algo, y `/lista` antes de ir al súper (que es donde el ✅ registra la fecha de
compra, que es el dato que el predictor necesita).

**Lo único que sí valdría construir, y solo si a las 2 semanas sigue en cero:** un nudge desde
Proactividad («llevas N días sin agregar nada a la lista»), respetando el tope 1/día. No antes —
sería resolver con código un problema de hábito que todavía no se sabe si existe.

### ⬜ Paso 5 — el gate: medir antes de abrir Compras Fase 2

**La regla:** no se construye el predictor hasta que haya con qué. Canon: *calla hasta tener
datos* (mismo criterio que el factor de optimismo y las ventanas de salud).

**Umbral concreto:** **≥5 ítems distintos con ≥3 eventos de compra cada uno.** Con menos de 3
fechas por ítem no hay intervalo que estimar —dos compras dan un solo intervalo, y con uno solo no
se distingue una compra mensual de una casualidad—, y con menos de 5 ítems el módulo avisaría de
tan poco que no cambia nada.

**Cómo se mide (lo único que hay que construir de este paso, ~30 min):** una función que cuente
eventos por ítem cruzando las dos fuentes —`Compras_Detalle` con `Predecible=sí` (pasando
`sheet_id=sheets.fin_id()`, que cruza de Donna a Louis) y la hoja `Compras` con
`Estado=comprado`— y devuelva la tabla ítem → nº de eventos → intervalo mediano. Sale en la
revisión dominical, en una línea, junto al resto.

**Estado hoy (2026-07-25): 0 ítems califican.** `Predecible=sí` está en 0 de 65 líneas y la lista
tiene 0 filas. Con el paso 3 desplegado, la cuenta empieza a subir desde la próxima vuelta al
súper — pero el gate se evalúa con el dato, no con la expectativa.

- **Inferencia a confirmar por Nico:** las 11 filas que decían `Tarjeta crédito` sin banco ni nº
  de tarjeta quedaron como **`BCh crédito`**. Evidencia: van del 21-may al 17-jun y el estado de
  BCh cierra el 18-jun (`Deuda_Mensual`); es además la única tarjeta que no manda correo por
  compra en pesos, que es justo por lo que faltaban y las trajo el estado de cuenta. Si eran de
  Mach, se corrigen con un reemplazo en la columna F.
  **Resuelto (2026-07-24): la inferencia estaba MAL.** Nico las revisó: eran mezcladas — 7
  `BCh crédito` + 4 `Mach crédito`. Ya las corrigió a mano y no se salió del vocabulario. La
  causa de raíz (el producto se sabía y se tiraba) quedó cerrada en el commit siguiente.

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

## Fase 0 — Reparación de bugs activos (comprometida 2026-07-03, ANTES de Compras)

Decidido: los bugs activos se cierran **antes** de construir el módulo siguiente y antes del harness.
El detalle técnico completo (2 opciones por ítem, con output esperado, para ejecutar por IA) vive en
`Plan_Reparacion_Bugs_y_Datos.md`. Orden: A1 Recordatorios → A2 Proyectos/Tareas → B1/B2 (desregistrar
`metas`/`tiempo` del brain) → C2 Mes activo → C1 categorías → C3 captura de sueño/ventanas → C4-C6.
Gate de salida: `pytest tests/` verde con los tests nuevos + smoke manual por Telegram + tablero de este
documento actualizado (ítems 4 y 6 dejan de estar en ⚠️).

**Avance (2026-07-04) — FASE 0 COMPLETA (código):** ✅ **A1** (recordatorios: schema real) ·
✅ **A2** (proyectos/tareas: por nombre, sin IDs) · ✅ **B1/B2** (desregistrar `metas`/`tiempo`) ·
✅ **C1** (validación de categorías vs `Categorias` + limpieza: 14 transacciones normalizadas, categoría
`Transferencias` creada, cero huérfanas) · ✅ **C2** (Mes activo: toque del día 1) ·
✅ **C3** (captura de sueño/ventanas por chips) · ✅ **C4** (vencido-insiste con botón ✅ Hecho) ·
✅ **C5** (higiene: fila placeholder borrada + `% Avance` normalizado a `N%`) ·
✅ **C6** (ancla de fecha del panel de cierre). **Deployado a Railway el 2026-07-04** (push a
`origin/main`; hasta entonces los 11 commits de Fase 0 llevaban días solo en local, sin efecto en
producción — lección: verificar push, no solo commit, antes de dar un fix por "hecho").

**2026-07-04/05 — bugs reales encontrados usando el bot en producción** (fuera del alcance original de
Fase 0, pero mismo espíritu de reparación): el brief seguía preguntando el binario "¿dormiste 7h+?" en
vez de la hora real → **arreglado**, ahora deriva el 7h+ de la ventana dormí↔despertar
(`salud.derivar_sueno_de_ventana`); el editor de ítems del desglose de compras se trababa al re-tocar el
mismo deseo/categoría (Telegram tira "message is not modified" sin capturar) → **arreglado** con
`flows._edit_ok`; los textos fijos del brief/cierre salían idénticos todos los días → **arreglado** con
`core/frases.py` (pools de variantes, sin DB, versión lean). **147 tests verdes.**

**Decisión de alcance (2026-07-04):** con el negocio fuera del horizonte cercano, el **harness propio
completo se descarta por ahora** (su valor real es la escalera de autonomía hacia terceros de
`Vision_Donna_Ampliada.md`, que no aplica a un asistente solo-personal). Se optó por una versión **lean**
del autodiagnóstico.

**Autodiagnóstico lean — CONSTRUIDO (2026-07-05).** `core/diagnostico.py` + tabla `incidentes`
(migración `014`, aplicada a Supabase). Detección determinista (sin Haiku), tres tipos:
`tool_excepcion` (wrapper en `brain._ejecutar_tool` → registra + responde en carácter sin stacktrace),
`schema_sheets` (guardián al boot `sheets.verificar_headers` sobre las hojas críticas → **habría atrapado
los bugs de A1/A2 el día uno**; corrido contra la planilla real da "ninguno ✓"), `verificacion_escritura`
(`sheets.append_row_verificado` relee y confirma; conectado en `rec_agregar`, el que corrompía columnas).
Dedup por firma con normalización de números validada contra Supabase real (dos errores "fila 5"/"fila 99"
→ un incidente, frecuencia 2). Tool `diag_estado` ("¿qué se ha roto?"). 10 tests. **Queda afuera** (por
ser lean, se puede sumar después): el diagnóstico con Haiku, el CLI puente `scripts/incidentes.py`, el
watchdog de jobs, el detector `correccion_nico`, y extender `append_row_verificado` al resto de escritores.

**Único pendiente para cerrar el gate formal de Fase 0:** el **smoke manual por Telegram** completo
(crear recordatorio/tarea, tocar el panel del cierre) — sin confirmar explícitamente por Nico, aunque el
uso real del bot en 07-04/05 ya ejerció brief/cierre/desglose y esos caminos están probados en la práctica.

Con el **autodiagnóstico lean ya construido** (ver arriba), el siguiente en la secuencia era
**Compras Fase 1** (Módulo 3) — **ya construida** (2026-07-05, ver ítem 3 del tablero). Finanzas siguió
creciendo fuera de secuencia con v4 porque era la prioridad real de Nico, y eso está bien: la regla madre
ya no se sigue estricta (ver nota arriba del tablero).

## Secuencia redecidida (2026-07-23)

Nueva prioridad, por decisión de Nico:

1. **Calendario + Recordatorios `rec_` (fusión real)** — Módulo 4, ver ficha arriba. Se construye
   Calendario en serio (lectura ampliada + escritura vía `agenda.crear_evento()`, hoy sin conectar) y se
   fusiona con la escalera de Recordatorios en un solo módulo, en vez de dejarlos como dos paneles
   separados.
2. **Correo `cor_`** — Módulo 5, inmediatamente después. Cerrar el bucket "importante→resumen brief" que
   falta (spam y financiero ya funcionan).
3. Productividad, Proactividad-ampliado y Familia quedan después de Correo — sin fecha todavía.

Esto no cambia la numeración de los 8 módulos (Calendario+Recordatorios ya era el 4 y Correo ya era el 5
en la lista original) — lo que cambia es el **alcance** del módulo 4 (fusión real, no solo lectura menor
del calendario) y la **confirmación explícita** de que es el siguiente en construirse, saltándose
Productividad/Proactividad-ampliado/Familia por ahora.

---

*El gate "un módulo a la vez" ya lo decidiste (lo llevas junto con arreglos puntuales a lo construido,
no en secuencia estricta). La decisión que faltaba —cuándo entran Productividad/Recordatorios a
arreglarse— quedó tomada: Fase 0, inmediata (ver arriba).*
