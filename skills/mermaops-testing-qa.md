# skill: mermaops-testing-qa
Objetivo: Checklist de QA antes de demo. Sin excusas.
Cuándo: Antes de demo, después de bloque de cambios, antes de commit.

BACKEND:
- [ ] cd tfm-final-master && python -m pytest backend/tests/ -q → debe ser 735/735
- [ ] python -m uvicorn backend.main:app --port 8001 arranca sin error
- [ ] GET http://localhost:8001/api/v1/health → {"status":"ok"}
- [ ] GET http://localhost:8001/docs → Swagger carga
- [ ] GET http://localhost:8001/api/v1/dashboard → devuelve datos o error claro

FLUTTER:
- [ ] flutter analyze --no-pub → No issues found
- [ ] flutter pub get → sin conflictos
- [ ] App carga sin crash en pantalla principal
- [ ] Dashboard muestra datos (o error amigable si backend off)
- [ ] Acciones cargan lista
- [ ] No hay "detail=str(e)" visible al usuario

SUPABASE:
- [ ] SUPABASE_URL y SUPABASE_KEY en .env
- [ ] Tabla 'stores' existe con STORE_ID=demo-store-001
- [ ] Tabla 'products' tiene datos demo
- [ ] Tabla 'batches' tiene lotes activos
- [ ] Tabla 'actions' tiene acciones pendientes

TELEGRAM:
- [ ] TELEGRAM_BOT_TOKEN en .env (sin imprimir el valor)
- [ ] python scripts/check_all.py → Telegram status OK
- [ ] /start responde con welcome dinámico
- [ ] Brief diario llega por Telegram

IA/CLAUDE:
- [ ] ANTHROPIC_API_KEY en .env (sin imprimir)
- [ ] Un llamada mínima a llm.call() no falla
- [ ] Kuine genera brief sin timeout

SEGURIDAD:
- [ ] grep -r "sk-ant-" . --include="*.py" --include="*.dart" → 0 resultados
- [ ] .env en .gitignore
- [ ] No hay secretos en README ni docs

Si algo falla: márcar como P0 o P1 en BUG_BACKLOG.md. No ignorar.
