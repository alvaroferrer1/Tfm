# CLAUDE.md — Memoria del proyecto MermaOps

> Fuente de verdad para futuras sesiones. Actualizar cuando cambie la arquitectura.
> Última actualización: junio 2026 — sistema completo, 774/774 tests, demo-ready.

---

## Identidad

**MermaOps** — sistema multi-agente de IA para reducción de merma en supermercados españoles.

- Backend: FastAPI + Python 3.14, puerto **8001** (8000 bloqueado por Manager.exe)
- Base de datos: Supabase (PostgreSQL + Auth + Realtime)
- Telegram: @ChuwiMermaOpsBot — agente real con 30+ comandos
- App móvil: Flutter (Android/iOS) — 8 pantallas, Riverpod, Supabase Realtime
- Tests: **774/774** en < 3s (sin conexión real a Supabase)

---

## Reglas de trabajo — NO cambiar sin aviso

1. **NO commits** hasta "sube" o "commit" explícito del usuario
2. **NO push** hasta "sube a GitHub" explícito
3. **NO credenciales en código** — todo por `.env`
4. **NO desperdiciar tokens Claude API** — solo en pruebas y demo real
5. Puerto backend: **8001** (no 8000)
6. Tests: siempre ≥774/774 tras cualquier cambio
7. No inventar capacidades — solo lo que está conectado y funciona

---

## Arranque rápido

```bash
make start          # verifica .env + Supabase + Telegram + arranca en puerto 8001
make verify         # solo verificar sin arrancar
make check          # diagnóstico completo (con backend corriendo)
python -m pytest backend/tests/ -q   # 774/774 tests
```

---

## Agentes — 12 activos

| Agente | Archivo | Modelo | Estado |
|--------|---------|--------|--------|
| **Kuine** (orquestador) | `backend/agents/supervisor.py` | Opus 4.7/Sonnet 4.6 | activo — loop real, 16 tools, hasta 20 iter |
| **Chuwi** (Telegram) | `backend/core/chuwi.py` | Sonnet 4.6 | activo — agente real, streaming |
| **Evaluador** | `backend/agents/evaluator.py` | Sonnet 4.6 | activo — score 0-100, extended thinking ≥65 |
| **ForkMerge** | `backend/agents/fork_merge.py` | Sonnet 4.6×3 + Opus síntesis | activo — valor>50€ o caducado |
| **Validador** | `backend/agents/validator.py` | Sonnet 4.6 | activo — 23 ataques adversariales, 100% |
| **Consenso** | `backend/agents/consensus.py` | Sonnet 4.6 | activo — 3 instancias paralelas |
| **Predictor** | `backend/agents/predictor.py` | Haiku 4.5 | activo — Open-Meteo + historial |
| **Visión** | `backend/agents/vision.py` | Haiku 4.5 | activo — análisis de fotos |
| **Precio** | `backend/agents/price.py` | heurístico | activo — cálculo descuentos |
| **Stock** | `backend/agents/stock.py` | heurístico | activo — FEFO |
| **Notificador** | `backend/agents/notifier.py` | python-telegram-bot | activo — alertas proactivas horario 8-21h |
| **Reportero** | `backend/agents/reporter.py` | Sonnet 4.6 | activo — briefs y resúmenes |

---

## Archivos clave — backend

```
backend/core/chuwi.py              — núcleo Telegram: handlers, callbacks, _ACTION_MAP, _format_brief_html
backend/core/chuwi_commands.py     — comandos /mapa /historial /merma7 /estado /criticos /ayuda + _run_cmd_from_action
backend/core/telegram_formatter.py — plantillas HTML visuales para todos los mensajes de Chuwi
backend/core/chuwi_persistence.py  — estado, historial, caché usuario, Supabase
backend/core/chuwi_intent.py       — clasificador 0-token, 10 intents
backend/core/scheduler.py          — 15 trabajos cron: brief 7:30, check 12:00, cierre 20:00, monitor 30min
backend/core/pdf_generator.py      — 6 tipos de PDF con fpdf2 (brief, semanal, mensual, TFM, pitch, promo)
backend/agents/supervisor.py       — Kuine: run_daily_brief, run_intraday_check, run_closing
backend/agents/notifier.py         — alertas Telegram: en horario 8-21h nunca silencia
backend/api/routes.py              — todos los endpoints REST
```

## Archivos clave — Flutter

```
app/lib/features/dashboard/dashboard_screen.dart  — KPIs streaming, shimmer, donut chart, área chart
app/lib/features/actions/actions_screen.dart       — FEFO, rol-based (staff/manager), swipe, export/import CSV
app/lib/features/map/map_screen.dart               — mapa interactivo pasillos, FEFO tab, QR por pasillo
app/lib/features/scan/scan_screen.dart             — barcode + foto IA (Vision agent)
app/lib/features/agents/agents_screen.dart         — 4 tabs: agentes, conversaciones, runs Kuine, decisiones
app/lib/core/api_service.dart                      — todos los métodos HTTP incluyendo export/import CSV
app/lib/core/user_role_provider.dart               — UserRole enum: staff/manager/admin
app/lib/features/actions/actions_provider.dart     — pendingActionsStreamProvider (asyncMap Realtime)
```

---

## Chuwi — comandos registrados

**Comandos públicos (sin login):** `/start`, `/yo`, `/menu`, `/estado`, `/ayuda`, `/agentes`, `/kuine`

**Comandos operativos:** `/acciones`, `/criticos`, `/ruta`, `/brief`, `/hoy`, `/scan`, `/merma`, `/donaciones`, `/prediccion`, `/stats`, `/mapa`, `/historial`, `/merma7`

**Comandos de simulación/demo:** `/simular` (panel con 5 botones: 07:30, 12:00, 20:00, alerta proactiva, escalación)

**Comandos manager:** `/proveedores`, `/pedido`, `/esg`, `/citar`, `/costes`, `/reflexiones`, `/informe`, `/semana`, `/demo`

**Callbacks clave en `_ACTION_MAP`:** `brief`, `stats`, `acciones`, `ruta`, `merma`, `donaciones`, `proveedores`, `pedido`, `runbrief`, `sistema`, `simular`, `scan_help`, `ayuda`, `tour`, `mapa`, `historial`, `merma7`, `donar_flow`, `esg`, `prediccion`, `citar`

### Formato visual Telegram
- `_format_brief_html(text)` en chuwi.py — convierte salida LLM a HTML visual con cabecera fija + secciones
- `telegram_formatter.py` — `format_actions`, `format_stats`, `format_merma`, `format_donaciones`, `format_proveedores`, `format_pedido`, `format_estado`
- `_pasillo_label()` en telegram_formatter.py — convierte número a nombre real, "Sin ubicación" si null
- `_PASILLO_NAMES`: `{"1":"🍞 Panadería","2":"🥛 Lácteos","3":"🥩 Carnicería","4":"🐟 Pescadería","5":"🥦 Frutas y Verduras"}`

---

## Scheduler — 15 trabajos cron

| Hora | Job | Función |
|------|-----|---------|
| 07:00 | Predicción | `_run_prediction` — Open-Meteo + historial |
| 07:28 | Morning greeting | `_morning_greeting` — saludo proactivo |
| 07:30 | Brief diario | `supervisor.run_daily_brief` — Kuine completo |
| 12:00 | Check mediodía | `supervisor.run_intraday_check` |
| 16:00 | Reflexión | `_retrospective_reflection` |
| 20:00 | Cierre | `supervisor.run_closing` |
| Lunes 06:00 | Semanal | `supervisor.run_weekly_report` |
| Día 1 08:00 | Mensual | `supervisor.run_monthly_report` |
| Cada 2h 8-20h | Escalación | `_escalate_critical_actions` (score≥85 sin resolver >4h) |
| Cada 30min 8-21h | Monitor | `_proactive_monitor` — botones donación en Telegram |
| Cada 15min 8-20h | SLA check | `_check_sla_violations` |
| Cada 30min 8-21h | Spike | `_auto_brief_on_spike` |
| Cada 30min 8-21h | Triggers | `_evaluate_intent_triggers` |
| 21:30 | Anomalías | `_detect_inventory_anomalies` |
| 9/13/18h | Health | `_run_health_check` |

**Notifier quiet hours:** solo silencia 21:00-08:00. En horario 8-21h nunca silencia.

---

## Endpoints REST — principales

```
GET  /api/v1/dashboard              — KPIs en tiempo real
GET  /api/v1/actions                — acciones pendientes
POST /api/v1/actions/{id}/complete  — marcar completada (escribe merma_log)
GET  /api/v1/export/actions         — CSV acciones completadas 30d
GET  /api/v1/export/batches         — CSV lotes activos
POST /api/v1/import/batches         — importar CSV desde TPV
GET  /api/v1/agent/status           — estado 12 agentes
GET  /api/v1/agent/conversations    — sesiones Chuwi
GET  /api/v1/agent/runs             — runs Kuine
GET  /api/v1/agent/decisions        — decisiones Kuine
GET  /api/v1/reports/brief/pdf      — PDF brief diario
GET  /api/v1/reports/weekly/pdf     — PDF informe semanal
GET  /api/v1/telegram/status        — estado bot Telegram
```

---

## Flutter — features implementadas

- **Dashboard:** KPIs streaming realtime, shimmer loading, donut urgencia, área chart merma 7d, impact card donaciones
- **Acciones:** swipe to complete (manager) / bloqueado (staff), donación con deducción fiscal 35%, import CSV TPV, **export CSV** (share_plus), rol-based con `userRoleProvider`
- **Mapa:** plano interactivo por pasillos, tab FEFO ordenado, tab Pasillos grid, QR por pasillo deeplink, "Sin ubicación" cuando pasillo es null
- **Scan:** barcode + foto, Vision agent (Haiku), carga visual con CircularProgress
- **Agentes:** 4 tabs (estado 12 agentes, conversaciones, runs Kuine, decisiones)
- **Caché de productos:** `_allProductsCacheProvider` (map) + `_actionProductsCacheProvider` (actions) — fallback cuando join Supabase falla por RLS

---

## Tablas Supabase

**Operativas:** `stores`, `users`, `products`, `batches`, `warehouse_stock`, `actions`, `merma_log`, `daily_briefs`, `weekly_reports`, `monthly_reports`, `agent_runs`, `agent_memory`, `knowledge_base`, `suppliers`, `supplier_merma`, `donations`, `store_comparison`

**Fase 1 (migradas):** `agent_conversations`, `agent_messages`, `agent_sessions`, `telegram_users`

---

## Variables de entorno requeridas (.env)

```bash
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://XXXX.supabase.co
SUPABASE_KEY=sb_anon_...
SUPABASE_SERVICE_KEY=sb_service_...
TELEGRAM_BOT_TOKEN=123456:ABC...
STORE_ID=demo-store-001
APP_PORT=8001
```
