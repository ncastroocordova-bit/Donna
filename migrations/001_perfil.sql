-- Tabla perfil: hechos estables sobre Nico (+ estado de sistema con categoria '_sistema').
CREATE TABLE IF NOT EXISTS perfil (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clave      TEXT NOT NULL UNIQUE,
    valor      TEXT NOT NULL,
    categoria  TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Función reutilizada por los triggers de updated_at de las demás tablas.
CREATE OR REPLACE FUNCTION actualizar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER perfil_updated_at
    BEFORE UPDATE ON perfil
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();
