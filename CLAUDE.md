# CLAUDE.md — Memoria del proyecto MermaOps

> Este archivo es la fuente de verdad para futuras sesiones de Claude Code.
> Actualizar cuando cambie la arquitectura, el estado de los agentes o las fases.

---

## Identidad del sistema

**MermaOps** — sistema multi-agente de IA para reducción de merma en supermercados españoles.

- Backend: FastAPI + Python 3.14, puerto **8001** (8000 bloqueado por Manager.exe en el PC del usuario)
- Base de datos: Supabase (PostgreSQL + Auth + Realtime)
- Interfaz principal: Telegram AI Agent @ChuwiMermaOpsBot
- App móvil: Flutter (Android/iOS)
- Tests: 323/323 en < 1s (sin conexión real a Supabase)

---

## Agentes — estado real (no el README)

| Agente | Archivo | Modelo | Estado |
|--------|---------|--------|--------|
| **Kuine** (orquestador) | `backend/agents/supervisor.py` | Opus 4.7 | activo — loop real, 25 tools, hasta 20 iter |
| **Chuwi** (Telegram) | `backend/core/chuwi.py` | Sonnet 4.6 | activo — agente real, streaming, 6 iter |
| **Evaluador** | `backend/agents/evaluator.py` | Sonnet 4.6 | activo — score 0-100, extended thinking >=65 |
| **Validador** | `backend/agents/validator.py` | Sonnet 4.6 | activo — 23 ataques adversariales, 100% |
| **Consenso** | `backend/agents/consensus.py` | Sonnet 4.6 | activo — 3 instancias paralelas score >=90 |
| **Predictor** | `backend/agents/predictor.py` | Haiku 4.5 | activo — Open-Meteo + historial |
| **Visión** | `backend/agents/vision.py` | claude-3-5-sonnet | activo — análisis de fotos |
| **Precio** | `backend/agents/price.py` | Haiku 4.5 | activo — cálculo descuentos |
| **Stock** | `backend/agents/stock.py` | Haiku 4.5 | activo — decisiones reposición |
| **Notificador** | `backend/agents/notifier.py` | Sonnet 4.6 | activo — alertas proactivas |
| **Reportero** | `backend/agents/reporter.py` | Sonnet 4.6 | activo — briefs y resúmenes |

---

## Arquitectura de datos — tablas Supabase

### Tablas operativas (existían antes de Fase 1)

- `stores`, `users`, `products`, `batches`, `warehouse_stock`
- `actions` — acciones pendientes/completadas
- `merma_log` — se escribe al llamar `complete_action()` (fix Fase 1)
- `daily_briefs`, `weekly_reports`, `monthly_reports`
- `agent_runs`, `agent_memory` (key-value episódica)
- `knowledge_base` (RAG, VECTOR 1536)
- `suppliers`, `supplier_merma`, `donations`, `store_comparison`

### Tablas nuevas (Fase 1 — APLICADAS en Supabase via CLI)

- `agent_conversations` — sesiones de chat Chuwi-usuario
- `agent_messages` — cada mensaje con `tools_used` (JSONB), `intent_tag`, `agent_source`
- `agent_sessions` — tracking de sesiones con contadores de tools y llamadas a Kuine
- `telegram_users` — registro de TODOS los usuarios (vinculados y no vinculados)

Migración: `supabase/migrations/20260519000001_agent_foundations.sql`

---

## Flujo de persistencia de conversaciones (Fase 1+2)

```text
Usuario → Telegram → handle_message()
    ↓
_upsert_telegram_user()              ← registra en telegram_users (vinculado o no)
    ↓
if not user → bloqueo + mensaje      ← NO ejecuta Chuwi si no está vinculado
    ↓
_classify_intent(text)               ← Fase 2: 0 tokens, 10 intents, keyword-based
_build_intent_context(intent)        ← contexto pre-cargado según intención
    ↓
_get_chat_history(chat_key)          ← Supabase agent_memory (fallback JSON)
    ↓
_run_agent_loop() → (response, tools_used)   ← devuelve tupla
    ↓
_persist_chat_history()              ← sigue en agent_memory (historial compacto)
    ↓
_persist_conversation_message()      ← agent_conversations + agent_messages
    ├─ crea/recupera conversation_id (cache en _conv_id_cache)
    ├─ log mensaje usuario (role=user, intent_tag)
    ├─ log respuesta Chuwi (role=assistant, tools_used, intent_tag)
    ├─ si "analyze_product" en tools: log Kuine (role=system)
    └─ fallback silencioso si Supabase no disponible
```

---

## Reglas de trabajo (NO cambiar sin aviso)

1. **NO commits** hasta que el usuario diga explícitamente "sube" o "commit"
2. **NO push a GitHub** hasta "sube a GitHub" explícito
3. Cuando se autorice commit: `mejora: convertir Telegram y agentes en sistema operativo real`
4. **NO credenciales en código** — todo por `.env` con `os.getenv()`
5. **NO desperdiciar tokens Claude API** — solo en pruebas y demo real
6. Puerto backend: **8001** (no 8000)
7. Tests: deben seguir >=307/307 después de cada cambio
8. No inventar capacidades — solo implementar lo que está conectado

---

## Fases de implementación

### Fase 1 — COMPLETADA + APLICADA EN SUPABASE

- Tablas `agent_conversations`, `agent_messages`, `agent_sessions`, `telegram_users` en Supabase
- Migración aplicada vía Supabase CLI
- `complete_action()` escribe en `merma_log` automáticamente
- `_run_agent_loop()` devuelve tupla `(str, list[str])`
- `_persist_conversation_message()` persiste en Supabase con fallback
- Log Chuwi-Kuine en `agent_messages` con `agent_source="kuine"`
- `_upsert_telegram_user()` registra todos los usuarios
- `scripts/check_all.py` + `make check` para diagnóstico
- `docs/runbook.md` con guía completa de arranque
- 323/323 tests

### Fase 2 — COMPLETADA — Chuwi intent classification

- `_classify_intent(text)` — clasificador sin LLM, 0 tokens, 10 intents
- `_build_intent_context(intent, store_id)` — contexto pre-cargado según intent
- `_run_agent_loop()` acepta `intent_tag` e `intent_context`
- `handle_message()` clasifica antes de llamar al loop
- `agent_messages.intent_tag` guardado en cada turno

### Fase 6 — COMPLETADA — Endpoints backend

- `GET /api/v1/agent/conversations`
- `GET /api/v1/agent/conversations/{id}/messages`
- `GET /api/v1/agent/sessions`
- `GET /api/v1/agent/activity`
- `GET /api/v1/agent/status`
- `GET /api/v1/telegram/status`

### Fase 3 — Kuine supervisor trace — COMPLETADA

- `agent_runs` extendida con tools\_used/count/duration\_ms/trigger\_source
- `supervisor_decisions` tabla con cada decisión de Kuine (rebajar/donar/retirar...)
- `run_daily_brief()` mide duración, guarda trace completo, obtiene run\_id
- `create_action` en executor llama `log_supervisor_decision()` automáticamente
- Endpoints: `GET /api/v1/agent/runs`, `GET /api/v1/agent/decisions`

### Fase 4 — Clasificación de agentes — COMPLETADA

- `/api/v1/agent/status` devuelve los 11 agentes con modelo, tipo y descripción real
- `check_all.py` verifica imports y función principal de cada agente

### Fase 5 — Flutter pantalla de actividad — COMPLETADA

- `app/lib/features/agents/agents_screen.dart` — 4 tabs
- Wired en `router.dart` como `/agents` y en `shell_scaffold.dart` como 6º nav item
- API methods en `api_service.dart`: getAgentStatus, getAgentActivity, getAgentConversations, getAgentRuns, getSupervisorDecisions, getTelegramStatus

### Fase 7 — Documentación viva (PENDIENTE)

Solo falta: architecture.md, agents.md, api.md, demo-checklist.md. runbook.md ya existe.

### Fase 8 — Calidad y defensa TFM (PENDIENTE)

---

## Arranque rápido — UN SOLO COMANDO

```bash
# Verifica .env + Supabase + Telegram + arranca backend + imprime guía completa
make start
# o equivalente:
python scripts/start.py

# Solo verificar sin arrancar
make verify

# Diagnóstico completo (con backend ya corriendo)
make check

# Tests
python -m pytest backend/tests/ -q
```

## Sesiones integradas en Chuwi

Chuwi crea/actualiza `agent_sessions` en Supabase en cada turno:

- `_session_cache[user_id]` → `session_id` (en memoria del proceso)
- Al primer mensaje de un usuario: `create_agent_session()`
- En cada turno: `increment_session_stats(tools_called, kuine_calls)`
- Las sesiones son visibles en `/api/v1/agent/sessions` y en la pantalla Agentes de Flutter

## Flutter — pantalla Agentes

- Ruta: `/agents` → `AgentsScreen`
- Tab en bottom nav: icono `psychology` (6º elemento)
- 4 tabs: estado de los 11 agentes, conversaciones Chuwi, runs Kuine, decisiones Kuine
- Accessible desde el nav bar principal

---

## Variables de entorno requeridas (.env)

```bash
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://XXXX.supabase.co
SUPABASE_KEY=sb_secret_...
SUPABASE_SERVICE_KEY=sb_secret_...
TELEGRAM_BOT_TOKEN=123456:ABC...
STORE_ID=demo-store-001
APP_PORT=8001
```

---

## SQL de verificación post-migración (Supabase SQL Editor)

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('agent_conversations','agent_messages','agent_sessions','telegram_users')
ORDER BY table_name;
-- Debe devolver 4 filas
```
