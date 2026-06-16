-- Tabla proyectos (Fase 2): seguimiento de proyectos de Nico. Tools proy_*.
-- Nota: updated_at se setea desde el código (no por trigger), a diferencia de
-- perfil/inferencias/compromisos.
CREATE TABLE IF NOT EXISTS proyectos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre       TEXT NOT NULL,
    descripcion  TEXT DEFAULT '',
    estado       TEXT DEFAULT 'activo'
                     CHECK (estado IN ('activo', 'pausado', 'completado')),
    progreso     INT DEFAULT 0 CHECK (progreso BETWEEN 0 AND 100),
    fecha_inicio DATE DEFAULT CURRENT_DATE,
    fecha_limite DATE,
    notas        TEXT DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE proyectos ENABLE ROW LEVEL SECURITY;
