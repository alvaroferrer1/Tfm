# BUG_BACKLOG.md — MermaOps
> Actualizado: 2026-05-25

## P0 — Críticos (bloquean demo o seguridad real)

### BUG-P0-001 | Seguridad | Demo endpoints sin auth
- **Área**: backend/api/routes_demo.py
- **Evidencia**: `def advance_demo(body)` y `def reset_demo()` sin `Depends(verify_token)`
- **Impacto**: Cualquiera con la URL puede resetear toda la BD de demo
- **Fix**: Añadir `DEMO_TOKEN` env var o reutilizar `verify_token`
- **Validación**: `curl -X POST /api/v1/demo/advance` sin JWT → debe dar 401

### BUG-P0-002 | Seguridad | detail=str(exc) en routes_demo.py
- **Área**: backend/api/routes_demo.py líneas 82, 112
- **Evidencia**: `raise HTTPException(status_code=500, detail=str(exc))` — pasa por `http_exception_handler` que reenvía el detail directamente
- **Impacto**: Stacktrace/errores internos visibles al cliente
- **Fix**: Cambiar a `detail="Error interno"` y loggear exc_info=True
- **Validación**: Forzar error → respuesta JSON no debe contener ruta de fichero ni excepción Python

### BUG-P0-003 | Seguridad | CORS wildcard en producción
- **Área**: backend/main.py
- **Evidencia**: Sin CORS_ORIGINS en .env → `allow_origins=["*"]`
- **Impacto**: Cualquier dominio puede hacer requests autenticados al API
- **Fix**: Documentar que CORS_ORIGINS es requerido en .env de producción
- **Validación**: Verificar .env.example tiene CORS_ORIGINS comentado

---

## P1 — Importantes (degradan experiencia demo / nota)

### BUG-P1-001 | Seguridad | 23 detail=str(e) en routes.py
- **Área**: backend/api/routes.py (~23 ocurrencias)
- **Evidencia**: `raise HTTPException(status_code=500, detail=str(e))` — HTTPException handler devuelve el detail literal
- **Fix**: Script de reemplazo masivo → `detail="Error interno del servidor"`
- **Validación**: grep `detail=str` en routes.py → 0 resultados

### BUG-P1-002 | App | store_comparison vacío
- **Área**: backend/data/demo_actions.py o seed.py, app dashboard tab comparativa
- **Evidencia**: Tab "comparativa tiendas" en dashboard no muestra datos
- **Fix**: Insertar 3-4 filas en store_comparison en seed/demo_actions
- **Validación**: Tab muestra al menos 3 tiendas con datos

### BUG-P1-003 | App | Chat screen no muestra tools usados
- **Área**: app/lib/features/chat/chat_screen.dart, backend/api/routes.py /agent/chat
- **Evidencia**: toolsUsed siempre vacío en UI — el endpoint devuelve tools pero el mapping puede fallar
- **Fix**: Verificar que /agent/chat devuelve tools_used y que Flutter los parsea
- **Validación**: Chat con "¿qué hago hoy?" → muestra chips de tools usadas

### BUG-P1-004 | App | Login sin feedback de error
- **Área**: app/lib/features/auth/login_screen.dart
- **Evidencia**: Si credenciales incorrectas, solo spinner sin mensaje
- **Fix**: Capturar AuthException de Supabase → mostrar SnackBar con mensaje
- **Validación**: Intentar login con email/pass incorrectos → mensaje visible en español

### BUG-P1-005 | Telegram | advance_demo no actualiza providers Flutter
- **Área**: app/lib/features/demo/demo_control_screen.dart
- **Evidencia**: Tras advance, la app no recarga dashboard ni actions automáticamente
- **Fix**: Después de advanceDemo() invalidar dashboardProvider y actionsProvider
- **Validación**: Advance → dashboard se actualiza solo sin reload manual

---

## P2 — Mejoran nota

### BUG-P2-001 | App | Import CSV sin feedback real
- **Evidencia**: Botón existe, llama endpoint, pero la UI no muestra qué filas se importaron

### BUG-P2-002 | App | Fechas en UTC en briefs históricos
- **Evidencia**: Briefs de días anteriores muestran hora UTC, no local

### BUG-P2-003 | Telegram | /demo sin confirmación antes de advance masivo
- **Evidencia**: /demo advance 30 avanza 30 días sin pedir confirmación

### BUG-P2-004 | Backend | Scheduler no arranca si faltan vars de entorno
- **Evidencia**: scheduler.py falla silenciosamente si STORE_ID vacío

---

## Resueltos (esta sesión)
- ✅ BUG-001: _get_user bloqueaba event loop Telegram → cache TTL + run_in_executor
- ✅ BUG-005: Tool errors exponían stacktrace → mensaje genérico amigable
- ✅ BUG-006: typing_loop se quedaba colgado → finally + timeout
- ✅ BUG-007: get_event_loop() deprecado → get_running_loop()
- ✅ BUG-008: notifier usaba print() → logger
- ✅ BUG-009: advance_demo sin notificación Telegram → se añadió
- ✅ BUG-010: Brief muy corto → max_tokens=1200, 400-600 palabras
- ✅ BUG-CAM: Cámara mostraba errorCode.name → mensaje amigable en español
- ✅ BUG-ACT: completedActionsProvider no se invalidaba → añadido
- ✅ BUG-TG: _telegramStatusProvider no se invalidaba → añadido
- ✅ BUG-UTC: datetime.utcnow() en database.py y chuwi.py → now(timezone.utc)
