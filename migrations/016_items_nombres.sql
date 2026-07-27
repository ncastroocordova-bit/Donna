-- Memoria de nombres de ítem: cuando Nico corrige el nombre de un ítem mal leído por la foto o
-- el dictado (OCR/transcripción, ej. "pahales" -> "Pañales Emilio"), la corrección se aprende y
-- se aplica sola la próxima vez que la misma boleta/dictado traiga el mismo texto crudo — mismo
-- patrón que `comercios` (012) e `items_predecibles` (015): el aprendizaje se persiste en
-- Supabase, no se vuelve a corregir a mano cada boleta.
--
-- Distinto de `items_predecibles`: acá el patrón es el texto CRUDO completo (normalizado), no
-- una palabra clave suelta — es una corrección literal de un texto mal leído, no una
-- clasificación difusa, así que un match parcial de una sola palabra sería más riesgoso.

CREATE TABLE IF NOT EXISTS items_nombres (
    patron          TEXT PRIMARY KEY,   -- texto crudo del ítem (normalizado, minúsculas)
    nombre_canonico TEXT NOT NULL,      -- el nombre correcto que Nico escribió
    veces           INT DEFAULT 1,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE items_nombres ENABLE ROW LEVEL SECURITY;
