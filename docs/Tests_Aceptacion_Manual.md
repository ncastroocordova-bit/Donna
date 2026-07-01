# Tests de aceptación manual — Donna

Esto es tuyo, Nico. No es un eval automático (esos viven en `tests/`) — es la lista de
cosas que **tú** pruebas con la vida real (tu plata, tu correo, tus boletas) para
comprobar que cada función y cada herramienta de un módulo hace lo que promete.

## Cómo usarlo
- Marca `- [x]` cuando lo probaste y salió bien. Anota la fecha y, si algo falló, qué pasó
  exactamente (mensaje que mandaste + lo que respondió Donna) justo debajo del ítem.
- No hace falta hacerlos todos el mismo día — de hecho varios necesitan que pase tiempo real
  (un cargo real del banco, una boleta real, un par de días para ver si algo se duplica).
- Commitea este archivo a medida que avanzas, así queda el historial de cuándo se probó cada cosa.
- **Un módulo se da por completo (gate del roadmap) cuando todos sus tests están en verde**, no
  antes — eso reemplaza al "7 días estable" mientras no tengamos telemetría real de producción.

## Índice de módulos
1. [Finanzas](#finanzas-fin_) — ✅ listo abajo
2. [Salud](#salud-sal_) — ✅ listo abajo
3. Recordatorios (`rec_`) — 🔜 pendiente
4. Correo/spam (`cor_`) — 🔜 pendiente (recuerda: tiene el riesgo de invariante del `trash`, ver Roadmap_Modular.md)
5. Productividad — Tareas y Proyectos — 🔜 pendiente
6. Proactividad (`pro_`) — 🔜 pendiente
7. Compras (`cmp_`) y Familia (`fam_`) — ⬜ no aplica, no tienen código todavía

---

## Finanzas (`fin_`)

**Antes de empezar, tres atajos que te ahorran tiempo** (no hace falta esperar el reloj):
- `/correos` — fuerza la sincronización de correos de gasto ahora mismo (si no, corre solo cada 3h).
- `/digest` — muestra el digest del día en cualquier momento.
- `/cierre` — abre el panel de cierre a mano, sin esperar a las 22:00.

### A. Captura pasiva por correo (banco → buffer)
- [ ] **A1.** Deja que llegue un cargo real (Banco de Chile o Mach) durante el día. Al rato, corre `/correos` y revisa `/digest`: debe aparecer con categoría razonable y el monto exacto.
- [ ] **A2.** Un cargo en dólares (compra online, suscripción gringa) → en el digest debe salir marcado ⚠️ dudosa, con el motivo (estimado a $1.000/US$).
- [ ] **A3.** Una transferencia tuya entre tus propias cuentas (Banco de Chile ↔ Itaú, por ejemplo) → **NO** debe aparecer como gasto en el digest. Se ignora por diseño.
- [ ] **A4.** Una transferencia a un tercero (le pagas a alguien) → **sí** debe aparecer como gasto, con el nombre de la persona como comercio.

### B. Captura pasiva por foto (Vision, ítem a ítem)
- [ ] **B1.** Manda la foto de una boleta legible con productos (súper, farmacia). Donna debe responder al toque con el monto, la categoría y cuántos ítems leyó.
- [ ] **B2.** Manda la foto de un ticket sin detalle de productos (bencinera, estacionamiento) → responde solo con el monto y categoría, sin ítems.
- [ ] **B3.** Manda una boleta larga (10+ productos). En el digest de esa noche, revisa que la suma de los ítems (más una línea "Resto" si no cuadra) se acerque al total — no debe faltar plata por repartir.

### C. Captura pasiva por dictado (texto o voz)
- [ ] **C1.** Escribe: *"compré en el Jumbo arroz 1290, leche 990 y pan 1200"* → confirma que anotó 3 ítems.
- [ ] **C2.** Dila igual pero por nota de voz → debe funcionar exactamente igual (transcribe y anota).
- [ ] **C3.** Dila con "resto": *"en San Valentín gasté 2000 en chanchería, el resto pan"* — sin decir el total. Anota qué hace Donna cuando no le das el total explícito (puede que pida el total, o que "resto" quede en 0 — repórtame el comportamiento real).

### D. Correlación foto/dictado + correo (jamás doble conteo)
- [ ] **D1.** El mismo gasto: manda la foto de la boleta Y deja que llegue (o fuerza con `/correos`) el cargo del banco por el mismo monto y fecha. Esa noche en el digest debe aparecer **una sola línea** con los ítems — no dos gastos separados.
- [ ] **D2.** Justo después de mandar la foto (antes de que llegue el correo), revisa `/digest` → debe estar ahí como una entrada con ítems. Después de que cruce con el correo, sigue siendo una sola línea, no se duplica.

### E. Pregunta "¿qué compraste?" (condicional)
- [ ] **E1.** *Este solo aplica si ya corregiste la categoría de un súper/almacén un par de veces en el digest (eso lo "aprende" como comercio de compras).* Deja pasar un cargo sin detalle de ese comercio — dentro de las próximas ~5 horas Donna debería preguntarte "¿qué compraste?" con botones 📷/✍️/⏭️. Si nunca has corregido ningún comercio así, anota este test como "no aplica todavía" y sáltalo.

### F. Consultas conversacionales
- [ ] **F1.** *"¿Cómo voy de plata este mes?"* → ingresos, gastos y balance; compáralo con lo que tú sabes que gastaste.
- [ ] **F2.** *"¿Me estoy pasando en alguna categoría?"* → presupuesto por categoría, con montos y %.
- [ ] **F3.** *"¿Cuánta deuda tengo en las tarjetas?"* → el faro completo (deuda real, intereses muertos, % de utilización).
- [ ] **F4. (el freno)** *"Me quiero comprar unos audífonos en 12 cuotas"* → Donna tiene que mostrarte el costo real de tu deuda **antes** de opinar. No debe darte el sí fácil ni tampoco prohibirte sin datos.
- [ ] **F5.** *"¿Qué tengo pendiente de confirmar hoy?"* (o `/digest`) → la lista del día.
- [ ] **F6.** *"¿Cómo voy con mis metas?"* → si no tienes metas cargadas en la hoja `Metas`, debe decírtelo. Si ya tienes una o más, te muestra avance vs. objetivo.
- [ ] **F7.** Con una meta que ya exista en la hoja `Metas`: *"aboné 50 mil al fondo de emergencia"* → confirma el aporte y el nuevo % de avance (revísalo también en la hoja).

### G. Digest nocturno — botones del panel
- [ ] **G1.** `/cierre` (o espera las 22:00) → llega el panel de hábitos y, si hay movimientos, el digest con botones.
- [ ] **G2.** Toca **"✅ Aceptar todo"** → te dice cuántos escribió; revisa que efectivamente aparecieron en la hoja `Transacciones`.
- [ ] **G3.** Toca una línea marcada ⚠️/✏️ y escribe la categoría correcta → la próxima vez que ese mismo comercio aparezca (día distinto), debería llegar ya con esa categoría sin que la corrijas de nuevo.
- [ ] **G4.** Toca **"📝 Detallar"** en un gasto sin ítems → te ofrece foto o desglosar por texto. Prueba las dos rutas en gastos distintos.
- [ ] **G5.** Toca **"📋 N ítems"** en un gasto con detalle → abre el editor. Toca un ítem, cámbiale Necesario/Inversión/Deseo, alterna Despensa/Perecible, toca "Categoría" y escribe una nueva, prueba "⬅️ Volver" y por último "✅ Listo".
- [ ] **G6.** Al corregir una línea, escribe *"descartar"* → esa línea debe desaparecer del digest sin escribirse a la planilla.

### H. Anti-duplicado
- [ ] **H1.** Corre `/correos` dos veces seguidas → la segunda vez no debe traer de nuevo los mismos gastos.
- [ ] **H2.** Di el mismo gasto manual dos veces el mismo día (*"gasté 5000 en Uber"* dos veces) → la segunda vez Donna debe decirte que ya lo tenía anotado.
- [ ] **H3.** Toca "Aceptar todo" y después vuelve a correr `/digest` el mismo día → lo ya aceptado no debe reaparecer ni duplicarse en la planilla.

### I. Faro de deuda — cifras exactas
- [ ] **I1.** Compara la respuesta de F3 con lo que dice físicamente la hoja "Tarjetas y Deuda" (celdas B4 a B8) — deben calzar exacto, incluida la línea de crédito.
- [ ] **I2.** Después de una cuota nueva o un abono a la tarjeta, vuelve a preguntar por la deuda → el número tiene que reflejar el cambio real de la planilla, no quedarse pegado en el valor anterior.

### J. Gap conocido — no es un bug nuevo, ya lo tengo mapeado
- [ ] **J1.** Pide *"crea una meta nueva: viaje a Brasil, objetivo 800 mil"* → hoy Donna probablemente **no** la crea en la hoja `Metas` (el mensaje de `fin_metas` lo insinúa pero no existe esa herramienta todavía). Si de verdad te la crea, avísame — significaría que hay código que no vi.

---

## Salud (`sal_`)

Antes de correr esto: `python setup_sheets.py` tiene que haber corrido contra tu planilla real
al menos una vez (agrega las columnas nuevas de `Diario`/`Semanal` sin tocar tus datos — es
aditivo). Si nunca lo corriste, estas columnas no existen todavía en tu Sheet y los tests van
a fallar por eso, no por el código.

### A. Toques del panel de cierre (botones)
- [ ] **A1.** `/cierre` (o espera las 22:00) → toca **"🏃 Hice ejercicio"** → revisa la fila de hoy en `Diario`, columna `Ejercicio`.
- [ ] **A2.** Toca **"🏃 Hoy no"** en otro día → queda "No", no rompe nada, solo no suma a la racha.
- [ ] **A3.** Toca **"💧 Tomé agua"** y **"🥩 Comí proteína"** → revisa que escribieron en `Agua` y `Proteína`.
- [ ] **A4.** Toca uno de los chips de **"🍽️ hora"** (última comida) → revisa `Última comida`.
- [ ] **A5.** Toca un **Ánimo** (1 a 4) → revisa `Ánimo (1-4)`.
- [ ] **A6.** Toca **"Avancé un MIT"** / **"Hoy no"**.
- [ ] **A7.** Después del panel, dicta por voz tus 1-3 prioridades de mañana → revisa `MITs de mañana`.

### B. Sueño
- [ ] **B1.** En el brief de las 8:00, toca **"😴 Dormí 7h+"** o **"Menos de 7h"** → revisa `Sueño 7h+`.
- [ ] **B2.** En cualquier momento, dile *"anoche me dormí como a la 1"* → revisa `Hora dormí` (HH:MM).

### C. Horas nuevas — primera comida / hora de despertar (v2)
- [ ] **C1.** *"Recién comí por primera vez, tipo las 8"* → revisa la columna nueva `Primera comida`.
- [ ] **C2.** *"Desperté a las 7"* → revisa la columna nueva `Hora desperté`. Confirma que NO tocó `Hora dormí` (son cosas distintas).
- [ ] **C3.** Corrige la última comida por texto en vez del chip: *"cené como a las 21:45"* → revisa `Última comida`.

### D. Peso semanal (v2)
- [ ] **D1.** Un domingo, al final del panel del cierre debe llegar un mensaje aparte: *"¿cuánto pesaste esta semana?"*. Verifica que llegue solo los domingos, no el resto de la semana.
- [ ] **D2.** Respóndele con tu peso (ej. *"77.5"* o *"peso 78 kilos"*) → revisa la columna `Peso (kg)` en `Diario`.
- [ ] **D3.** Dile tu peso un día que NO es domingo → igual debe anotarlo (no lo rechaza, solo no lo pide a diario).

### E. Evento contextual (v2)
- [ ] **E1.** Cada noche, después del panel, debe llegar la pregunta *"¿hubo algo hoy fuera de tu control que te bajó el ánimo o no te dejó hacer lo planeado?"*. Respóndele *"no"* o *"nada"* → Donna no debe decir que anotó nada ni tratarlo como dato guardado.
- [ ] **E2.** Otro día, cuéntale algo real (ej. *"se enfermó Emilio y tuve que llevarlo a urgencias"*) → debe confirmarte que lo anotó como contexto, no como patrón.

### F. Ventanas y score (v2, conversacional)
- [ ] **F1.** *"¿Cómo ando con mi ventana de comida/ayuno?"* → te da la mediana real (semana vs. fin de semana) con cuántos días la sostienen. No debe proponerte una meta ni un objetivo todavía (canon: solo mide).
- [ ] **F2.** *"¿Cómo va mi score de hábitos esta semana?"* → un % que puedas verificar a mano contra lo que realmente tocaste esa semana (ejercicio + meditación + sueño 7h + agua + proteína, sobre 7 días).

### G. Resumen semanal automático — hoja `Semanal` (domingo 22:30)
- [ ] **G1.** El lunes, revisa la hoja `Semanal`: debe existir una fila para la semana que acaba de terminar (columna `Semana (lunes)` con la fecha del lunes de esa semana), con `Score hábitos`, `Ventana comida`, `Ventana sueño` llenos. `Peso` debe tener algo si registraste tu peso esa semana (o la última lectura que tengas, si esa semana no hubo).

### H. Señal de salud (brief / cierre)
- [ ] **H1.** Después de 3+ noches seguidas marcando "menos de 7h", el brief de la mañana debe mencionar el patrón sueño→ánimo con su dato (no debe inventarlo antes de esas 3 noches).
- [ ] **H2.** Verifica en `/perfil` (si ya la usas) que no aparece ningún patrón sin su dato al lado.

### I. Resumen de la semana (conversacional, ahora con agua/proteína)
- [ ] **I1.** *"¿Cómo voy esta semana?"* → ahora debe incluir agua y proteína además de ejercicio/meditación/sueño/ánimo, cada uno como "x/7".

### J. Correlador — guardia anti-patrón-falso (horizonte largo, ≥2-3 semanas)
- [ ] **J1.** Este es de plazo largo: identifica un día en que registraste un evento contextual (E2) Y esa misma noche dormiste mal. Con el tiempo, cuando el correlador tenga suficientes datos para proponerte el cruce sueño↔ánimo, ese día en particular no debería aparecer arrastrando el promedio hacia abajo — si notas que Donna te muestra un patrón que se apoya fuerte en un día que tú sabes que tuvo una causa externa, avísame.
