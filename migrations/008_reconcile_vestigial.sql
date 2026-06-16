-- Reconciliación de drift histórico.
-- La base viva tenía dos columnas que vienen de los creates originales (anteriores
-- a estas migraciones) y que el código actual NO usa: `inferencias.preguntado_en`
-- y `compromisos.recordado_en`. Se agregan acá solo para que un despliegue limpio
-- reproduzca exactamente el estado vivo.
--
-- Son vestigiales: si se confirma que no harán falta, pueden eliminarse con
--   ALTER TABLE inferencias DROP COLUMN preguntado_en;
--   ALTER TABLE compromisos DROP COLUMN recordado_en;
ALTER TABLE inferencias ADD COLUMN IF NOT EXISTS preguntado_en TIMESTAMPTZ;
ALTER TABLE compromisos ADD COLUMN IF NOT EXISTS recordado_en  TIMESTAMPTZ;
