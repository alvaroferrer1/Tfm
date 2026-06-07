# skill: mermaops-demo-docs
Objetivo: Demo de 10 min que gane la defensa del TFM. Sin improvisación.
Cuándo: Al preparar la defensa, al tocar advance_demo.py, al hacer el guión.

Guión de demo (10 min exactos):

**0:00-1:00 — Arranque en vivo**
- `make seed && make advance N=2` → "simulamos que han pasado 2 días"
- Dashboard carga: mostrar CRÍTICOS en rojo, barra de progreso
- Frase: "El sistema lleva trabajando 48 horas. Kuine ha analizado estos lotes."

**1:00-3:00 — Kuine detecta y actúa**
- Ir a Acciones → filtrar CRÍTICO
- Mostrar que hay acciones ya generadas automáticamente (no manuales)
- Frase: "Kuine no espera a que nadie le diga. Detecta, razona y propone."

**3:00-5:00 — Chuwi en Telegram (mostrar móvil)**
- Abrir @ChuwiMermaOpsBot → escribir "¿qué hay urgente?"
- Ver respuesta con datos reales (no inventados)
- Enviar foto de producto → análisis visual en <15s
- Frase: "Chuwi es el canal de comunicación entre el sistema y el encargado."

**5:00-7:00 — Avanzar un día más en vivo**
- `curl -X POST http://localhost:8001/api/demo/advance -d '{"days":1}'`
- Telegram recibe alerta proactiva automáticamente
- Dashboard se actualiza → nuevos CRÍTICOS
- Frase: "El sistema reacciona solo. Sin que nadie haga nada."

**7:00-9:00 — Métricas y rigor técnico**
- Abrir pantalla Agentes → mostrar 11 agentes, modelos, runs de Kuine
- Mostrar Informes → supplier risk con negociación
- Frase: "323 tests, 23 ataques adversariales neutralizados, 100% evaluación."

**9:00-10:00 — Impacto real**
- Mostrar merma_log → productos donados al banco de alimentos
- Frase: "En España se tiran 7.7M toneladas de comida al año. Esto lo frena."

Estado antes de la demo (preparar el día antes):
- [ ] `make seed` ejecutado con éxito
- [ ] Backend arranca con `make start`
- [ ] Telegram responde a /start con datos reales
- [ ] Dashboard muestra CRÍTICO/ALTO/BAJO con colores
- [ ] `make advance N=2` genera mínimo 2 CRÍTICO + 3 ALTO

Datos que deben estar presentes (verificar):
- Batches activos: ≥20
- Acciones pendientes: ≥10 (mínimo 3 CRÍTICO)
- Productos únicos: ≥15
- Proveedores: ≥3
- Donaciones previas: ≥2 (para mostrar en merma_log)

Si algo falla durante la demo:
- Backend caído → `make start` (30s) → continuar con Telegram
- Telegram no responde → mostrar logs de agent_runs en Flutter
- Flutter error → abrir http://localhost:3000 en Chrome (fallback web)
- Base de datos vacía → `make seed` en vivo (es rápido, parece intencional)
