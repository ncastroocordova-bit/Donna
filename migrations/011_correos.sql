-- v7 + correo: registro de correos ya procesados, para no re-bufferizar el mismo
-- gasto dos veces (anti-duplicado a nivel de mensaje, además del ID_Único del monto).
-- `tipo` distingue 'gasto' (fue al buffer financiero) de otros usos futuros.

CREATE TABLE IF NOT EXISTS correos_vistos (
    proveedor  TEXT NOT NULL,            -- gmail | outlook
    msg_id     TEXT NOT NULL,            -- id del mensaje en el proveedor
    tipo       TEXT NOT NULL DEFAULT 'gasto',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (proveedor, msg_id)
);

ALTER TABLE correos_vistos ENABLE ROW LEVEL SECURITY;
