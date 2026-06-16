-- Tabla inferencias: lo que Donna dedujo, con estado (inferencia validada).
CREATE TABLE IF NOT EXISTS inferencias (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contenido  TEXT NOT NULL,
    estado     TEXT NOT NULL DEFAULT 'pendiente'
                   CHECK (estado IN ('pendiente', 'confirmada', 'corregida', 'descartada')),
    correccion TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER inferencias_updated_at
    BEFORE UPDATE ON inferencias
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();
