# skill: audit-real
Objetivo: Auditar como usuario/CTO, no como verificador de tests.
Cuándo: Al inicio de sesión, tras un bloque de cambios, antes de demo.
Checklist:
- Leer PROJECT_STATE.md y BUG_BACKLOG.md primero
- Por cada pantalla: ¿qué ve el usuario si no hay datos? ¿y si hay error?
- Por cada endpoint: ¿devuelve error técnico al cliente?
- Por cada flujo: ¿se puede quedar colgado?
- Buscar: detail=str(e), print(), utcnow(), get_event_loop()
- Buscar: pantallas sin datos reales, botones que no hacen nada
- NO decir "funciona" sin flujo concreto verificado
Output: Lista de hallazgos con evidencia (archivo:línea), sin teoría.
