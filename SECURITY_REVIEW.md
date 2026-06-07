# SECURITY_REVIEW.md — MermaOps
> Actualizado: 2026-05-25

## Riesgos por gravedad

### CRÍTICO
1. **Demo endpoints sin auth** — POST /api/v1/demo/advance y /demo/reset sin Depends(verify_token)
   Cualquiera con la URL resetea la BD. Fix: ver BUG-P0-001.

2. **detail=str(exc) en HTTPException** — 25 endpoints exponen Python exceptions al cliente.
   El global handler genérico NO aplica a HTTPException — esas sí pasan el detail.
   Fix: reemplazar todos por detail="Error interno del servidor".

### ALTO
3. **CORS wildcard** — Sin CORS_ORIGINS en .env, accept any origin.
   Riesgo en prod. En TFM/demo es aceptable si se documenta.

4. **Prompt injection en chat Telegram** — Chuwi procesa texto libre del usuario.
   El validador (validator.py) tiene 23 ataques conocidos pero no inspecciona en tiempo real.
   Mitigación actual: system prompt con instrucciones claras + herramienta allowlist.

### MEDIO
5. **Logs con datos de usuario** — chuwi.py loggea partes del mensaje de usuario (intent, texto).
   No loggea passwords ni tokens, pero sí nombres de producto y cantidades.

6. **TELEGRAM_BOT_TOKEN en env** — Correcto. Pero si el proceso crashea con env dump visible, se expone.

7. **Supabase anon key en Flutter** — La anon key está en --dart-define, no en el código.
   Correcto para Flutter. La service key NUNCA debe ir en el app.

### BAJO / ACEPTABLE
8. **Rate limiting solo en algunos endpoints** — /scan, /brief/run tienen límites. /actions/complete no.
   Para TFM con 1 usuario es OK.

9. **Sin validación de tamaño en import CSV** — Un CSV masivo podría bloquear el backend.
   Mitigación: timeout en endpoint (30s).

## Secrets en código — auditoria
- ✅ ANTHROPIC_API_KEY: solo os.getenv()
- ✅ SUPABASE_URL/KEY: solo os.getenv() 
- ✅ TELEGRAM_BOT_TOKEN: solo os.getenv()
- ✅ .env en .gitignore
- ⚠️ chuwi.py línea 2516: texto "configura ANTHROPIC_API_KEY" — hardcoded string con nombre de var (no secret, OK)

## Acciones peligrosas sin confirmación
- ⚠️ /demo/reset elimina todos los batches y los recrea — sin confirmación
- ⚠️ Telegram /demo advance X no pide confirmación si X > 7 días
