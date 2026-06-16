-- Tabla memoria: notas episódicas con contextual retrieval (Plan v5 §4.2).
-- `texto`   = la nota verbatim.
-- `contexto`= etiqueta (fecha/dominio/situación) que se antepone al embeber.
-- `embedding` = vector de la versión contextualizada (Voyage, 1024 dims).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memoria (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    texto      TEXT NOT NULL,
    contexto   TEXT NOT NULL DEFAULT '',
    dominio    TEXT DEFAULT '',
    embedding  VECTOR(1024),
    off_record BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW: no necesita entrenamiento, rinde bien con datos que crecen de a poco.
CREATE INDEX IF NOT EXISTS memoria_embedding_idx
    ON memoria USING hnsw (embedding vector_cosine_ops);

-- Búsqueda semántica por coseno. Devuelve texto + contexto + dominio.
CREATE OR REPLACE FUNCTION buscar_memoria(
    query_embedding VECTOR(1024),
    match_count     INT DEFAULT 5
)
RETURNS TABLE (
    id         UUID,
    texto      TEXT,
    contexto   TEXT,
    dominio    TEXT,
    created_at TIMESTAMPTZ,
    similitud  FLOAT
)
LANGUAGE SQL STABLE AS $$
    SELECT
        id, texto, contexto, dominio, created_at,
        1 - (embedding <=> query_embedding) AS similitud
    FROM memoria
    WHERE off_record = FALSE AND embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
