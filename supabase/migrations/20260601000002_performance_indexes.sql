-- ============================================================
-- MermaOps: Índices de rendimiento para queries frecuentes
-- Migración: 20260601000002_performance_indexes
-- Ejecutar en: Supabase > SQL Editor
-- ============================================================

-- get_batches_expiring_soon — llamada en dashboard, proactive monitor (cada 30min), brief
-- Sin este índice: full scan de batches en cada petición
CREATE INDEX IF NOT EXISTS idx_batches_store_status_expiry
    ON batches(store_id, status, expiry_date);

-- get_pending_actions — llamada en cada mensaje de Chuwi y en el brief
CREATE INDEX IF NOT EXISTS idx_actions_store_status_priority
    ON actions(store_id, status, priority_score DESC);

-- merma_log — historial de merma por período
CREATE INDEX IF NOT EXISTS idx_merma_log_store_date
    ON merma_log(store_id, date DESC);

-- donations — stats de donaciones por período
CREATE INDEX IF NOT EXISTS idx_donations_store_donated_at
    ON donations(store_id, donated_at DESC);
