# MermaOps

**Sistema multi-agente de inteligencia artificial para la reducción de merma alimentaria en supermercados**

> TFM — Máster en IA Generativa e Innovación — Evolve Business School 2026
> Autor: Álvaro Ferrer Margarit

---

## El problema

El desperdicio alimentario en el retail español cuesta entre **2% y 5% de los ingresos** por tienda. Una cadena media pierde 80.000–200.000 € anuales en merma de producto fresco. Las causas son conocidas: nadie revisa los lineales con datos en tiempo real, las decisiones de rebaja o retirada se toman tarde o no se toman, y el personal no tiene herramientas operativas adaptadas a su ritmo de trabajo.

Los sistemas actuales (Winnow, Orbisk) funcionan en grandes cadenas con hardware dedicado. **Nadie ha resuelto esto para el pequeño y mediano supermercado español**, con una interfaz conversacional real, sin hardware adicional, integrada en Telegram y accesible desde el móvil del encargado.

---

## La solución: MermaOps

Sistema de IA multi-agente que convierte datos de productos, lotes y caducidades en decisiones operativas concretas para el personal de tienda — en tiempo real, de forma autónoma, con trazabilidad y con interfaz conversacional multimodal.

```
Producto próximo a caducar
        ↓
   Kuine (orquestador)
     analiza el riesgo
        ↓
  Evaluator + Validator
  confirman la decisión
        ↓
   Price + Stock + Route
   calculan acción exacta
        ↓
  Reporter redacta el brief
        ↓
  Chuwi lo envía por Telegram
  con respuesta progresiva
        ↓
  Empleado actúa → confirma
  desde el teléfono
```

---

## Resultados cuantitativos

| Métrica | Valor |
|---------|-------|
| Precisión del sistema de evaluación | **100%** (5/5 casos) |
| Mejora sobre baseline sin IA | **+83.3 puntos porcentuales** |
| Baseline (aleatorio uniforme) | 16.7% |
| Tests automatizados | **233 / 233** (0.30 s) |
| Robustez adversarial | **23 / 23** ataques neutralizados |
| Modelos Claude integrados | 3 (Haiku, Sonnet, Opus) |
| Agentes especializados | 11 |
| Herramientas del agente supervisor | 25 |

---

## Arquitectura

### Kuine — el orquestador (Claude Opus 4.7)

Kuine es el cerebro del sistema. Ejecuta un **loop agéntico con 25 herramientas**, razona con **adaptive thinking** (interleaved entre tool calls), y coordina todos los subagentes en paralelo.

```
Kuine (Opus 4.7, adaptive thinking)
├── Evaluator (Sonnet 4.6, extended thinking)
│   └── Consenso de 3 instancias en paralelo (score ≥ 90, valor > 30€)
├── Validator (Sonnet 4.6) — adversarial, detecta errores
├── Price (Haiku 4.5) — descuento exacto sobre coste
├── Stock (Haiku 4.5) — reposición FEFO
├── Route (Sonnet 4.6) — ruta optimizada por pasillos
├── Reporter (Opus 4.7) — brief diario + informes
├── Vision (Sonnet 4.6) — análisis visual de fotos
├── Scanner (Haiku 4.5) — OpenFoodFacts integration
├── ESG (Haiku 4.5) — CO2/agua/deducción fiscal
├── Predictor (Sonnet 4.6) — riesgo próximos 5-7 días
└── Notifier — Telegram chunking
```

### Chuwi — agente conversacional real (NO es un bot)

Chuwi no responde comandos. **Razona, recuerda y actúa de forma proactiva** sin que nadie le pregunte.

- **Streaming progresivo**: el texto aparece mientras Claude genera (como escribir en WhatsApp)
- **Proactividad**: monitoriza la tienda cada 30 minutos y avisa cuando algo cambia
- **Memoria episódica**: recuerda qué pasó ayer, qué proveedor falló la semana pasada
- **Multimodal**: texto, fotos de productos (Claude Vision), notas de voz (Whisper)
- **Teclados inteligentes**: botones contextuales según la respuesta (no menús fijos)
- **Modo ruta activa**: guía al empleado acción por acción como un GPS de tienda

### Técnicas de IA implementadas

| Técnica | Implementación | Fuente |
|---------|---------------|--------|
| Extended thinking | Evaluator con razonamiento profundo | Anthropic, 2025 |
| Adaptive thinking | Kuine en todo el loop agéntico | Anthropic, mayo 2025 |
| Interleaved thinking | Entre tool calls del supervisor | τ-Bench +54% |
| Prompt caching | `cache_control: ephemeral` en todos los prompts | 90% ahorro tokens |
| Citations API | Trazabilidad normativa → decisión | Anthropic, 2025 |
| Structured output | `tool_use` para JSON garantizado | vision.py, evaluator |
| Multi-agent consensus | 3 instancias en paralelo, mayoría | casos extremos |
| Adversarial robustness | 23 ataques testados: injection, falsos datos | backend/tests |
| OTEL observability | Langfuse + AnthropicInstrumentor | auto-instrumentado |
| FEFO enforcement | Validator bloquea decisiones que ignoran orden | normativa EU |
| Streaming async | AsyncAnthropic + Telegram edit progressive | chuwi.py |

---

## Stack técnico

```
Backend        Python 3.11 · FastAPI · APScheduler · Supabase
IA             Claude API (Anthropic) · Haiku 4.5 / Sonnet 4.6 / Opus 4.7
App            Flutter 3.x · Riverpod · Supabase Realtime
Mensajería     Telegram Bot API · python-telegram-bot 21.x
Observabilidad Langfuse · OpenTelemetry · AnthropicInstrumentor
Datos externos Open-Meteo (clima) · OpenFoodFacts (productos)
Tests          pytest · 233 tests deterministas · <0.5s
```

---

## Estructura del proyecto

```
mermaops/
├── backend/
│   ├── agents/
│   │   ├── supervisor.py      # Kuine — orquestador principal
│   │   ├── evaluator.py       # Análisis de riesgo con extended thinking
│   │   ├── validator.py       # Validación adversarial de decisiones
│   │   ├── price.py           # Cálculo de descuentos
│   │   ├── stock.py           # Reposición FEFO
│   │   ├── route.py           # Ruta diaria optimizada
│   │   ├── reporter.py        # Brief diario + informes + citations
│   │   ├── vision.py          # Análisis visual con Claude Vision
│   │   ├── scanner.py         # OpenFoodFacts barcode lookup
│   │   ├── esg.py             # Métricas ESG (CO2, agua, Ley 49/2002)
│   │   ├── predictor.py       # Predicciones de merma + clima
│   │   └── notifier.py        # Alertas Telegram
│   ├── core/
│   │   ├── llm.py             # Wrapper Claude API (caching, streaming, tools)
│   │   ├── database.py        # Supabase queries
│   │   ├── chuwi.py           # Agente Telegram real (streaming, proactivo)
│   │   ├── scheduler.py       # APScheduler (7 jobs autónomos)
│   │   ├── memory.py          # Memoria episódica
│   │   └── knowledge.py       # Base de conocimiento normativo
│   ├── api/
│   │   ├── main.py            # FastAPI app
│   │   ├── routes.py          # Todos los endpoints
│   │   ├── auth.py            # JWT Supabase
│   │   └── limiter.py         # Rate limiting
│   ├── data/
│   │   ├── seed.py            # Datos demo Super Martínez
│   │   ├── advance_demo.py    # Simulación temporal (make advance N=3)
│   │   ├── demo_actions.py    # Acciones demo pre-calculadas
│   │   └── evaluation.py      # Evaluación cuantitativa automatizada
│   └── tests/                 # 233 tests (unitarios + adversariales)
├── app/                       # Flutter app (6 pantallas)
├── scripts/
│   └── setup_supabase.py      # Setup guiado de BD
├── .env.example               # Variables de entorno requeridas
├── requirements.txt
├── Makefile
└── SETUP.md                   # Guía de instalación completa
```

---

## Quick Start (5 minutos)

### 1. Requisitos

- Python 3.11+
- Flutter 3.x (para la app)
- Cuenta Supabase (gratuita)
- API Key Anthropic (~3€ para toda la demo)
- Bot Telegram (via @BotFather, gratis)

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

Variables requeridas:
```env
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://XXXX.supabase.co
SUPABASE_KEY=eyJ...
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100...
STORE_ID=demo-store-001
```

### 3. Base de datos

```bash
python scripts/setup_supabase.py   # guía interactiva
# O ejecuta los SQLs de docs/schema.sql en Supabase
```

### 4. Cargar datos demo

```bash
pip install -r requirements.txt
make seed                          # carga datos del Super Martínez
```

### 5. Arrancar

```bash
# Terminal 1: backend
make run

# Terminal 2: agente Telegram
make chuwi

# Terminal 3: app Flutter
cd app && flutter run \
  --dart-define=SUPABASE_URL=https://XXX.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=eyJ... \
  --dart-define=API_URL=http://TU_IP:8000/api/v1
```

---

## Comandos

```bash
make run          # Backend FastAPI (puerto 8000)
make chuwi        # Agente Telegram Chuwi
make seed         # Datos demo del Super Martínez
make advance N=3  # Simula 3 días de paso del tiempo (demo en vivo)
make demo-reset   # Vuelve al estado inicial
make test         # Ejecuta 233 tests
make test-eval    # Evaluación cuantitativa (100% precisión)
```

### Demo en vivo durante la presentación

```bash
make seed          # estado base hoy
make advance N=2   # simula 2 días → nuevos CRÍTICOS aparecen
# → Chuwi envía alerta automática por Telegram
# → Dashboard actualizado en tiempo real
make advance N=1   # un día más → productos de hoy están CRÍTICOS
make demo-reset    # vuelve al inicio para repetir
```

---

## Flows autónomos (sin intervención humana)

| Job | Hora | Qué hace |
|-----|------|----------|
| Brief diario | 07:30 | Kuine analiza toda la tienda, Reporter redacta, Chuwi envía |
| Check mediodía | 12:00 | Validator revisa pasillos sin acción |
| Cierre | 20:00 | Reporter genera informe del día |
| Escalación | cada 2h (8-20h) | Alerta si hay CRÍTICOS sin resolver >4h |
| Monitor proactivo | cada 30min (8-21h) | Chuwi avisa si aparece algo nuevo sin acción |
| Informe semanal | lunes 06:00 | Resumen de la semana para el dueño |
| Informe mensual | día 1, 08:00 | KPIs mensuales + deducción fiscal donaciones |

---

## Evaluación

### Cuantitativa

```
Sistema vs baseline (clasificación aleatoria):
  CRÍTICO: 1/1 correctos (100%)
  ALTO:    1/1 correctos (100%)
  BAJO:    1/1 correctos (100%)
  Sin riesgo: 2/2 correctos (100%)

Precisión sistema:  100.0%
Precisión baseline: 16.7%
Mejora:            +83.3 pp
```

### Adversarial (23 ataques)

Ataques testados: inyección de prompt, datos falsos, precio < coste, fechas inconsistentes, proveedores ficticios, escalación falsa, bypass FEFO, desbordamiento de stock, instrucciones contradictorias entre agentes.

**Resultado: 23/23 neutralizados**

---

## Seguridad

- Cero credenciales en el código fuente — todo via `os.getenv()`
- JWT Supabase verificado en cada endpoint
- Rate limiting en endpoints públicos (slowapi)
- Validación de entrada en todos los endpoints
- Modo dev: bypass solo con token `dev-bypass` explícito

---

## Donaciones y ESG

Cuando un producto lleva más de 6 horas en estado CRÍTICO sin acción asignada y tiene stock ≥ 5 unidades, Kuine propone automáticamente donación al banco de alimentos. El sistema calcula:

- CO2 evitado (kg, fuente: Poore & Nemecek 2018)
- Agua ahorrada (litros)
- Deducción fiscal estimada (Ley 49/2002, art. 17 — 35%)
- Registro en `merma_log` para el informe mensual al dueño

---

## Licencia

MIT — libre para uso académico y comercial.

---

*MermaOps — Álvaro Ferrer Margarit — TFM Máster IA Generativa e Innovación — Evolve Business School 2026*
