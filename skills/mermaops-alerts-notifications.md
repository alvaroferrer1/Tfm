# skill: mermaops-alerts-notifications
Objetivo: Alertas proactivas reales que demuestren que el sistema trabaja solo.
Cuándo: Al tocar notifier.py, scheduler.py, o cualquier alerta Telegram.

Flujo de alerta proactiva:
scheduler → proactive_monitor (cada 30min, 8h-21h)
    → notifier.py → evalúa batches CRÍTICOS sin acción reciente
    → Telegram vía send_message()
    → agent_messages (role=system, agent_source=notifier)

Jobs scheduler activos (no cambiar horarios sin razón):
- daily_brief: 07:30 → reporter.py → brief del día
- intraday: 12:00 → supervisor → revisión mediodía
- closing: 20:00 → supervisor → cierre día
- weekly: lunes 06:00 → weekly report
- monthly: día 1 08:00 → monthly report
- escalation: cada 2h (8-20h) → productos >6h en CRÍTICO
- proactive_monitor: cada 30min (8-21h) → cambios de estado

Qué hace notifier.py (funciones reales):
- `notify_critical_batch()` → alerta inmediata cuando algo cruza a CRÍTICO
- `notify_daily_summary()` → resumen diario con acciones pendientes
- `notify_escalation()` → cuando CRÍTICO lleva >6h sin atención → propone donación

Formato Telegram para alertas (sin markdown, sin asteriscos):
```
🔴 CRÍTICO — [Nombre producto] (Pasillo X)
Caduca: mañana | Unidades: N
Kuine recomienda: [acción concreta]
```

Reglas:
- Máximo 1 alerta por producto por hora (deduplicar con agent_memory)
- Si Telegram falla: log error, continuar (nunca explotar scheduler)
- Alertas proactivas → agent_source="notifier" en agent_messages
- Donación propuesta → inline keyboard [Sí, donar] [No, rebajar]

Checklist al tocar notifier:
- [ ] ¿Deduplica alertas con agent_memory?
- [ ] ¿Tiene try/except que no detiene el scheduler?
- [ ] ¿El mensaje tiene max 200 chars (legible en notificación)?
- [ ] ¿Loguea en agent_messages con agent_source="notifier"?
