# Donna — Plan v5 (final)

**Para:** Nico
**Regla madre:** Donna gana su lugar el día que te dice algo sobre ti que tú no habías visto.
**Qué es v5:** la versión final del plan. Toma v4 (núcleo + Finanzas + Salud en la Fase 1, + módulo Proyectos) y le integra las correcciones de la auditoría contra los cursos de Anthropic. De aquí se va a construir, no a re-planificar.

**Las 3 correcciones grandes de v5:**
1. **Capa de evaluación de verdad** (set de evals automatizado) — para medir si Donna mejora o empeora con cada cambio.
2. **Prompt caching** de la constitución + anclas — hace barato y rápido el re-inyectar el carácter completo.
3. **Contextual retrieval** en la memoria — para que recupere la memoria *correcta*, no solo la parecida.

Más correcciones menores: tools sin solapamiento, aislamiento de contexto de los módulos, política de qué guardar, y resiliencia del scheduler.

---

## 1. Filosofía (se mantiene)
1. **Simplicidad primero.** Nada entra hasta que el uso real lo justifique.
2. **Contexto finito.** Siempre en cabeza: lo chico y de alta señal (carácter + anclas). El resto, just-in-time + compactación.
3. **Modular y a prueba de roturas.** Cada módulo se enchufa por la interfaz; si uno falla, el resto sigue.
4. **Medible.** Nada se da por bueno sin un eval que lo demuestre. *(nuevo en v5)*

---

## 2. Quién es Donna (carácter — núcleo)
**Donna Paulsen** de *Suits*: te lee como rayos X, se anticipa, cálida pero filosa, confianza y humor constante, no sumisa, lealtad y memoria total. Marcas: "te conozco", "ya lo resolví", "no me vengas con eso", "soy Donna".

**Ancla maestra:**
> *"Nico. Cuarta noche después de la 1am. No me vengas con que estás 'cansado nomás' — el viernes te desplomas y lo sabes. Mañana a las 23:00 estás en cama. Te conozco."*

---

## 3. Arquitectura
```
        DONNA — NÚCLEO (estable, con caché de carácter)
        carácter (constitución+anclas, CACHEADO) · conversación (Telegram/voz)
        · memoria (Supabase + contextual retrieval) · inferencia validada
        · brief 8:00 / cierre 22:00 (con resiliencia) · privacidad · EVALS
                 │  interfaz de módulos (señal destilada, contexto aislado)
   ┌─────────────┼──────────────┬──────────────────────────────┐
 [Finanzas]   [Salud]       [Proyectos]                  [Proactividad /
  Fase 1       Fase 1        Fase 2                       Aprendizaje av.]
```

---

## 4. El núcleo (qué incluye)
Carácter blindado · memoria con recuperación a demanda + compactación · inferencia validada básica · brief/cierre · privacidad · **capa de evals**.
**Tablas de memoria (4):** `perfil`, `memoria` (verbatim + **contexto + embedding**), `inferencias`, `compromisos`.

### 4.1 Presupuesto de contexto + prompt caching *(corrección v5)*
- **Siempre en cabeza:** constitución + 3–5 anclas + datos del día + top-K memorias relevantes.
- La constitución + anclas se sirven con **prompt caching** (prefijo estable cacheado): se re-inyectan completas en cada mensaje, pero el costo y la latencia caen fuerte. Esto hace viable el diseño anti-deriva sin pagar de más.
- Conversaciones largas → **compactación** (resumir lo crítico: decisiones, correcciones; descartar lo redundante).

### 4.2 Memoria con contextual retrieval *(corrección v5)*
Cada nota episódica se guarda **verbatim + una etiqueta de contexto** (qué pasaba, cuándo, qué dominio) y se embebe esa versión contextualizada. Resultado: `buscar_memoria` trae la memoria correcta, no solo la semánticamente parecida. Embeddings con **Voyage AI**. Opcional: combinar con búsqueda por palabra clave (híbrido) para casos donde el término exacto importa.

### 4.3 Política de qué guardar *(corrección v5)*
Donna guarda solo lo que pasa una barra de relevancia (no cada mensaje trivial). Más: "off the record" no se guarda; "Donna, olvida X" borra. Memoria curada = recuperación sana.

---

## 5. La capa de evaluación *(corrección grande v5 — antes no existía)*
Anthropic insiste en evals como disciplina central. Donna lleva **cuatro evals** que corren automáticos:

| Eval | Qué mide | Cuándo corre |
|---|---|---|
| **Set de comportamiento** | Un set fijo de ~10 entradas representativas (nota de voz, pregunta de plata, hábito, excusa de gym) con la respuesta/acción esperada | Antes y después de cada cambio de prompt o modelo |
| **Test de deriva** | Que el carácter no se ablande ni se vuelva genérico | Cada cierto tiempo + en cada cambio de modelo |
| **Calibración** | Tasa de acierto de inferencias por tipo | Continuo (llega con Aprendizaje avanzado) |
| **Selección de tool** | Que Donna elija la herramienta correcta cuando hay varias | Cada vez que se agrega un módulo |

Regla: **ningún cambio (constitución, modelo, módulo) se da por bueno hasta que los evals lo confirman.** El set de comportamiento se construye en la Fase 1, no después.

---

## 6. Módulos: Finanzas y Salud (injertos Fase 1)
**Finanzas:** registra gastos/ingresos, mantiene workbook (categorías, tarjetas, línea de crédito, cuotas), extrae de mail y fotos (Vision). Señal destilada: *"esta semana hay $X por pagar; vas 12% sobre el mes pasado."* Datos: Sheets.
**Salud:** ejercicio/sueño/ayuno de un toque; rachas y caídas; empuje a las 23:00. Señal destilada: *"4ta noche tarde; patrón sueño→ánimo activándose."* Datos: Sheets.

### 6.1 Aislamiento de contexto de los módulos *(corrección v5)*
El trabajo pesado de un módulo (Vision sobre una boleta, parsear un mail largo) corre en su **propia llamada a Claude, con contexto aislado**, y le devuelve a Donna **solo la conclusión destilada**. Así el detalle no le tapa la ventana al núcleo. Es el patrón subagente de Anthropic aplicado.

---

## 7. Módulo Proyectos (después)
Seguimiento de tesis y proyectos personales: bloquea tiempo en Calendar, registra avance, alerta semanas en cero. Señal: *"la tesis lleva 4 semanas en cero; 2 entregas esta semana."* Datos: Sheets + Calendar.

---

## 8. El contrato de módulo (garantiza que nada se rompe)
1. Un módulo **nunca** modifica el núcleo.
2. Se comunica **solo** por la interfaz (lee/escribe memoria, registra tools).
3. Le pasa a Donna **señal destilada**, no datos crudos.
4. Su trabajo pesado corre **con contexto aislado**.
5. **Degradación elegante:** si falla, Donna sigue.
6. Sus tools llevan **prefijo de módulo** (ej. `fin_registrar_gasto`, `salud_marcar_habito`) y descripciones sin solapamiento — para que Donna nunca dude cuál usar. *(corrección v5)*

---

## 9. Operación: brief/cierre con resiliencia *(corrección v5)*
El brief (8:00) y el cierre (22:00) corren con JobQueue. Para que un reinicio de Railway no se coma un toque: al arrancar, Donna chequea si el brief/cierre de hoy ya salió; si no, lo manda. Sin punto único de falla silencioso.

---

## 10. Roadmap
| Fase | Qué queda andando |
|---|---|
| **Fase 1** ✅ | Núcleo + Finanzas + Salud + **capa de evals** (deployado) |
| **Fase 2** ✅ | Proyectos (proy_*) + bloqueo de tiempo en Calendar |
| **Fase 3** ✅ | Proactividad — mensaje espontáneo (máx 1/día) |
| **Fase 4** ✅ | Aprendizaje avanzado — calibración, decay, guardia anti-patrones-falsos |

**Test de promoción** (módulo → proceso propio): solo si trabaja solo, en su horario, sin que le hables a Donna.

---

## 11. Build (resumen; el runbook detallado para Claude Code va aparte)
- **Fase 0:** cuentas y llaves (Telegram, Anthropic, Google Cloud + Sheets, Supabase + pgvector, Voyage, Whisper, Railway, GitHub).
- **Fase 1:** scaffold (agent-builder) → memory.py (Supabase + contextual retrieval) → brain.py (constitución cacheada + presupuesto de contexto) → módulo Finanzas → módulo Salud → scheduler con resiliencia → **set de evals** → voz (Whisper) → deploy Railway.
- Reglas para Claude Code: monolito simple; contrato de módulo; presupuesto de contexto; prompt caching del prefijo; tools con prefijo y sin solapamiento; deploy + correr evals al final de cada fase.

---

## 12. Costo mensual estimado (con caching, baja respecto a v4)
| Concepto | Costo |
|---|---|
| Railway | ~$5 |
| Supabase (free tier) | $0 |
| Claude API (con prompt caching) | ~$5–10 |
| Voz + embeddings (Whisper + Voyage) | ~$2–4 |
| **Total Fase 1** | **~$12–19 USD/mes** |

---

## 13. Riesgos honestos
- Un agente que infiere puede equivocarse con confianza → mitigado con inferencia validada, "te muestro el dato", contextual retrieval y el guardia anti-patrones-falsos.
- Donna es consejera con buena memoria, **no un oráculo**.
- **Nada vive hasta deployar en Railway.** v5 es final justamente para que el próximo paso sea código, no v6.

---

## 14. Próximos pasos
1. Fase 0: dejar las llaves listas
2. Construir Fase 1 con el runbook de Claude Code (incluye la capa de evals)
3. Usar Donna unas semanas, mirar los evals y dónde falla
4. Agregar Proyectos → Proactividad → Aprendizaje avanzado, según lo que el uso real pida

---

*v5, final: una Donna chica, medible y con carácter blindado, que desde el día uno te ordena la plata y los hábitos — y crece por piezas sin romper lo que ya corre. Lo que sigue es construirla.*
