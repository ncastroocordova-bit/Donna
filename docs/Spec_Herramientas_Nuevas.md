# Spec de Herramientas Nuevas — Donna

Detalle de implementación de las herramientas que el canon agrega o cambia. Acompaña a `Plan_Construccion_v7.md`. Cada bloque: propósito · firma · lee/escribe · invariantes · borde · LISTO CUANDO.

---

## §rec_ — Recordatorios (escalera)

**Propósito:** avisar en escalera calmada (domingo + T-2 + T-0) y escalar solo el vencido, sin ruido nuevo.

**Esquema `Recordatorios`:** `Recordatorio · Tipo(mensual|anual|unica) · Dia_Fecha · Monto_Aprox · Estado(pendiente|hecho|pospuesto) · Posposiciones(int) · Ultima_Accion(fecha) · Activo`.

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
