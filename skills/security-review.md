# skill: security-review
Objetivo: Detectar riesgos de seguridad reales en el proyecto.
Cuándo: Antes de demo, antes de commit, tras cambios en routes/auth.
Checklist:
- grep "detail=str" en routes*.py → debe ser 0
- grep "verify_token" por cada POST/PUT/DELETE → todos deben tenerlo
- grep "print(" en backend/ → debe ser 0 (usar logger)
- grep "utcnow\|get_event_loop\(\)" → debe ser 0
- .env en .gitignore → verificar con git status
- CORS_ORIGINS: ¿es "*" en producción?
- Prompt injection: ¿el system prompt protege contra override?
Output: Lista de hallazgos con severidad y fix aplicado.
