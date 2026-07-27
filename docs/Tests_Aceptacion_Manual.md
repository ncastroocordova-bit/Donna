# Tests de aceptación manual — Donna

Esto es tuyo, Nico. No es un eval automático (esos viven en `tests/`) — es la lista de
cosas que **tú** pruebas con la vida real (tu plata, tu correo, tus boletas) para
comprobar que cada función y cada herramienta de un módulo hace lo que promete.

> **Actualizado 2026-07-06** contra el código real (no telemetría de producción). Se reescribió
> por completo: el flujo de sueño del brief cambió (ya no es el botón «7h+/menos», ahora son chips
> de hora con derivación automática), los MITs viven en `Tareas`, y se agregaron los módulos que ya
> están cableados en el bot pero no estaban aquí (Recordatorios, Correo/Spam, Proyectos/Tareas,
> Diagnóstico). El mismo día se sacó agua/proteína del cierre (quedan como columnas legado) y el
> peso pasó de preguntarse solo el domingo a preguntarse cada cierre.
>
> **Addendum 2026-07-17** (aún sin re-verificar test por test contra el código nuevo): el **digest
> nocturno es ahora "vivo"** — un solo mensaje anclado que se edita en el lugar, con **chips top-3
> aprendidos** (confirmar categoría/comercio de un toque) e ítems por excepción, y escribe en **un commit
> único** al cerrar (ver sección 1.G, que puede necesitar ajuste). El **cierre se reorganizó** a una
> **cadena de una pregunta a la vez** y ahora acepta MITs y evento contextual **por voz o por texto**
> indistintamente; las **horas de comida** se capturan en dos franjas (mañana 6-12 / noche 18-01), así que
> los valores exactos de los chips en 2.A4/A5 pueden diferir. Se agregó el comando **`/brief`** (brief a
> demanda, solo lectura, no consume el de las 8:00). Canon de datos: **dos planillas** (Donna vida / Louis
> plata) — las finanzas viven en Louis.

## Cómo usarlo
- Marca `- [x]` cuando lo probaste y salió bien. Anota la fecha y, si algo falló, qué pasó
  exactamente (mensaje que mandaste + lo que respondió Donna) justo debajo del ítem.
- No hace falta hacerlos todos el mismo día — de hecho varios necesitan que pase tiempo real
  (un cargo real del banco, una boleta real, un par de días para ver si algo se duplica).
- Commitea este archivo a medida que avanzas, así queda el historial de cuándo se probó cada cosa.
- **Gate híbrido (alineado con `Roadmap_Modular.md`):** todos los tests de un módulo en verde =
  **🔨 construido** (habilita usarlo en serio); **7 días corriendo estable** en producción =
  **✅ promovido** (recién ahí, el módulo siguiente). Los tests manuales son el sustituto de la
  telemetría que aún no tenemos, no un reemplazo del sello de estabilidad.

## Atajos por comando (te ahorran esperar el reloj)
- `/cierre` — abre el panel del cierre a mano (hábitos + ánimo + MIT + digest), sin esperar las 22:00.
- `/brief` — muestra el brief a demanda (solo lectura; **no** consume el brief programado de las 8:00).
- `/digest` — muestra el digest financiero del día en cualquier momento.
- `/correos` — fuerza la sincronización de correos de gasto ahora (si no, corre solo cada 3h).
- `/lista` — manda la lista del súper tocable (un ✅ por producto).
- `/spam` — muestra el digest de spam para archivar por toque.
- `/perfil` — la vista "lo que sé de ti" (perfil + inferencias top).
- `/onboarding` — re-arranca el onboarding (si tu perfil quedara vacío).

## Trabajos automáticos (para saber cuándo esperar cada cosa)
- **Brief 8:00** (solo lectura) · **Proactividad 12:00** (máx 1/día) · **Cierre 22:00** (panel + digest).
- **Resumen semanal**: domingo 22:30 (escribe en la hoja `Semanal`, no manda mensaje).
- **Sync de correos**: cada 3h · **"¿qué compraste?"**: revisa cada 5h · **Digest de spam**: 1×/día.
- **Estados de cuenta**: diario 9:30, pero solo actúa cuando llega un PDF nuevo (≈ mensual).
- Al reiniciarse el bot recupera el brief/cierre/spam del día si se los perdió, y corre un
  **guardián de schema** que anota un incidente si a una hoja crítica le falta una columna.

## Índice de módulos
1. [Finanzas](#1-finanzas-fin_) — ✅ construido (v1–v4). Tests abajo.
2. [Salud](#2-salud-sal_) — ✅ construido (base + v2). Tests abajo.
3. [Compras](#3-compras-cmp_) — ✅ Fase 1 (lista manual). Tests abajo. Fase 2 (predictor) diferida.
4. [Recordatorios](#4-recordatorios-rec_) — 🔶 parcial (schema real OK, falta la escalera completa). Tests abajo.
5. [Correo / Spam](#5-correo--spam-cor_--spam_) — 🔶 parcial (spam archivar OK; bucket "importante" pendiente). Tests abajo.
6. [Proyectos y Tareas](#6-proyectos-y-tareas-proy_--tarea_) — 🔶 parcial (schema real OK, falta reconciliación/factor optimismo). Tests abajo.
7. [Núcleo: memoria, perfil, inferencias, diagnóstico](#7-núcleo-memoria-perfil-inferencias-diagnóstico) — transversal. Tests abajo.
8. Proactividad (`pro_`) — 🔶 base construida, se prueba junto con las señales de cada módulo (ver 7.E).
9. Familia (`fam_`) — ⬜ sin código todavía. No aplica.

---

## 1. Finanzas (`fin_`)

Tools cableadas: `fin_registrar_gasto`, `fin_saldo_mes`, `fin_presupuesto`, `fin_estado_deuda`,
`fin_armar_digest`, `fin_metas`, `fin_aportar_meta`, `fin_compra_detallada`, `fin_progreso_deuda`.

### A. Captura pasiva por correo (banco → buffer del día)
- [ ] **A1.** Deja que llegue un cargo real (Banco de Chile o Mach) durante el día. Corre `/correos` y revisa `/digest`: debe aparecer con categoría razonable y el monto exacto.
- [ ] **A2.** Un cargo en dólares (compra online, suscripción gringa) → en el digest sale marcado ⚠️ dudosa, con el motivo (estimado a $1.000/US$, pide confirmar el monto en pesos).
- [ ] **A3.** Una transferencia tuya entre tus propias cuentas → **NO** debe aparecer como gasto. Se ignora por RUT (requiere que tu RUT esté en el perfil; si nunca lo cargaste, anótalo como "no aplica" y avísame).
- [ ] **A4.** Una transferencia a un tercero (le pagas a alguien) → **sí** aparece como gasto, con el nombre de la persona como comercio. Una transferencia que te hacen a ti (Itaú) → aparece como **Ingreso**.

### B. Captura pasiva por foto (Vision, ítem a ítem)
- [ ] **B1.** Manda la foto de una boleta legible con productos (súper, farmacia). Donna responde al toque con el monto, la categoría y cuántos ítems leyó.
- [ ] **B2.** Manda la foto de un ticket sin detalle de productos (bencinera, estacionamiento) → responde solo con el monto y categoría, sin ítems.
- [ ] **B3.** Manda una boleta larga (10+ productos). En el digest de esa noche, la suma de los ítems (más una línea "Resto" si no cuadra) debe acercarse al total — no debe faltar plata por repartir.

### C. Captura pasiva por dictado (texto o voz)
- [ ] **C1.** Escribe: *"compré en el Jumbo arroz 1290, leche 990 y pan 1200"* → confirma que anotó 3 ítems (usa `fin_compra_detallada`).
- [ ] **C2.** Dila igual pero por nota de voz → transcribe y anota igual.
- [ ] **C3.** Dila con "resto" sin dar el total: *"en San Valentín gasté 2000 en chanchería, el resto pan"* — anota qué hace Donna cuando no le das el total explícito y repórtame el comportamiento (el "resto" solo cuadra si hay un total del cargo con que cruzarlo).
- [ ] **C4.** Un gasto simple sin desglose: *"gasté 5000 en Uber"* → lo anota al buffer (usa `fin_registrar_gasto`) y avisa que lo confirmas en el cierre.

### D. Correlación foto/dictado + correo (jamás doble conteo)
- [ ] **D1.** El mismo gasto: manda la foto de la boleta Y deja que llegue (o fuerza con `/correos`) el cargo del banco por el mismo monto y fecha (±2 días). Esa noche en el digest debe aparecer **una sola línea** con los ítems — no dos gastos.
- [ ] **D2.** Justo después de dictar una compra con detalle, a los ~30 min Donna intenta cruzarla con el cargo del correo; si lo logra te avisa "quedó como un solo gasto". Verifica que en el digest sea una sola línea.

### E. Pregunta "¿qué compraste?" (condicional)
- [ ] **E1.** *Solo aplica si ya corregiste la categoría de un súper/almacén un par de veces en el digest (así lo aprende como comercio "de compras").* Deja pasar un cargo **bajo $15.000** sin detalle de ese comercio — dentro de las próximas ~5h Donna debería preguntarte "¿qué compraste?" con botones 📷/✍️/⏭️. Si nunca corregiste un comercio así, márcalo "no aplica todavía".
- [ ] **E2. (compra grande → pide la boleta)** Deja pasar un cargo **sobre $15.000** de un comercio de compras. El mensaje debe ser distinto: *"Vi $X en Y. Eso no es un ítem — mándame la boleta y la desgloso yo. 📷"*, y el botón **📷 Mandar la boleta** debe venir **solo, en su propia fila** arriba (el texto baja a "✍️ Prefiero escribirlo").
- [ ] **E3. (la foto se pega a ESE cargo)** Toca 📷 y manda la foto de la boleta. Donna debe responder *"Leí la boleta: N ítem(s) en \<el comercio del cargo\>"* — y en el digest ese cargo tiene que quedar como **una sola línea con sus ítems**, no como dos movimientos (el del banco + el de la foto). Ese era el riesgo: antes la foto se buffeaba aparte y dependía de que la correlación por monto+fecha+comercio la juntara.
- [ ] **E4. (los ítems suman el total del banco)** En el mismo caso de E3, abre los ítems (📋) y verifica que **sumen exactamente el monto del cargo**. Si la boleta traía menos, debe aparecer una línea `Resto` que cuadra la diferencia.
- [ ] **E5. (responder por texto igual funciona)** Toca 📷 pero en vez de la foto escribe el desglose ("12000 pañales, resto abarrotes"). Debe tomarlo como desglose **de ese mismo cargo**, no mandarlo al chat como mensaje suelto.
- [ ] **E6. (el chip 📦/🥖 se aprende)** En el digest, entra a los ítems de una compra y cambia el chip de un producto de despensa (ej. arroz) a 📦. La próxima vez que aparezca ese mismo producto debe venir ya marcado 📦 solo. *(Es lo que antes se olvidaba: el toque moría en ese digest.)*

### F. Consultas conversacionales
- [ ] **F1.** *"¿Cómo voy de plata este mes?"* (`fin_saldo_mes`) → ingresos, gastos y balance; compáralo con lo que sabes que gastaste.
- [ ] **F2.** *"¿Me estoy pasando en alguna categoría?"* (`fin_presupuesto`) → presupuesto por categoría, con montos y %.
- [ ] **F3.** *"¿Cuánta deuda tengo en las tarjetas?"* (`fin_estado_deuda`) → el faro completo (deuda real, intereses muertos, % de utilización, total a pagar).
- [ ] **F4. (el freno)** *"Me quiero comprar unos audífonos en 12 cuotas"* → Donna debe mostrarte el costo real de tu deuda **antes** de opinar. No el sí fácil ni la prohibición sin datos.
- [ ] **F5.** *"¿Qué tengo pendiente de confirmar hoy?"* o `/digest` (`fin_armar_digest`) → la lista del día.
- [ ] **F6.** *"¿Cómo voy con mis metas?"* (`fin_metas`) → si no tienes metas en la hoja `Metas`, te lo dice; si hay una o más, te muestra avance vs. objetivo.
- [ ] **F7.** Con una meta que ya exista en `Metas`: *"aboné 50 mil al fondo de emergencia"* (`fin_aportar_meta`) → confirma el aporte y el nuevo % (revísalo también en la hoja).
- [ ] **F8. (Fase 4, ¡nuevo!)** *"Muéstrame mis cargos"* o *"¿qué he gastado esta semana?"* (`fin_movimientos_recientes`) → lista cada movimiento real ya escrito en `Transacciones` (fecha, comercio, monto, medio), más reciente primero — no solo el total como F1. Antes de esto Donna no tenía ninguna tool para esto y podía quedarse muda o improvisar.

### G. Digest nocturno — botones del panel
- [ ] **G1.** `/cierre` (o espera las 22:00) → llega el panel de hábitos y, si hay movimientos, el digest con botones.
- [ ] **G2.** Toca **"✅ Aceptar todo"** → dice cuántos escribió (y si algo ya estaba, no lo duplica); revisa que aparecieron en la hoja `Transacciones`.
- [ ] **G3.** Toca una línea marcada ⚠️/✏️ y escribe la categoría correcta → la próxima vez que ese mismo comercio aparezca (día distinto), debería llegar ya con esa categoría sin corregirla de nuevo.
- [ ] **G4.** Toca **"📝 Detallar"** en un gasto sin ítems → te ofrece foto o desglosar por texto. Prueba las dos rutas en gastos distintos.
- [ ] **G5.** Toca **"📋 N ítems"** en un gasto con detalle → abre la grilla de ítems (solo los ⚠️ por revisar; "👀 Ver los N" expande a todos). Cada fila trae 4 botones: **✏️ nombre** (abre chips de categoría + "⌨️ Escribirla"), **Intención▸** (cicla Necesario/Inversión/Deseo con un toque), **📦/🥖** (alterna predecible) y **"✅ Listo"** para volver al digest. Verifica que no se traba al re-tocar el mismo valor.
- [ ] **G5-bis. Corregir el NOMBRE del ítem, y que se aprenda (Fase 5, ¡nuevo!)** Toca **✎** en un ítem → te pide el nombre correcto por texto (ej. la foto leyó "pahales" y le escribes *"Pañales Emilio"*). Confirma que el ítem queda con el nombre nuevo en la grilla. **La prueba real:** la próxima vez que una boleta o dictado traiga el mismo texto mal leído (mismo comercio/ítem), el nombre debería salir ya corregido solo, sin que tengas que volver a tocar ✎.
- [ ] **G6.** Al corregir una línea, escribe *"descartar"* → esa línea desaparece del digest sin escribirse a la planilla.

### H. Anti-duplicado
- [ ] **H1.** Corre `/correos` dos veces seguidas → la segunda no debe traer de nuevo los mismos gastos.
- [ ] **H2.** Di el mismo gasto manual dos veces el mismo día (*"gasté 5000 en Uber"* dos veces) → la segunda vez Donna debe decir que ya lo tenía anotado.
- [ ] **H3.** Toca "Aceptar todo" y después vuelve a correr `/digest` el mismo día → lo ya aceptado no reaparece ni se duplica en la planilla.

### I. Faro de deuda — cifras exactas
- [ ] **I1.** Compara la respuesta de F3 con lo que dice físicamente "Tarjetas y Deuda" (celdas B4 a B8) — deben calzar exacto, incluida la línea de crédito.
- [ ] **I2.** Después de una cuota nueva o un abono a la tarjeta, vuelve a preguntar por la deuda → el número refleja el cambio real de la planilla, no se queda pegado.

### J. Gap conocido — no es un bug nuevo
- [ ] **J1.** Pide *"crea una meta nueva: viaje a Brasil, objetivo 800 mil"* → hoy Donna **no** tiene tool para crear metas (solo leer/aportar). Debería decirte que la cargues tú en la hoja `Metas`. Si de verdad te la crea, avísame.

### K. Estados de cuenta automáticos (v4)
Sin atajo por comando — corre solo a las **9:30** y solo actúa cuando hay un PDF de estado nuevo
en el correo (Banco de Chile o Mach). Para forzarlo sin esperar, avísame en la sesión.
- [ ] **K1.** El día que llegue un estado real, espera al día siguiente después de las 9:30 → debe llegarte un mensaje con el detalle y el delta vs. el mes anterior. Revisa la hoja `Deuda_Mensual`: fila nueva para ese mes/banco/producto.
- [ ] **K2.** Revisa "Tarjetas y Deuda" (las celdas-input, no las fórmulas B4:B8) → el monto de deuda/cupo de ese producto refleja el valor real del estado, no el viejo.
- [ ] **K3.** Pregunta *"¿cómo va mi deuda?"* (`fin_progreso_deuda`) → historial mes a mes (hasta 6 meses) desde `Deuda_Mensual`, y dice si subió o bajó. Antes de que exista algún estado procesado, dice que aún no tiene historial (no inventa).
- [ ] **K4.** La reconciliación del estado contra `Transacciones` solo **marca** posibles compras faltantes (no las escribe solas).
- [ ] **K5. (invariante)** El correo con el PDF sigue en tu inbox después de procesado — el módulo solo lee/baja, jamás borra ni archiva ese correo.

---

## 2. Salud (`sal_`)

> **Antes de correr esto:** `python setup_sheets.py` tiene que haber corrido contra tu planilla
> real al menos una vez (agrega las columnas nuevas de `Diario`/`Semanal` sin tocar tus datos).
> Si nunca lo corriste, esas columnas no existen y los tests fallan por eso, no por el código.

Tools cableadas: `sal_marcar_habito`, `sal_registrar_animo`, `sal_registrar_sueno`, `sal_racha`,
`sal_resumen_semana`, `sal_set_hora`, `sal_peso`, `sal_resumen_ventanas`, `sal_score_semana`,
`sal_evento_contextual`.

### A. Panel del cierre (botones) — un solo mensaje, marca varios
`/cierre` (o espera las 22:00). El panel trae, en filas: ejercicio, meditación, última comida,
ánimo, y un botón por cada MIT pendiente. Cada toque marca ✅ **sin cerrar el panel** (puedes
anotar varios). *Agua/proteína se sacaron del panel — ya no se preguntan en el cierre; las
columnas `Agua`/`Proteína` quedan como legado sin capturar. Primera comida también se sacó de
acá (Fase 3) — a las 22:00 ya se le había olvidado a Nico; ahora tiene su propio aviso de
mediodía, ver sección A-bis.*
- [ ] **A1.** Toca **"🏃 Hice ejercicio"** → revisa la fila de hoy en `Diario`, columna `Ejercicio` = "Sí".
- [ ] **A2.** Otro día toca **"🏃 Hoy no"** → queda "No" (registrado, pero no suma a la racha).
- [ ] **A3.** Toca **"🧘 Medité"** → columna `Meditación`.
- [ ] **A5.** Toca un chip **"🍽️ 18/19/20/21+"** (última comida) → columna `Última comida`.
- [ ] **A6.** Toca un **Ánimo** (1 a 4) → columna `Ánimo (1-4)`.
- [ ] **A7.** Si hay MITs pendientes, cada uno es un botón (☐/✅). Tócalo → lo marca hecho en `Tareas`; tócalo de nuevo → lo desmarca (toggle).
- [ ] **A8.** Después del panel llega el pedido de MITs por voz. Dicta 1-3 prioridades de mañana → se crean como filas en `Tareas` (Tipo=MIT, Fecha objetivo=mañana). *Ojo: la columna `MITs de mañana` de `Diario` es legado y ya no se usa — los MITs viven en `Tareas`.*

### A-bis. Primera comida — aviso independiente de mediodía (Fase 3, ¡nuevo!)
A las 12:30 (después de Proactividad, que ocupa las 12:00) llega un mensaje aparte con chips de
hora (6 a 12), solo si todavía no quedó anotada la primera comida de hoy.
- [ ] **A9.** A las 12:30, si no le has contado tu primera comida por otro medio, te llega *"¿A qué hora comiste hoy por primera vez?"* con chips. Tócalo → columna `Primera comida` (HH:00).
- [ ] **A10.** Si ya se la contaste antes por chat (ej. *"comí a las 8"*, ver C1) o ya tocaste el chip, el aviso de las 12:30 **no debe llegar** ese día.

### B. Sueño — ahora por hora, con derivación automática (¡cambió!)
El brief de las 8:00 ya **no** pregunta el binario "7h+/menos". En su lugar manda una pregunta
con chips de hora y encadena dos pasos:
- [ ] **B1.** En el brief, toca uno de los chips de **hora en que te dormiste** (22:30 / 23:00 / 00:00 / 01:00 / 02:00) → revisa `Hora dormí`. Donna encadena "¿y a qué hora despertaste?".
- [ ] **B2.** Toca uno de los chips de **hora que despertaste** (06:30 / 07:00 / 07:30 / 08:00 / 09:00) → revisa `Hora desperté`. Donna calcula la ventana de sueño y **setea `Sueño 7h+` sola** (Sí/No) — verifica que la columna quedó coherente con las dos horas que tocaste, y que el mensaje te dice si dormiste tus 7h+.
- [ ] **B3.** Por texto en cualquier momento: *"anoche me dormí como a la 1"* (`sal_registrar_sueno`) → revisa `Hora dormí`.

### C. Horas conversacionales — primera comida / despertar (v2)
- [ ] **C1.** *"Recién comí por primera vez, tipo las 8"* (`sal_set_hora`) → columna `Primera comida`.
- [ ] **C2.** *"Desperté a las 7"* → columna `Hora desperté`. Confirma que **NO** tocó `Hora dormí` (son cosas distintas).
- [ ] **C3.** Corrige la última comida por texto: *"cené como a las 21:45"* → columna `Última comida`.

### D. Peso — se pregunta cada cierre (¡cambió!)
- [ ] **D1.** Cada noche, al final del panel del cierre debe llegar un mensaje aparte preguntando el peso (ej. *"¿cuánto marcaste hoy en la pesa?"*). Verifica que llega todos los días, no solo domingo.
- [ ] **D2.** Respóndele con tu peso (*"77.5"* o *"peso 78 kilos"*, `sal_peso`) → columna `Peso (kg)`.

### E. Evento contextual (v2)
- [ ] **E1.** Cada noche, después del panel, llega la pregunta *"¿hubo algo hoy fuera de tu control…?"*. Respóndele *"no"* / *"nada"* → Donna no debe decir que anotó nada (no guarda un evento nulo).
- [ ] **E2.** Otro día, cuéntale algo real (*"se enfermó Emilio y tuve que llevarlo a urgencias"*, `sal_evento_contextual`) → confirma que lo anotó como **contexto**, no como patrón (memoria con tag `evento_externo`).

### F. Ventanas y score (conversacional)
- [ ] **F1.** *"¿Cómo ando con mi ventana de comida/ayuno?"* (`sal_resumen_ventanas`) → mediana real (semana vs. finde) con cuántos días la sostienen. No propone meta todavía (canon: solo mide). Si aún no hay horas suficientes, lo dice.
- [ ] **F2.** *"¿Cómo va mi score de hábitos esta semana?"* (`sal_score_semana`) → un % que puedas verificar a mano (ejercicio + meditación + sueño 7h, sobre los días con fila esa semana).

### G. Revisión semanal — mensaje del domingo 22:30 (¡ahora visible!)
El domingo 22:30 Donna te manda la **revisión de la semana** en su voz (además de escribir la hoja `Semanal`). Antes esto era silencioso; ahora te llega.
- [ ] **G1.** El domingo a las 22:30 (después del cierre) debe llegar un mensaje con tu semana: score de hábitos, ventanas de ayuno/sueño y tu peso con la tendencia (ej. *"77 kg (-1.0 vs la anterior)"*). Los números tienen que cuadrar con lo que registraste.
- [ ] **G2.** Justo después, si el correlador tiene cruces vigentes (sueño↔ánimo / sueño↔gasto), te llega **uno por cruce** con los botones *"Sí, me pasa" / "No, coincidencia" / "Es por otra razón…"* — incluidos los que ya estaban confirmados. Prueba **"No, coincidencia"** en uno que veas raro → lo archiva (deja de insistir). Prueba **"Es por otra razón…"** → te pide la razón y la guarda.
- [ ] **G3.** El lunes, revisa la hoja `Semanal`: fila de la semana que terminó (columna `Semana (lunes)` con la fecha del lunes), con `Score hábitos`, `Ventana comida`, `Ventana sueño` llenos. `Peso` tiene algo si registraste peso esa semana (o la última lectura disponible).
- [ ] **G4. (resiliencia)** Si el domingo el bot estuvo caído a las 22:30 y arranca más tarde (aún domingo), la revisión debe salir igual al reiniciar (no se pierde en silencio como antes).

### H. Señal de salud (brief / cierre)
- [ ] **H1.** Después de 3+ noches seguidas con poco sueño (ventana < 7h), el brief debe mencionar el patrón sueño→ánimo con su dato (no lo inventa antes de esas 3 noches).
- [ ] **H2.** Verifica en `/perfil` que no aparece ningún patrón sin su dato al lado.
- [ ] **H3.** Con 3+ días seguidos de un hábito binario (ejercicio/meditación), la señal puede mencionar la racha. *"¿cuántos días llevo meditando?"* (`sal_racha`) debe darte el número real.

### I. Resumen de la semana (conversacional)
- [ ] **I1.** *"¿Cómo voy esta semana?"* (`sal_resumen_semana`) → incluye ejercicio, meditación (cada uno "x/7"), sueño 7h+ y ánimo promedio.

### J. Correlador — guardia anti-patrón-falso (horizonte largo, ≥2-3 semanas)
- [ ] **J1.** Plazo largo: un día con evento contextual (E2) Y mala noche de sueño. Cuando el correlador tenga datos para proponer el cruce sueño↔ánimo, ese día no debería arrastrar el promedio hacia abajo. Si ves que un patrón se apoya fuerte en un día que tuvo causa externa, avísame.

---

## 3. Compras (`cmp_`)

Fase 1 (lista manual del súper) — parser determinista, sin LLM. Fase 2 (predictor de reposición)
diferida por canon: no hay nada de eso que probar todavía. Tools: `cmp_agregar`, `cmp_lista`, `cmp_comprado`.

### A. Agregar (`cmp_agregar`)
- [ ] **A1.** *"Donna falta arroz"* → confirma "Anotado para el súper: Arroz." Revisa la hoja `Compras`: fila nueva, Estado=`pendiente`, `Fecha_Agregado`=hoy.
- [ ] **A2.** *"queda poco atún y se acabó el papel higiénico"* (dos ítems en una frase) → **dos** filas separadas ("Atún" y "Papel Higiénico"), no una mezclada.
- [ ] **A3.** Repite *"falta arroz"* (ya está pendiente) → Donna dice que ya estaba, **sin** crear fila duplicada.
- [ ] **A4.** Dilo por nota de voz → funciona igual que A1.

### B. Lista (`cmp_lista` y `/lista`)
- [ ] **B1.** *"dame la lista del súper"* → devuelve **solo** lo pendiente (no lo comprado). Compáralo con la hoja.
- [ ] **B2.** Con la lista vacía → dice que está vacía, no inventa ni tira error.
- [ ] **B3.** `/lista` → mismo contenido pero con un botón ✅ por producto (teclado tocable).

### C. Marcar comprado (`cmp_comprado` y botón)
- [ ] **C1.** *"ya compré el arroz"* → confirma que lo sacó. Revisa `Compras`: la misma fila queda Estado=`comprado`, `Fecha_Comprado`=hoy.
- [ ] **C2.** Toca el botón ✅ de un ítem en `/lista` → mismo resultado, y el mensaje se refresca mostrando la lista sin ese ítem (sin trabarse).
- [ ] **C3.** Intenta marcar algo que **no** está en la lista (*"tacha el chocolate"* sin haberlo agregado) → dice que no lo encontró, no crea nada ni falla en silencio.
- [ ] **C4.** Pide la lista de nuevo → el ítem comprado ya no aparece.

---

## 4. Recordatorios (`rec_`)

🔶 Parcial: el schema real ya está bien (lee/escribe las columnas reales, incluye vencidos, la
escritura es verificada). **Falta scope de la ficha:** la escalera completa (domingo + T-2 + T-0),
"posponer exige fecha" y "nombra el patrón tras 3 posposiciones" — todavía no están construidos.
Tools: `rec_proximos`, `rec_agregar`.

### A. Agregar (`rec_agregar`)
- [ ] **A1.** *"recuérdame pagar la contadora el 5 de cada mes"* → confirma que lo anotó. Revisa `Recordatorios`: fila nueva bien puesta (Recordatorio · Tipo=mensual · Día/Fecha=5 · Estado=Pendiente · Activo=Sí) — sin columnas corridas.
- [ ] **A2.** Uno anual: *"avísame de la patente el 31 de marzo"* → Tipo=anual, Día/Fecha en formato fecha.
- [ ] **A3.** Uno único: *"recuérdame la revisión técnica el 2026-09-15"* → Tipo=única (puede quedar vencido sin repetirse).

### B. Leer (`rec_proximos`)
- [ ] **B1.** *"¿qué recordatorios tengo cerca?"* → lista los activos no-hechos dentro de la ventana, **incluyendo los vencidos** (con "venció hace N días"). Compáralo con la hoja.
- [ ] **B2.** Un recordatorio con monto → aparece con el monto aproximado.

### C. Brief y vencidos (escalera parcial — C4 del roadmap)
- [ ] **C1.** Si tienes un recordatorio dentro de los próximos 7 días, el brief de las 8:00 debe mencionarlo.
- [ ] **C2.** Con un recordatorio **vencido**, el brief debe empujarlo con un botón **✅ Hecho**. Tócalo → queda Estado=Hecho y deja de insistir (revisa la hoja).

### D. Gap conocido
- [ ] **D1.** Intenta posponer un recordatorio ("pospón el IVA para el 20"). Hoy **no** está construido el flujo de posponer-con-fecha ni el "nombra el patrón tras 3 posposiciones". Anota qué hace Donna realmente (probablemente lo trate como un recordatorio nuevo). Es gap de scope, no bug.

---

## 5. Correo / Spam (`cor_` / `spam_`)

🔶 Parcial: el triage de spam (archivar por toque, **jamás borra**) está construido; el bucket
"importante → resumen del brief" todavía no es visible; el bucket financiero ya lo cubre Finanzas.
**Requiere Gmail conectado** (Outlook OFF por canon). Tool: `spam_resumen`.

### A. Digest de spam (`/spam` y job diario)
- [ ] **A1.** `/spam` (o espera el job diario) → lista el spam del día con dominios y asuntos, botón "🗄️ Archivar todo" y un "✋ Conservar" por línea.
- [ ] **A2.** Toca **"🗄️ Archivar todo"** → dice cuántos archivó. **Invariante:** en Gmail quedan con la etiqueta `Donna/Archivado` y **sin** `INBOX` — verifica que **NO** están en la papelera (recuperables de un clic).
- [ ] **A3.** Toca **"✋ Conservar"** en una línea antes de archivar → esa se salva y el resto sigue en la lista.
- [ ] **A4.** Con el spam vacío → dice que está limpio, no inventa.

### B. Conversacional
- [ ] **B1.** *"¿tengo spam?"* (`spam_resumen`) → cuenta cuántos hay y da una muestra, sin archivar nada todavía.

### C. Invariante duro (revísalo con calma)
- [ ] **C1.** Después de cualquier acción de spam, entra a Gmail y confirma que **ningún** correo terminó en Papelera/Trash. Si alguno desapareció de verdad, es una violación de invariante — avísame de inmediato.

---

## 6. Proyectos y Tareas (`proy_` / `tarea_`)

🔶 Parcial: el bug de schema quedó **cerrado** (operan por nombre sobre el schema real). **Falta
scope:** reconciliación nocturna, tiempo-por-frente en `Semanal` y factor de optimismo — no construidos.
Tools: `proy_listar`, `proy_crear`, `proy_actualizar`, `proy_cerrar`, `tarea_listar`, `tarea_crear`, `tarea_completar`.

> **Riesgo cruzado con Salud:** los MITs viven en la misma hoja `Tareas` (Tipo=MIT). El código de
> Proyectos los **excluye** del avance, pero si mezclas MITs y tareas normales al probar, tenlo presente.

### A. Proyectos
- [ ] **A1.** *"tengo un proyecto nuevo: tesis"* (`proy_crear`) → revisa `Proyectos`: fila nueva (Proyecto · Estado=Activo · …) sin columnas corridas.
- [ ] **A2.** *"¿cómo van mis proyectos?"* (`proy_listar`) → lista los activos con avance real (tareas hechas/total de **ese** proyecto, no todas). Verifica el conteo contra la hoja.
- [ ] **A3.** *"en la tesis, el foco ahora es el capítulo 2"* (`proy_actualizar`) → actualiza Foco actual; revisa la hoja.
- [ ] **A4.** *"terminé el proyecto X"* (`proy_cerrar`) → queda Estado=Completado.

### B. Tareas
- [ ] **B1.** *"agrega a la tesis: escribir la intro"* (`tarea_crear`) → fila nueva en `Tareas` (Creada · Descripción · Proyecto=tesis · …), Estado=Pendiente.
- [ ] **B2.** *"¿qué tareas tengo?"* (`tarea_listar`) → lista las pendientes con su descripción real (no "None"). Los MITs salen etiquetados `[MIT]`.
- [ ] **B3.** *"terminé la intro de la tesis"* (`tarea_completar`) → la marca Completada. Verifica en la hoja y que el avance del proyecto (A2) sube.
- [ ] **B4.** Tras completar tareas, `proy_listar` debe reflejar el nuevo %.

---

## 7. Núcleo: memoria, perfil, inferencias, diagnóstico

Transversal (la espina). Tools de núcleo: `buscar_memoria`, `guardar_memoria`, `actualizar_perfil`,
`leer_agenda`, `abrir_inferencia`, `registrar_compromiso`, `ver_compromisos`, y `diag_estado`.

### A. Perfil (`/perfil`, `actualizar_perfil`)
- [ ] **A1.** Cuéntale un hecho estable tuyo (*"me dedico a Ñoomi y a la tesis"*) → debe guardarlo. Luego `/perfil` lo muestra bajo "lo que sé de ti".
- [ ] **A2.** `/perfil` muestra también las inferencias top, cada una con su marca (✓ confirmada / · por validar) y su dato.

### B. Memoria (`guardar_memoria`, `buscar_memoria`)
- [ ] **B1.** Cuéntale algo que valga la pena recordar → luego, en otra conversación, pregúntale por eso y debe recuperarlo.
- [ ] **B2. (privacidad)** Arranca un mensaje con *"off the record …"* → no debe guardar eso. Y *"olvida X"* debe borrarlo.

### C. Inferencias (mecanismo estrella)
- [ ] **C1.** Cuando Donna te proponga una inferencia (en el cierre, si hay una pendiente) con botones **"Sí, me pasa" / "No, coincidencia" / "Es por otra razón…"** → prueba las tres rutas en momentos distintos y verifica que responde acorde (confirma, archiva, o pide la razón).
- [ ] **C2. (invariante)** Nunca debe afirmarte un patrón sin mostrarte el dato que lo respalda. Si lo hace, avísame.

### D. Compromisos (`registrar_compromiso`, `ver_compromisos`)
- [ ] **D1.** *"mañana llamo al banco"* → lo registra como compromiso. Luego *"¿qué tengo pendiente?"* debe listarlo.

### E. Proactividad (12:00, máx 1/día)
- [ ] **E1.** Un día que NO le hayas escrito y haya una señal real (compromiso vencido / proyecto en riesgo / meta atrasada), cerca de las 12:00 Donna puede romper el silencio con **un** mensaje. Verifica que es máximo 1 al día y que calla si no hay señal.

### F. Diagnóstico (`diag_estado`)
- [ ] **F1.** *"¿qué se ha roto?"* / *"¿estás funcionando bien?"* → lista los incidentes abiertos que detectó (o dice que está todo en orden). No inventa.
- [ ] **F2.** Si alguna tool falla mientras la usas, Donna te responde **en carácter** (sin stacktrace) y deja el incidente anotado. Si lo pillas, confirma que `diag_estado` después lo muestra.

---

*Familia (`fam_`) no tiene código todavía — cuando se construya, se agrega su sección aquí siguiendo
la misma estructura (ver la nota de mantenimiento en `Roadmap_Modular.md`).*
