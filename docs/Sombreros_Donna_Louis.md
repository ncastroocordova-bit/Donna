# Sombreros de Donna: Donna (vida) + Louis (plata)

**Qué es:** la separación de Donna en dos sombreros, cada uno con su propia planilla de
Google Sheets, para tener control aislado de lo financiero. Reemplaza el canon v7.2 de
"un solo workbook".

## Los dos sombreros

| Sombrero | Planilla (env) | Dominio | Hojas |
|----------|----------------|---------|-------|
| **Donna** (vida) | `GOOGLE_SHEET_ID` | recordatorios, salud, familia, correo, productividad, compras | Diario, Tareas, Proyectos, Recordatorios, Reconciliacion, Semanal, Compras, Ideas, ⚙️ Config |
| **Louis** (plata) | `GOOGLE_SHEET_ID_LOUIS` | finanzas + estados de cuenta | Transacciones, Categorias, **Tarjetas y Deuda**, **Dashboard**, **Comparativo**, Metas, Compras_Detalle, Deuda_Mensual |

(**Negrita** = hojas con fórmulas; el código solo las lee por celda, `setup_sheets.py` no las toca.)

## Cómo quedó cableado (código, ya hecho)

- **`config.py`** — nueva env `GOOGLE_SHEET_ID_LOUIS`. `sheet_finanzas` resuelve
  `Louis → legacy Finanzas → Donna`. Mientras Louis esté vacío, finanzas sigue en la
  planilla Donna (modo single-workbook): **nada se rompe antes de migrar**.
- **`core/sheets.py`** — `vida_id()` = Donna, `fin_id()` = Louis (cae a Donna si vacío).
  Finanzas y estados de cuenta ya pasaban `sheet_id=sheets.fin_id()` en cada lectura/
  escritura, así que no hubo que tocar lógica de módulos.
- **`setup_sheets.py`** — `TABS` partido en `TABS_DONNA` y `TABS_LOUIS`; asegura cada
  grupo contra su planilla. `TABS` combinado se mantiene para el guardián de schema.
- **`core/scheduler.py`** — `job_verificar_schema` chequea las hojas de vida contra Donna
  y las de finanzas contra `fin_id()` (Louis). Sin esto, el guardián tiraría incidentes
  falsos "columnas faltantes" al no encontrar las hojas de plata en la planilla de vida.

## Migración (pasos manuales de Nico, una vez)

1. **Crear la planilla Louis** en Google Drive (nombre sugerido: `Louis`), compartida con
   el mismo service account (rol Editor) que ya usa Donna.
2. **Mover las hojas de finanzas** desde la planilla Donna a Louis. En Google Sheets:
   clic derecho en la pestaña → *Copiar a → planilla existente → Louis*, para cada una de:
   Transacciones, Categorias, Tarjetas y Deuda, Dashboard, Comparativo, Metas,
   Compras_Detalle, Deuda_Mensual. **Copia primero, borra de Donna solo tras verificar.**
   - Ojo con las fórmulas de Dashboard/Comparativo/Tarjetas y Deuda: si referencian otras
     hojas por nombre (`=Transacciones!...`), al mover todas juntas las referencias siguen
     resolviendo dentro de Louis. Revisa el faro tras mover (debe seguir dando la cifra real).
3. **Setear la env** en `.env` (local) y en Railway:
   ```
   GOOGLE_SHEET_ID_LOUIS=<id de la planilla Louis>
   ```
   (`GOOGLE_SHEET_ID` sigue siendo la planilla Donna.)
4. **Correr** `python setup_sheets.py` — asegura los tabs de cada sombrero en su planilla
   (idempotente y aditivo; no borra ni reordena).
5. **Verificar:** `fin_progreso_deuda` / el faro dan la cifra real desde Louis; el brief y
   el cierre (vida) siguen leyendo desde Donna; el guardián de schema al boot no reporta
   incidentes.

## Reversa

Para volver al single-workbook: dejar `GOOGLE_SHEET_ID_LOUIS` vacío. El código vuelve a
apuntar finanzas a la planilla Donna sin más cambios.

## Pendiente futuro (no bloquea la separación)

- **Compras Fase 2** (diferida) leerá `Compras_Detalle`, que ahora vive en Louis. Cuando se
  construya, esa lectura debe pasar `sheet_id=sheets.fin_id()` explícito (cruza de la
  planilla Donna a la Louis). Registrado también en `CLAUDE.md` como "cable cruzado a vigilar".
