-- RLS para tablas de agentes MermaOps
-- Aplicar en Supabase SQL Editor o via supabase db push

-- ── Habilitar RLS en todas las tablas de agentes ──────────────────────────────

ALTER TABLE IF EXISTS agent_conversations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS agent_messages       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS agent_sessions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS telegram_users       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS supervisor_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS agent_runs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS agent_memory         ENABLE ROW LEVEL SECURITY;

-- ── agent_conversations ───────────────────────────────────────────────────────
-- Solo el service role (backend) puede leer/escribir.
-- Los usuarios autenticados ven solo sus propias conversaciones.

DROP POLICY IF EXISTS "agent_conversations_service" ON agent_conversations;
CREATE POLICY "agent_conversations_service"
  ON agent_conversations
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- agent_conversations_own: el backend usa service_role exclusivamente
-- No exponemos conversaciones directamente a usuarios autenticados via Supabase REST
DROP POLICY IF EXISTS "agent_conversations_own" ON agent_conversations;

-- ── agent_messages ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "agent_messages_service" ON agent_messages;
CREATE POLICY "agent_messages_service"
  ON agent_messages
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "agent_messages_own" ON agent_messages;
-- agent_messages: solo service_role (backend) accede directamente

-- ── agent_sessions ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "agent_sessions_service" ON agent_sessions;
CREATE POLICY "agent_sessions_service"
  ON agent_sessions
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "agent_sessions_own" ON agent_sessions;
-- agent_sessions: solo service_role (backend) accede directamente

-- ── telegram_users ────────────────────────────────────────────────────────────
-- Solo service_role puede leer/escribir. No exponemos IDs de Telegram a usuarios.

DROP POLICY IF EXISTS "telegram_users_service" ON telegram_users;
CREATE POLICY "telegram_users_service"
  ON telegram_users
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Los usuarios autenticados pueden ver su propio registro (por supabase_user_id)
DROP POLICY IF EXISTS "telegram_users_own" ON telegram_users;
-- telegram_users: solo service_role — no exponemos IDs de Telegram via REST

-- ── supervisor_decisions ──────────────────────────────────────────────────────
-- Solo service_role escribe. Encargados autenticados pueden leer.

DROP POLICY IF EXISTS "supervisor_decisions_service" ON supervisor_decisions;
CREATE POLICY "supervisor_decisions_service"
  ON supervisor_decisions
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "supervisor_decisions_read" ON supervisor_decisions;
CREATE POLICY "supervisor_decisions_read"
  ON supervisor_decisions
  FOR SELECT
  TO authenticated
  USING (store_id = current_setting('app.store_id', true));

-- ── agent_runs ────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "agent_runs_service" ON agent_runs;
CREATE POLICY "agent_runs_service"
  ON agent_runs
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "agent_runs_read" ON agent_runs;
CREATE POLICY "agent_runs_read"
  ON agent_runs
  FOR SELECT
  TO authenticated
  USING (store_id = current_setting('app.store_id', true));

-- ── agent_memory ──────────────────────────────────────────────────────────────
-- Memoria episódica: solo service_role.

DROP POLICY IF EXISTS "agent_memory_service" ON agent_memory;
CREATE POLICY "agent_memory_service"
  ON agent_memory
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- ── Tablas operativas — RLS básico ────────────────────────────────────────────
-- Asegurar que actions, batches, etc. también tienen RLS por store_id.

ALTER TABLE IF EXISTS actions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS batches  ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS merma_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS donations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "actions_service" ON actions;
CREATE POLICY "actions_service" ON actions FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "actions_authenticated" ON actions;
CREATE POLICY "actions_authenticated" ON actions FOR SELECT TO authenticated USING (store_id = current_setting('app.store_id', true));

DROP POLICY IF EXISTS "batches_service" ON batches;
CREATE POLICY "batches_service" ON batches FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "batches_authenticated" ON batches;
CREATE POLICY "batches_authenticated" ON batches FOR SELECT TO authenticated USING (store_id = current_setting('app.store_id', true));

DROP POLICY IF EXISTS "merma_log_service" ON merma_log;
CREATE POLICY "merma_log_service" ON merma_log FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "merma_log_authenticated" ON merma_log;
CREATE POLICY "merma_log_authenticated" ON merma_log FOR SELECT TO authenticated USING (store_id = current_setting('app.store_id', true));

DROP POLICY IF EXISTS "donations_service" ON donations;
CREATE POLICY "donations_service" ON donations FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "donations_authenticated" ON donations;
CREATE POLICY "donations_authenticated" ON donations FOR SELECT TO authenticated USING (store_id = current_setting('app.store_id', true));
