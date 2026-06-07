# PROJECT_STATE.md — Estado vivo MermaOps
> Actualizado: 2026-05-25 (sesión 3)

## Idea del TFM
Sistema multi-agente IA (Claude) para reducción de merma en supermercados. Dos interfaces: app Flutter (encargado/dueño) + Telegram (Chuwi, agente real con streaming). Orquestador: Kuine (supervisor.py, Opus 4.7). 11 agentes especializados.

## Backend (FastAPI, puerto 8001)
- ✅ Auth JWT Supabase, rate limiting (SlowAPI), CORS correcto (credentials solo si no wildcard)
- ✅ Scan/barcode → evaluador → validador → respuesta IA
- ✅ Actions CRUD, complete (escribe merma_log auto)
- ✅ Brief diario: síncrono + background + PDF
- ✅ Informes semanal/mensual + PDFs + presentación TFM
- ✅ 11 agentes activos con tests
- ✅ Demo: advance_demo + reset — **con auth (verify_token en ambos)**
- ✅ Stats: donaciones, ESG, proveedores, merma, comparativa
- ✅ Import CSV batches
- ✅ Chat endpoint → chat_direct() con asyncio.get_running_loop()
- ✅ Errores sanitizados — ningún detail=str(e) en HTTPException 500
- ✅ 735/735 tests

## App Flutter
- ✅ Login (Supabase auth)
- ✅ Dashboard con Realtime, gráfico merma 7d, snackbar críticos en tiempo real
- ✅ Actions: completar acción, donación inline, invalidación correcta de providers
- ✅ Reports: 9 tabs — briefs, semanales (con "Generar ahora"), mensuales, merma, donaciones, ESG, proveedores, predicciones, pedidos
- ✅ PDF download (brief, semanal, mensual) + share
- ✅ Scan: cámara + barcode, errores amigables, foto con IA visual
- ✅ Map: plano visual 3 tabs (pasillo, urgencia, donaciones)
- ✅ Profile: vincular/desvincular Telegram
- ✅ Agents screen: 4 tabs + **botón descarga Presentación TFM PDF**
- ✅ Demo control: advance + reset con notificación local
- ✅ Chat: llama /agent/chat (Chuwi con tools_used visibles)
- ✅ Navegación: 7 items incluyendo Agentes y Chuwi

## Telegram (Chuwi)
- ✅ /start, menú inline, tarjetas por producto
- ✅ Streaming progresivo ("escribiendo...")
- ✅ Fotos: análisis visual Vision
- ✅ Voz: transcripción Whisper
- ✅ Comandos: /estado, /criticos, /brief, /semana, /ruta, /demo, /yo, /agentes, /kuine
- ✅ PDFs: brief y semanal
- ✅ Donaciones: flujo interactivo botones
- ✅ Ruta del día: modo tarjeta por tarjeta
- ✅ Cache _get_user (TTL 60s), run_in_executor en todos los handlers
- ✅ Alertas: scheduler notifier cada 30min (requiere backend corriendo)
- ✅ /demo reset → dialog confirmación (no reset accidental)
- ✅ /demo N>5 → dialog confirmación (no avance masivo accidental)

## Seguridad (sesión 3 — corregida)
- ✅ /demo/advance y /demo/reset — Depends(verify_token)
- ✅ detail=str(exc) → mensajes genéricos en todos los endpoints
- ✅ CORS: allow_credentials=False cuando allow_origins=["*"]
- ✅ asyncio.get_event_loop() → get_running_loop() en agent_chat y _run_agent_loop
- ✅ datetime.utcnow() → datetime.now(timezone.utc) en todo el código
- ✅ POST /reports/weekly → verify_token añadido
- ✅ POST /brief/run/sync → optional_token + rate limit 3/minute

## Estado de bugs
### P0 — Todos corregidos ✅
### P1 — Estado actual
- ✅ CORS/wildcard corregido
- ✅ detail=str(e) corregido en routes.py y routes_demo.py
- ⚠️ store_comparison: requiere datos de seed para el tab comparativa
- ✅ App chat: tools_used ya se muestran en _MessageBubble

### P2 — Estado actual
- ✅ Import CSV: feedback real del resultado en la UI
- ⚠️ Scheduler proactivo: funciona solo con backend corriendo continuamente (esperado)

## Métricas clave para la defensa
- Tests: **735/735** en < 2s
- Agentes: 11 activos
- Adversarial: 23/23 ataques neutralizados
- Benchmark: 100% precisión vs 16.7% baseline aleatorio
- Endpoints: >55 rutas RESTful documentadas (incl. /stats/overview)
- Seguridad: 0 vulnerabilidades P0 abiertas
