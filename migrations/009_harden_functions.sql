-- Hardening (#5): fijar search_path en las funciones para cerrar el advisor
-- `function_search_path_mutable`. Sin search_path fijo, un search_path mutable
-- de rol podría hacer que la función resuelva objetos de un esquema inesperado.
--
-- actualizar_updated_at: solo usa NOW() (pg_catalog) → search_path vacío basta.
CREATE OR REPLACE FUNCTION actualizar_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- buscar_memoria: usa la tabla `memoria` y el operador `<=>` (extensión vector),
-- ambos en `public` → search_path = public.
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
LANGUAGE SQL STABLE
SET search_path = public
AS $$
    SELECT
        id, texto, contexto, dominio, created_at,
        1 - (embedding <=> query_embedding) AS similitud
    FROM memoria
    WHERE off_record = FALSE AND embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Decisión deliberada: la extensión `vector` se DEJA en el schema `public`.
-- El advisor `extension_in_public` sugiere moverla, pero:
--   * la base es de un solo usuario y solo la toca la service_role (sin acceso anon);
--   * mover `vector` obliga a que toda DDL futura con el tipo `vector` y el operador
--     `<=>` lleve `extensions` en el search_path → frágil y propenso a romper la
--     búsqueda semántica por poca ganancia real;
--   * es el default de Supabase para pgvector.
-- Si algún día se expone una clave pública (anon), reconsiderar:
--   ALTER EXTENSION vector SET SCHEMA extensions;  -- (y ajustar search_path de buscar_memoria)
