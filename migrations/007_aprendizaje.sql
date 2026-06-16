-- Aprendizaje avanzado (Fase 4): calibración por dominio + patrones con decay.
-- Más la columna `dominio` en inferencias, que alimenta la calibración.

-- Nivel 3: tasa de acierto de inferencias por dominio.
CREATE TABLE IF NOT EXISTS calibracion (
    dominio     TEXT PRIMARY KEY,
    confirmadas INT DEFAULT 0,
    descartadas INT DEFAULT 0,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Nivel 2: patrones consolidados (inferencias confirmadas que se repiten).
CREATE TABLE IF NOT EXISTS patrones (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    descripcion    TEXT NOT NULL,
    dominio        TEXT DEFAULT '',
    peso           REAL DEFAULT 1.0,
    confirmaciones INT DEFAULT 1,
    estado         TEXT DEFAULT 'activo'
                       CHECK (estado IN ('activo', 'silenciado')),
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    last_visto     TIMESTAMPTZ DEFAULT NOW()
);

-- Las inferencias se etiquetan por dominio (sueño, plata, ánimo…) para la calibración.
ALTER TABLE inferencias ADD COLUMN IF NOT EXISTS dominio TEXT DEFAULT '';

ALTER TABLE calibracion ENABLE ROW LEVEL SECURITY;
ALTER TABLE patrones    ENABLE ROW LEVEL SECURITY;
