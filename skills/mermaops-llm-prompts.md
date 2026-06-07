# skill: mermaops-llm-prompts
Objetivo: Uso correcto de Claude. Coste controlado. Outputs útiles.
Cuándo: Al tocar llm.py, prompts en agentes, o cuando las respuestas son malas.

Modelos y cuándo usarlos:
Opus 4.7 → Kuine supervisor solo. Razonamiento complejo, decisiones críticas.
Sonnet 4.6 → Chuwi, Evaluador, Validador, Reportero. Calidad alta, precio razonable.
Haiku 4.5 → Precio, Stock, Predictor, Visión. Tareas simples o alta frecuencia.

Regla de la IA: No calcular lo que el motor de reglas ya calcula.
- Urgencia → motor de reglas (days_left, priority_score). NO pedir a la IA.
- Precio de descuento → price.py con lógica fija. IA solo si hay ambigüedad.
- Estado visual de producto → vision.py (Haiku). IA necesaria aquí.
- Brief y resumen → reporter.py (Sonnet). IA necesaria aquí.
- Respuesta a empleado → Chuwi (Sonnet). IA necesaria aquí.

Prompts en producción:
- CHUWI_SYSTEM: chuwi.py línea 112. Sin asteriscos ni markdown.
- _VISION_SYSTEM: vision.py línea 50. Diagnóstico directo y operativo.
- Kuine: supervisor.py. No hace el trabajo sucio, delega.

Checklist al tocar un prompt:
- [ ] ¿El prompt dice "sin asteriscos" y "sin markdown" si va a Telegram?
- [ ] ¿El max_tokens es el mínimo necesario (no 4096 por defecto)?
- [ ] ¿El modelo es el adecuado para la tarea?
- [ ] ¿El prompt tiene instrucción de fallback si no hay datos?
- [ ] ¿_log_usage() registra la llamada para auditoría de coste?

Si la IA inventa datos: revisar que el prompt pide usar herramientas reales primero.
Si la IA tarda mucho: bajar max_tokens o cambiar a modelo más ligero.
