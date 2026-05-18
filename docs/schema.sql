-- MermaOps — Supabase Schema
-- Ejecutar en el SQL Editor de Supabase

-- Habilitar extensión para embeddings RAG
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Stores ─────────────────────────────────────────────────────────────────
CREATE TABLE stores (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name        TEXT NOT NULL,
    telegram_chat_id TEXT,
    config      JSONB DEFAULT '{}'
);

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id          UUID PRIMARY KEY REFERENCES auth.users(id),
    email       TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'staff')),
    store_id    TEXT REFERENCES stores(id),
    telegram_user_id TEXT UNIQUE
);

-- ── Products ───────────────────────────────────────────────────────────────
CREATE TABLE products (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    name        TEXT NOT NULL,
    sku         TEXT,
    barcode     TEXT,
    category    TEXT,
    expiry_type TEXT DEFAULT 'caducidad' CHECK (expiry_type IN ('caducidad', 'consumo_preferente')),
    price       NUMERIC(10,2) NOT NULL DEFAULT 0,
    cost        NUMERIC(10,2) NOT NULL DEFAULT 0,
    pasillo     TEXT,
    estanteria  TEXT,
    nivel       TEXT,
    alert_days_1 INT DEFAULT 7,
    alert_days_2 INT DEFAULT 3,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX products_store_barcode ON products(store_id, barcode) WHERE barcode IS NOT NULL;

-- ── Batches ────────────────────────────────────────────────────────────────
CREATE TABLE batches (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    product_id  TEXT NOT NULL REFERENCES products(id),
    lot_number  TEXT,
    expiry_date DATE NOT NULL,
    quantity    INT NOT NULL DEFAULT 0,
    status      TEXT DEFAULT 'active' CHECK (status IN ('active', 'sold', 'discarded', 'donated')),
    photo_url   TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX batches_expiry ON batches(store_id, expiry_date) WHERE status = 'active';

-- ── Warehouse stock ────────────────────────────────────────────────────────
CREATE TABLE warehouse_stock (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    product_id  TEXT NOT NULL REFERENCES products(id),
    quantity    INT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(store_id, product_id)
);

-- ── Actions ────────────────────────────────────────────────────────────────
CREATE TABLE actions (
    id                   TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id             TEXT NOT NULL REFERENCES stores(id),
    batch_id             TEXT REFERENCES batches(id),
    action_type          TEXT NOT NULL CHECK (action_type IN ('rebajar','retirar','donar','mover','revisar','reponer')),
    priority_score       INT DEFAULT 0,
    price_adjustment_pct INT DEFAULT 0,
    new_price            NUMERIC(10,2),
    status               TEXT DEFAULT 'pending' CHECK (status IN ('pending','in_progress','completed','cancelled')),
    completed_by         TEXT,
    completed_at         TIMESTAMPTZ,
    photo_url            TEXT,
    notes                TEXT,
    donation_entity      TEXT,
    donation_quantity    INT,
    created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX actions_pending ON actions(store_id, status, priority_score DESC) WHERE status = 'pending';

-- ── Merma log ──────────────────────────────────────────────────────────────
CREATE TABLE merma_log (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id        TEXT NOT NULL REFERENCES stores(id),
    batch_id        TEXT REFERENCES batches(id),
    quantity_lost   INT NOT NULL,
    value_lost      NUMERIC(10,2) NOT NULL,
    reason          TEXT,
    date            DATE DEFAULT CURRENT_DATE
);

-- ── Daily briefs ───────────────────────────────────────────────────────────
CREATE TABLE daily_briefs (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id        TEXT NOT NULL REFERENCES stores(id),
    date            DATE NOT NULL,
    summary         TEXT,
    value_at_risk   NUMERIC(10,2) DEFAULT 0,
    actions_count   INT DEFAULT 0,
    UNIQUE(store_id, date)
);

-- ── Weekly reports ─────────────────────────────────────────────────────────
CREATE TABLE weekly_reports (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    week_start  DATE NOT NULL,
    content     TEXT,
    stats       JSONB DEFAULT '{}'
);

-- ── Agent runs ─────────────────────────────────────────────────────────────
CREATE TABLE agent_runs (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    agent_type  TEXT NOT NULL,
    started_at  TIMESTAMPTZ DEFAULT now(),
    tokens_used INT DEFAULT 0,
    result      TEXT
);

-- ── Agent memory (episódica) ───────────────────────────────────────────────
CREATE TABLE agent_memory (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id        TEXT NOT NULL REFERENCES stores(id),
    pattern_key     TEXT NOT NULL,
    pattern_value   TEXT NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(store_id, pattern_key)
);

-- ── Knowledge base (RAG) ───────────────────────────────────────────────────
CREATE TABLE knowledge_base (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT,
    content     TEXT NOT NULL,
    embedding   VECTOR(1536),
    category    TEXT,
    source      TEXT
);

CREATE INDEX knowledge_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops);

-- ── Suppliers ──────────────────────────────────────────────────────────────
CREATE TABLE suppliers (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    name        TEXT NOT NULL,
    contact     TEXT
);

-- ── Supplier merma ─────────────────────────────────────────────────────────
CREATE TABLE supplier_merma (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    supplier_id TEXT REFERENCES suppliers(id),
    product_id  TEXT REFERENCES products(id),
    merma_pct   NUMERIC(5,2),
    period      TEXT
);

-- ── Donations log ─────────────────────────────────────────────────────────
CREATE TABLE donations (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id        TEXT NOT NULL REFERENCES stores(id),
    batch_id        TEXT REFERENCES batches(id),
    action_id       TEXT REFERENCES actions(id),
    entity          TEXT NOT NULL,
    quantity        INT NOT NULL,
    product_name    TEXT,
    value_donated   NUMERIC(10,2) DEFAULT 0,
    donated_by      TEXT,
    donated_at      TIMESTAMPTZ DEFAULT now(),
    notes           TEXT
);

CREATE INDEX donations_store ON donations(store_id, donated_at DESC);

-- ── Store comparison (Feature #15) ────────────────────────────────────────
CREATE TABLE store_comparison (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL,
    store_name  TEXT NOT NULL,
    period      TEXT NOT NULL,
    merma_value NUMERIC(10,2) DEFAULT 0,
    merma_rate_pct NUMERIC(5,2) DEFAULT 0,
    actions_resolved INT DEFAULT 0,
    donations_value NUMERIC(10,2) DEFAULT 0,
    ranking     INT DEFAULT 0,
    UNIQUE (store_id, period)
);
CREATE INDEX store_comparison_period ON store_comparison(period, merma_rate_pct);

-- ── Monthly reports (Feature #24) ─────────────────────────────────────────
CREATE TABLE monthly_reports (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id    TEXT NOT NULL REFERENCES stores(id),
    month       DATE NOT NULL,
    content     TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (store_id, month)
);

-- ── Migration: add columns to existing actions table (run if upgrading) ────
-- ALTER TABLE actions ADD COLUMN IF NOT EXISTS price_adjustment_pct INT DEFAULT 0;
-- ALTER TABLE actions ADD COLUMN IF NOT EXISTS new_price NUMERIC(10,2);
-- ALTER TABLE actions ADD COLUMN IF NOT EXISTS donation_entity TEXT;
-- ALTER TABLE actions ADD COLUMN IF NOT EXISTS donation_quantity INT;

-- ── Trigger: crear public.users al registrar un nuevo usuario de Auth ────────
-- Sin este trigger, Chuwi nunca reconoce a nadie y el vinculo de Telegram falla.
-- El rol y store_id se pueden pasar como raw_user_meta_data al invitar al usuario.
CREATE OR REPLACE FUNCTION handle_new_auth_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, role, store_id)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'role', 'staff'),
        COALESCE(NEW.raw_user_meta_data->>'store_id', 'demo-store-001')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_auth_user();

-- ── Supabase Storage bucket para evidencias (crear en el dashboard) ──────────
-- Crear manualmente en Supabase > Storage > New bucket:
--   Nombre: evidence
--   Público: true (para que la app pueda mostrar las fotos)
-- O via SQL (requiere extensión storage habilitada):
-- INSERT INTO storage.buckets (id, name, public) VALUES ('evidence', 'evidence', true)
--   ON CONFLICT DO NOTHING;

-- ── Demo store seed ────────────────────────────────────────────────────────
INSERT INTO stores (id, name, telegram_chat_id) VALUES
('demo-store-001', 'Super Martinez', NULL);
