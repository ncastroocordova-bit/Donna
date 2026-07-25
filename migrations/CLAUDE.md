# migrations/ — instrucciones locales

**El canon del proyecto vive en [`../CLAUDE.md`](../CLAUDE.md).** Claude Code ya lo carga; este
archivo NO lo repite. Hasta el 2026-07-24 sí lo repetía —una copia completa— y se desincronizó en
silencio: seguía anunciando el faro viejo ($2.028.091 / $48.236), no conocía la planilla Louis ni
la hoja `Saldos`, y mandaba a documentos archivados. **Si algo de acá empieza a parecerse al canon,
bórralo y deja el link.**

## Qué es esta carpeta

El esquema de **Supabase**, que en el canon es la mitad "lo que Donna aprende" de las dos capas de
datos. Los **registros** (lo que pasó, lo que Nico ve y edita) viven en Google Sheets y no se
tocan desde acá. Regla dura del canon: el aprendizaje —patrones, ratios, inferencias, lookups de
corrección— se persiste en Supabase y **nunca** en el Sheet.

## Convención

- Un archivo por cambio, numerado y correlativo: `NNN_nombre.sql`. **Nunca se edita una migración
  ya aplicada** — se agrega la siguiente.
- Idempotentes: `CREATE TABLE IF NOT EXISTS`, `ALTER ... IF NOT EXISTS`.
- Toda tabla nueva termina con `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;`.
- Comentario de cabecera que explique **por qué** existe la tabla, no solo qué guarda.
- Aplicar es un paso manual (Supabase MCP o el SQL editor). Escribir el `.sql` no es aplicarlo:
  si no corriste la migración, la tabla no existe y el módulo degrada en producción.

## Tablas por migración

| # | Tablas |
|---|--------|
| 001–004 | `perfil` · `inferencias` · `compromisos` · `memoria` (episódica + embeddings pgvector) |
| 005 | RLS sobre lo anterior |
| 006 | `proyectos` |
| 007 | `calibracion` · `patrones` — la calibración y el factor de optimismo |
| 008–009 | limpieza de vestigios · endurecimiento de funciones |
| 010 | `buffer_transacciones` (gastos pendientes de confirmar en el digest) · `jobs_log` |
| 011 | `correos_vistos` |
| 012 | `comercios` — lookup aprendido: patrón → nombre + categoría + `es_compras` |
| 013 | `Compras_Detalle` (es una hoja de Sheets, no una tabla: la migración solo documenta) |
| 014 | `incidentes` — autodiagnóstico lean |
| 015 | `items_predecibles` — lookup aprendido del chip 📦/🥖 (qué se repone y qué no) |
