-- Memoria de comercios: Donna aprende, por cada comercio crudo del banco, un nombre
-- amigable y su categoría. El parser consulta esta tabla; las correcciones del digest
-- la alimentan (lookup de correcciones del canon). Persistencia en Supabase, no en el Sheet.

CREATE TABLE IF NOT EXISTS comercios (
    patron     TEXT PRIMARY KEY,      -- substring (en minúsculas) a buscar en el comercio crudo del banco
    nombre     TEXT NOT NULL,         -- nombre amigable para mostrar (ej. "negocio San Vale")
    categoria  TEXT DEFAULT '',       -- categoría aprendida para ese comercio
    veces      INT DEFAULT 1,         -- cuántas veces se ha visto/confirmado (para priorizar)
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE comercios ENABLE ROW LEVEL SECURITY;
