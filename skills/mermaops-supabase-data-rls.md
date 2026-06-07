# skill: mermaops-supabase-data-rls
Objetivo: Base de datos, schema, seed, RLS y consistencia con backend.
Cuándo: Al tocar schema, seed, migrations, o cuando BD devuelve 0 resultados.

Estado actual:
- Schema: docs/schema.sql (existe)
- Migrations: supabase/migrations/ (1 migración de tablas agentes, 1 de RLS)
- RLS migration: creada pero NO aplicada a Supabase aún
- STORE_ID demo: demo-store-001

Tablas críticas para demo:
stores, users, products, batches, warehouse_stock, actions, merma_log,
daily_briefs, weekly_reports, donations, agent_runs, agent_memory,
agent_conversations, agent_messages, agent_sessions, telegram_users,
supplier_merma, store_comparison.

Checklist antes de demo:
- [ ] SUPABASE_URL y SUPABASE_KEY en .env
- [ ] SELECT * FROM stores WHERE id='demo-store-001' → devuelve 1 fila
- [ ] SELECT count(*) FROM products → > 0
- [ ] SELECT count(*) FROM batches WHERE status='active' → > 0
- [ ] SELECT count(*) FROM actions WHERE status='pending' → > 0
- [ ] python scripts/advance_demo.py existe y funciona
- [ ] make seed → carga datos demo sin error

RLS (PENDIENTE DE APLICAR):
Ejecutar en Supabase SQL Editor:
supabase/migrations/20260526000001_rls_agent_tables.sql
AVISO: Esto puede romper queries del backend si usa anon key en lugar de service_role.
Verificar que backend usa SUPABASE_SERVICE_KEY (service_role) antes de aplicar RLS.

Si BD devuelve 0 resultados:
1. Verificar STORE_ID=demo-store-001 en .env
2. Verificar que seed se ejecutó
3. Verificar que RLS no bloquea (usar service_role key en backend)
