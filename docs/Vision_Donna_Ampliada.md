# Visión Donna Ampliada — de agente personal a secretaria de negocios

**Fecha:** 2026-07-03 · **Estado:** visión auditada contra el repo real, no construida.
**Alcance objetivo declarado por Nico:** finanzas personales · finanzas de negocios · creación de
contenido · salud/hábitos/parámetros personales · y a futuro lo tedioso de los negocios (correos,
clientes, cobranza; llamadas al final).

Este documento NO reemplaza el `Roadmap_Modular.md` (que manda en la secuencia corta: Fase 0 →
autodiagnóstico → Compras → Familia). Define hacia dónde apunta todo eso y qué decisiones
de arquitectura conviene tomar HOY para no tener que demoler después.

> **Nota (2026-07-17):** el **harness propio completo se descartó** el 2026-07-04 (se hizo una versión
> *lean* del autodiagnóstico; ver `Roadmap_Modular.md` §Fase 0). Donde este documento lo lista como
> paso de la secuencia (§6), léase "autodiagnóstico lean". Su valor real —la escalera de autonomía
> hacia terceros— sigue vigente como visión, pero no como paso inmediato.

---

## 1. Auditoría: dónde está Donna respecto de esa visión

| Dominio objetivo | Estado real hoy | Distancia |
|---|---|---|
| Finanzas personales | 🔨 v1+v2+v3 construidas (captura, faro, digest, intención, metas, ítem-a-ítem) | Corta: cerrar Fase 0 (categorías) + semana estable |
| Salud/hábitos/parámetros | 🔨 base + E8 construidas; captura de sueño/ventanas coja (C3 del plan) | Corta |
| Finanzas de negocios | ⬜ **No existe.** Peor: hoy la plata de negocio se mezcla con la personal (ver §3.1) | Media — es el siguiente gran dominio |
| Clientes / ventas (Monetizar Noomi) | ⬜ No existe en Donna (existe material comercial fuera del repo) | Media-larga |
| Creación de contenido | ⬜ No existe | Media |
| Correos hacia terceros / llamadas | ⛔ Prohibido por invariante actual (correcto por ahora) | Larga — requiere escalera de autonomía |

**Lectura honesta:** Donna hoy es un agente de *vida personal* con finanzas personales maduras. La
visión de negocio no requiere reconstruir nada — la arquitectura (orquestador + módulos con prefijo +
espina de memoria + toques) escala a los dominios nuevos. Lo que NO escala tal cual: (a) el modelo de
datos (una sola `Transacciones` para toda la plata), (b) el invariante binario "no manda correos", y
(c) el presupuesto de atención de Nico (toques y proactividad diseñados para 1 vida, no 3 negocios).

## 2. Decisión de arquitectura madre: una Donna, dominios aislados

Una sola Donna (un repo, un bot, una espina de memoria) con **dominios como módulos** — NO un bot por
negocio. Razones: el valor diferencial es justamente el cruce (el correlador viendo
negocio↔sueño↔ánimo↔gasto: "las semanas que Noomi Cookies vende más, duermes 1h menos y tu ánimo
cae"); y Nico es uno solo — una secretaria, varias carpetas.

Pero con **tres aislamientos duros** desde el día uno de cada dominio nuevo:

1. **Datos por dominio, no por tabla compartida.** La plata del negocio jamás en la `Transacciones`
   personal (ver §3.1). Regla general: cada dominio nuevo de negocio nace **Supabase-first** (tablas
   propias `neg_*`, `cli_*`, `cont_*`) con el Sheet como *vista* para Nico si hace falta — la
   inversa del canon personal, y consistente con `Vision`/auditoría previa: Sheets escala para la
   vida de una persona, no para operaciones de negocio.
2. **Memoria etiquetada por dominio.** `memoria`/`inferencias` ya tienen dominio — volverlo
   obligatorio y agregar `negocio: noomi_cookies | monetizar | delivery | personal`. El correlador
   puede cruzar dominios; el contexto inyectado en una conversación de cobranza NO debe arrastrar
   datos de salud (y viceversa: un borrador a un cliente jamás debe poder citar tu Diario).
3. **Presupuesto de atención por dominio.** El tope "proactividad 1/día" se vuelve por-dominio con un
   tope global (p. ej. personal 1 + negocios 2, configurable en `⚙️ Config`). El brief de las 8:00
   **no se toca** (canon); lo de negocio vive en touchpoints propios (§3.2).

## 3. Los dominios nuevos, uno por uno

### 3.1 Finanzas de negocio (`neg_`) — el siguiente gran dominio, y el más urgente

**Evidencia de que ya duele:** en la `Transacciones` real conviven gastos personales con lo que parece
operación de negocio (categoría "Negocio", compras a "Comercializadora agroconcepcio" por $51.000 que
huelen a insumos de Noomi Cookies, ingresos "Uber Eats" del delivery). Sin separación no hay margen
real de las galletas, ni utilidad del delivery, ni gasto personal limpio — los tres números están
contaminados entre sí. **Primera tarea del dominio: separar, no agregar features.**

- **Modelo de datos (Supabase-first):** `neg_movimientos` (negocio, fecha, tipo, concepto, monto,
  contraparte, medio, id_tx_personal si salió de tu bolsillo), `neg_productos` (para costeo de
  cookies: receta → costo insumos → margen), `neg_resumen` mensual materializado. El Sheet gana una
  hoja-vista `Negocios` (solo lectura, la escribe Donna) para que mires sin abrir nada más.
- **Captura sin fricción (reusar lo construido):** el extractor de correos/fotos de `fin_` ya
  funciona; se le agrega UN toque al digest: «¿esto es personal o de un negocio? [Personal] [🍪
  Cookies] [🤖 Noomi] [🛵 Delivery]» — mismo patrón de confirmación existente, cero flujo nuevo. Las
  reglas aprendidas (Supabase `aprendizaje`) hacen que a la tercera vez ya no pregunte
  ("Comercializadora agro → Cookies/insumos").
- **Señales que entrega:** margen por lote de cookies, flujo de caja proyectado del mes,
  delivery $/hora real (cruzando con reconciliación de tiempo cuando exista), y el faro de deuda
  personal DEJA de estar contaminado por capital de trabajo del negocio.
- **IVA/contadora:** los recordatorios ya existen (Pago IVA, contadora) — el dominio les agrega el
  dato ("el IVA de este mes viene ~$X según las ventas registradas").

### 3.2 Clientes y ventas (`cli_`) — donde Donna empieza a ser secretaria de verdad

CRM liviano para Monetizar Noomi (pastelerías/panaderías) y pedidos de Cookies:

- **Datos:** `cli_clientes` (nombre, negocio, canal, etapa: prospecto→propuesta→negociación→cliente→
  cobranza), `cli_interacciones` (fecha, tipo, resumen, próximo paso, fecha_seguimiento).
- **El valor está en el seguimiento, no en el registro:** Donna vigila `fecha_seguimiento` y empuja:
  «La pastelería San Pedro lleva 8 días sin responder la propuesta. Te dejé un borrador de seguimiento
  — ¿lo mando?». Ahí entra la **escalera de autonomía** (§4): nivel 2 (borrador + toque) durante
  meses antes de considerar nivel 3.
- **Touchpoint propio:** un "cierre comercial" semanal (p. ej. viernes 18:00) con pipeline, cobranzas
  pendientes y propuestas frías — separado del cierre personal de las 22:00, que es sagrado para la
  vida.
- **Cobranza:** el caso de mayor valor/esfuerzo: recordatorios de pago a clientes con plantilla
  aprobada = nivel 3 alcanzable temprano (destinatario conocido, texto plantillado, riesgo acotado).

### 3.3 Creación de contenido (`cont_`) — el dominio más barato de alto valor

Contenido de marketing para Noomi (y lo que Nico quiera publicar). Es el dominio *ideal* para la
escalera de autonomía porque el borrador es gratis y la aprobación es un toque:

- **Flujo:** calendario editorial simple (`cont_calendario`: fecha, canal, tema, estado) → Donna
  genera borradores por lote (subagente, modelo barato, con la voz de marca como prompt cacheado
  propio — NO la voz de Donna: son dos personajes distintos) → cola de aprobación por Telegram
  (aprobar / editar / descartar, mismo patrón de toques) → publicación vía API (Meta/IG ya hay
  tooling disponible) → medición básica (alcance/interacción) → `aprendizaje`: qué formatos/temas
  rinden, para proponer mejor el mes siguiente.
- **Regla dura nueva:** contenido público JAMÁS se publica sin toque (nivel 2 permanente para
  publicar; solo la *programación* de algo ya aprobado puede ser nivel 3). Un post malo es un error
  público e irreversible — la clase de acción más cara después de un correo a cliente.
- **Cruce con la espina:** el calendario alimenta la reconciliación de tiempo (frente Noomi) y el
  correlador puede detectar "publicas 3x más las semanas que duermes bien" — señal accionable real.

### 3.4 Salud, hábitos y parámetros personales — ya es el dominio más maduro; protegerlo

No necesita ampliación de scope (E8 ya cubre nutrición/ventanas/peso/score/eventos): necesita que la
expansión de negocios **no lo canibalice**. Dos guardias: el cierre 22:00 mantiene su duración actual
(nada de negocio dentro), y el eje #1 (sueño) conserva prioridad en proactividad — si hay que elegir
el único toque proactivo del día entre "cobra a X" y "llevas 4 días durmiendo <6h", gana el sueño.
La secretaria existe para que duermas, no al revés.

## 4. La escalera de autonomía (el mecanismo que habilita todo lo anterior)

Reemplaza gradualmente el invariante binario "no manda correos a terceros". Se implementa en el
harness como nivel por **clase de acción** (no por tool suelta), persistido en `⚙️ Config`:

| Nivel | Qué puede hacer Donna | Ejemplos |
|---|---|---|
| 0 | Solo leer | triage de inbox, leer pipeline |
| 1 | Escribir en MIS registros con toque | lo de hoy (digest, reconciliación) |
| 2 | **Borrador hacia terceros + toque para enviar** | respuesta a cliente, post, cotización |
| 3 | Enviar sola con plantilla/whitelist | recordatorio de cobranza a cliente conocido |
| 4 | Autonomía plena en el dominio | (lejano; quizá nunca para contenido público) |

**Regla de promoción (calca del gate de módulos):** una clase de acción sube de nivel solo con N
semanas de historial limpio en el nivel anterior, medido por la telemetría del autodiagnóstico
(incidentes + tasa de corrección de Nico en los toques). Bajar de nivel es inmediato ante un incidente
grave. Las **llamadas telefónicas** quedan explícitamente al final: son la única superficie sin toque
de aprobación posible en tiempo real.

## 5. Transversales que la ampliación exige (y que conviene decidir ya)

1. **El harness se diseña con niveles, no con booleano** — `ToolSpec.confirmar: bool` pasa a
   `ToolSpec.clase_accion: str` + tabla de niveles. Costo marginal hoy, demolición evitada mañana.
2. **Identidad de Donna hacia afuera:** para nivel ≥3 Donna necesita remitente propio (correo
   dedicado ya existe para finanzas; extender el patrón: `donna@` o el correo del negocio, jamás tu
   personal) y firma clara. Un cliente debe poder distinguir "me escribió la asistente de Nico".
3. **Privacidad cruzada:** datos de clientes en Supabase caen bajo la misma regla que los tuyos
   ("solo lo justo"); y el contexto de dominios personales nunca se inyecta en acciones hacia
   terceros (aislamiento §2.2 — esto es un guardrail del harness, no una convención).
4. **Costo:** cada dominio nuevo suma llamadas. Mantener el canon (determinista primero, LLM para el
   residuo, subagentes Haiku para lo pesado, batch para contenido). La telemetría de la ficha de
   autodiagnóstico ya mide `uso` — agregar corte por dominio para ver qué negocio paga su cuenta.
5. **Evals por dominio:** cada dominio nuevo entra con su `tests/test_<dominio>.py` + casos de eval
   ANTES de tocar producción (el patrón dry_run ya existe). Para nivel ≥2, evals de borradores
   (¿tono correcto? ¿datos del cliente correctos? ¿sin datos personales filtrados?).

## 6. Secuencia recomendada (extiende el roadmap, no lo reemplaza)

```
Fase 0 (bugs)  →  Autodiagnóstico lean + variedad   [harness completo descartado 2026-07-04]
  →  Compras F1 · Familia (cierra el roadmap personal comprometido)
  →  N1: Finanzas de negocio — separación personal/negocio + toque de dominio en el digest
  →  N2: Clientes/cobranza — CRM liviano + seguimientos nivel 2 (borrador+toque)
  →  N3: Contenido — calendario + borradores por lote + cola de aprobación + publicación
  →  N4: Correo saliente nivel 3 (plantillas/whitelist) · cierre comercial semanal
  →  N5 (lejos): llamadas / voz saliente
```

Cada N con la misma cadencia del canon: ficha → construir → eval verde → deploy → semana estable →
promover. La regla madre no cambia porque el dominio sea de plata: **un dominio a la vez.**

## 7. Riesgos principales de esta ampliación (para releer antes de cada N)

- **Contaminación de datos personal/negocio** — ya está ocurriendo (§3.1); es la razón de que N1 vaya
  primero.
- **Fatiga de toques:** si cada dominio pide 5 confirmaciones diarias, Nico deja de leerlas y aprueba
  en piloto automático — y el human-in-the-loop se vuelve teatro. Presupuesto de toques por día,
  medirlo, y agrupar (un digest con 8 ítems > 8 mensajes).
- **Patrones espurios del correlador** con más dominios (más variables = más falsos cruces): la
  guardia anti-patrones-falsos existente se vuelve más importante, no menos; exigir N mínimo mayor
  para cruces inter-negocio.
- **Deriva de carácter:** Donna-secretaria-comercial y Donna-de-la-vida son la misma persona con
  registros distintos; la voz hacia clientes se define en prompts propios por dominio, la
  constitución no se ablanda ni se contamina de tono corporativo.
- **Disciplina:** el riesgo #1 sigue siendo empezar N1 con la Fase 0 a medias. Este documento no
  autoriza a saltarse nada.
