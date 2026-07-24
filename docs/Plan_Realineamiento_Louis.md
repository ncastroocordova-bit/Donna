# Plan de Realineamiento — planilla Louis + el código que la escribe

**Fecha del diagnóstico:** 2026-07-23 (auditoría de las 8 hojas de Louis vía Sheets API + cruce con el código).
**Planilla auditada:** "Louis" `1W5S3BSXHrrFgCzc0N6D4swwUVcO4vEh1HD8X0wNUbu8` (locale `es_CL`, TZ `America/Santiago`).
**Para quién:** una sesión de Claude Code que ejecute los fixes. **Prerequisito: leer `CLAUDE.md` completo antes de tocar nada.**

Este plan NO reemplaza el contrato del repo; lo aplica. Modela su formato en
[`docs/archivo/Plan_Reparacion_Bugs_y_Datos.md`](archivo/Plan_Reparacion_Bugs_y_Datos.md) (Fase 0, ya ejecutado).

---

## Por qué existe este plan

La migración al canon v8 (dos sombreros, dos planillas) **sí se ejecutó** — Louis existe desde 2026-07-18
y recibe transacciones reales. Pero la migración dejó daño colateral que nadie verificó, y encima
destapó problemas de datos que venían de antes.

Hay **dos frentes** y no son independientes:

- **Frente 1 — la planilla.** Fórmulas muertas, rangos desalineados, datos sucios.
- **Frente 2 — el código que la escribe.** Si solo arreglo el Frente 1, el Frente 2 vuelve a ensuciarla
  en días.

El orden de este plan resuelve esa tensión: **primero lo que no requiere ninguna decisión** (Ola 0, el
Dashboard vuelve a vivir hoy), después las decisiones de Nico, y recién ahí el código y la limpieza de
datos — para no tocar los mismos datos dos veces.

---

## Reglas de ejecución (aplican a todos los ítems)

1. **Invariantes duros vigentes** (`CLAUDE.md`): Sheets nunca se escribe sin OK de Nico. Los fixes de
   *código* no escriben nada por sí solos; **todo script de limpieza de datos corre en dry-run primero
   e imprime el diff antes de pedir confirmación**. Correo jamás borra. Inferencias siempre con dato.
2. **Nada se borra sin respaldo.** Antes de la primera escritura de cada ola, duplicar la hoja afectada
   (`Transacciones_bak_0723`, etc.) o exportar la planilla completa. La deuda de Nico vive acá.
3. **Una rama por ola:** `fix/louis-formulas`, `fix/louis-faro`, `fix/finanzas-categorias`,
   `fix/louis-datos`. Commit por paso, mensajes en español, concretos.
4. **Locale `es_CL`: las fórmulas usan `;` como separador, NO `,`.** Verificado: escribir
   `=SUMIFS(A:A,B:B,"x")` con coma da *"Formula parse error"*. Con `;` funciona. Esto aplica a toda
   escritura de fórmulas vía API con `valueInputOption='USER_ENTERED'`.
5. **Ningún fix está hecho hasta que sus tests pasan** (`python -m pytest tests/ -q` verde) **y** se
   verificó el efecto en la planilla real.
6. **Al cerrar:** actualizar el tablero de `Roadmap_Modular.md` y, si cambian tools,
   `Spec_Herramientas_Nuevas.md` (regla de mantenimiento del Roadmap §"Al cerrar un módulo").
7. Infraestructura disponible (no reinventar): `core/sheets.py` → `fin_id()` (id de Louis), `get_dicts`,
   `get_rows`, `append_row`, `set_cell`, `upsert_por_clave`, `append_row_verificado`.

---

## Resumen de hallazgos

| # | Hallazgo | Sev | Frente | Ola |
|---|----------|-----|--------|-----|
| 1 | Dashboard y Comparativo: referencias cruzadas muertas → todo `#N/A`/`#REF!` | 🔴 | Planilla | 0 |
| 2 | Dashboard apunta a `Categorias!A3:A20`: fila vacía + 4 categorías fuera del cuadro | 🟠 | Planilla | 0 |
| 3 | Mes activo congelado en junio (`E2=6`) estando a 23 de julio | 🟠 | Planilla+Código | 0 |
| 4 | `Categorias` con fila vacía (A3) y `Regalos`/`Regalo` duplicados | 🟡 | Planilla | 0 |
| 5 | `Deuda_Mensual`: fechas como seriales (46203, 46225…) | 🔵 | Planilla | 0 |
| 6 | **El faro calcula el interés en vez de usar el del estado de cuenta** → subreporta $6.652 | 🟠 | Ambos | 1 |
| 7 | El faro mezcla meses: BCh de junio, Mach y línea de julio | 🟠 | Ambos | 1 |
| 8 | `_categoria_item` inventa categorías fuera del catálogo (6 en `Compras_Detalle`) | 🟡 | Código | 2 |
| 9 | El matcher correlaciona foto↔correo pero **no dictado↔correo** → doble conteo $4.340 | 🟡 | Código | 2 |
| 10 | `Compras_Detalle` no valida contra `Categorias` (a diferencia de `Transacciones`) | 🟡 | Código | 2 |
| 11 | `Predecible = no` en 12/12 → el predictor de Compras Fase 2 nace sin datos | 🟡 | Código | 2 |
| 12 | Solo 10/69 transacciones tienen línea en `Compras_Detalle` — **D3/D10** | 🟠 | Código | 2 y 3 |
| 13 | 3 categorías huérfanas en `Transacciones` (`chancheria`, `Droga`, `Deuda / Tarjeta`) | 🟡 | Datos | 3 |
| 14 | Transferencias contadas como Gasto: **$40.500** de gasto fantasma | 🟡 | Ambos | 3 |
| 15 | Pago de tarjeta duplicado ($68.416 correo + $68.000 manual) | 🟡 | Datos | 3 |
| 16 | 14/69 filas sin Intención; `Inversión` nunca aparece | 🔵 | Datos | 3 |
| 17 | `Subcategoría` usada como cajón del nº de tarjeta (2 semánticas) | 🔵 | Código | 4 |
| 18 | El mismo comercio bajo 3 nombres (San Valentín) | 🔵 | Código | 4 |
| 19 | Cero ingresos registrados (69/69 son Gasto) — resuelto por **D12** | 🟠 | Ambos | 5 |
| 20 | `Metas` vacío (solo header) | 🟡 | Realidad | 4 |
| 21 | BCh sobre el cupo ($30.608); Mach exacto en el tope | 🟠 | Realidad | 4 |
| 22 | `correo_dias=2`: si Donna no corre 3 días, el gasto se pierde para siempre | 🟠 | Código | 1 |
| 23 | La reconciliación ignora las cartolas → el gasto con **débito** no se cuadra | 🟠 | Código | 5 |
| 24 | El Dashboard suma categorías de `Transacciones`, no de `Compras_Detalle` | 🟠 | Ambos | 3 |

---

## Decisiones — TOMADAS por Nico (2026-07-23)

La Ola 0 no dependía de ninguna. **Doce decisiones**, tomadas en tres rondas, definen las Olas 1–5.
Varias respuestas no fueron ninguna de las opciones ofrecidas y cambiaron el plan — quedan registradas
tal como Nico las formuló. **D3 corrige (revierte) lo que se había entendido en la primera ronda.**

### ✅ D1. Transferencias — la regla es el destinatario, no la categoría
> *"Si me la realizo a mí mismo, no es gasto; si le transfiero a otra persona sí lo es."*

Más preciso que cualquier opción que ofrecí. La regla real:

| Destinatario | ¿Gasto? | Cómo se registra |
|---|---|---|
| **A ti mismo** (Mach → tu cuenta) | ❌ No | Categoría `Transferencias`, fuera del conteo de gasto |
| **A otra persona** | ✅ Sí | Categorizado por **para qué fue** (Alimentación, Transporte…) |

**Las 5 filas de categoría `Transferencias` van todas a "Nicolas Castro" = él mismo** → salen del
conteo (**$40.500**). El resto de transferencias a terceros (Maria Baez → Alimentación, Fabian Latorre
→ Transporte, Patricia Castillo → Chanchería…) **ya está bien categorizado** y se queda como está.

Corolario de esquema: **la categoría `Transferencias` pasa a significar exclusivamente "traspaso entre
mis propias cuentas"**. Si `finanzas.py` la asigna a una transferencia hacia otra persona, es un bug.

### ✅ D2. El pago de tarjeta SÍ es gasto
> *"Sale de mi cuenta para el banco, por lo que pierdo dinero, pero pago parte de la deuda."*

Se mantiene `Tipo=Gasto`. **Único cambio:** debe usar la categoría canónica `Tarjeta Crédito`
(hoy usa `Otro Gasto` y `Deuda / Tarjeta`, que ni existe en el catálogo).

### ✅ D3. Dos hojas, dos trabajos — *(corregido por Nico el 2026-07-23, revierte la versión anterior)*
> *"En la hoja Transacciones están todas las transacciones, pero luego está Compras_Detalle, que es donde
> quiero que vaya el detalle por ítem de cada compra. El reconciliador debe hacerlo con mi hoja de
> transacciones, y la información y métricas financieras de lo que compro debe venir de Compras_Detalle."*

⚠️ **Esto corrige una lectura equivocada de la respuesta anterior.** Yo había entendido "partir la compra
en dos filas de `Transacciones`". **No es eso.** El modelo correcto es:

| Hoja | Qué guarda | Para qué sirve |
|---|---|---|
| **`Transacciones`** | **Una fila por movimiento del banco.** El San Valentín de $4.340 es **una** fila de $4.340 | **Reconciliar** contra el banco: es exactamente lo que el banco ve |
| **`Compras_Detalle`** | El desglose: pan $2.500 (Necesario) + chanchería $1.840 (Deseo) | **Todas las métricas** de en qué gastas |

**Consecuencias buenas de la corrección:**
- ✅ **Desaparece la dependencia dura** que había con el reconciliador (la vieja F5.4). `Transacciones`
  conserva el monto que el banco reporta, así que el match por monto exacto sigue funcionando.
- ✅ **No hace falta sufijar `ID_Único`.** Se mantiene tal cual.
- ✅ **`Mixto` sobrevive**, pero degradado a **etiqueta de resumen** en `Transacciones`. Ya no es donde
  se mide nada: la intención que cuenta es la de cada línea de `Compras_Detalle`. El conflicto con el
  canon se disuelve porque `Mixto` deja de ser un valor de análisis.

### ✅ D10. Toda transacción genera al menos una línea de `Compras_Detalle`
Si las métricas salen de `Compras_Detalle`, lo que no esté ahí es invisible — y hoy solo **10 de 69**
transacciones tienen desglose.

**Decisión:** cada transacción escribe **≥1 línea** de detalle. La bencina de $15.000 genera una línea
sola de $15.000 (Transporte). Un solo lugar de donde salen todas las métricas, sin sumas mezcladas
entre dos hojas ni riesgo de contar la misma plata dos veces.

**Implica:** el **Dashboard debe sumar desde `Compras_Detalle`, no desde `Transacciones`** → ver **F0.6**
(cambio sobre lo que se acaba de reparar en la Ola 0). Y hay que **backfillear** las ~59 transacciones
sin detalle.

### ✅ D11. Guardar el saldo de la cuenta al cierre de cada cartola — *cambia el canon*
Una cifra al mes, sacada del PDF de la cartola. Cero fricción para Nico.

⚠️ **`CLAUDE.md` dice hoy:** *"No se agregan cuentas con saldos auto / doble-entrada (rompe registro sin
fricción)"*. Esa línea **debe actualizarse**: la objeción era la fricción de mantenerlos a mano, y acá el
dato sale gratis del documento. Sin tocar el canon, esto queda en contradicción con el contrato.

### ✅ D12. Los abonos son ingreso — salvo los que vienen de sus propias cuentas
> *"Si los depósitos llegan desde mis mismas cuentas (por el RUT), entonces son solo movimiento de plata
> y no un abono real."*

**Es la misma regla de D1, en la otra dirección.** Queda como una sola regla del sistema:

> **Regla del RUT propio:** un movimiento entre cuentas de Nico **no es gasto ni es ingreso** — es
> traslado. Solo cuenta lo que cruza hacia (o desde) un tercero.
>
> | Dirección | Contraparte = Nico | Contraparte = tercero |
> |---|---|---|
> | Sale plata | traslado (no gasto) — **D1** | **gasto**, categorizado por para qué fue |
> | Entra plata | traslado (no ingreso) — **D12** | **ingreso** |

**Implica:** hace falta la lista de RUTs/cuentas propias de Nico como dato de configuración. Hoy existe
`dueno_rut` (uno solo); si tiene más de una cuenta o RUT asociado, debe poder listarlos.

### ✅ D4. `Droga` → `Entretenimiento`
Remapear la fila del 2026-07-05 ($10.000). No se crea categoría nueva.

### ✅ D6–D9. Reconciliación de estados de cuenta (pedido 2026-07-23) → ver **Ola 5**
| | Decisión |
|---|---|
| **D6. ¿Qué documentos?** | **Crédito Y débito.** Se incorporan las cartolas de cuenta corriente, hoy ignoradas — es donde vive la mayoría del gasto real |
| **D7. ¿Qué período?** | **El del estado** (ej. 18-jun → 18-jul), no el mes calendario. Es el único rango donde un descuadre significa algo |
| **D8. ¿Qué se compara?** | **Solo compras nuevas.** Intereses, comisiones, mantención y cuotas van en línea aparte como "cobros del banco" |
| **D9. ¿Qué hace con lo que falta?** | **Avisa con botón para agregar.** Respeta el invariante "nunca escribe sin OK" y evita tipear 11 compras a mano |

### ✅ D5. Los dos pares son duplicados — se borran
- **$4.340 San Valentín:** se borra la del **16-07 (dictado)**, se mantiene la del 15-07 (correo, total
  canónico). **También se borran sus 2 líneas en `Compras_Detalle`.**
- **Pago tarjeta:** se borra la del **08-07 ($68.000, manual)**, se mantiene la del 07-07 ($68.416,
  correo). La que queda pasa a categoría `Tarjeta Crédito` (D2).

---

# OLA 0 — Reparación estructural — ✅ **EJECUTADA 2026-07-23**

> Objetivo: el Dashboard vuelve a calcular hoy. Nada acá depende de D1–D5.
> **Resultado: 0 errores en Dashboard y Comparativo. Gastos de julio = $514.992. 234 tests verdes.**
> Respaldo previo de fórmulas/datos en `scratchpad/louis_bak_0723.json`.

| Ítem | Estado | Qué se hizo |
|---|---|---|
| F0.1 | ✅ | Fórmulas de `Dashboard!B4:B8`, el bloque de categorías y `Comparativo!B3:D5` reescritas → re-atadas a los sheetId actuales |
| F0.2 | ✅ | Bloque regenerado a **28 filas** (`Dashboard!12:39`) sobre `Categorias!A3:A30`, con guarda `=IF(Categorias!A{k}="";"";…)` para que crezca solo |
| F0.3 | ✅ | Mes activo → **7** (julio) |
| F0.4 | ✅ | Fila vacía borrada + `Regalos` (duplicada y sin uso) eliminada → 20 categorías en filas 3-22 |
| F0.5 | ✅ | `Deuda_Mensual` H:I con formato `yyyy-mm-dd` (antes seriales) |

**Guarda extra que se agregó sobre lo planeado:** la columna `% Usado` ahora usa
`IF(AND(ISNUMBER(Categorias!C{k});Categorias!C{k}>0);…)`. Sin `ISNUMBER`, las categorías con presupuesto
de texto `-` (`Transferencias`, `Regalo`) daban `#VALUE!`, porque en Sheets el texto es "mayor" que
cualquier número y `"-">0` evalúa a TRUE.

**Lo que el Dashboard reveló apenas revivió** (entra a la Ola 3, no se tocó):
- **Transporte al 215,7%** del presupuesto ($107.872 sobre $50.000) y **Tecnología al 110,5%**.
- **`Otro Gasto` = $183.667**, el segundo mayor del mes — cajón de sastre que oculta gasto real.
- **`Transferencias` = $27.500** contados como gasto (los otros $13.000 son de junio) → los limpia F3.2.
- **Ingresos = `-`** y "¿Llego a fin de mes?" = *"Negativo por $514.992"*, consecuencia directa de F4.1.

---

### (Plan original de la Ola 0, conservado para trazabilidad)

Rama `fix/louis-formulas`.

## F0.1 🔴 Rebindear las fórmulas de Dashboard y Comparativo

**Causa raíz.** Google Sheets ata las referencias entre hojas por **ID interno de hoja**, no por nombre.
Al copiar Dashboard/Comparativo a Louis, sus referencias quedaron apuntando a IDs del workbook Donna
original. El *texto* de la fórmula sigue viéndose bien; el enlace está muerto.

**Evidencia** (Sheets API, `includeGridData`, campo `errorValue`):
```
Dashboard!B4..B8  → {type: N_A,  message: "Argument must be a range."}
Dashboard!A12..   → {type: REF,  message: "Unresolved sheet name 'Categorias'."}
```
…mientras la hoja `Categorias` existe, con ese nombre exacto (verificado con `repr()`: sin espacios ni
caracteres invisibles) y sin ocultar.

**Prueba que lo confirma** (ejecutada en `Dashboard!J40`, celda vacía, borrada después):

| Fórmula escrita de cero | Resultado |
|---|---|
| `=Categorias!A4` | `Alimentación` ✅ |
| `=COUNTA(Categorias!A:A)` | `23` ✅ |
| `=SUMIFS(Transacciones!F:F;…;DATE(2026;7;1);…)` | **`514992`** ✅ |
| la misma con `,` en vez de `;` | `Formula parse error` ❌ |

Por eso `Tarjetas y Deuda` sobrevivió: sus fórmulas solo se referencian a sí mismas. Dashboard y
Comparativo son los únicos que cruzan hojas.

**Instrucciones:**
1. Leer las fórmulas actuales con `valueRenderOption='FORMULA'` de `Dashboard!B4:B8`, `Dashboard!A12:D29`
   y `Comparativo!B3:D5`. Guardarlas a un archivo de respaldo en el scratchpad.
2. Reescribir **el mismo texto** en las mismas celdas con `valueInputOption='USER_ENTERED'`. Eso las
   re-ata a los IDs de hoja actuales. **No cambiar el texto** (salvo lo de F0.2) y **mantener los `;`**.
3. Verificar releyendo con `includeGridData` que ningún `effectiveValue` tenga `errorValue`.

**Output esperado:** `Gastos del mes` deja de ser `#N/A`. Con mes activo = 7 (F0.3) debe dar
**$514.992** (menos los ajustes de las Olas 3, si se aplican después).

## F0.2 🟠 Corregir el rango de categorías del Dashboard

**Causa raíz.** El bloque "Gasto por categoría" ocupa `Dashboard!12:29` (18 filas) y referencia
`Categorias!A3` … `Categorias!A20`. Pero en `Categorias`: **A3 está vacía** (fila en blanco entre el
header de fila 2 y el primer dato) y los datos van de **A4 a A24** (21 categorías).

Resultado: una fila del cuadro se gasta en la fila vacía y **4 categorías quedan fuera** — `Clases`,
`Transferencias`, `Regalos`, `Regalo`.

**Instrucciones:**
1. Ejecutar F0.4 primero (borra la fila vacía A3) — cambia el rango destino.
2. Regenerar el bloque como **21 filas** (`Dashboard!12:32`) referenciando `Categorias!A3:A23` tras el
   borrado. Por cada fila `n`:
   - `A{n}` = `=Categorias!A{k}`
   - `B{n}` = `=Categorias!C{k}`
   - `C{n}` = el SUMIFS con `Categorias!A{k}` como criterio de categoría
   - `D{n}` = `=IF(Categorias!C{k}>0;C{n}/B{n};"-")`
3. Generar las fórmulas programáticamente (no a mano) para que las autorreferencias `C{n}/B{n}` queden
   correctas fila por fila. Es donde se cuelan los off-by-one.
4. **Dejarlo a prueba de futuro:** si mañana se agrega una categoría, el cuadro vuelve a quedar corto.
   Considerar generar el bloque con 30 filas y que las sobrantes muestren `""` cuando `Categorias!A{k}`
   esté vacía.

## F0.3 🟠 Mes activo congelado en junio

`Dashboard!E2 = 6` estando a 23 de julio. Aunque F0.1 arregle las fórmulas, mostraría junio.

Fase 0 · C2 construyó "Mes activo: toque del día 1" — **no corrió el 1 de julio, o corrió y no escribió**.

**Instrucciones:**
1. Poner `Dashboard!E2 = 7`, `G2 = 2026`.
2. Investigar por qué no disparó: revisar el job en `core/scheduler.py` y `incidentes` en Supabase
   alrededor del 2026-07-01.
3. Si el toque depende de que Nico responda y él no lo hizo, **agregar un fallback**: si el mes activo
   quedó atrás del mes real, actualizarlo solo y avisar en el brief. Un dashboard que muestra el mes
   pasado en silencio es peor que uno que se corrige y lo dice.

## F0.4 🟡 Higiene de `Categorias`

1. **Borrar la fila 3** (vacía). Ojo: mueve todo hacia arriba — coordinar con F0.2.
2. **Fusionar `Regalos` / `Regalo`.** Duplicados: `Regalos` (presupuesto vacío) y `Regalo` (`-`). El
   roadmap dice que Finanzas v4 creó `Regalo` "de paso", sobre una que ya existía. Quedarse con **una**
   (recomendado `Regalo`, que es la que usan las transacciones reales) y remapear.
3. `Clases` tiene presupuesto `0` mientras el resto usa `-`. Normalizar a `-` por consistencia
   (`IF(C>0;…)` los trata igual, es cosmético).

## F0.5 🔵 Formato de fechas en `Deuda_Mensual`

`Fecha estado` y `Actualizado` muestran seriales crudos (46203, 46208, 46191, 46194, 46225, 46204) —
se perdió el formato en la migración. Aplicar `numberFormat` tipo `DATE` patrón `yyyy-mm-dd` a las
columnas H e I (mismo patrón que ya usa `Transacciones!A`).

---

# OLA 1 — El faro (bloqueada por: verificación con Nico)

> Rama `fix/louis-faro`. Toca la cifra que Donna usa como verdad de tu deuda.

## F1.1 🟠 El faro calcula el interés en vez de usar el del estado de cuenta

**Este es el hallazgo que más importa de la Ola 1, y es peor de lo que parecía.**

El faro deriva el interés de sus celdas-input en vez de usar la cifra que el banco ya reportó:

```
B25 (BCh)  = B20*B21  = 0,0345 × 667.993 = $23.046
B37 (Mach) = B32*B33  = 0      × 0       = $0
B45 (línea)= input                       = $34.210
B5 INTERESES MUERTOS = B25+B37+B45       = $57.256
```

Pero `Deuda_Mensual` — que llena `modules/estados_cuenta.py` leyendo los PDF reales — dice otra cosa:

| Banco / producto | Mes | Interés del estado | Lo que usa el faro | Δ |
|---|---|---|---|---|
| bch tarjeta_credito | 2026-06 | $24.388 | $23.046 | −$1.342 |
| mach tarjeta_credito | 2026-07 | **$5.310** | **$0** | −$5.310 |
| bch línea | 2026-07 | $34.210 | $34.210 | ✅ |

**El faro subreporta $6.652/mes. El número real de intereses muertos es ~$63.908, no $57.256.**

**Causa raíz en código.** `_celdas_faro` ([estados_cuenta.py:38](../modules/estados_cuenta.py:38)) para
`producto == "tarjeta_credito"` escribe **solo** `deuda_total` (B29/B40) y `cupo` (B28/B39). El
`interes_mes` que sí extrae del PDF **nunca llega al faro** — va a `Deuda_Mensual` y muere ahí. Para
Mach eso es fatal porque su tasa-input es 0.

**Decisión técnica (recomendada):** que el interés reportado por el estado mande sobre el calculado.
- Agregar una celda-input de interés real por tarjeta (o convertir B25/B37 en input y mover el cálculo
  `tasa×rotativa` a una celda "estimado" al lado).
- Extender `_celdas_faro` para escribir `interes_mes` en esa celda cuando el PDF lo trae.
- Mantener el cálculo como **fallback** cuando el estado no reporta interés.
- Test: un estado de Mach con interés $5.310 deja `B5` en $63.908, no $57.256.

**Antes de tocar nada: que Nico confirme** que los $5.310 de Mach son interés real y no una comisión
que ya está contada en "Mantención mensual" ($5.257 — sospechosamente parecido). Si fuera lo mismo,
estaríamos duplicando. *No asumir.*

## F1.2 🟠 El faro mezcla meses — *y NO es culpa del agente (verificado 2026-07-23)*

`Deuda_Mensual` muestra que la foto no es de un solo mes:
- **BCh tarjeta:** solo tiene fila `2026-06` → el faro usa deuda de **junio**.
- **Mach tarjeta:** tiene `2026-07`.
- **Línea:** interés de `2026-07`.

**Causa verificada contra el Gmail real:** el último estado de cuenta de tarjeta BCh que existe en el
correo es del **23 de junio**. El de julio **todavía no llega** (confirmado por Nico). No falló ningún
job — el dato no existe aún. *(La versión anterior de este ítem pedía "revisar si el job falló": queda
descartado.)*

**Instrucción (lo que sí queda):** hacer explícita la mezcla. Que el faro / `fin_progreso_deuda` muestre
**de qué mes es cada cifra** en vez de presentar un total con fecha implícita, y que diga cuándo está
esperando un estado que no ha llegado. Encaja con el invariante de inferencia validada: si Donna afirma
una deuda, que muestre de cuándo es el dato.

## F1.4 🟠 `correo_dias = 2` es una ventana de pérdida permanente

**Hallazgo nuevo (auditoría de Gmail, 2026-07-23).** `ingerir_gastos_email` busca con
`newer_than:{correo_dias}d` y `correo_dias = 2` ([config.py:38](../config.py:38)). **Si Donna no corre
durante más de 2 días, esos gastos no se recuperan nunca** — la próxima corrida ya no los ve.

**Evidencia:** de 42 correos de gasto que el parser entiende en los últimos 30 días, **3 nunca llegaron
a `Transacciones`**, todos transferencias a sí mismo: $52.000 (07-07), $90.000 (06-30), $2.700 (06-29).
Por **D1** no son gasto, así que no distorsionan el total — pero sí revelan el agujero: otras 5
transferencias equivalentes **sí** se registraron. La diferencia no es de criterio, es de ventana.

**Instrucciones:** subir `correo_dias` (7-14) apoyándose en el dedup por `ID_Único`, que ya evita
reprocesar; y/o llevar una marca de "último correo procesado" para que la ventana sea *desde la última
corrida* en vez de un número fijo de días. Lo segundo es lo correcto; lo primero es el parche barato.

## F1.5 ✅ Sobregiro no pactado — **revisado y descartado**

`_producto` clasifica `LiqIntSobregiroNoPactado.pdf` como `sobregiro` y lo ignora, con el comentario
*"menor, se ignora"*. Se levantó como sospecha (¿estará ocultando intereses muertos?) y **se verificó
descifrando el PDF real**: período 05/2026, monto sobregiro $18.525, **interés total = $26**.

**La decisión del código es correcta.** No se toca. Queda registrado para que nadie vuelva a
levantar la misma sospecha.

## F1.3 🟠 Estás sobre el cupo (esto es realidad, no bug — pero el faro lo calla)

- **BCh:** deuda $1.030.608 contra cupo $1.000.000 → **$30.608 por encima del límite**.
- **Mach:** $300.000 / $300.000 → exactamente en el tope.
- **% Utilización:** 99,98% (muestra 100,0%).
- Disponible total: **$30.969**, todo en la línea.

El semáforo dice 🔴 Alto, pero no nombra que un producto ya se pasó del cupo — que suele traer comisión
de sobregiro. **Instrucción:** agregar al faro una alerta explícita cuando `deuda > cupo` en cualquier
producto, y que el digest/brief la nombre. Es exactamente el tipo de cosa que Donna debería decir sin
que se la pregunten.

---

# OLA 2 — El código que ensucia (bloqueada por: D3)

> Rama `fix/finanzas-categorias`. Sin esto, la Ola 3 se vuelve a ensuciar sola.

## F2.1 🟡 `_categoria_item` inventa categorías

**Causa raíz.** [finanzas.py:578](../modules/finanzas.py:578):
```python
return cat if cat != "Otro Gasto" else (nombre.strip().capitalize() or "Otro Gasto")
```
Si el ítem no mapea a una categoría conocida, **usa el nombre del ítem capitalizado como categoría**.
Por eso `Compras_Detalle` tiene 6 categorías que no existen en el catálogo:
`Bebidas`, `Calzado`, `Compota`, `Pago movida`, `Pan`, `entretenimiento`.

Nótese el patrón: `compota` → `Compota`, `pan` → `Pan`, `Pago movida` → `Pago movida`. Es el ítem
repetido en la columna de categoría.

**Instrucción:** que el fallback caiga a `Otro Gasto` (o a la categoría de la transacción padre, que sí
está validada) en vez de inventar. Nunca escribir una categoría que no exista en `Categorias`.

## F2.2 🟡 `Compras_Detalle` no valida contra el catálogo

`Transacciones` pasa por `_validar_categoria` ([finanzas.py:491](../modules/finanzas.py:491)) y cae a
`Otro Gasto` si no calza. `Compras_Detalle` **no pasa por ahí** — por eso F2.1 pudo escribir basura.

**Instrucción:** enrutar toda escritura de `Compras_Detalle` por `_validar_categoria`.

**Nota aparte — hueco en la validación:** `_validar_categoria` hace passthrough si no puede leer
`Categorias` (`if not reales: return cat, True`). Es "degrada elegante" bien intencionado, pero deja
pasar cualquier cosa cuando Sheets falla. Evaluar registrar un incidente vía `core/diagnostico.py`
cuando eso ocurra, para que no sea silencioso.

## F2.3 🟡 El matcher no cubre `dictado`

El canon exige *"foto y correo del mismo gasto → una sola transacción, jamás doble conteo"*.
`fin_correlacionar` ([finanzas.py:637](../modules/finanzas.py:637)) empareja por monto+fecha+comercio,
pero la fuente `dictado` no entra al matcher.

**Evidencia:** 07-15 $4.340 (correo) y 07-16 $4.340 (dictado), mismo comercio, ambos con desglose en
`Compras_Detalle`. Es exactamente el doble conteo que el canon prohíbe.

**Instrucción:** incluir `dictado` en la correlación con la misma ventana (±1-2 días). Cuando haya
match, el **correo manda como total canónico** y el dictado aporta los ítems.

## F2.4 🟡 `Predecible` en 12/12 → el predictor nace sin datos

Ninguna línea quedó `Predecible=sí`, así que Compras Fase 2 no tiene de qué aprender.

En parte es correcto por diseño (pan y chanchería **deben** ser `no`). Pero conviene verificar que
`_predecible` ([finanzas.py:555](../modules/finanzas.py:555)) no esté siendo demasiado estricto: exige
que el ítem calce con `_PREDECIBLE_KW`, así que **cualquier cosa de despensa fuera de esa lista cae en
`no`**. Con 12 filas no se puede concluir; instrucción: **medir antes de tocar** — cuando haya ~30
líneas, revisar cuántas de despensa real quedaron fuera. `Cantidad` está vacía en 12/12: verificar si
el extractor la captura o si la columna está muerta.

## F2.5 🟠 Toda transacción escribe su línea de detalle (D3 + D10)

> **Reemplaza por completo la versión anterior de este ítem**, que proponía partir `Transacciones` en
> varias filas. Nico corrigió el modelo: `Transacciones` **no se toca**, una fila por movimiento.

**Instrucciones:**
1. `Transacciones` **sigue escribiendo una sola fila** por movimiento, con su monto total y su
   `ID_Único` actual. **No** se parte, **no** se sufija. El reconciliador depende de esto.
2. **Toda** transacción escribe además **≥1 línea** en `Compras_Detalle` con el mismo `ID_Tx`:
   - **Con desglose** (foto/dictado/correo con ítems) → N líneas, una por ítem, cada una con su
     categoría e intención propias.
   - **Sin desglose** (bencina, revisión técnica, un cargo suelto) → **1 línea** por el monto completo,
     heredando la categoría de la transacción.
3. **Verificar que las líneas sumen exacto** el total de la transacción padre. Si no cuadra, escribir
   una sola línea por el total y registrar un incidente — mejor un detalle honesto que uno inventado.
4. `_intencion_resumen` ([finanzas.py:564](../modules/finanzas.py:564)) **se mantiene**, pero su
   resultado (`Mixto` incluido) queda como **etiqueta de resumen** en `Transacciones`. Ninguna métrica
   se calcula sobre esa columna.
5. **Backfill:** generar la línea faltante para las ~59 transacciones que hoy no tienen detalle.
   Va en la Ola 3, con dry-run.

**Tests obligatorios:** una compra de $4.340 con desglose deja **1** fila en `Transacciones` y **2**
líneas en `Compras_Detalle` que suman $4.340 · una bencina sin desglose deja 1 fila y 1 línea · la suma
de `Compras_Detalle` por `ID_Tx` **siempre** cuadra con el monto de `Transacciones`.

**Dato aparte:** **`Inversión` no aparece nunca** en 69 filas. O no gastas en eso, o los keywords de
`_INTENCION_KW` no pegan. Revisar con Nico.

---

# OLA 3 — Limpieza de datos (decisiones tomadas, lista para ejecutar)

> Rama `fix/louis-datos`. **Dry-run obligatorio + respaldo de `Transacciones` antes de escribir.**
> Ejecutar **después** de la Ola 2, para que lo que se limpie no se vuelva a ensuciar.
> **Orden interno obligatorio: F3.3 (borrar duplicados) → F3.1/F3.2 (recategorizar) → F2.5 (partir).**
> Partir antes de borrar duplicaría el trabajo sobre filas que igual se van.

## F3.1 🟡 Categorías huérfanas
| Fila | Categoría actual | Monto | Acción (decidida) |
|---|---|---|---|
| 2026-07-03 | `chancheria` | $3.590 | → `Chanchería` (duplicado por tilde/minúscula) |
| 2026-07-05 | `Droga` | $10.000 | → **`Entretenimiento`** (D4) |
| 2026-07-07 | `Otro Gasto` | $68.416 | → **`Tarjeta Crédito`** (D2) |
| 2026-07-08 | `Deuda / Tarjeta` | $68.000 | **se borra** (D5, duplicado) |

Mientras existan, suman **$0** en el Dashboard: el SUMIFS matchea contra el nombre exacto de `Categorias`.

## F3.2 🟡 Transferencias a ti mismo → fuera del conteo (D1)
Las **5 filas** de categoría `Transferencias`, todas con destinatario "Nicolas Castro", por **$40.500**:
```
2026-06-23  $8.000    2026-06-30  $5.000    2026-07-05  $7.000
2026-07-05  $12.000   2026-07-19  $8.500
```
**Verificación previa (rápida, con Nico):** confirmar que ese "Nicolas Castro" es él y no un tercero
homónimo. Si es él → salen del conteo de gasto.

**Cómo sacarlas del conteo:** el Dashboard filtra por `Tipo="Gasto"`, así que basta cambiar su `Tipo`
(a `Transferencia`) para que queden fuera **sin tocar ninguna fórmula**. Siguen visibles en la hoja.

Normalizar de paso `Transferencia a persona` / `Transferencia a terceros`, hoy usados indistintamente
para lo mismo. Y **revisar el texto de la categoría** en `Categorias`: su nota dice "entre cuentas
propias", que ahora es la definición oficial (D1) — debe quedar explícito.

## F3.3 🟡 Duplicados — confirmados por Nico, se borran (D5)
| Se borra | Se mantiene | Por qué |
|---|---|---|
| 2026-07-16 $4.340 San Valentín (`dictado`) | 2026-07-15 $4.340 (`correo`) | El correo es el total canónico |
| 2026-07-08 $68.000 pago tarjeta (`manual`) | 2026-07-07 $68.416 (`correo`) | Idem |

**Ojo:** borrar también las **2 líneas de `Compras_Detalle`** del 2026-07-16 (pan $2.340 + chanchería
$2.000), o quedan huérfanas apuntando a un `ID_Tx` que ya no existe.

Total que sale del mes: **$72.340**.

## F3.4 🔵 Intención vacía
14/69 filas sin Intención, todas del tramo 06-18 → 06-24 (el digest no las confirmó). Decidir: backfill
con la inferencia de `_intencion_de`, o dejarlas vacías como registro honesto de que no se confirmaron.
**Recomendado: dejarlas.** Rellenarlas con una inferencia no confirmada contradice el espíritu de
"se confirma en el digest".

---

## F3.5 🟠 Backfill de `Compras_Detalle` + el Dashboard cambia de fuente (D10)

**Va al final de la Ola 3: depende de que F2.5 ya esté escribiendo bien y de que los duplicados estén
borrados.** Dos pasos, en este orden:

**1. Backfill.** Generar la línea de detalle faltante para las ~59 transacciones que no la tienen
(1 línea = monto completo, categoría heredada de la transacción). Dry-run obligatorio. Verificar al
terminar que **para toda transacción**, `SUM(Compras_Detalle por ID_Tx) == Monto`. Sin ese 100%, el
paso 2 pierde plata en silencio.

**2. Cambiar la fuente del Dashboard.** El bloque "Gasto por categoría" que se regeneró en la Ola 0 hoy
suma desde `Transacciones!C:C`. Debe pasar a sumar desde **`Compras_Detalle`** (columna `Categoría`,
monto `Precio`, fecha `Fecha`), que es donde vive la categoría real por ítem.

⚠️ **Este paso reescribe lo que se reparó en F0.2 — es esperado, no un retroceso.** La Ola 0 dejó el
Dashboard *funcionando*; esto lo deja *correcto*. Hacerlo antes del backfill mostraría solo el 14% del
gasto.

**Verificación de que no se perdió plata:** el total del bloque de categorías debe seguir cuadrando con
`Gastos del mes` (que sigue leyendo `Transacciones`). Si no cuadran, hay transacciones sin detalle.
Ese cuadre es la mejor prueba permanente de que las dos hojas están sincronizadas — vale la pena
dejarlo como celda visible en el Dashboard.

---

# OLA 4 — Deuda de fondo (no bloquea nada, pero no desaparece sola)

## F4.1 ✅ Cero ingresos registrados — **resuelto por D12, se construye en F5.7**
Las 69 filas son `Gasto`. **Ninguna `Ingreso`.** Por eso `Tasa de ahorro` da `-` y `¿Llego a fin de mes?`
dice "negativo" siempre. `Categorias` tiene 4 categorías de Ingreso (`Freelance`, `Ayuda Familiar`,
`Uber Eats`, `Clases`), ninguna usada.

**Ya tiene solución:** los abonos de las cartolas de cuenta corriente (F5.7), filtrados por la regla del
RUT propio (D12). Este ítem deja de ser una decisión abierta y pasa a ser una consecuencia de la Ola 5.

## F4.2 🟡 `Metas` vacío
Solo el header. Finanzas v2 pedía 2-3 metas (fondo de emergencia, pagar TC) y el `Semanal`/digest las
leen. Sin filas, `fin_metas` no tiene qué mostrar. Requiere que Nico las defina — no es código.

## F4.3 🔵 `Subcategoría`: dos escritores, dos semánticas
Filas de `correo` meten ahí el identificador de tarjeta (`****1969`, `Rut 78247927-K`,
`Tarjeta ****5502`); las de `estado_cuenta` la dejan vacía. La columna no sirve para analizar nada.
Decidir: columna `Tarjeta`/`Medio_Detalle` propia, o aceptar que `Subcategoría` es eso y renombrarla.

## F4.4 🔵 El mismo comercio bajo 3 nombres
`negocio San Vale` (truncado) / `MERCADOPAGO*SANVA` / `MERCADOPAGO*SANVALEN`. Rompe el análisis por
comercio y **debilita el matcher de F2.3**, que empareja por monto+fecha+comercio. Evaluar una tabla de
alias de comercio (ya existen `_aplicar_reglas_comercio`) y normalizar al escribir.

---

# OLA 5 — Reconciliación de estados de cuenta (**capacidad nueva**, Finanzas v5)

> Pedido por Nico el 2026-07-23. **No es reparación: es construcción.** Decisiones D6–D9 tomadas.
> Rama `feat/finanzas-v5-reconciliacion`. Va **después** de la Ola 2 — ver la dependencia dura en F5.4.

**Objetivo en una frase:** cada vez que llega un estado de cuenta, Donna lo abre, lo compara contra
`Transacciones`, y te dice **cuánta plata del estado no está anotada** y **cuál falta**.

## Lo que YA existe (no reconstruir)
`_reconciliar` ([estados_cuenta.py:162](../modules/estados_cuenta.py:162)) ya compara las compras del
estado contra `Transacciones` (match por monto exacto + fecha ±5d), filtra ruido con `_NO_COMPRA`, **no
escribe nada** y reporta vía `texto_reporte`. Así se encontraron las 11 compras de junio sin registrar.

**Sus tres límites, que es lo que hay que levantar:**
1. Solo corre sobre `tarjeta_credito`. Las cartolas de cuenta corriente caen en `_producto → "otro"`
   y se saltan enteras → **el gasto con débito nunca se reconcilia**.
2. Usa una ventana fija `dias_recientes=45` en vez del período real del estado.
3. Da una **lista** de faltantes, nunca un **diferencial en plata**.

## F5.1 🟠 Leer las cartolas de cuenta corriente (D6)
1. `_producto` ([estados_cuenta.py:62](../modules/estados_cuenta.py:62)): clasificar
   `cartola_cuenta_corriente` (hoy `"otro"`). Ojo con el orden de los `if`: "cartola" aparece también en
   los nombres de línea de crédito, así que la regla nueva va **después** de las de línea/sobregiro.
2. Enseñar al extractor el formato de cartola (lista de movimientos: fecha, descripción, cargo/abono).
   Es un PDF distinto al de tarjeta — probar contra los reales de BCh (`CartolaCuentaCorrienteNacionalMensual.pdf`)
   y Mach (`Cartola_CtaCte_MACHBANK de junio 2026.pdf`).
3. ⚠️ **Una cartola NO es un documento de deuda.** Debe **saltarse** `_celdas_faro` y `_upsert_historial`
   — si entra por ahí, corrompe el faro. Va **solo** a reconciliación.
4. Dedup: agregar la llave de producto `cartola_cc` para que no se reprocese.
5. Filtrar los abonos (ingresos) — la reconciliación es de gasto. *(Aunque ver F4.1: sería la primera
   fuente real de ingresos que tendría Donna.)*

## F5.2 🟠 Reconciliar por período del estado (D7)
Reemplazar `dias_recientes=45` por el **rango real del documento**. Los PDF lo traen (verificado: el de
sobregiro dice `PERIODO DESDE : 01/05/2026 … HASTA : 31/05/2026`). Agregar `periodo_desde`/`periodo_hasta`
a lo que extrae `_extraer`, y compararlos contra las `Transacciones` de esas mismas fechas.

Si el PDF no trae período legible: **caer a la ventana fija y decirlo en el reporte** — nunca presentar
un cuadre como exacto cuando el rango se adivinó.

## F5.3 🟠 El diferencial en plata (D8) — *la pieza nueva*
Dos cuadres separados, nunca mezclados:

```
📄 Estado BCh Visa · 18 jun → 18 jul
   Compras del estado      $412.300  (23 movimientos)
   Anotado por Donna       $389.100  (21 movimientos)
   ─────────────────────────────────
   ⚠️ Falta anotar          $23.200  (2 compras)

   Cobros del banco (no son gasto que se te olvidó):
   intereses $24.388 · mantención $6.061 · cuotas $65.861
```

- La línea de **compras** es la que importa: un descuadre ahí = gasto perdido.
- Los **cobros del banco** van aparte porque Donna nunca los captura por correo; meterlos en el mismo
  número garantizaría un descuadre permanente que no significa nada. `_NO_COMPRA` ya sabe reconocerlos:
  hoy los descarta, ahora los **agrupa** en esta segunda línea.

## F5.4 ✅ La dependencia dura **se disolvió** (D3 corregido)
La versión anterior de este ítem advertía que partir `Transacciones` rompería el matcher por monto
exacto, y exigía reagrupar por raíz de `ID_Único`.

**Ya no aplica.** Con el modelo corregido (D3), `Transacciones` conserva una fila por movimiento con el
monto que el banco reporta. El matcher funciona tal cual, sin reagrupar nada.

**Lo único que queda de este ítem:** el reconciliador debe seguir leyendo **`Transacciones`** y no
`Compras_Detalle`. Son hojas con trabajos distintos: una cuadra contra el banco, la otra alimenta las
métricas. Cruzarlas produciría falsos faltantes.

## F5.7 🟠 Ingresos y saldo desde la cartola (D11 + D12)
Las cartolas de cuenta corriente que se incorporan en F5.1 traen dos datos que hoy Donna no tiene:

**Abonos → `Transacciones` con `Tipo=Ingreso`.** Aplicando la **regla del RUT propio** (D12): si el
depósito viene de una cuenta de Nico, es traslado y **no** se registra como ingreso. Requiere la lista
de RUTs/cuentas propias como configuración (hoy solo existe `dueno_rut`, singular).

**Saldo de cierre → una cifra al mes.** Guardar en `Deuda_Mensual` (o una hoja `Saldos` propia — decidir
al construir; `Deuda_Mensual` ya tiene la forma `Mes · Banco · Producto · …`, así que probablemente
calce como un producto más).

⚠️ **Antes de construir esto hay que actualizar `CLAUDE.md`**, que hoy prohíbe los saldos automáticos.
Ver D11.

**Esto resuelve F4.1** (cero ingresos registrados), que era la razón de que "tasa de ahorro" y "¿llego a
fin de mes?" no sirvieran para nada.

## F5.5 🟡 Botón para agregar lo que falta (D9)
Extender el reporte con un toque por compra faltante (y un "agregar todas"). Al tocar:
1. Escribe en `Transacciones` con categoría **inferida y validada** contra `Categorias` (F2.2).
2. `Fuente = estado_cuenta`, `ID_Único` con la misma convención de hoy.
3. Pasa por el dedup existente — tocar dos veces no debe duplicar.
4. Respeta el invariante: **nada se escribe hasta el toque.**

Reusar el patrón de chips del digest vivo (`core/flows.py`), que ya resuelve mensaje anclado + edición
en el lugar + commit único a Sheets.

## F5.6 🟡 Cuándo corre
El job diario de las 9:30 ya trae dedup interno (actúa solo cuando hay documento nuevo). Se mantiene.
Agregar además una tool a demanda (*"Donna, cuadra el último estado"*) para poder pedirlo sin esperar.

**Eval de la ola:** un estado con 23 compras de las que 21 están anotadas reporta exactamente $23.200 en
2 compras · una compra partida en 2 categorías **no** se reporta como faltante (F5.4) · una cartola de
cuenta corriente **no** altera el faro ni `Deuda_Mensual` · el botón agrega sin duplicar · los intereses
salen en la línea de cobros, nunca en la de compras.

---

## Gate de salida

El realineamiento está cerrado cuando:

1. **Dashboard sin un solo `#N/A`/`#REF!`**, mostrando el mes en curso, con las 21 categorías.
2. **Comparativo** calcula mes activo vs. anterior.
3. **El faro usa los intereses del estado de cuenta**, muestra de qué mes es cada cifra y alerta sobre
   cupo excedido.
4. `Transacciones` sin categorías huérfanas; `Compras_Detalle` **solo** con categorías del catálogo.
5. Los dos duplicados resueltos (borrados o confirmados como reales por Nico).
6. **La reconciliación de estados (Ola 5) da un diferencial en plata** por período de estado, cubre
   crédito **y** débito, y ofrece el toque para agregar lo que falta.
7. `python -m pytest tests/ -q` **verde**, con tests nuevos para: rebinding de fórmulas, interés desde
   estado de cuenta, correlación `dictado`↔`correo`, validación de categoría en `Compras_Detalle`,
   y **reagrupación por raíz de `ID_Único` en el reconciliador** (F5.4).
8. Tablero de `Roadmap_Modular.md` actualizado + este doc movido a `docs/archivo/` con su nota de cierre.

## Qué NO entra en este plan

- **Construir Calendario+Recordatorios** (Módulo 4) ni **Correo** (Módulo 5) — la secuencia decidida el
  2026-07-23 sigue vigente; esto es reparación, no avance de roadmap.
- **Compras Fase 2** (el predictor) — sigue diferida por canon. F2.4 solo se asegura de que cuando
  llegue, tenga datos sanos.
- **Rediseñar el esquema de `Transacciones`** — F4.3/F4.4 quedan como decisión abierta, no como trabajo
  comprometido.
