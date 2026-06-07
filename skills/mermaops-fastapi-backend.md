# skill: mermaops-fastapi-backend
Objetivo: Backend estable, endpoints probados, sin secretos expuestos.
Cuándo: Al tocar routes.py, main.py, database.py, llm.py, scheduler.py.

Archivos clave:
- backend/main.py → arranque, CORS, lifespan
- backend/api/routes.py → todos los endpoints
- backend/api/routes_demo.py → endpoints demo (requieren JWT)
- backend/core/database.py → queries Supabase
- backend/core/llm.py → wrapper Claude API
- backend/core/scheduler.py → 7 jobs programados
- backend/api/auth.py → verify_token, optional_token

Puerto: 8001. Comando: uvicorn backend.main:app --port 8001 --reload

Endpoints críticos para demo:
GET  /api/v1/health
GET  /api/v1/dashboard
GET  /api/v1/actions
POST /api/v1/brief/run/sync
POST /api/v1/agent/chat
GET  /api/v1/agent/status
GET  /api/v1/telegram/status
POST /api/v1/demo/advance  (requiere JWT)

Reglas al tocar:
- Nunca detail=str(e) en HTTP 500 → "Error interno del servidor"
- Todos los endpoints sensibles → Depends(verify_token)
- Rate limit en chat y brief
- Logs sin secretos, sin IPs, sin stack traces completas
- CORS: allow_credentials solo si allow_origins no es ["*"]

Scheduler jobs activos (verificar que arrancan):
daily_brief 07:30, intraday 12:00, closing 20:00,
weekly Mon 06:00, monthly day-1 08:00,
escalation cada 2h 8-20, proactive_monitor cada 30min 8-21.
