# skill: telegram-real
Objetivo: Verificar y mejorar Chuwi como agente Telegram real.
Cuándo: Al tocar chuwi.py, notifier.py, o flujos de Telegram.
Checklist:
- ¿Los handlers usan run_in_executor para operaciones sync?
- ¿El typing_loop siempre tiene done.set() en finally?
- ¿Los errores de herramientas dan mensaje amigable (no str(e))?
- ¿Las respuestas del LLM se streaman progresivamente?
- ¿Los comandos clave responden en < 3s para la mayoría de casos?
- ¿advance_demo notifica por Telegram inmediatamente?
- ¿El bot funciona si no hay datos en la BD? (fallback graceful)
Output: Lista de handlers verificados vs. problemáticos.
