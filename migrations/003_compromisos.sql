-- Tabla compromisos: lo que Nico dijo que iba a hacer.
CREATE TABLE IF NOT EXISTS compromisos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    descripcion  TEXT NOT NULL,
    estado       TEXT NOT NULL DEFAULT 'abierto'
                     CHECK (estado IN ('abierto', 'cumplido', 'descartado')),
    fecha_limite TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER compromisos_updated_at
    BEFORE UPDATE ON compromisos
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();
