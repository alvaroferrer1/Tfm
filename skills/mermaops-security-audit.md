# skill: mermaops-security-audit
Objetivo: Auditoría de seguridad real. Sin pasar nada por alto.
Cuándo: Antes de demo, antes de commit público, tras cambios en auth/routes.
Fusiona: security-review + OWASP + Trail of Bits basics.

Checklist P0 (bloquea demo si falla):
- grep -r "sk-ant-\|eyJhbGc\|bot[0-9]\{9\}" . --include="*.py" --include="*.dart" --include="*.md" → 0
- .env en .gitignore y NO en repo
- SUPABASE_SERVICE_ROLE_KEY solo en backend, nunca en Flutter
- ANTHROPIC_API_KEY nunca en Flutter ni README
- TELEGRAM_BOT_TOKEN nunca en código ni logs
- routes.py: grep "detail=str(e)" → 0 ocurrencias en HTTP 500

Checklist P1 (funcionalidad insegura):
- FastAPI CORS: allow_origins no es ["*"] con credentials=True
- Auth endpoints: verify_token en todos los endpoints sensibles
- Rate limiting: @limiter.limit en /agent/chat y /brief/run
- Prompt injection: detección básica en agent_chat (ya implementada)
- Historial chat: limitado a 20 turnos (ya implementado)
- Supabase: SUPABASE_KEY es anon/public, SUPABASE_SERVICE_KEY es service_role

Checklist P2 (mejoras de seguridad):
- Logs: logger.info/warning/error solo, sin print()
- Excepciones: nunca exponer stack traces al usuario
- RLS migration: supabase/migrations/20260526000001_rls_agent_tables.sql (creada, NO aplicada aún)
- Vision: imágenes no se guardan en disco permanente

Flutter solo puede tener: SUPABASE_URL + SUPABASE_ANON_KEY (públicas) + API_URL.
Si detectas secreto en frontend: P0 inmediato, rotar credencial.
