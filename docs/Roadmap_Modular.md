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
- **Surfacing:** bajo demanda + resumen domingo + **proactivo cuando es accionable** (esto último aterriza en el Módulo 6).

## Ficha de módulo (plantilla — se rellena igual cada vez)
> Objetivo · Scope ("completo") · Prefijo · Datos (hojas + Supabase) · Aporte a la espina · Eval que lo gatilla · Semana cumplida.

---

## Los 6 módulos

### 1. Finanzas `fin_`
- **Objetivo:** capturar tu plata sin fricción y mostrarte la verdad de tu deuda.
- **Scope completo:** foto + manual + categorización + faro de deuda (con línea) + dashboard + digest nocturno en el cierre. **Correo NO** (va en Módulo 4).
- **Datos:** Sheets `Transacciones`/`Categorias`/`Tarjetas y Deuda`/`Dashboard`; Supabase `inferencias`.
- **Espina:** nace mínima. Siembra `perfil` con lo que ya sabemos de ti; escribe inferencias de gasto/deuda. **Se construye la vista `/perfil` (aún corta).** Sin correlación todavía.
- **Eval:** foto→categoría correcta · "aceptar todo" escribe sin duplicar · faro da $2.028.091 y $48.236 · el freno muestra la deuda antes de una cuota.
- **Semana:** 7 días registrando gastos reales, estable, evals verdes.

### 2. Salud `sal_`
- **Objetivo:** el eje #1 (sueño) + hábitos y ánimo, y fijar el ritmo diario.
- **Scope completo:** `Diario` (ejercicio, meditación, última comida, sueño 7h, ánimo 1-4, hora dormí) + brief 8:00 (lectura) + cierre 22:00 (toques) + señal sueño×ánimo.
- **Datos:** Sheets `Diario`; Supabase `inferencias`.
- **Espina:** **se enciende el correlador** (2º dominio). Primeros cruces: sueño↔ánimo; y con finanzas, sueño↔gasto.
- **Eval:** marcas hábitos por botón → fila correcta · señal coherente · el cruce sueño↔ánimo aparece con su dato.
- **Semana:** 7 días de cierre real, estable, evals verdes.

### 3. Recordatorios / Calendario `rec_`
- **Objetivo:** que no se te olvide nada y que el calendario esté a la vista.
- **Scope completo:** escalera (domingo + T-2 + T-0 con ✅ Hecho + vencido-insiste) + estados (pendiente/hecho/pospuesto) + tipos (mensual/anual/única) + posponer con fecha; lectura del Google Calendar en el brief.
- **Datos:** Sheets `Recordatorios`; Calendar (lectura).
- **Espina:** inferencias de cumplimiento ("pospones el IVA seguido") → un "contra" con dato.
- **Eval:** T-2/T-0/vencido disparan cuando deben · posponer sin fecha se rechaza · tras 3 posposiciones, nombra el patrón.
- **Semana:** idem.

### 4. Correo `cor_`
- **Objetivo:** triage del inbox sin que tengas que mirarlo, y que **jamás borre**.
- **Scope completo:** inbox dedicado financiero + triage 3 buckets (spam→archivar · importante→resumen brief · financiero→digest) + jamás borra (etiqueta). Enchufa al digest de Finanzas (ya estable).
- **Datos:** Gmail; alimenta `Transacciones` vía `fin_`; Supabase `remitentes`/`aprendizaje`.
- **Espina:** aprende qué remitentes te importan (de tus rescates de `Donna/Archivado`).
- **Eval:** 3 buckets correctos · **assert: ninguna acción borra** · rescatar promueve al remitente.
- **Semana:** idem. *(Es el más delicado; por eso va 4º, con Finanzas ya recibiendo su señal.)*

### 5. Productividad `prod_` / `apr_`
- **Objetivo:** saber en qué se te va el tiempo y frenarte cuando planificas de más.
- **Scope completo:** reconciliación nocturna (con delta) + tiempo por frente en `Semanal` + factor de optimismo (observador externo). **El brief no se toca.**
- **Datos:** Calendar; Sheets `Reconciliacion`/`Semanal`; Supabase `aprendizaje`.
- **Espina:** el factor de optimismo es tu primer "contra" duro con dato; cruces tiempo↔ánimo↔gasto.
- **Eval:** "hice todo" escribe duraciones · con ≥3 semanas frena un plan inflado con su dato · con <2 calla.
- **Semana:** idem.

### 6. Proactividad `pro_`
- **Objetivo:** que Donna hable sola, máx 1/día, **solo cuando un patrón es accionable ahora**.
- **Scope completo:** 1 mensaje espontáneo/día, gatillado por la espina (un cruce accionable). Acá vive tu decisión de "proactivo cuando es accionable".
- **Datos:** Supabase (`inferencias` top); sin escritura nueva.
- **Espina:** es el **brazo de salida** de la espina — convierte lo aprendido en un aviso oportuno.
- **Eval:** dispara solo con señal real · respeta el tope 1/día · calla si nada mueve la aguja.
- **Semana:** idem.

---

## Tablero (una línea por módulo)
Estados: ⬜ pendiente · 🔨 construyendo · 🧪 prueba sem X/7 · ✅ promovido

- Finanzas — ⬜
- Salud — ⬜
- Recordatorios/Calendario — ⬜
- Correo — ⬜
- Productividad — ⬜
- Proactividad — ⬜

---

*El próximo artefacto no es un documento. Es Finanzas en 🧪 prueba sem 1/7.*
