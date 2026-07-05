-- Autodiagnóstico lean (Ficha_Autodiagnostico_y_Variedad, Parte 1 — versión reducida).
--
-- Donna DETECTA cuando algo se rompe (excepción de una tool, columna de hoja que no calza,
-- escritura que no cuadra al releerla), lo registra deduplicado por `firma`, y avisa a Nico en
-- su voz. NO se auto-arregla: los fixes van por Claude Code con OK de Nico.
--
-- Versión lean: solo detección determinista (sin diagnóstico con Haiku). Por eso NO hay columnas
-- causa_probable / prompt_reparacion todavía — quedan para una versión futura con diagnóstico LLM.
-- `firma` = hash de (tool, tipo, primera línea del error normalizada) → el mismo bug se agrupa.

CREATE TABLE IF NOT EXISTS incidentes (
    id            BIGSERIAL PRIMARY KEY,
    creado        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    firma         TEXT NOT NULL,
    tool          TEXT NOT NULL DEFAULT '-',        -- 'rec_agregar', 'sheet:Recordatorios', '-'
    tipo          TEXT NOT NULL,                     -- tool_excepcion | schema_sheets | verificacion_escritura
    resumen       TEXT NOT NULL,                     -- 1 frase para humanos
    error_texto   TEXT,                              -- excepción/diff, truncado a 2000 chars
    input_json    JSONB,                             -- input de la tool al fallar (sin off-record)
    frecuencia    INT NOT NULL DEFAULT 1,            -- repeticiones de la misma firma
    ultimo_visto  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    estado        TEXT NOT NULL DEFAULT 'abierto',   -- abierto | cerrado
    cerrado_en    TIMESTAMPTZ
);

-- Una firma abierta a la vez → los repetidos suben `frecuencia`, no crean filas nuevas.
CREATE UNIQUE INDEX IF NOT EXISTS incidentes_firma_abierto ON incidentes (firma) WHERE estado = 'abierto';

ALTER TABLE incidentes ENABLE ROW LEVEL SECURITY;
