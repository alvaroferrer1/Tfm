-- ============================================================
-- MermaOps: Columnas de donación en tabla actions
-- Migración: 20260601000001_actions_donation_columns
-- Necesaria para: registro de donaciones desde Telegram y app Flutter
-- Backend usa: database.py:167 (donation_quantity), actions_screen.dart:607-608
-- ============================================================

ALTER TABLE actions
    ADD COLUMN IF NOT EXISTS donation_entity   TEXT,
    ADD COLUMN IF NOT EXISTS donation_quantity INTEGER;

COMMENT ON COLUMN actions.donation_entity   IS 'Entidad receptora de la donación (Cáritas, Banco de Alimentos, etc.)';
COMMENT ON COLUMN actions.donation_quantity IS 'Unidades donadas (puede diferir de la cantidad del lote si es donación parcial)';
