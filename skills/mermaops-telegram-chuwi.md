# skill: mermaops-telegram-chuwi
Objetivo: Chuwi como agente operativo, no bot de comandos.
Cuándo: Al tocar chuwi.py, notifier.py, telegram_formatter.py.
Fusiona: telegram-real.

Arquitectura:
- chuwi.py: agente principal Telegram. Streaming, intent classification, 6 tools, historial comprimido.
- notifier.py: alertas proactivas (scheduler → notifier → Telegram).
- telegram_formatter.py: formateo HTML/MarkdownV2 seguro.

Comandos activos: /start, /menu, /yo, /ruta, /resumen, /criticos, /demo.
Handle: texto libre, voz (Whisper), foto (Vision), callbacks inline keyboard.

Chuwi NO es un bot. Diferencias clave en código y docs:
- Monitoriza sin que le pregunten (scheduler proactivo).
- Recuerda contexto entre sesiones (agent_memory).
- Llama a Kuine para decisiones complejas.
- Muestra "escribiendo..." mientras piensa.

Checklist al tocar:
- [ ] run_in_executor en todas las operaciones síncronas
- [ ] _typing_loop siempre tiene finally
- [ ] _get_user() usa TTL cache 60s
- [ ] Ningún handler imprime el token
- [ ] test: send /start → welcome dinámico con datos reales de tienda
- [ ] test: send foto → análisis visual en < 15s (haiku modelo)
- [ ] test: "¿qué hay urgente?" → respuesta con datos reales, no inventados

Telegram token: solo en .env. Nunca en logs, README, código, tests.
Si hay error 401/403: verificar TELEGRAM_BOT_TOKEN. No imprimir el valor.
