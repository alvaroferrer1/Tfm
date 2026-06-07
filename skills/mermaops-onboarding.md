# skill: mermaops-onboarding
Objetivo: Que cualquier persona pueda levantar MermaOps desde cero en < 10 min.
Cuándo: Al escribir docs, README, runbook, o cuando alguien dice "no arranca".

Credenciales necesarias y dónde conseguirlas:
- ANTHROPIC_API_KEY → console.anthropic.com → API Keys → ~3€ para demo completa
- SUPABASE_URL + SUPABASE_KEY + SUPABASE_SERVICE_KEY → supabase.com → Settings → API
- TELEGRAM_BOT_TOKEN → @BotFather → /newbot → nombre "Chuwi"
- STORE_ID → "demo-store-001" (valor fijo para demo)
- APP_PORT → 8001 (8000 bloqueado por Manager.exe en el PC del desarrollador)

Arranque en 3 pasos:
```bash
# 1. Credenciales
cp .env.example .env   # y rellenar los valores

# 2. Datos demo
make seed              # carga Super Martínez con datos realistas
make advance N=2       # simula 2 días → genera CRÍTICOS visibles

# 3. Arrancar
make start             # backend 8001 + verificación completa
cd app && flutter run --dart-define=SUPABASE_URL=... --dart-define=SUPABASE_ANON_KEY=... --dart-define=API_URL=http://TU_IP:8001/api/v1
```

Diagnóstico rápido:
```bash
make verify            # verifica .env + Supabase + Telegram sin arrancar
make check             # diagnóstico completo (requiere backend corriendo)
curl http://localhost:8001/api/v1/health  # debe devolver {"status":"ok",...}
```

Errores comunes y solución:
- "Address already in use 8001" → matar proceso: Get-NetTCPConnection -LocalPort 8001
- "401 Unauthorized Telegram" → verificar TELEGRAM_BOT_TOKEN en .env
- "no module named backend" → activar venv: .venv\Scripts\Activate.ps1
- Flutter "Failed to load" → verificar que API_URL apunta a la IP correcta (no localhost si en móvil)
- "supabase.PostgrestException" → verificar SUPABASE_SERVICE_KEY (no anon key)

Variables Flutter — SOLO estas tres (públicas, seguro en frontend):
- SUPABASE_URL
- SUPABASE_ANON_KEY  (anon/public, no service_role)
- API_URL

Variables NUNCA en Flutter ni en código:
- ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, SUPABASE_SERVICE_KEY, JWT_SECRET
