# MermaOps — Arquitectura Técnica

> Documento vivo. Última actualización: 2026-05-31

---

## 1. Visión general

MermaOps es un sistema multi-agente de IA para la reducción de merma alimentaria en supermercados españoles. El sistema combina:

- Un **orquestador agéntico** (Kuine) con loop real de Claude API
- Un **agente conversacional** (Chuwi) en Telegram con NLP propio
- Una **app Flutter** (móvil + web) como segundo canal de gestión
- Un **pipeline de datos** sobre Supabase (PostgreSQL + Auth + Realtime)

---

## 2. Diagrama de componentes

```
┌──────────────┐     ┌───────────────────────────────────────────────────────┐
│  Telegram    │     │              Backend FastAPI (puerto 8001)              │
│  Bot Chuwi   │────▶│  /api/v1/                                               │
└──────────────┘     │  ├── /scan      → Kuine → [Evaluador | ForkMerge]      │
                     │  ├── /brief/run → Kuine (loop 20 iter, timeout 5min)   │
┌──────────────┐     │  ├── /actions   → database                              │
│  Flutter App │────▶│  ├── /stats/*   → analytics queries                    │
│  (web/móvil) │     │  ├── /reports/* → Reportero → PDF                      │
└──────────────┘     │  ├── /agent/chat → Chuwi (chat_direct)                 │
                     │  └── /demo/*    → advance_demo                          │
                     └───────────────────────────────┬───────────────────────┘
                                                     │
                          ┌──────────────────────────▼────────────────────┐
                          │          Capa de agentes IA                    │
                          │                                                │
                          │  Kuine (Opus 4.7) ──▶ Evaluador (Sonnet 4.6) │
                          │         │         ──▶ ForkMerge (3×Sonnet     │
                          │         │              + Opus síntesis)        │
                          │         │         ──▶ Consenso (3×Sonnet)     │
                          │         │         ──▶ Validador (Sonnet 4.6)  │
                          │         └─────────▶  Reportero (Sonnet 4.6)  │
                          │                                                │
                          │  Chuwi (Sonnet 4.6) ──▶ Reflexion (Haiku)    │
                          │  Predictor (Haiku 4.5) ──▶ Open-Meteo API    │
                          │  Visión (claude-3-5-sonnet) ← foto base64    │
                          └──────────────────────┬─────────────────────┘
                                                 │
                                 ┌───────────────▼──────────────┐
                                 │   Supabase (PostgreSQL)       │
                                 │   - stores, products, batches │
                                 │   - actions, merma_log        │
                                 │   - agent_conversations       │
                                 │   - agent_sessions, memory    │
                                 └──────────────────────────────┘
```

---

## 3. Sistema multi-agente — agentes reales vs. heurísticos

Esta distinción es importante para la honestidad académica:

### Agentes con llamada LLM real (Claude API)

| Agente | Modelo | Función principal | Técnica destacada |
|--------|--------|-------------------|-------------------|
| **Kuine** (orquestador) | Opus 4.7 | Análisis diario, escaneo, decisiones | Loop agéntico, 16 tools, extended thinking |
| **Chuwi** (Telegram) | Sonnet 4.6 | Conversación, comandos, voz | Reflexion loop, intent classification 0-token |
| **Evaluador** | Sonnet 4.6 | Score de riesgo 0–100 | Extended thinking adaptativo |
| **ForkMerge** | 3×Sonnet + Opus (síntesis) | Evaluación paralela casos valor>50€ | Fork-merge multi-agente (Anthropic 2024) |
| **Validador** | Sonnet 4.6 | 23 ataques adversariales | Corrección de decisiones extremas |
| **Consenso** | Sonnet 4.6 | Verificación casos críticos (score≥90) | 3 instancias paralelas, regla 2/3 |
| **Predictor** | Haiku 4.5 | Predicción de merma 7 días | Combinación clima + historial |
| **Visión** | claude-3-5-sonnet | Análisis visual de productos | Image understanding |
| **Reportero** | Sonnet 4.6 | Briefs y resúmenes | Síntesis de datos estructurados |

### Módulos deterministas (heurísticos, no LLM)

Estos módulos son **decisiones de diseño justificadas**: no todo necesita LLM. El costo computacional y de latencia de llamar a Claude para calcular un descuento lineal sería injustificable.

| Módulo | Función | Justificación |
|--------|---------|---------------|
| **price.py** | Cálculo de descuento óptimo | Fórmula determinista: días_restantes × factor_categoría |
| **stock.py** | Decisión de reposición FEFO | Reglas de negocio claras, umbral configurable |
| **route.py** | Ruta diaria por urgencia | Ordenación por score descendente, agrupación por pasillo |
| **notifier.py** | Alertas Telegram | Formateo y envío, sin decisión IA |

---

## 4. Loop agéntico de Kuine

```
Prompt usuario/sistema
        │
        ▼
 Claude API (Opus 4.7)
 ┌─────────────────────┐
 │  ¿Necesito tools?   │──NO──▶ Respuesta final
 └────────┬────────────┘
          │ SÍ (hasta 20 iteraciones)
          ▼
 _make_executor(store_id) ─────▶ tool_name ────▶ resultado
          │
          │ evaluate_all_products_parallel → ThreadPoolExecutor
          │ create_action                  → Supabase insert
          │ calculate_discount             → price.calculate()
          │ get_warehouse_stock            → Supabase query
          │ store_memory / recall_memory   → agent_memory table
          │ search_food_regulations        → pgvector RAG
          │ think                          → razonamiento interno
          │ ... (16 tools total)
          │
          ▼
 Resultado devuelto a Claude
 (siguiente iteración)
```

**Umbral de consenso**: cuando `score ≥ 90` Y `value_at_risk ≥ 30€`, se activa `consensus.py` con 3 instancias paralelas del evaluador. La decisión solo se toma si ≥2/3 instancias coinciden.

---

## 5. Patrón Fork-Merge (evaluación paralela de alto impacto)

Implementa el patrón fork-merge descrito en "Building Effective Agents" (Anthropic, 2024) para productos con `value_at_risk > 50€` O lotes ya caducados (`days_left ≤ 0`).

```
                      ┌──────────────────────────────────┐
                      │   should_use_fork_merge()?        │
                      │   value > 50€ OR days_left ≤ 0   │
                      └──────┬───────────────────────────┘
                             │ SÍ
                             ▼
              ┌──────────────────────────────────┐
              │     ThreadPoolExecutor (3 ramas)  │
              │                                   │
              │  rama "clearance" ─────────────── │──▶ Sonnet 4.6
              │  (maximizar sell-through:         │     "rebajar agresivo"
              │   descuento para vaciar lote)     │
              │                                   │
              │  rama "margin" ──────────────────-│──▶ Sonnet 4.6
              │  (proteger margen bruto:          │     "no vender bajo coste"
              │   análisis coste vs. precio)      │
              │                                   │
              │  rama "donation" ──────────────── │──▶ Sonnet 4.6
              │  (impacto social + Ley 49/2002:   │     "donar, deducción 35%"
              │   deducción fiscal disponible)    │
              └──────────────┬────────────────────┘
                             │ 3 hipótesis en paralelo
                             ▼
                    ┌─────────────────┐
                    │   Opus 4.7      │
                    │   (síntesis)    │
                    │  "¿cuál de las  │
                    │  3 hipótesis    │
                    │  es más sólida?"│
                    └────────┬────────┘
                             │
                             ▼
                    Decisión final estructurada
                    {action, price_adjustment_pct,
                     reasoning, fork_merge_used: true}
```

**Activación en run_scan()**: Kuine llama a `should_use_fork_merge(product, batches)`. Si se activa, sustituye al Evaluador estándar. Coste: 3× Sonnet (ramas) + 1× Opus (síntesis) — solo para los casos de mayor impacto económico.

**Justificación del umbral**: El coste de equivocarse en un lote de 50€ supera el coste de las 4 llamadas adicionales. Para productos de bajo valor, el Evaluador estándar es suficiente.

---

## 6. Reflexion Loop (aprendizaje continuo)

Basado en Shinn et al. (2023) "Reflexion: Language Agents with Verbal Reinforcement Learning":

```
Conversación Chuwi ──▶ herramienta analyze_product usada
                              │
                              ▼
                    reflexion.async_generate_and_save()
                    (Haiku 4.5, fire-and-forget)
                              │
                    "¿Qué aprendí de esta interacción?"
                    "¿Qué haría diferente?"
                              │
                              ▼
                    agent_memory (key: "reflexion_lessons")
                    Buffer de 5 lecciones más recientes
                              │
                              ▼
                    Próximo sistema_prompt de Chuwi
                    incluye lecciones como contexto
```

---

## 7. Clasificación de intención zero-token

```python
intents = [
  ("consulta_estado",    ["estado", "cuántos", "qué hay", "muéstrame"]),
  ("pedir_brief",        ["brief", "resumen", "informe", "análisis del día"]),
  ("completar_accion",   ["completado", "hecho", "ya", "listo", "terminado"]),
  ("pedir_ruta",         ["ruta", "recorrido", "orden", "por dónde empiezo"]),
  ("registrar_donacion", ["donación", "banco de alimentos", "donar"]),
  ("registrar_merma",    ["tirar", "caducado", "se ha puesto malo", "merma"]),
  ("otros",              []),  # fallback → LLM decide
]
```

**Ventaja**: 0 tokens Claude API en clasificación. Solo se llama al LLM si el intent es "otros" o si la respuesta requiere datos del sistema. **Ahorro estimado: ~60% de llamadas evitadas** en consultas simples.

**Nota sobre `registrar_merma`**: es el único intent sin contexto precargado. Los detalles (qué producto, cuánto, motivo) requieren diálogo con el usuario, por lo que el agente usa su loop completo. Ver `chuwi_intent.py` para la justificación técnica.

---

## 8. Prompt Caching — ROI real

Los 16 tools de Kuine y los tools de Chuwi son estáticos entre llamadas de un mismo usuario. Se usa `cache_control: {"type": "ephemeral"}` en el último tool de cada lista (marca el punto de cacheo).

### ¿Qué se cachea?

| Elemento | Tokens aprox. | Cacheable |
|----------|--------------|-----------|
| SYSTEM_BASE (instrucciones base) | ~800 | Sí, siempre |
| Lista de 16 tools de Kuine | ~3.000 | Sí, TTL 5min |
| Lista de tools de Chuwi | ~2.000 | Sí, TTL 5min |
| Historial de conversación | Variable | No (cambia cada turno) |

### Impacto económico estimado

Precio de Sonnet 4.6: $3/MTok input, $0.30/MTok cached input (90% descuento).

Ejemplo en un brief diario (Opus 4.7, ~8 iteraciones):
- Sin caché: 8 × 4.000 tokens tools = 32.000 tokens input → ~$0.48
- Con caché caliente: 8 × 400 tokens uncached + 8 × 3.600 cached = ~$0.058
- **Ahorro por brief**: ~88% del coste de input

Ejemplo en conversación Chuwi (Sonnet 4.6, usuario activo, 6 turnos/sesión):
- Sin caché: 6 × 2.500 = 15.000 tokens → $0.045
- Con caché: 6 × 500 uncached + 6 × 2.000 cached → $0.007
- **Ahorro por sesión**: ~85%

- **TTL de caché**: 5 minutos (límite Anthropic — conversaciones activas mantienen el caché caliente)
- **Visibilidad**: endpoint `/api/v1/llm/stats` devuelve `cache_hit_pct` y `saved_usd` reales acumulados

---

## 9. Extended Thinking — latencia adaptativa

- **`fast=True`** (escaneo, preguntas Telegram): `enabled` mode + `budget_tokens=1500` → ~5–8s
- **`fast=False`** (brief diario, análisis profundo): `adaptive` mode → sin límite, el modelo decide

La elección es consciente: un empleado esperando el resultado de un escaneo no puede esperar 40 segundos.

---

## 10. Métricas ESG — fuentes y cálculos

### CO₂ evitado
Basado en **Poore & Nemecek (2018)**, Science 360(6392):

| Categoría | kg CO₂e / kg producto |
|-----------|----------------------|
| Carne vacuno | 27.0 |
| Lácteos | 3.2 |
| Cereales | 1.4 |
| Frutas/Verduras | 0.4 |

### Agua ahorrada
Basado en **Mekonnen & Hoekstra (2011)**, Water footprint:

| Categoría | litros / kg producto |
|-----------|---------------------|
| Carne vacuno | 15,415 |
| Lácteos | 1,020 |
| Cereales | 1,644 |
| Frutas/Verduras | 322 |

### Donaciones — deducción fiscal
**Ley 49/2002** (Art. 20): donaciones a entidades sin ánimo de lucro con derecho a deducción del **35%** sobre el valor de lo donado (hasta 150€ primeros, luego 35%). El sistema calcula la deducción sobre el valor de coste del producto.

---

## 11. Benchmarks de industria (fuentes reales)

| Métrica | Referencia | Valor industria |
|---------|-----------|-----------------|
| Tasa de merma (valor) | WRAP Food Waste Report 2023 | 1.3% del revenue |
| Tasa de recuperación | FAO Food Loss and Waste 2022 | 28% del total generado |
| Merma España supermercados | AECOC Spain 2023 | 2.1% del revenue |

**Limitación**: el cálculo de `waste_rate_pct` asume que el stock activo ≈ 2 semanas de ventas (sin datos reales de facturación). Esta estimación está documentada en el código y en la UI con el texto "estimación basada en stock activo". No se presenta como dato exacto.

---

## 12. Decisiones de diseño justificadas

### ¿Por qué Supabase y no PostgreSQL directo?
- **Auth integrada**: JWT sin implementar servidor de autenticación propio
- **Realtime**: el badge de acciones críticas en Flutter usa Supabase Realtime (WebSocket)
- **RLS (Row Level Security)**: aislamiento por `store_id` a nivel de BD, no de aplicación
- **Storage**: preparado para fotos de productos (aunque en demo no se usa)

### ¿Por qué puerto 8001 y no 8000?
El puerto 8000 está bloqueado en el entorno de desarrollo por `Manager.exe` de Windows. Documentado en CLAUDE.md y en el Makefile.

### ¿Por qué STORE_ID es una variable de entorno y no se extrae del JWT?

Decisión de diseño para el MVP single-tenant. El sistema está diseñado para una tienda por despliegue — `STORE_ID=demo-store-001` en `.env` es el identificador de la tienda activa. El aislamiento entre tiendas se garantiza a nivel de BD mediante RLS (`store_id` en cada tabla), no a nivel de aplicación.

Para escalar a multi-tenant real, el `store_id` se extraería del claim del JWT (Supabase permite claims personalizados en `app_metadata`). La arquitectura soporta este cambio sin modificar la lógica de negocio — solo el punto de extracción del `store_id` en `auth.py`.

Esta limitación está documentada en la sección de limitaciones y es una decisión consciente de alcance de TFM, no un bug.

### ¿Por qué clasificación keyword en lugar de LLM para intents?
Coste y latencia. Un mensaje de Telegram que dice "¿cuántos críticos hay?" no necesita 500 tokens de Claude para clasificarse. El fallback LLM cubre los casos ambiguos.

### ¿Por qué el consenso solo para score≥90 Y valor≥30€?
Doble umbral para evitar falsos positivos: un yogur de 0.80€ con score 92 no necesita consenso de 3 agentes. El umbral de 30€ asegura que solo los casos con impacto económico real activan el mecanismo costoso.

---

## 13. Limitaciones conocidas y trabajo futuro

| Limitación | Impacto | Workaround actual |
|------------|---------|-------------------|
| Sin datos de ventas reales (POS) | `waste_rate_pct` es estimado (stock activo ÷ 14 días) | Campo `methodology_note` en `/stats/benchmark` lo documenta |
| STORE_ID single-tenant por despliegue | No soporta múltiples tiendas en la misma instancia | Diseño documentado; escala con JWT claims sin cambiar lógica de negocio |
| Sin cámara en demo web | Análisis visual solo en móvil | Entrada manual de barcode en web |
| Historial de precios no persistido | Predictor usa solo fecha+cantidad | Historial de merma como proxy |
| Chuwi no es multiusuario concurrente | Colisiones en alta concurrencia | Rate limiting + caché de usuarios |
| Búsqueda semántica RAG básica | Sin embeddings actualizados | Índice estático en knowledge_base |

---

*Elaborado para el TFM "MermaOps: Sistema Multi-Agente de IA para Reducción de Merma Alimentaria en Supermercados Españoles"*
*Máster en Inteligencia Artificial — 2026*
