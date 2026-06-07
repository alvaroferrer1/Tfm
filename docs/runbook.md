# MermaOps — Runbook de arranque y verificación

> Guía real para arrancar el sistema y verificarlo end-to-end.
> Todos los comandos están verificados contra el código real del repo.

---

## Requisitos previos

| Componente | Versión mínima | Verificar con |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Flutter | 3.16+ | `flutter --version` |
| Supabase CLI | 2.x | `supabase --version` |
| Node.js | 18+ | `node --version` |
| ngrok (opcional, local) | cualquiera | `ngrok --version` |

---

## Variables .env necesarias

Crear `.env` en la raíz del proyecto (nunca subir a git):

```
ANTHROPIC_API_KEY=sk-ant-...          # Claude API
SUPABASE_URL=https://xxx.supabase.co  # Supabase project URL
SUPABASE_KEY=sb_secret_...            # Supabase anon/service key
SUPABASE_SERVICE_KEY=sb_secret_...    # Supabase service role (para seed/admin)
TELEGRAM_BOT_TOKEN=123456:ABC-...     # Token de @BotFather
STORE_ID=demo-store-001               # ID de la tienda demo
APP_ENV=development
APP_PORT=8001
API_HOST=127.0.0.1
STORE_LAT=40.4168
STORE_LON=-3.7038
LANGFUSE_PUBLIC_KEY=pk-lf-...         # Opcional — observabilidad LLM
LANGFUSE_SECRET_KEY=sk-lf-...         # Opcional
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 1. Arrancar el backend

```bash
# Instalar dependencias (primera vez)
pip install -r requirements.txt

# Arrancar en desarrollo (puerto 8001)
python -m backend.main

# Verificar que arrancó
curl http://localhost:8001/api/v1/health
# → {"api":"ok","db":"ok","db_latency_ms":300,"store_id":"demo-store-001"}
```

---

## 2. Cargar datos demo en Supabase

```bash
# Carga completa (productos + lotes + acciones + brief + comparativa)
make seed

# Solo acciones y brief (sin recrear productos)
make seed-actions

# Avanzar N días (para demo en vivo)
make advance N=2      # simula 2 días hacia adelante
make advance N=1      # un día más

# Volver al estado inicial
make demo-reset

# Generar brief manual
make brief
```

---

## 3. Aplicar migraciones Supabase

```bash
# Verificar qué migraciones se van a aplicar (sin aplicar)
make migrate-dry

# Aplicar migraciones
make migrate
# → Aplica supabase/migrations/20260519000001_agent_foundations.sql

# Verificar que las tablas existen
python -c "
from dotenv import load_dotenv; load_dotenv()
from backend.core.database import get_db
db = get_db()
for t in ['agent_conversations','agent_messages','agent_sessions','telegram_users']:
    r = db.table(t).select('id').limit(1).execute()
    print(f'OK {t}')
"
```

---

## 4. Arrancar app Flutter

```bash
cd app

# Instalar dependencias
flutter pub get

# Correr en emulador (necesita SUPABASE_URL y KEY del .env)
# Usa make flutter-run para generar el comando con las variables
make flutter-run
# → imprime el comando flutter run con --dart-define

# O manualmente (sustituye los valores reales):
flutter run \
  --dart-define=SUPABASE_URL=https://xxx.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=eyJ... \
  --dart-define=API_URL=http://TU_IP_LOCAL:8001/api/v1
```

---

## 5. Configurar Telegram AI Agent (local con ngrok)

```bash
# 1. Arrancar backend
python -m backend.main

# 2. Exponer con ngrok (en otra terminal)
ngrok http 8001
# → copia la URL https://xxxx.ngrok-free.app

# 3. Configurar webhook (sustituye TOKEN y URL)
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://xxxx.ngrok-free.app/webhook"

# 4. Verificar webhook
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
# → {"url":"https://xxxx.ngrok-free.app/webhook","has_custom_certificate":false,...}

# 5. Probar en Telegram
# Buscar @ChuwiMermaOpsBot → /start
```

### Telegram en producción (sin ngrok)

```bash
# Con URL pública del backend
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://tudominio.com/webhook"

# Verificar
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

> **Nota técnica**: Telegram requiere un bot token de BotFather como mecanismo de transporte.
> La lógica del sistema es un agente operativo completo (no un bot básico) con:
> intent classification, memoria persistente, tool use, streaming y trazabilidad en Supabase.

---

## 6. Diagnóstico completo

```bash
# Script de diagnóstico (todo el sistema)
make check
# o
python scripts/check_all.py

# Salida esperada:
#   OK:   39+
#   WARN: <5 (solo opcionales)
#   FAIL: 0
#   Sistema listo para demo
```

---

## 7. Pruebas end-to-end

### Caso A — Usuario Telegram NO vinculado

```
1. Busca @ChuwiMermaOpsBot en Telegram
2. Escribe cualquier mensaje (sin /start)
3. Resultado esperado:
   "Para usar MermaOps necesitas vincular tu cuenta.
    Tu ID de Telegram es: 123456789
    Pásaselo al encargado para que lo vincule en la app."
4. Verificar en Supabase:
   SELECT status FROM telegram_users WHERE telegram_user_id = '123456789';
   → status = 'pending'
5. NO debe haberse creado agent_conversation
```

### Caso B — Usuario vinculado, mensaje simple

```
1. Vincular desde la app: Perfil → Telegram → pegar ID
2. Enviar en Telegram: "hola, cómo estás?"
3. Resultado esperado: Chuwi responde en ~2s con streaming
4. Verificar en Supabase:
   SELECT role, intent_tag, tools_used FROM agent_messages
   ORDER BY created_at DESC LIMIT 4;
   → 2 filas: user (intent='pregunta_libre') y assistant
```

### Caso C — Consulta de estado con herramientas

```
1. Enviar en Telegram: "cuántos críticos hay ahora mismo"
2. Resultado esperado:
   - Chuwi muestra "⏳ Consultando estado..." mientras piensa
   - Responde con número de críticos y detalles
3. Verificar en Supabase:
   SELECT tools_used FROM agent_messages
   WHERE role = 'assistant' ORDER BY created_at DESC LIMIT 1;
   → ["get_expiring_batches", "evaluate_batch"] o similar
   SELECT intent_tag FROM agent_messages
   WHERE role = 'user' ORDER BY created_at DESC LIMIT 1;
   → "consulta_estado"
```

### Caso D — Pedir brief (delegación a Kuine)

```
1. Enviar en Telegram: "generar brief del día"
   o en app: Dashboard → Generar Brief
2. Resultado esperado: análisis completo de la tienda
3. Verificar en Supabase:
   SELECT role, agent_source, content FROM agent_messages
   WHERE agent_source = 'kuine' ORDER BY created_at DESC LIMIT 2;
   → filas con coordinación Chuwi→Kuine
```

### Caso E — Completar acción y merma_log

```
1. Enviar en Telegram: "listo, terminé la merluza"
   o en app: Acciones → Completar
2. Resultado esperado: acción marcada como completada
3. Verificar en Supabase:
   SELECT * FROM merma_log ORDER BY date DESC LIMIT 3;
   → fila nueva con quantity_lost y value_lost
   SELECT status FROM actions ORDER BY completed_at DESC LIMIT 1;
   → status = 'completed'
```

### Caso F — Reinicio del backend (sin JSON)

```
1. Parar el backend: Ctrl+C
2. Reiniciar: python -m backend.main
3. Enviar un mensaje en Telegram
4. Resultado esperado: Chuwi recuerda el contexto desde Supabase
5. Verificar: NO usa .tmp/chuwi_history.json como fuente principal
   → Supabase agent_memory es el almacén principal
```

---

## 8. Queries de verificación en Supabase

```sql
-- Últimas conversaciones
SELECT id, telegram_user_id, message_count, last_message_at
FROM agent_conversations
ORDER BY last_message_at DESC
LIMIT 10;

-- Últimos mensajes con intent y tools
SELECT role, intent_tag, tools_used, agent_source, created_at
FROM agent_messages
ORDER BY created_at DESC
LIMIT 20;

-- Sesiones del agente
SELECT id, telegram_user_id, messages_count, tools_called, kuine_calls, resolved
FROM agent_sessions
ORDER BY session_start DESC
LIMIT 10;

-- Registro de merma
SELECT batch_id, quantity_lost, value_lost, reason, date
FROM merma_log
ORDER BY date DESC
LIMIT 10;

-- Usuarios de Telegram (vinculados y no vinculados)
SELECT telegram_user_id, telegram_username, status, linked_at, last_seen_at
FROM telegram_users
ORDER BY last_seen_at DESC
LIMIT 10;

-- Acciones recientes
SELECT id, action_type, status, priority_score, completed_at
FROM actions
ORDER BY created_at DESC
LIMIT 10;

-- Briefs diarios
SELECT date, value_at_risk, actions_count
FROM daily_briefs
ORDER BY date DESC
LIMIT 5;

-- Tablas de Fase 1 creadas (verificación de migración)
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('agent_conversations','agent_messages','agent_sessions','telegram_users')
ORDER BY table_name;
-- Debe devolver 4 filas
```

---

## 9. Errores comunes y soluciones

| Error | Causa | Solución |
|---|---|---|
| `SUPABASE_URL y SUPABASE_KEY deben estar definidos` | .env no cargado | Verificar .env en raíz del proyecto |
| Puerto 8000 ocupado | Manager.exe en Windows | El backend usa el 8001, ya configurado |
| `Could not find table 'agent_conversations'` | Migración no aplicada | `make migrate` |
| Telegram no responde | Webhook no configurado | Usa polling local o configura ngrok |
| Chuwi no reconoce al usuario | telegram_user_id no vinculado | Vincular desde app: Perfil → Telegram |
| `401 Unauthorized` en endpoints | Token JWT requerido | Usar token de Supabase auth |
| Flutter no compila | --dart-define faltantes | Usar `make flutter-run` para generar el comando |

---

## 10. Endpoints del backend

| Endpoint | Método | Auth | Descripción |
|---|---|---|---|
| `/api/v1/ping` | GET | No | Health básico |
| `/api/v1/health` | GET | No | Health con DB |
| `/api/v1/dashboard` | GET | No | KPIs dashboard |
| `/api/v1/actions` | GET | No | Acciones pendientes |
| `/api/v1/actions/complete` | POST | Sí | Completar acción |
| `/api/v1/products/expiring` | GET | No | Productos caducando |
| `/api/v1/agent/status` | GET | No | Estado de los 12 agentes |
| `/api/v1/agent/conversations` | GET | Sí | Conversaciones recientes |
| `/api/v1/agent/conversations/{id}/messages` | GET | Sí | Mensajes de una conversación |
| `/api/v1/agent/sessions` | GET | Sí | Sesiones del agente |
| `/api/v1/agent/activity` | GET | Sí | Actividad últimas 24h |
| `/api/v1/telegram/status` | GET | No | Estado Telegram AI Agent |
| `/api/v1/demo/advance` | POST | Sí | Avanzar N días en demo |
| `/api/v1/demo/reset` | POST | Sí | Reset estado demo |
| `/api/v1/stats/merma` | GET | No | Estadísticas de merma |
| `/api/v1/stats/esg` | GET | No | Métricas ESG |
| `/api/v1/predict/risk` | GET | No | Predicción de riesgo |
| `/api/v1/brief/run` | POST | Sí | Generar brief (async) |
| `/api/v1/user/me` | GET | Sí | Perfil usuario |
| `/api/v1/user/link-telegram` | POST | Sí | Vincular Telegram |
