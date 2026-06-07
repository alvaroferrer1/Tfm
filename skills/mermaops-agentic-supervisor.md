# skill: mermaops-agentic-supervisor
Objetivo: Arquitectura multiagente correcta. Kuine coordina, no hace todo.
Cuándo: Al tocar supervisor.py, evaluator.py, validator.py, cualquier agente.
Fusiona: agents-real.

Agentes y modelos:
Kuine (supervisor.py) → Opus 4.7 → orquesta, delega, consolida
Chuwi (chuwi.py) → Sonnet 4.6 → interfaz Telegram, streaming
Evaluador (evaluator.py) → Sonnet 4.6 → score 0-100, extended thinking ≥65
Validador (validator.py) → Sonnet 4.6 → 23 ataques adversariales, 100%
Consenso (consensus.py) → Sonnet 4.6 → 3 instancias paralelas, score ≥90
Predictor (predictor.py) → Haiku 4.5 → Open-Meteo + historial
Visión (vision.py) → Haiku 4.5 → análisis foto (cambiado de sonnet para velocidad)
Precio (price.py) → Haiku 4.5 → cálculo descuentos
Stock (stock.py) → Haiku 4.5 → decisiones reposición FEFO
Notificador (notifier.py) → Sonnet 4.6 → alertas proactivas
Reportero (reporter.py) → Sonnet 4.6 → briefs y resúmenes

Patrón supervisor correcto:
1. Kuine recibe trigger (scheduler, Chuwi, endpoint).
2. Lee estado real de BD (no inventa).
3. Llama subagentes en paralelo si puede.
4. Consolida resultados.
5. Escribe decisión en agent_runs + supervisor_decisions.
6. Notifica via Chuwi si procede.

Regla de oro: Si el agente devuelve datos que no tienen fuente en BD → es alucinación.
Checklist antes de cambiar un agente:
- ¿Llama a herramientas reales con datos reales?
- ¿Escribe resultado en BD (agent_runs)?
- ¿Loguea decisión con razonamiento?
- ¿Falla de forma silenciosa (fallback) o explota en demo?
