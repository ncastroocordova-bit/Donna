# Donna — Plan v7 (final antes del código)

**Para:** Nico
**Regla madre:** Donna gana su lugar el día que te dice algo sobre ti que tú no habías visto.
**Qué es v7:** v6 + **una sola función nueva** (el digest financiero nocturno) + el runbook de construcción aparte. **No es un rediseño.** Es el último documento antes de escribir código. Si aparece un v8 de "rediseño", esa es la recaída — el eval más importante del proyecto es que este `.md` sea el último.

**Eje de medición:** salud (el sueño es salud) · orden · productividad.

---

## 0. Qué cambia de v6 a v7 (el delta, nada más)

**Lo nuevo:** un **digest financiero diario en el cierre de las 22:00**.
- Durante el día, Donna procesa **en segundo plano** tus correos (Banco de Chile / Mach / MP) y las fotos de boletas que le mandes — cada uno en su propia llamada con **contexto aislado** (patrón subagente, ya en v6 §N4). Vision sobre la foto, parseo sobre el mail.
- A las 22:00 te muestra un **resumen ya listo**, no te hace esperar el procesamiento: una lista de los movimientos del día, **pre-categorizados con su mejor apuesta**.
- Tú haces una de dos cosas: **"✅ Aceptar todo"** (1 toque) si está bien, o **tocas la línea que está mal** para corregir categoría/monto. Solo las dudosas vienen marcadas (ej: *"¿Tecnología o Suscripción?"*).
- Al confirmar, Donna **escribe a `Finanzas_vigente!Transacciones`** con su `ID_Único` (anti-duplicado).

**Lo que NO cambia:** todo lo demás de v6 (tiers, faro de deuda, salud como eje #1, núcleo, evals, contrato de módulo, costo). El brief de la mañana sigue **solo-lectura**.

**Por qué de noche y no de mañana:** a las 22:00 el día ya cerró — todos los movimientos están. Confirmas el gasto del día en el mismo cierre donde ves tu balance. La mañana solo te *muestra* el saldo corriendo; la noche es donde lo *cierras*.

### Adenda v7.1 — módulo Correo (additivo, NO rediseño)
Tras el digest se suma un segundo módulo: **triage diario de inbox**. Clasifica todo tu correo en tres buckets — **spam/bulk → archivar** (etiqueta, fuera del inbox, **nunca borra**), **importante → resumen en el brief 8:00**, **financiero → al digest nocturno**. Es additivo: no toca el núcleo ni reabre el diseño, y **vive en una Fase 1.5, después de que Fase 1 corra sola en Railway** (prueba de promoción). El detalle está en §4.2, §5, §9 y §11. Esta adenda existe justo para no caer en el v8 de "rediseño": el correo es un módulo más bajo el mismo contrato, no una reescritura.

### Adenda v7.2 — reconciliación nocturna + factor de optimismo (additivo)
Dos piezas más, mismo contrato: (1) **reconciliación nocturna** en el cierre — Donna lista los bloques del Calendar del día y tú marcas qué hiciste y si tomó *menos/igual/más* de lo planeado; eso captura tu **tiempo por frente** (Tesis/Noomi/Delivery/Hijo/Personal) y alimenta el Semanal, **sin tocar el brief**. (2) **Factor de optimismo** sobre el módulo de aprendizaje: Donna aprende tu ratio plan-vs-real por frente y se vuelve tu *observador externo*, frenándote cuando planificas de más (corrección de la falacia de planificación vía reference class forecasting). Decisiones de canon que acompañan: productividad **simple** (sin log de tiempo diario), **Tiempo log OFF** (dormido), **Outlook OFF**, y la deuda real **incluye la línea** ($2.028.091; $48.236/mes muertos). **Realidad del proyecto:** el bot ya está ~80% construido (repo Donna.zip); v7.2 ya no se "construye de cero" — se **extiende** para cerrar 8 brechas (ver `Plan_Construccion_v7.md` y `Alineacion_Donna.md`).

---

## 1. Filosofía
1. **Simplicidad primero.** Nada entra hasta que el uso real lo justifique.
2. **Contexto finito.** En cabeza, lo chico y de alta señal. El resto, just-in-time + compactación.
3. **Modular y a prueba de roturas.** Si un módulo cae, el resto sigue.
4. **Medible.** Nada se da por bueno sin un eval que lo demuestre.
5. **Tier por impacto.** La atención de Donna se gasta solo en Tier A (≥80%).
6. **Toque > texto, panel > conversación.** *(refuerzo v7)* La fricción la crean los turnos y el teclado, no la cantidad de campos.

---

## 2. Quién es Donna (carácter — núcleo)
**Donna Paulsen** de *Suits*: te lee como rayos X, se anticipa, cálida pero filosa, confianza y humor, no sumisa, lealtad y memoria total. Marcas: "te conozco", "ya lo resolví", "no me vengas con eso", "soy Donna".

**Ancla maestra (sueño):**
> *"Nico. Cuarta noche después de la 1am. No me vengas con que estás 'cansado nomás' — el viernes te desplomas y lo sabes. Mañana a las 23:00 estás en cama. Te conozco."*

**Ancla de deuda real (v6):**
> *"Pagaste $48.000 este mes y tu deuda no bajó ni un peso — eso es lo que cuesta solo tener la línea topada. Antes de comprar en cuotas, mírame."*

---

## 3. Arquitectura
```
        DONNA — NÚCLEO (estable, carácter cacheado)
        carácter (constitución+anclas, CACHEADO) · conversación (Telegram/voz)
        · memoria (Supabase + contextual retrieval) · inferencia validada
        · brief 8:00 (read-only) / cierre 22:00 (panel único + digest $) · privacidad · EVALS
                 │  interfaz de módulos (señal destilada, contexto aislado)
   ┌──────────┬────────────┬─────────────┬───────────────┬──────────────┬─────────┐
 [Salud]   [Finanzas]   [Correo]    [Productividad] [Recordatorios]  [Noomi]
  Tier A     Tier A       Tier A       Tier A          Tier A         después
  sueño/     digest/      triage/      MITs/           pagos+
  hábitos    deuda/gasto  resumen 8:00 proyectos       fechas
```
Base de datos: `Vida_v6.xlsx` y `Finanzas_vigente.xlsx`. Donna lee y escribe ahí; tú casi no las tocas.

---

## 4. Catálogo de microherramientas por Tier
*(Solo se listan los cambios de v7 sobre el catálogo v6; el resto se mantiene idéntico.)*

### 4.1 MÓDULO FINANZAS — fila nueva ⭐

| # | Herramienta | De dónde sale | Señal / flujo de Donna | Impacto | Tier |
|---|---|---|---|---|---|
| **F0** | **Digest financiero nocturno (confirmar/modificar)** | Correos + fotos del día → `Transacciones` | "Hoy detecté 4 movimientos ($61.690). ✅ Aceptar todo, o toca el que esté mal." | **90%** | **A** |

El resto del módulo Finanzas (F1–F12) queda igual que v6. El digest F0 es el **alimentador** de F1, F8 y F9: sin captura confiable, el motor del mes y el comparativo se llenan de basura. Por eso es Tier A alto.

### 4.2 MÓDULO CORREO — módulo nuevo ⭐ (Fase 1.5, post-deploy)

| # | Herramienta | De dónde sale | Señal / flujo de Donna | Impacto | Tier |
|---|---|---|---|---|---|
| **C0** | **Triage diario de inbox (3 buckets)** | Gmail API → reglas → LLM (residuo) | "19 correos: 3 importantes, 14 archivados, 2 financieros al digest." | **85%** | **A** |
| **C1** | **Resumen de importantes (brief 8:00)** | bucket importante | una línea por correo, solo lectura | 85% | A |
| **C2** | **Archivado seguro (jamás borra)** | bucket spam/bulk | etiqueta `Donna/Archivado`, fuera del inbox, recuperable de un clic | 80% | A |

Filosofía de costo (la misma del digest): **Gmail filtra el spam crudo gratis**; las reglas deterministas (header `List-Unsubscribe`, remitentes `no-reply`, allowlist financiera, allowlist de importantes) resuelven el grueso; el **LLM solo juzga el residuo ambiguo en una sola llamada con snippets** (nunca el cuerpo completo). El módulo comparte la tabla `remitentes(remitente, clase, conteo)` con Finanzas y **aprende de tus acciones**: lo que rescatas de `Donna/Archivado` sube a importante; lo que archivas y estaba como importante, baja.

**Correo dedicado financiero:** tú creas una casilla exclusiva (`finanzas.nico@…`) y rediriges ahí los avisos de tus bancos. Donna la lee como dominio financiero puro. Dentro de esa casilla igual corre el filtro (el banco te manda la alerta real *y* su marketing desde el mismo remitente): transacción = monto + palabra clave (`compra`/`cargo`/`transferencia`/`giro`); marketing = `List-Unsubscribe` → archivar.

### 4.3 MÓDULO RECORDATORIOS — escalera v7.1 ⭐

| # | Herramienta | De dónde sale | Señal / flujo de Donna | Impacto | Tier |
|---|---|---|---|---|---|
| **R0** | **Escalera de aviso (3 toques + escalada)** | `Recordatorios` (+ Calendar opcional) | domingo "esta semana: IVA mar, luz jue" · T-2 "en 2 días: IVA" · T-0 "HOY: IVA ✅ Hecho" · vencido → push aparte, insiste hasta responder | **90%** | **A** |

**Cómo funciona la escalera.** Antes de la fecha, **tres toques calmados que viajan dentro de touchpoints que ya existen** (cero interrupciones nuevas): (1) **domingo**, el cierre extendido lista *todos* los recordatorios de la semana en un solo mensaje; (2) **2 días antes (T-2)**, una línea en el brief; (3) **el día (T-0)**, en el brief con botón **✅ Hecho** (al tocar, cierra; si es recurrente, agenda la próxima). Solo cuando **pasa la fecha sin marcar hecho**, Donna sube el tono: sale del brief, manda su propio push más directo y **insiste cada día hasta que respondas** (hecho o posponer). El loop siempre lo cierras tú; nunca queda sin salida.

**Alcance (v7.1).** Tres tipos: **mensual**, **anual** y ahora **única** (fecha puntual). Cubre cuentas fijas + tareas con fecha + citas. Regla anti-duplicado con `Tareas`: *con fecha y que te persiga = recordatorio; backlog sin fecha = tarea*. Opcional: las citas del Google Calendar pueden heredar la misma escalera sin reingresarlas (togglable por calendario).

**Por qué es Tier A 90%.** Sos olvidadizo y un pago olvidado cuesta plata. La escalera da *más* avisos con *casi cero* ruido nuevo, porque solo el vencido se vuelve interrupción propia — y esa quieres que moleste.

### 4.4 MÓDULO PRODUCTIVIDAD — reconciliación + optimismo v7.2 ⭐

| # | Herramienta | De dónde sale | Señal / flujo de Donna | Impacto | Tier |
|---|---|---|---|---|---|
| **P0** | **Reconciliación nocturna (plan vs real, con delta)** | Calendar del día → `Reconciliacion` | en el cierre: "✅ Hice todo" o marca los no; por bloque, ⏱️ Menos/Igual/Más | **85%** | **A** |
| **P1** | **Factor de optimismo (observador externo)** | `Reconciliacion` → `aprendizaje` | "dijiste 5 bloques de tesis; tu real es ~3 — ¿bajamos?" (con su dato) | **85%** | **A** |

**Cómo funciona.** Sigues planificando optimista en tu calendario (sin disciplina nueva). En el **cierre**, Donna lista los bloques del día y con un toque ("Hice todo") o corrigiendo las excepciones captura qué hiciste y cuánto tomó de verdad. Eso llena el **tiempo por frente** del Semanal (Tesis/Noomi/Delivery/Hijo/Personal) y, sobre 2-3 semanas, deja que el módulo de aprendizaje calcule tu **factor de optimismo** y te frene al planificar de más. **El brief queda intacto** — la reconciliación vive solo de noche, porque el plan vs. real solo se sabe cuando el día cerró.

**Productividad simple (canon).** Tareas sueltas + Proyectos + Semanal de rachas. **Sin log de tiempo diario** (`tiempo` queda dormido). El tiempo por frente NO sale de cronometrar sesiones, sale de la reconciliación.

---

## 5. Operación: brief / cierre (actualizado en v7)

**Brief 8:00 — solo lectura, ~5s de input:**
agenda del día (Calendar) · "¿cuánto dormiste?" (1 toque, S1) · tus 1-3 MITs (P1) · **recordatorios: T-2 y T-0 del día con botón ✅ Hecho** (R0) · **saldo del mes corriendo** (F1, solo mostrar) · señal de deuda si hay pago esta semana (F4) · **resumen de correos** (C1): N importantes con una línea c/u, M archivados, K financieros al digest de la noche (solo mostrar; el triage corrió en segundo plano).

**Cierre 22:00 — panel único de toques + digest, ~45–50s:**
1. 3 botones de hábito (S2 ejercicio / S3 última comida / S5 meditación) — *~9s*
2. Ánimo 1-4 (S4) — *~3s*
3. "¿Avanzaste un MIT?" (P1) — *~3s*
4. MITs de mañana, 1-3, **por voz** (P1) — *~20s*
5. ⭐ **Digest financiero:** lista pre-categorizada del día → "✅ Aceptar todo" (1 toque) o corregir las marcadas — *~10–15s promedio* (3s en día limpio, hasta ~30s en día cargado)
6. ⭐ **Reconciliación (v7.2):** bloques del Calendar de hoy → "✅ Hice todo" o marca los no; por bloque, ⏱️ Menos/Igual/Más — *~10–15s* (1 toque en día como se planeó)
7. La línea madre cuando corresponde: *"a la cama a las 23:00, te conozco."*

**Domingo:** se extiende con el resumen Semanal (P4), revisión de Ideas (P7) y el **preview de recordatorios de la semana** (R0: todos los de los próximos 7 días en un solo mensaje).

**Excepción al "todo dentro de un touchpoint":** los recordatorios **vencidos** sí generan un push propio (fuera del brief), porque ese es el único caso donde quieres que Donna te interrumpa. Insiste a diario hasta que respondas; no es proactividad espontánea, es un aviso de algo que ya se atrasó.

**Resiliencia:** al arrancar, Donna chequea si el brief/cierre de hoy ya salió; si no, lo manda. El digest se arma con lo procesado durante el día, así que a las 22:00 ya está listo.

---

## 6. Presupuesto de tiempo diario (lo que de verdad te cuesta)

| Momento | Input real |
|---|---|
| Brief 8:00 | ~5s (solo el sueño; el resto es lectura) |
| Cierre 22:00 — hábitos + ánimo + MIT | ~15s (toques) |
| Cierre 22:00 — MITs de mañana (voz) | ~20s |
| Cierre 22:00 — **digest financiero** | ~10–15s promedio |
| Ad-hoc en el día (confirmar gasto, soltar idea) | ~15s |
| **Total promedio** | **~1 a 1¼ min/día** |
| Peor caso (día de mucho gasto, varias correcciones) | ~2 min |

Regla de oro de fricción: el digest **nunca te hace esperar el procesamiento** (corre durante el día) y **por defecto es 1 toque** ("aceptar todo"). Solo tocas las líneas dudosas, que Donna marca explícitamente.

---

## 7. El núcleo y el contrato de módulo (se mantienen de v6)
Presupuesto de contexto + prompt caching · contextual retrieval (Voyage) · 4 tablas de memoria · aislamiento de contexto por subagente. Contrato: un módulo nunca toca el núcleo; habla solo por la interfaz; entrega señal destilada; corre pesado aislado; degrada elegante; tools con prefijo (`sal_`, `fin_`, `rec_`, `cor_`, `prod_`, `apr_`). El digest usa `fin_procesar_dia` (corre en el día, aislado) y `fin_confirmar_digest` (escribe a Sheets al aceptar).

---

## 8. La capa de evals (se mantiene)
Set de comportamiento (~10 entradas, ahora **incluye un caso de digest**: foto de boleta → categoría correcta propuesta) · test de deriva · calibración · selección de tool. Ningún cambio se da por bueno hasta que los evals lo confirman.

---

## 9. Roadmap v7
| Fase | Qué queda andando |
|---|---|
| **Fase 1** ⭐ | Núcleo + Salud + Finanzas (**con digest nocturno** + faro de deuda) + Recordatorios + evals (deployado) |
| **+ Correo (1.5)** | Triage de inbox: spam→archivar, importante→resumen 8:00, financiero→digest + correo dedicado. **Solo después de que Fase 1 corra sola.** |
| **+ Productividad (v7.2)** | MITs, proyectos, alerta semanas en cero, semanal + **reconciliación nocturna** (tiempo por frente) + **factor de optimismo**. Modelo **simple**: sin log de tiempo diario (`tiempo` dormido), Outlook descartado. |
| **+ Noomi** | Conexión con el bot de Noomi (solo lee su señal destilada) |
| **+ Proactividad** | Mensaje espontáneo (máx 1/día) |
| **+ Aprendizaje avanzado** | Calibración, decay, guardia anti-patrones-falsos |

---

## 10. Costo mensual estimado
Railway ~$5 · Supabase $0 · Claude API (con caching) ~$5–10 · Voz + embeddings ~$2–4 · **Total Fase 1 ~$12–19 USD/mes.** El digest agrega algunas llamadas de Vision/parseo, ya contempladas en el rango. El módulo Correo (Fase 1.5) agrega ~1 llamada batch/día con snippets — centavos — porque Gmail y las reglas hacen el grueso; sigue dentro del rango.

---

## 11. Riesgos honestos
- El digest puede categorizar mal → mitigado: pre-apuesta + tú confirmas + `ID_Único` anti-duplicado + caso en el eval.
- El triage de correo puede archivar algo importante (falso positivo) → mitigado: **nunca borra, solo archiva** (recuperable de un clic) + las reglas gratis (`List-Unsubscribe`) hacen el grueso y el LLM solo el residuo + rescatar enseña al sistema + invariante de no-borrado en el eval.
- Migrar tus bancos al correo dedicado puede hacerte perder un aviso en la transición → mitigado: la allowlist del inbox viejo corre **en paralelo** hasta confirmar que el nuevo recibe todo; recién ahí se apaga.
- La escalera de recordatorios puede saturarte (fatiga de alerta) → mitigado: los 3 toques previos viajan dentro del brief y el cierre del domingo (cero interrupciones nuevas); solo el **vencido** se vuelve push propio.
- "Posponer" puede volverse trampa (postergas eternamente y nunca se hace) → mitigado: posponer exige un día concreto, y tras N posposiciones Donna nombra el patrón ("llevas 3 posposiciones del IVA — ¿se hace o lo bajamos?") en vez de seguir habilitando la evasión.
- Donna es consejera con buena memoria, **no un oráculo**.
- **El riesgo real no es la planilla — es la deuda** ($2.028.091 reales; $48.236/mes muertos). Donna la mide; bajarla es tuyo.
- **Nada vive hasta deployar en Railway.** v7 es el último plan: el próximo artefacto es código, no un v8.

---

*v7, final: v6 + el digest que captura tu plata sin fricción, lista para construir con el runbook adjunto. El próximo paso no es escribir — es deployar.*
