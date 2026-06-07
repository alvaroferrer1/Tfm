# TESTING_REPORT.md — MermaOps
> Actualizado: 2026-05-25

## Estado actual
- **735/735 tests pasando** en < 2s, sin conexión Supabase ni llamadas LLM reales
- Warnings: 4 de librería slowapi (deprecation asyncio), no son nuestros

## Tests útiles (detectan bugs reales)
- test_real_bugs.py — 28 tests, detectan BUGs 001-010 + notifier quiet hours
- test_adversarial.py — 23 ataques adversariales, 100% bloqueados
- test_intent_classification.py — 40 tests, clasificador 0 tokens LLM
- test_pdf_generator.py — verifica generación PDF sin LLM
- test_validator.py — 21 tests validador de seguridad
- test_evaluator.py — 27 tests incluyendo consenso, food safety rules (Ley 49/2002)
- test_stock.py — 30 tests: FEFO, velocity-based restock, suggested order qty
- test_price.py — 28 tests: velocity boost, category multipliers, cost floor
- test_scanner.py — 16 tests: OpenFoodFacts parsing, error handling
- test_route.py — 22 tests: format_route_html, FEFO sorting, HTML generation
- test_compute_baseline.py — 22 tests de métricas vs baseline aleatorio
- test_eval_framework.py — 33 tests del framework de evaluación cuantitativa

## Tests de humo (solo verifican que el código no explota)
- test_chuwi_agent.py — mocks de Telegram, no prueba comportamiento real
- test_api_endpoints.py — FastAPI TestClient (54 tests), no Supabase real
- test_database_functions.py — mocks de DB

## Pruebas manuales reales pendientes
- [ ] Telegram: enviar mensaje de voz real y verificar transcripción
- [ ] Telegram: enviar foto de producto y verificar análisis Vision
- [ ] Telegram: avanzar demo y verificar notificación inmediata
- [ ] App: completar acción y verificar que desaparece de pendientes Y aparece en completadas
- [ ] App: vincular Telegram y verificar que el badge cambia sin reload
- [ ] App: descargar PDF y verificar que se abre correctamente
- [ ] App: login con credenciales incorrectas → verificar mensaje de error
- [x] Backend: POST /demo/advance sin token → da 401 (verify_token aplicado)

## Tests que NO son confiables para detectar bugs de producción
- Cualquier test con MagicMock de Supabase — el schema real puede diferir
- test_chuwi_agent.py con mock de Telegram — no detecta el event loop blocking
- Tests con datos hardcoded — no validan el seed real
