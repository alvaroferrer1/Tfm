-- ============================================================
-- MermaOps: Fase 3 — Kuine supervisor trace completo
-- Migración: 20260519000002_agent_runs_trace
-- ============================================================

-- Añadir columnas de traza a agent_runs (idempotente)
ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS tools_used      JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS tools_count     INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS duration_ms     INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS trigger_source  TEXT DEFAULT 'scheduler',
    ADD COLUMN IF NOT EXISTS error           TEXT;

-- Índice para búsquedas por tipo y fecha
CREATE INDEX IF NOT EXISTS agent_runs_type_date
    ON agent_runs(agent_type, started_at DESC);

-- supervisor_decisions: decisiones explícitas de Kuine sobre productos
-- Cada vez que Kuine decide rebajar/donar/retirar, queda trazado aquí.
CREATE TABLE IF NOT EXISTS supervisor_decisions (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id        TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    agent_run_id    TEXT REFERENCES agent_runs(id) ON DELETE SET NULL,
    product_id      TEXT REFERENCES products(id) ON DELETE SET NULL,
    batch_id        TEXT REFERENCES batches(id) ON DELETE SET NULL,
    decision_type   TEXT NOT NULL CHECK (decision_type IN ('rebajar','donar','retirar','revisar','reponer','mantener')),
    score           INT DEFAULT 0,
    reason          TEXT,
    validated       BOOLEAN DEFAULT false,
    validated_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS supervisor_decisions_store
    ON supervisor_decisions(store_id, created_at DESC);

CREATE INDEX IF NOT EXISTS supervisor_decisions_run
    ON supervisor_decisions(agent_run_id) WHERE agent_run_id IS NOT NULL;
