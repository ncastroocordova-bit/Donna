-- Memoria de reposición: por cada ítem de compra, si Nico lo considera despensa
-- (predecible = se repone, entra al predictor de Compras Fase 2) o cotidiano/perecible.
--
-- Por qué existe: hasta ahora `finanzas._predecible` decidía SOLO con una lista fija de
-- palabras clave, y el chip 📦/🥖 del digest —que existe desde v3— cambiaba el valor de ese
-- digest y nada más. Nico podía marcar "pañales" como reposición todas las semanas y Donna
-- lo olvidaba cada vez. Eso rompe el canon de la espina: el aprendizaje se persiste en
-- Supabase, no se vuelve a inferir desde cero. Esta tabla es el lookup de correcciones.
--
-- Mismo patrón que `comercios` (012): clave = substring en minúsculas del nombre del ítem.

CREATE TABLE IF NOT EXISTS items_predecibles (
    patron     TEXT PRIMARY KEY,      -- substring (en minúsculas) del nombre del ítem, ej. "pañales"
    predecible BOOLEAN NOT NULL,      -- true = despensa/reposición · false = cotidiano/perecible
    veces      INT DEFAULT 1,         -- cuántas veces Nico lo confirmó (para priorizar y para auditar)
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE items_predecibles ENABLE ROW LEVEL SECURITY;
