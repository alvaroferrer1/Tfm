# MermaOps — Agentes y Módulos

> Descripción técnica de cada componente del sistema. Última actualización: 2026-05-31

---

## Agentes con LLM real (Claude API)

### Kuine — Orquestador principal
- **Modelo**: claude-opus-4-7
- **Tools**: 16 herramientas reales conectadas a Supabase
- **Loop**: hasta 20 iteraciones por sesión
- **Extended thinking**: adaptativo (sin límite de tokens, decide el modelo)
- **Activa**: daily brief (07:30), intraday (12:00), cierre (20:00), escalaciones cada 2h
- **Tools disponibles**:
  - `think` — razonamiento interno antes de decisiones críticas
  - `get_expiring_batches` — lotes que caducan en N días
  - `get_warehouse_stock` — stock en almacén por producto
  - `recall_memory` / `store_memory` — memoria episódica en `agent_memory`
  - `evaluate_product_risk` — llama al Evaluador (score 0-100)
  - `calculate_discount` — llama al módulo Precio
  - `create_action` — crea acción en BD (rebajar/donar/retirar/revisar)
  - `get_pending_actions` — lista de acciones pendientes
  - `search_food_regulations` — RAG sobre normativa alimentaria (pgvector)
  - `get_day_context` — día de la semana, hora, brief anterior
  - `get_merma_history` — historial de merma de N días
  - `evaluate_all_products_parallel` — evaluación batch con ThreadPoolExecutor
  - `get_supplier_stats` — estadísticas por proveedor
  - `get_order_suggestions` — sugerencias de pedido semanal
  - `get_roi` — ROI de acciones completadas (merma evitada)

---

### Chuwi — Bot de Telegram
- **Modelo**: claude-sonnet-4-6
- **Iteraciones**: hasta 6 por mensaje
- **Técnicas**: prompt caching, intent classification 0-token, reflexion loop, rate limiting
- **Comandos activos**: 23 comandos + callbacks + inline query + voz + foto
- **Intent classification** (0 tokens Claude) — ver `backend/core/chuwi_intent.py`:
  - `consulta_estado` → precarga conteo de acciones críticas/altas
  - `pedir_brief` → precarga fecha + valor en riesgo del último brief
  - `completar_accion`, `pedir_ruta` → precarga top 3 acciones por prioridad
  - `registrar_donacion` → precarga estadísticas de donaciones del mes
  - `registrar_merma` → **LLM fallback** (sin contexto precargado). Flujo: el empleado informa de un producto deteriorado o caducado → Chuwi llama `get_pending_actions` para localizar el lote → llama `complete_action` con `action_type=retirar` → escribe en `merma_log` vía `database.log_merma({store_id, batch_id, quantity_lost, value_lost, reason, date})`. La decisión final (retirar vs. donar si aún es apto) la toma Claude tras analizar días restantes y categoría del producto. Sin contexto precargado porque producto, cantidad y motivo sólo se conocen durante el diálogo.
  - `crear_accion`, `configuracion`, `pregunta_libre` → LLM fallback
- **Módulos**: `chuwi.py` (handlers, run), `chuwi_persistence.py` (historial, sesiones, caché), `chuwi_intent.py` (clasificador)
- **Reflexion loop**: aprende de cada interacción con Kuine, guarda 5 lecciones en `agent_memory`

---

### Evaluador
- **Modelo**: claude-sonnet-4-6
- **Score**: 0–100 (0=sin riesgo, 100=caducado hoy con stock alto)
- **Extended thinking**: `enabled` (budget 1500 tokens) para score ≥ 65, `disabled` para casos simples
- **Output**: risk_level (CRÍTICO/ALTO/MEDIO/BAJO), action, price_adjustment_pct, reasoning

---

### ForkMerge — Evaluador paralelo para casos críticos
- **Activación**: cuando `value_at_risk > 50€` O `days_left ≤ 0`
- **Patrón**: 3 ramas paralelas con perspectivas distintas:
  - `clearance`: maximizar sell-through (rebajar agresivamente)
  - `margin`: proteger margen bruto (no vender bajo coste)
  - `donation`: impacto social + deducción fiscal Ley 49/2002
- **Síntesis**: Opus sintetiza las 3 hipótesis y elige la más sólida
- **Referencia**: Anthropic multi-agent fork-merge pattern, 2025
- **Coste**: 3× Sonnet (ramas) + 1× Opus (síntesis) — solo para casos de alto impacto

---

### Validador
- **Modelo**: claude-sonnet-4-6
- **Función**: corrección adversarial de decisiones extremas
- **23 ataques neutralizados**: barcodes maliciosos, inyección de prompt, escaladas injustificadas, etc.
- **Output**: `VALIDADO` / `CORREGIDO` / `RECHAZADO` + `final_action` + `explanation`

---

### Consenso
- **Modelo**: claude-sonnet-4-6 × 3 instancias paralelas
- **Activación**: score ≥ 90 AND value_at_risk ≥ 30€
- **Regla**: la decisión solo se toma si ≥ 2/3 instancias coinciden en la acción
- **Justificación del umbral**: un yogur de 0.80€ con score 92 no necesita consenso; el umbral de valor evita activaciones innecesarias

---

### Predictor
- **Modelo**: claude-haiku-4-5
- **Fuentes**: historial de merma (Supabase) + clima en tiempo real (Open-Meteo API)
- **Output**: predicciones por producto para los próximos 7 días con `risk_score` y `factors`
- **Factores**: temperatura, humedad, día de la semana, proximidad a festivos

---

### Visión
- **Modelo**: claude-haiku-4-5-20251001
- **Input**: imagen en base64 (foto del producto con cámara)
- **Output**: estado (fresco/deteriorado/caducado), confianza %, fecha visible en etiqueta, acción recomendada
- **Flujo**: app Flutter → `POST /scan/vision` → Visión → respuesta estructurada

---

### Reportero
- **Modelo**: claude-sonnet-4-6
- **Genera**: briefs diarios, informes semanales (PDF), informes mensuales (PDF)
- **PDF**: reportlab con branding MermaOps, tablas de merma, gráficas textuales, métricas ESG
- **Scheduler**: diario 07:30, semanal lunes 06:00, mensual día 1 08:00

---

## Módulos deterministas (heurísticos — sin LLM)

### Precio (`price.py`)
- **Decisión de diseño**: el cálculo de descuento óptimo es determinista. Usar LLM para calcular `18% × (5 - days_left)` sería desperdicio de recursos.
- **Fórmula**: `discount_pct = base_factor × urgency_multiplier × category_factor`
- **Categorías**: panadería (factor 1.4), carne/pescado (1.3), lácteos (1.2), resto (1.0)
- **Salida**: `new_price`, `discount_pct`, `recommendation_text`

### Stock (`stock.py`)
- **Algoritmo**: FEFO (First Expired First Out) — estándar de la industria alimentaria
- **Decisión**: reponer cuando `store_qty < reorder_threshold AND warehouse_qty > 0`
- **Latencia**: < 1ms (sin red, sin LLM)

### Notificador (`notifier.py`)
- **Función**: formateo HTML de alertas Telegram + envío via Bot API
- **Tipos**: alertas críticas, briefs diarios, donaciones, inline keyboards para decisiones
- **Proactive monitor**: cada 30min entre 08:00-21:00, envía alertas si hay nuevos críticos

---

## Scheduler (APScheduler)

| Job | Hora | Función |
|-----|------|---------|
| Brief diario | 07:30 | `run_daily_brief()` — Kuine loop completo |
| Check intraday | 12:00 | `run_intraday_check()` — validación de pendientes |
| Cierre | 20:00 | `run_closing()` — resumen del día |
| Informe semanal | Lun 06:00 | `run_weekly_report()` — Reportero |
| Informe mensual | Día 1 08:00 | `run_monthly_report()` — Reportero |
| Escalación | Cada 2h (8-20h) | `run_escalation()` — si hay pendientes >4h |
| Monitor proactivo | Cada 30min (8-21h) | `run_proactive_monitor()` — alertas nuevos críticos |
