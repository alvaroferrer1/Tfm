-- Fix RLS policies that used current_setting('app.store_id', true)
-- That setting is never set by the backend or Flutter, so store_id = NULL
-- was always false and authenticated users saw zero rows.
--
-- New approach: join the users table via auth.uid() to resolve the user's
-- store_id server-side. The users table must be readable by authenticated
-- users (own row only) for the subquery to work.

-- ── users table: let each user read their own row ─────────────────────────────

ALTER TABLE IF EXISTS users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_service" ON users;
CREATE POLICY "users_service"
  ON users FOR ALL TO service_role
  USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "users_own" ON users;
CREATE POLICY "users_own"
  ON users FOR SELECT TO authenticated
  USING (id = auth.uid());

-- ── Helper: resolved store_id for the current authenticated user ──────────────
-- Used in all the policies below as a subquery so it is evaluated once per row.

-- ── supervisor_decisions ──────────────────────────────────────────────────────

DROP POLICY IF EXISTS "supervisor_decisions_read" ON supervisor_decisions;
CREATE POLICY "supervisor_decisions_read"
  ON supervisor_decisions FOR SELECT TO authenticated
  USING (
    store_id IN (
      SELECT store_id FROM users WHERE id = auth.uid() LIMIT 1
    )
  );

-- ── agent_runs ────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "agent_runs_read" ON agent_runs;
CREATE POLICY "agent_runs_read"
  ON agent_runs FOR SELECT TO authenticated
  USING (
    store_id IN (
      SELECT store_id FROM users WHERE id = auth.uid() LIMIT 1
    )
  );

-- ── actions ───────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "actions_authenticated" ON actions;
CREATE POLICY "actions_authenticated"
  ON actions FOR SELECT TO authenticated
  USING (
    store_id IN (
      SELECT store_id FROM users WHERE id = auth.uid() LIMIT 1
    )
  );

-- ── batches ───────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "batches_authenticated" ON batches;
CREATE POLICY "batches_authenticated"
  ON batches FOR SELECT TO authenticated
  USING (
    store_id IN (
      SELECT store_id FROM users WHERE id = auth.uid() LIMIT 1
    )
  );

-- ── merma_log ─────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "merma_log_authenticated" ON merma_log;
CREATE POLICY "merma_log_authenticated"
  ON merma_log FOR SELECT TO authenticated
  USING (
    store_id IN (
      SELECT store_id FROM users WHERE id = auth.uid() LIMIT 1
    )
  );

-- ── donations ─────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "donations_authenticated" ON donations;
CREATE POLICY "donations_authenticated"
  ON donations FOR SELECT TO authenticated
  USING (
    store_id IN (
      SELECT store_id FROM users WHERE id = auth.uid() LIMIT 1
    )
  );
