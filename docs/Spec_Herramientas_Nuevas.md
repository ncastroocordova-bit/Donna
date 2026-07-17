# Spec de Herramientas Nuevas — Donna

Detalle de implementación de las herramientas que el canon agrega o cambia. Acompaña a `Plan_Construccion_v7.md`. Cada bloque: propósito · firma · lee/escribe · invariantes · borde · LISTO CUANDO.

---

## §rec_ — Recordatorios (escalera)

**Propósito:** avisar en escalera calmada (domingo + T-2 + T-0) y escalar solo el vencido, sin ruido nuevo.

**Esquema `Recordatorios` (real, verificado contra la planilla — no el fantasma que arregló el fix A1):** `Recordatorio · Tipo(mensual|anual|única) · Día / Fecha · Monto aprox · Estado(pendiente|hecho|pospuesto) · Posposiciones(int) · Última acción(fecha) · Activo`. Los nombres van **con tildes y espacios exactos** (así los lee `modules/recordatorios.py`).

**Firmas:**
- `rec_semana() -> list` — todos los activos cuya próxima ocurrencia cae en ≤7 días. Para el preview del domingo.
- `rec_proximos() -> {t2:[], t0:[]}` — los que disparan hoy: T-2 y T-0. Los T-0 traen `accion="hecho"`.
- `rec_marcar_hecho(id)` — `Estado=hecho`, `Ultima_Accion=hoy`; recurrente → reagenda próxima ocurrencia y vuelve a `pendiente` para el próximo ciclo; única → cierra (`Activo=No`).
- `rec_posponer(id, hasta:date)` — `hasta` **obligatorio** (sin fecha → rechaza). `Estado=pospuesto`, `Posposiciones+=1`.
- `rec_vencidos() -> list` — `Estado=pendiente` con fecha < hoy. Alimenta la escalada del scheduler.
- `rec_agregar(texto)` — NLP de fecha; clasifica tipo. Anti-duplicado con `Tareas`: con fecha + persigue = recordatorio; sin fecha = tarea.

**Cálculo de próxima ocurrencia:** mensual = próximo día N; anual = próxima fecha MM-DD; única = la fecha tal cual.

**Invariantes:** posponer sin fecha se rechaza; tras `Posposiciones>=3`, marca para que Donna **nombre el patrón** ("llevas 3 del IVA — ¿se hace o lo bajamos?"). El loop siempre lo cierra Nico.

**Borde:** recurrente marcado hecho no debe duplicar la fila; debe avanzar la fecha. Calendar opcional: citas pueden heredar la escalera (togglable), sin reingreso.

**LISTO CUANDO:** `rec_semana()` lista 7 días; `rec_proximos()` T-2 y T-0 correctos; hecho cierra/reagenda; posponer sin fecha falla; vencido aparece.

---

## §cor_ — Correo (triage + jamás borra)

**Propósito:** partir el inbox en 3 buckets con mínimo costo y **sin borrar nunca**.

**Pipeline (orden de costo, gratis→caro):**
1. `cor_traer_inbox()` — Gmail API, `INBOX` sin lo que Gmail ya marcó Spam, `format=metadata` (remitente/asunto/snippet), dedup por `message-id` de Gmail.
2. `cor_clasificar_reglas(msgs)` (**sin LLM**) — financiero si remitente ∈ allowlist financiera (→ `fin_`); archivar si `List-Unsubscribe` o `no-reply`/marketing; importante si ∈ allowlist importantes. Devuelve clasificados + **residuo**.
3. `cor_clasificar_llm(residuo)` — **una sola llamada**, lista `{remitente, asunto, snippet}`, **nunca el cuerpo**. Devuelve `{bucket: importante|archivar, resumen_linea}`.
4. `cor_archivar(ids)` — etiqueta `Donna/Archivado` + **quita `INBOX`**. **PROHIBIDO `trash`/`delete`.** Importante se queda; financiero → buffer `fin_`.
5. `cor_resumen_brief()` — solo lectura: conteo por bucket + 1 línea por importante.
6. `cor_reconciliar()` (**sin LLM, diario**) — lo rescatado de `Donna/Archivado` → sube remitente a importante; lo archivado que era importante → baja. Tabla `remitentes(remitente, clase, conteo)`, **compartida con Finanzas**.

**Correo dedicado:** casilla `finanzas.nico@…` como 2ª fuente de `fin_procesar_correo`. Dentro igual filtra: transacción = monto + palabra clave; marketing = `List-Unsubscribe` → archivar.

**Invariante duro:** ninguna acción llama a trash/delete. Pasividad total: el triage no pregunta nada, solo resume y archiva.

**Borde:** banco que manda alerta real y marketing desde el mismo remitente → distinguir por contenido (monto+keyword vs List-Unsubscribe), no por remitente.

**LISTO CUANDO:** 3 buckets con conteos correctos; marketing archivado (etiqueta+sin INBOX); assert no-borrado; rescate promueve al remitente al día siguiente.

---

## §prod_ — Reconciliación nocturna (opción 1, con delta)

**Propósito:** capturar tiempo real por frente y la brecha plan-vs-real **sin tocar el brief**, en el cierre, con toques.

**Esquema `Reconciliacion`:** `Fecha · Bloque · Frente(Tesis|Noomi|Delivery|Hijo|Personal) · Min_Planeados · Hecho(si|no) · Delta(Menos|Igual|Mas) · Min_Reales · Notas`.

**Firmas:**
- `prod_bloques_hoy()` — vía `core/agenda.py`, eventos/bloques de Calendar de hoy con duración planeada. Infiere `Frente` por etiqueta/keyword del evento.
- panel cierre: "✅ Hice todo" (1 toque) **o** marca los no-hechos; por bloque hecho, ⏱️ **Menos/Igual/Más**.
- `prod_guardar_reconciliacion(items)` — escribe filas en `Reconciliacion`. `Min_Reales` = planeados ajustados por delta (Menos≈0,6× / Igual=1× / Más≈1,3×, o pregunta fino si quieres exactitud).
- el `Semanal` del domingo: `h <Frente>` = SUMA de `Min_Reales`/60 por frente de la semana.

**Invariantes:** corre **solo en el cierre** (jamás en el brief). Patrón "aceptar todo / corrige excepciones" (igual que el digest). Frente dudoso se confirma con un toque, no se inventa.

**Borde:** día sin eventos en Calendar → pregunta un resumen grueso por frente (fallback) o salta sin romper. No bloquea el cierre si Calendar falla (degrada elegante).

**LISTO CUANDO:** "Hice todo" escribe duraciones por bloque; un "Menos" baja `Min_Reales`; el Semanal suma horas por frente; el brief no cambió.

---

## §apr_ — Factor de optimismo (sobre aprendizaje)

**Propósito:** ser el **observador externo** que corrige tu falacia de planificación, con dato.

**Firmas:**
- `apr_factor_optimismo(frente) -> float` — ratio real/planeado por frente sobre últimas N semanas (lee los registros de `Reconciliacion` en Sheets). **Persiste el modelo aprendido (ratios e historial por frente) en Supabase, tabla `aprendizaje`** (migración 007). Escribe en el `Semanal` SOLO el resultado legible (`Factor_Optimismo`) — eso es una lectura, no el almacén. Reference class forecasting personal.
- `apr_observador(plan_propuesto) -> str|None` — si planeas por sobre tu promedio real (leído de Supabase), devuelve la señal ("dijiste 5 bloques de tesis; tu real es ~3 — ¿bajamos?"). Si `semanas_de_datos < 2`, devuelve `None` (calla).

**Capa de datos:** registros (lo que hiciste) viven en Sheets `Reconciliacion`; lo aprendido (tu ratio, calibración) vive en Supabase. Nunca al revés.

**Invariantes:** **inferencia validada** — el factor SIEMPRE viaja con el dato (n semanas + promedio). No habla hasta tener ≥2-3 semanas. No moraliza: ofrece bajar el plan, no reta.

**Borde:** un frente sin datos suficientes → no opina sobre ese frente. Datos ruidosos (1 semana atípica) → usa mediana, no promedio, si el set es chico.

**LISTO CUANDO:** con ≥3 semanas, ratio coherente y `apr_observador` frena un plan inflado con su dato; con <2 semanas, calla.

---

## §sal_ — Salud v2 (ventanas, peso, score, eventos)

**Propósito:** sumar ventanas de ayuno/sueño, peso, un score semanal y la captura de contexto, sin inflar el cierre.

**Esquema:** `Diario` += `Primera_Comida · Hora_Despertar · Peso` (ya existen `Ultima_Comida`, `Hora_Dormi`). `Agua`/`Proteina` quedan como columnas legado, sin capturar. `Semanal` += `Score_Habitos · Ventana_Comida · Ventana_Sueno · Peso`.

**Firmas:**
- `sal_marcar_habito(campo, valor)` — ejercicio/meditación/última comida en el cierre. `Agua`/`Proteina` se retiraron del cierre (columnas legado sin capturar).
- `sal_set_hora(campo, hora)` — escribe `Primera_Comida` / `Ultima_Comida` / `Hora_Despertar` (HH:MM) en la fila del día.
- `sal_peso(kg)` — escribe `Peso`; se pregunta **cada cierre** (22:00), no solo domingo.
- `sal_resumen_ventanas(semana) -> dict` — mediana de ventana de comida (1ª→última) y de sueño (dormir→despertar), **semana vs fin de semana**. **Solo mide**; no propone meta hasta ≥2-3 semanas de baseline. Escribe `Ventana_Comida`/`Ventana_Sueno` en `Semanal` (lectura).
- `sal_score_semana() -> int` — % de hábitos cumplidos (default: sueño 7h, ejercicio, meditación). Escribe `Score_Habitos` (lectura).
- `sal_evento_contextual(texto)` — guarda en `core/memory` con tag `evento_externo` lo que Nico no controló ese día.

**Invariantes:** las ventanas se **miden, no se exigen** (canon "calla hasta tener datos"). El `evento_externo` hace que el **correlador trate el día como contexto, no patrón** (guardia anti-patrón-falso). Score y ventanas en `Semanal` son **lectura**; el modelo no vive en el Sheet.

**Borde:** día sin hora de comida/despertar → la ventana de ese día no entra a la mediana (no inventa). Peso sin registro un día → muestra la última lectura de la semana, no falla.

**LISTO CUANDO:** toques de comidas escriben en `Diario`; `sal_peso` registra cada cierre; `sal_resumen_ventanas` da medianas coherentes; `Score_Habitos` cuadra con los toques; un evento contextual no se cuenta como patrón.

---

## §cmp_ — Compras (lista del súper, Fase 1)

**Propósito:** que no se te olvide qué comprar; lo dices suelto y Donna lo guarda; cuando pides la lista, te dice exactamente lo que falta.

**Esquema `Compras`:** `Item · Estado(pendiente|comprado) · Fecha_Agregado · Fecha_Comprado · Categoria`.

**Firmas:**
- `cmp_agregar(item)` — "Donna falta toalla nova" / "queda poco arroz, anótalo" → `Estado=pendiente`, `Fecha_Agregado=hoy`. Anti-duplicado por nombre normalizado (no agrega "arroz" dos veces).
- `cmp_lista() -> list` — "Donna dame la lista del súper" → devuelve **exactamente** los `pendiente`.
- `cmp_marcar_comprado(item)` — `Estado=comprado`, `Fecha_Comprado=hoy`; sale de la lista. Toque o texto.

**Fase 2 (DIFERIDA, no en este módulo):** `cmp_frecuencia(item)` calcula el intervalo medio entre compras → infiere reposición → alerta *"puede que toque comprar arroz"* vía Proactividad. **Lee dos fuentes** de eventos (item, fecha): (a) la lista Fase 1 (ítems `comprado` con `Fecha_Comprado`) y (b) las líneas `Predecible=sí` de `Compras_Detalle` que escribe Finanzas v3 (`§fin_ v3`). **Solo despensa/reposición** (arroz, atún, fideos, limpieza); **nunca** lo cotidiano/perecible (pan, chanchería). Se persiste en Supabase (`aprendizaje`).

**Invariantes:** prefijo `cmp_` sin solapamiento. Degrada elegante si Sheets falla. Fase 1 **no** infiere nada; solo lista. La fecha de compra se guarda desde día 1 (insumo de Fase 2).

**Borde:** "anótalo" sin objeto claro → pide el ítem, no inventa. Marcar comprado algo que no estaba → lo agrega ya como `comprado` (registra historial igual).

**LISTO CUANDO:** "falta X" agrega sin duplicar; "dame la lista" devuelve solo lo pendiente; marcar comprado lo saca y registra `Fecha_Comprado`.

---

## §fam_ — Familia (módulo propio, opción B)

**Propósito:** que el tiempo con Emilio y la pareja esté medido y no se diluya, con inferencias y nudge propios.

**Esquema:** `Diario` += `Fam_Emilio · Fam_Pareja · Fam_Cena` (sí/no).

**Firmas:**
- `fam_marcar(campo, valor)` — 3 toques en el cierre (Emilio / pareja / cena juntos). Reusa el patrón de `sal_marcar_habito`.
- `fam_senal() -> str` — señal destilada: racha de días con/sin tiempo de calidad.
- `fam_nudge() -> str|None` — vía Proactividad (módulo 7): "llevas N días sin tiempo con Emilio". Respeta tope 1/día; `None` si no hay racha que nombrar.

**Espina:** escribe inferencias propias a Supabase; el correlador cruza **familia↔ánimo↔sueño**, cada cruce con su dato.

**Invariantes:** inferencia validada (el cruce viaja con su dato). Nunca etiqueta de carácter ("llevas 5 días sin verlo", no "eres mal padre"). El nudge respeta el tope 1/día de Proactividad.

**Borde:** semana atípica (viaje, examen) → el correlador usa mediana y no afirma patrón con N chico.

**LISTO CUANDO:** los 3 toques escriben en `Diario`; `fam_senal` da una racha coherente; el correlador cruza familia con ánimo con su dato; el nudge dispara tras una racha sin tiempo de calidad.

---

## §fin_ v2 — Intención del gasto + metas

**Propósito:** sumar el *por qué* del gasto y metas con progreso, sin volverse libro contable.

**Esquema:** `Transacciones` += `Intencion(Necesario|Inversion|Deseo)`. Tab nuevo `Metas` (`Meta · Objetivo · Actual · Progreso · Notas`).

**Firmas:**
- intención: el extractor (`procesar_correo`/`procesar_foto`) propone `Intencion`; se **confirma en el digest** junto con la categoría (mismo "aceptar todo / corrige excepciones"). `fin_resumen_intencion(mes)` → totales por Necesario/Inversión/Deseo.
- `fin_metas() -> list` — lee `Metas`, calcula `Progreso = Actual/Objetivo`. 2-3 metas (fondo de emergencia, pagar TC). Se muestran en `Semanal`/digest. **Sin input diario.**
- `fin_alerta_presupuesto() -> str|None` — gatillo de Proactividad: categoría al 90% de `Presupuesto` → nudge (tope 1/día).

**Invariantes:** la intención **no agrega fricción** (se infiere y se corrige en el mismo digest). **No** se construyen cuentas con saldos auto / doble-entrada (rompe "registro sin fricción"). `Progreso` en `Semanal` es lectura.

**Borde:** gasto ambiguo entre Necesario/Deseo → marca dudoso para que Nico lo confirme en el digest, no asume. Meta sin `Objetivo` → no calcula progreso, la muestra como informativa.

**LISTO CUANDO:** la intención se infiere y se corrige en el digest; el resumen mensual por intención cuadra; una meta muestra su % de avance; la alerta de presupuesto salta al 90% real.

---

## §fin_ v3 — Detalle de compra (ítems) + correlación foto↔correo + captura al momento

**Propósito:** que la boleta deje de ser un solo total y se vuelva ítem-a-ítem, **sin doble conteo** entre la foto y el correo, y que Donna pregunte qué compraste cuando el cargo no trae detalle. Es el insumo que la **predicción de Compras (Fase 2)** necesita. **Finanzas escribe el detalle; Compras solo lo lee** (sin solapar tools).

**Esquema:** tab nuevo `Compras_Detalle` (`Fecha · Comercio · Item · Cantidad · Precio · Categoria · Predecible(si|no) · ID_Tx · Fuente(foto|desglose|lista)`). `ID_Tx` = `ID_Unico` de la transacción padre en `Transacciones`. La suma de `Precio` por `ID_Tx` **cuadra al total** de la transacción (línea "resto/varios" si falta). Flag `es_compras` en las reglas de comercio (Supabase).

**Firmas:**
- `procesar_foto(img) -> {items:[{item,cantidad,precio}], total, comercio, fecha}` — Vision aislada; **lee cada ítem** (hoy devuelve un solo total). Escribe 1 fila en `Transacciones` (total) + N en `Compras_Detalle`.
- `fin_correlacionar(buffer)` — aparea la entrada **foto** con la **correo** del mismo gasto por **monto total + fecha (±1-2 días) + comercio** (fuzzy / vía reglas de comercio; resuelve "ALMACEN SAN VALENTIN" vs "MERCADOPAGO*SANVA"). El **correo manda en total/medio** (bancario); la **foto aporta los ítems**. Resultado: **una** transacción. Extiende el anti-duplicado actual (`_id_unico`/`_planificar_digest`), que hoy solo dedup por id exacto.
- `fin_preguntar_compra(tx) -> prompt` — si el cargo viene de un comercio `es_compras=true` **sin detalle**, manda prompt **transaccional** ("vi $X en San Valentín — ¿qué compraste?" · 📷 foto / ✍️ desglosar / ⏭️ después). **No** cuenta contra el tope 1/día de Proactividad. Requiere ingesta en **cadencia diurna** (poll), no solo en el cierre. **El brief no se toca.**
- `fin_desglose(texto, total) -> [{categoria, monto}]` — parsea "gasté 2000 en chanchería y el resto fue pan" → `[{Chanchería, 2000}, {Pan, total-2000}]`; usa el mapa de categorías + LLM para el residuo; el "resto" cuadra al total. Cada línea → `Compras_Detalle`.
- `fin_predecible(categoria|item) -> bool` — **sí** = despensa/reposición (arroz, atún, fideos, aceite, azúcar, papel, limpieza); **no** = perecible/cotidiano (pan, chanchería, verdura, comida preparada). Whitelist de categorías; ítems de la lista Fase 1 cuentan como predecibles.

**Invariantes:** **jamás doble conteo** (foto+correo del mismo gasto = una transacción). El detalle **cuadra al total** de `Transacciones`. La pregunta "¿qué compraste?" es captura, no insight → fuera del presupuesto proactivo. Solo `Predecible=sí` se expone a la Fase 2.

**Borde:** llega la foto antes que el correo (o al revés) → se guarda y se correlaciona cuando aparezca el par; si el correo nunca llega, la foto sostiene la transacción. Foto cuyo total ≠ correo → marca `dudosa` para confirmar en el digest, no asume. Comercio no `es_compras` (Uber, Netflix, bencina) → **no** pregunta.

**LISTO CUANDO:** una foto deja ítems con precio + total; foto + correo del mismo gasto = una sola transacción; un cargo de comercio "de compras" sin detalle dispara el prompt al momento; "2000 chanchería, resto pan" cuadra al total; arroz/atún `Predecible=sí`, pan/chanchería `no`.

---

## §arc_ — Archivista (captura a Córtex, F3-lite — fuera de los 8 módulos)

**Propósito:** que Donna escriba en **Córtex** (el segundo cerebro de Nico) lo que vale la pena recordar
más allá de la conversación y que **no** es perfil estable (`actualizar_perfil`) ni episodio personal
(`guardar_memoria`): decisiones y su porqué, datos del mundo real (clientes, proveedores, negocios),
juicios que solo viven en su cabeza. Pertenece al **Roadmap-Holding (F3)**, no a este roadmap; es la
rebanada delgada: **solo captura vía Telegram** (sin síntesis matinal ni loop nocturno).

**Firma:**
- `arc_guardar(titulo, contenido, area?, tipo?, tags?)` — escribe una nota en el vault de Córtex.
  `area` ∈ holding|personal|noomi|ncc|universidad|casa|recursos|meta · `tipo` ∈
  concepto|proyecto|persona|decision|recurso|diario|reunion|meta. Solo `titulo` + `contenido` obligatorios.
  Filosofía "captura todo ante la duda; el jardinero nocturno limpia después".

**Datos:** vía `cortex_core` **vendorizado como copia** en `cortex_core/`. `CORTEX_VAULT` apunta al vault
(local: disco directo; Railway: `scripts/start.sh` clona el repo de Córtex al arrancar si
`CORTEX_GITHUB_TOKEN` está seteado). Env nuevas de Railway: `CORTEX_GITHUB_TOKEN` (PAT scope `repo`),
`CORTEX_AUTOR=donna`, `CORTEX_GIT_AUTO=1` (opcional `CORTEX_LOCAL_PATH`).

**Invariantes:** prefijo `arc_` sin solapamiento. **Degrada elegante (contrato #4):** si `cortex_core` no
importa o el vault no está disponible, responde sin cortar la conversación, jamás truena a Donna.
No pisa `actualizar_perfil` ni `guardar_memoria` (tres destinos distintos).

**Borde:** sin las env de Railway, `arc_guardar` avisa y degrada (no rompe). Nota sin `area`/`tipo` →
Córtex la clasifica con sus defaults.

**LISTO CUANDO:** `arc_guardar` escribe la nota en el vault y hace commit/push (git ambiente); sin
`cortex_core` o sin vault, responde degradado sin excepción.

**Estado:** construido y probado end-to-end en local (2026-07-16); **pendiente commitear + setear las env
de Railway.** Ver el anexo Archivista en `Roadmap_Modular.md`.
