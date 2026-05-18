-- ============================================================
-- MermaOps: Fase 1 — Agent Foundations
-- Migración: 20260519000001_agent_foundations
-- Ejecutar en: Supabase > SQL Editor
-- ============================================================

-- ── agent_conversations ──────────────────────────────────────
-- Una fila por sesión de chat Chuwi↔usuario.
-- Agrupa los mensajes de una misma conversación.
CREATE TABLE IF NOT EXISTS agent_conversations (
    id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id            TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    telegram_user_id    TEXT,
    started_at          TIMESTAMPTZ DEFAULT now(),
    last_message_at     TIMESTAMPTZ DEFAULT now(),
    message_count       INT DEFAULT 0,
    total_tokens        INT DEFAULT 0,
    is_active           BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS agent_conversations_store
    ON agent_conversations(store_id, last_message_at DESC);

CREATE INDEX IF NOT EXISTS agent_conversations_user
    ON agent_conversations(telegram_user_id, last_message_at DESC);

-- ── agent_messages ───────────────────────────────────────────
-- Cada turno de la conversación con metadatos de agente.
-- tools_used: array de nombres de tools ejecutadas en ese turno.
-- intent_tag: intención clasificada antes del loop agéntico.
-- agent_source: "chuwi" | "kuine" | "telegram" | "scheduler"
CREATE TABLE IF NOT EXISTS agent_messages (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    conversation_id TEXT NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
    store_id        TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    intent_tag      TEXT,
    tools_used      JSONB DEFAULT '[]'::jsonb,
    tokens_in       INT DEFAULT 0,
    tokens_out      INT DEFAULT 0,
    agent_source    TEXT DEFAULT 'chuwi',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_messages_conv
    ON agent_messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS agent_messages_store
    ON agent_messages(store_id, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_messages_intent
    ON agent_messages(intent_tag) WHERE intent_tag IS NOT NULL;

-- ── agent_sessions ───────────────────────────────────────────
-- Tracking de sesiones para análisis de uso del agente.
-- Una sesión = arranque de Chuwi hasta inactividad o cierre.
CREATE TABLE IF NOT EXISTS agent_sessions (
    id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    store_id            TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    telegram_user_id    TEXT,
    session_start       TIMESTAMPTZ DEFAULT now(),
    session_end         TIMESTAMPTZ,
    messages_count      INT DEFAULT 0,
    tools_called        INT DEFAULT 0,
    kuine_calls         INT DEFAULT 0,
    resolved            BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS agent_sessions_store
    ON agent_sessions(store_id, session_start DESC);

-- ── telegram_users ───────────────────────────────────────────
-- Tracking de usuarios de Telegram (vinculados y no vinculados).
-- Permite auditar quién intenta usar el agente y el estado de vinculación.
-- user_id es NULL hasta que el usuario vincula su cuenta desde la app.
CREATE TABLE IF NOT EXISTS telegram_users (
    id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    telegram_user_id    TEXT UNIQUE NOT NULL,
    telegram_username   TEXT,
    telegram_chat_id    TEXT,
    user_id             UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    store_id            TEXT REFERENCES stores(id) ON DELETE SET NULL,
    status              TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'linked', 'blocked')),
    linked_at           TIMESTAMPTZ,
    last_seen_at        TIMESTAMPTZ DEFAULT now(),
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS telegram_users_status
    ON telegram_users(status, last_seen_at DESC);

-- ── RLS ──────────────────────────────────────────────────────
-- No se activa RLS en estas tablas en este momento porque:
-- 1. Solo el backend accede con service role key (bypassa RLS)
-- 2. La app Flutter usa el API backend, no Supabase directamente
-- 3. Los datos de conversación no se exponen al cliente anon
-- Si en el futuro la app lee directamente, activar RLS con:
--   ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
--   CREATE POLICY "store_access" ON agent_conversations
--     USING (store_id = (SELECT store_id FROM users WHERE id = auth.uid()));

-- ── Verificación ─────────────────────────────────────────────
-- Ejecutar tras aplicar la migración:
-- SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public'
--     AND table_name IN ('agent_conversations','agent_messages','agent_sessions','telegram_users')
--   ORDER BY table_name;
-- Debe devolver 4 filas.
