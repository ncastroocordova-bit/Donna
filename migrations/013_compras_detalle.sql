-- Finanzas v3: detalle de compra ítem-a-ítem + correlación foto/dictado ↔ correo.
--
-- 1) El buffer guarda, además del total, el DETALLE por ítem (retenido hasta confirmar en
--    el cierre — invariante "nada a Sheets sin OK") y la INTENCIÓN resumen del cargo.
--    `items` = [{item, cantidad, precio, categoria, intencion, predecible}].
-- 2) `preguntado_en` marca cuándo Donna preguntó "¿qué compraste?" por un cargo sin detalle,
--    para que el poll cada 5h no insista.
-- 3) `comercios.es_compras` marca los comercios de despensa/almacén (súper, San Valentín):
--    sus cargos sin detalle gatillan la pregunta. Aprendible al confirmar un desglose.

ALTER TABLE buffer_transacciones ADD COLUMN IF NOT EXISTS intencion     TEXT DEFAULT '';
ALTER TABLE buffer_transacciones ADD COLUMN IF NOT EXISTS items         JSONB;
ALTER TABLE buffer_transacciones ADD COLUMN IF NOT EXISTS preguntado_en TIMESTAMPTZ;

ALTER TABLE comercios ADD COLUMN IF NOT EXISTS es_compras BOOLEAN NOT NULL DEFAULT FALSE;
