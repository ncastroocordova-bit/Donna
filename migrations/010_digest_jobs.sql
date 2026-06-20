-- v7: dos piezas nuevas del núcleo.
--
-- 1) buffer_transacciones: el digest financiero nocturno NO escribe a Sheets durante
--    el día. Cada gasto/ingreso (de un correo o una foto de boleta) se procesa en
--    contexto aislado y aterriza acá como "pendiente". A las 22:00 Donna arma el
--    digest desde este buffer; al confirmar, escribe a Finanzas_vigente!Transacciones
--    y marca la fila como 'confirmada'. `id_unico` evita duplicados (anti-doble-registro).
--
-- 2) jobs_log: resiliencia del scheduler (Plan_Construccion_v7 Paso 1.7). Al arrancar,
--    Donna chequea acá si el brief/cierre de hoy ya salió; si no, lo manda. Sin punto
--    único de falla silencioso.

CREATE TABLE IF NOT EXISTS buffer_transacciones (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha        DATE NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Santiago')::date,
    tipo         TEXT NOT NULL DEFAULT 'Gasto',     -- Gasto | Ingreso
    categoria    TEXT DEFAULT '',                    -- mejor apuesta de Donna
    subcategoria TEXT DEFAULT '',
    comercio     TEXT DEFAULT '',
    monto        NUMERIC DEFAULT 0,
    medio        TEXT DEFAULT '',                    -- Banco de Chile, Mach, MP, efectivo…
    fuente       TEXT DEFAULT '',                    -- correo | foto | manual
    id_unico     TEXT UNIQUE,                        -- anti-duplicado
    dudosa       BOOLEAN NOT NULL DEFAULT FALSE,     -- ¿Donna marca esta línea para confirmar?
    motivo_duda  TEXT DEFAULT '',                    -- ej: "¿Tecnología o Suscripción?"
    estado       TEXT NOT NULL DEFAULT 'pendiente'   -- pendiente | confirmada | descartada
                     CHECK (estado IN ('pendiente', 'confirmada', 'descartada')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS buffer_pendientes_idx
    ON buffer_transacciones (fecha) WHERE estado = 'pendiente';

CREATE TABLE IF NOT EXISTS jobs_log (
    job        TEXT NOT NULL,                        -- brief | cierre | proactividad | decay
    fecha      DATE NOT NULL,
    enviado_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job, fecha)
);

ALTER TABLE buffer_transacciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs_log             ENABLE ROW LEVEL SECURITY;
