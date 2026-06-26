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
- **Datos:** Sheets `Transacciones`/`Categorias`/`Tarjetas y Deuda`/`Dashboard`/`Metas`; Supabase `inferencias`.
- **Espina:** nace mínima. Siembra `perfil` con lo que ya sabemos de ti; escribe inferencias de gasto/deuda. **Se construye la vista `/perfil` (aún corta).** Sin correlación todavía.
- **Eval:** foto→categoría correcta · "aceptar todo" escribe sin duplicar · faro da $2.028.091 y $48.236 · el freno muestra la deuda antes de una cuota · la intención se infiere y se corrige en el digest · una meta muestra su % de avance.
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
- **Fase 2 (DIFERIDA — no en este módulo):** motor de frecuencia — cada compra marcada guarda su fecha (Fase 1 ya siembra ese historial); luego calcula el intervalo medio por ítem → infiere reposición → alerta *"puede que toque comprar azúcar"* (sale por **Proactividad**). Se persiste en Supabase (`aprendizaje`).
- **Datos:** Sheets `Compras`; Supabase `aprendizaje` (recién en Fase 2).
- **Espina:** Fase 1 siembra el historial de compras con fecha (insumo de la inferencia de Fase 2).
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
Estados: ⬜ pendiente · 🔨 construyendo · 🧪 prueba sem X/7 · ✅ promovido

1. Finanzas — ⬜
2. Salud — ⬜
3. Compras — ⬜  *(nuevo)*
4. Recordatorios/Calendario — ⬜
5. Correo — ⬜
6. Productividad — ⬜
7. Proactividad — ⬜
8. Familia — ⬜  *(nuevo)*

---

*El próximo artefacto no es un documento. Es Finanzas en 🧪 prueba sem 1/7.*
