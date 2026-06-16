-- Privacidad (Plan v5 §7): bloquear las tablas a todo lo que no sea el backend.
-- Donna se conecta con la SERVICE_ROLE key (ignora RLS). Con RLS activado y sin
-- políticas, las claves públicas (anon/publishable) quedan sin acceso. La memoria
-- personal de Donna solo la lee/escribe Donna.
ALTER TABLE perfil      ENABLE ROW LEVEL SECURITY;
ALTER TABLE inferencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE compromisos ENABLE ROW LEVEL SECURITY;
ALTER TABLE memoria     ENABLE ROW LEVEL SECURITY;
