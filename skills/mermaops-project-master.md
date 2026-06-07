# skill: mermaops-project-master
Objetivo: Contexto base de MermaOps AI. Cargar ANTES de cualquier cambio.
Cuándo: Al inicio de cada sesión de trabajo.

Proyecto: Sistema multiagente para reducción de merma en supermercados.
Stack: Flutter (app) + FastAPI (backend) + Supabase (BD) + Claude API + Telegram (Chuwi).
Puerto backend: 8001 (8000 bloqueado en el PC del usuario).
Tests: 735/735. No deben bajar.

Agentes activos: Kuine (supervisor/Opus), Chuwi (Telegram/Sonnet), Evaluador, Validador,
Consenso, Predictor, Visión, Precio, Stock, Notificador, Reportero.

Chuwi es un AGENTE OPERATIVO sobre Telegram Bot API, no un bot de comandos.
No es un chatbot. No es un CRUD. Demuestra IA real, datos reales, agentes reales.

Demo target: módulo agéntico funcional, app conectada, Telegram funcionando, brief generado.

Reglas hard:
- NO commits sin que el usuario diga "sube" o "commit".
- NO push sin "sube a GitHub" explícito.
- NO credenciales en código — todo por .env.
- NO inventar capacidades.
- Ahorra tokens en cosas no importantes.
- Si algo no está probado, dilo. No vendas humo.

Valores en ROADMAP (no implementados): Langfuse, OCR, GS1 2D, etiquetas electrónicas.
