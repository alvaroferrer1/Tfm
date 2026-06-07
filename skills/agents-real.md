# skill: agents-real
Objetivo: Verificar que los agentes usan datos reales y razonan, no invetan.
Cuándo: Al tocar supervisor.py, evaluator.py, chuwi.py, reporter.py.
Checklist:
- ¿El agente llama herramientas con datos reales de la BD?
- ¿El score del evaluador varía según datos (no siempre el mismo valor)?
- ¿El brief menciona productos específicos con nombres reales?
- ¿Las decisiones de Kuine se loggean en agent_runs/supervisor_decisions?
- ¿El validador bloquea prompts adversariales?
- ¿chat_direct vs _run_agent_loop — cuál se usa dónde?
- ¿Los tools_used se persisten en agent_messages?
Output: Evidencia de que los agentes deciden con datos reales, no texto genérico.
