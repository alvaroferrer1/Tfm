# CHANGELOG.md — MermaOps
> Formato: [fecha] cambio — archivo(s) afectados

## 2026-05-25 (sesión 4)

### Tests — cobertura ampliada de 651 a 735/735
- [test_scanner.py] 5 → 16 tests: keys completas, barcode, fallback nombre, timeout, categoría "en:"
- [test_stock.py] 7 → 30 tests: FEFO stock minoritario, days_coverage, suggested_order_qty, velocity-based restock
- [test_route.py] 9 → 22 tests: format_route_html(), keys items, days_left calculados, pasillos múltiples
- [test_evaluator.py] 18 → 27 tests: donación panadería (Ley 49/2002), consenso triple activado, multi-batch
- [test_price.py] 14 → 28 tests: velocity boost, category multipliers, cost floor, calculate_text
- [test_api_endpoints.py] +12 tests: LLM stats, predict/risk, store overview detallado
- [test_chat_api.py] +3 tests: tools_used list, response string

### Calidad de código
- [main.py] Descripción API expandida en Swagger /docs — métricas clave visibles al tribunal

## 2026-05-25 (sesión 3)

### Seguridad P0 corregida
- [routes_demo.py] /demo/advance y /demo/reset ahora requieren JWT válido (Depends(verify_token))
- [routes_demo.py] detail=str(exc) → mensajes genéricos seguros
- [routes.py] 30 ocurrencias de detail=str(e) en HTTPException 500 → "Error interno del servidor"
- [routes.py] POST /reports/weekly sin auth → añadido verify_token
- [routes.py] POST /brief/run/sync sin auth ni rate limit → optional_token + @limiter.limit("3/minute")
- [main.py] CORS: allow_credentials=True con allow_origins=["*"] inválido → credentials solo si no es wildcard

### Calidad backend
- [routes.py] asyncio.get_event_loop() en agent_chat → get_running_loop()
- [routes.py] datetime.utcnow() en agent/activity → datetime.now(timezone.utc)

### Flutter
- [reports_screen.dart] Tab Semanal empty state: "const" → añadido botón "Generar ahora"
- [api_service.dart] Añadido runWeeklyReport() → POST /reports/weekly
- [dashboard_screen.dart] DashboardScreen ConsumerWidget → ConsumerStatefulWidget con snackbar de alerta cuando aparecen nuevos críticos via Realtime
- [reports_screen.dart] ESG tab y Predictions tab: snapshot.error → friendlyError(snapshot.error)
- [agents_screen.dart] _ErrorBanner → friendlyError(e)
- [scan_screen.dart] errorCode.name → mensaje amigable en cámara

### Telegram
- [chuwi.py] /demo reset → confirmation dialog antes de ejecutar
- [chuwi.py] /demo N>5 → confirmation dialog antes de avanzar muchos días

## 2026-05-25 (sesiones 1-2)

### Bugs reales corregidos
- [chuwi.py] _get_user() era síncrono y bloqueaba event loop Telegram → TTL cache 60s + run_in_executor en todos los handlers
- [chuwi.py] asyncio.get_event_loop() deprecado en _run_agent_loop → get_running_loop()
- [chuwi.py] _upsert_telegram_user usaba datetime.utcnow() → now(timezone.utc)
- [chuwi.py] _execute_tool_sync exponía str(e) con IPs/stacktraces → mensaje genérico amigable
- [chuwi.py] typing_loop sin finally → "escribiendo..." se quedaba para siempre → finally + timeout
- [chuwi.py] _telegramStatusProvider no se invalidaba tras vincular/desvincular Telegram → añadido
- [database.py] 7 ocurrencias de datetime.utcnow() → now(timezone.utc)
- [notifier.py] print() → logger en todos los puntos de fallo
- [routes_demo.py] advance_demo sin notificación Telegram → notifica con críticos inmediatamente
- [actions_screen.dart] completedActionsProvider no se invalidaba → añadido
- [scan_screen.dart] errorCode.name visible al usuario → mensajes amigables en español
- [reporter.py] brief limitado 700 tokens/350 palabras → 1200 tokens, 400-600 palabras, estructura 5 secciones

### Clasificador de intents
- [chuwi.py] _classify_intent: "cuánto" demasiado amplio → removido de consulta_estado
- [chuwi.py] _classify_intent: añadido "urgente" a consulta_estado

### Tests nuevos
- [test_intent_classification.py] 40 tests clasificador intent (0 tokens LLM)
- [test_real_bugs.py] 22 tests detectando los bugs reales corregidos
- Total: 735/735 tests

### Documentación
- PROJECT_STATE.md — estado vivo del proyecto
- BUG_BACKLOG.md — backlog P0/P1/P2 con evidencia
- ROADMAP_TO_10.md — plan matrícula
- SECURITY_REVIEW.md — riesgos reales
- CHANGELOG.md — este archivo
- skills/ — 8 skills de trabajo

## Sesiones anteriores (resumen)
- Fases 1-6: tablas agent_*, intent classification, endpoints agentes, Flutter agents screen
- advance_demo.py, routes_demo.py — simulación temporal
- PDF generator, telegram_formatter mejorado
- map_screen.dart — plano visual del supermercado
