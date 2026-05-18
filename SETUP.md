# MermaOps — Guía de instalación y puesta en marcha

Este documento cubre todo lo necesario para ejecutar MermaOps en local desde cero.

---

## Requisitos previos

| Herramienta | Versión mínima |
| ----------- | -------------- |
| Python | 3.11 |
| Flutter SDK | 3.22 |
| Dart SDK | 3.5 |
| Node.js (para Supabase CLI opcional) | 18 |

Cuentas externas necesarias:

- [Supabase](https://supabase.com) — gratis hasta 500 MB
- [Anthropic](https://console.anthropic.com) — pagar por uso (API key)
- [Telegram BotFather](https://t.me/BotFather) — gratis (`/newbot`, llamarlo Chuwi)

---

## 1. Clonar y configurar el entorno

```bash
git clone https://github.com/<tu-usuario>/mermaops.git
cd mermaops
```

Copiar el archivo de variables de entorno y rellenar los valores:

```bash
cp .env.example .env
```

Editar `.env` con los valores reales:

```env
ANTHROPIC_API_KEY=sk-ant-...          # Consola Anthropic
SUPABASE_URL=https://xxxx.supabase.co # Dashboard Supabase → Settings → API
SUPABASE_KEY=eyJ...                    # anon/public key
TELEGRAM_BOT_TOKEN=123456:ABC-...      # BotFather → /newbot
TELEGRAM_CHAT_ID=-100...               # ID del grupo o canal (ver nota abajo)
APP_ENV=development
APP_PORT=8000
STORE_ID=demo-store-001
OPENAI_API_KEY=sk-...                  # Opcional — solo para voz en Chuwi
```

> **TELEGRAM_CHAT_ID**: Añade el bot al grupo, manda un mensaje, y consulta
> `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver el chat_id.

---

## 2. Setup automático (recomendado)

Ejecuta el script interactivo que guía todo el proceso:

```bash
python scripts/setup_supabase.py
```

Hace automáticamente: `.env` → conexión Supabase → schema → bucket → seed → `flutter pub get`.

---

## 2b. Supabase — crear las tablas (manual)

1. Abre tu proyecto Supabase → **SQL Editor**
2. Copia el contenido de `docs/schema.sql` y ejecútalo completo
3. Verifica que se crearon las tablas: `stores`, `products`, `batches`, `actions`,
   `merma_log`, `daily_briefs`, `weekly_reports`, `monthly_reports`,
   `donations`, `suppliers`, `supplier_merma`, `store_comparison`, etc.

---

## 3. Backend — instalar dependencias y arrancar

```bash
# Instalar dependencias Python
make install
# o manualmente:
pip install -r requirements.txt

# Cargar datos demo (Super Martinez con 30 días de histórico realista)
make seed

# Arrancar el servidor FastAPI
make run
```

El servidor arranca en `http://localhost:8000`.
Documentación automática de la API en `http://localhost:8000/docs` (Swagger UI).

Para verificar que todo funciona:

```bash
curl http://localhost:8000/health
# → {"status":"ok","store_id":"demo-store-001","date":"...","version":"1.0.0"}

curl http://localhost:8000/api/v1/ping
# → {"pong":true}
```

---

## 4. Telegram — activar el agente Chuwi

Con el servidor corriendo, el bot Chuwi arranca automáticamente.
Busca tu bot en Telegram por el nombre que le diste a BotFather y escribe `/start`.

Comandos disponibles:

| Comando | Acceso | Descripción |
| ------- | ------ | ----------- |
| `/start` | todos | Saludo y lista de comandos |
| `/brief` | todos | Brief del día |
| `/acciones` | todos | Acciones pendientes |
| `/scan <barcode>` | todos | Analizar un producto |
| `/stats` | todos | Dashboard KPIs (semáforo, valor en riesgo, merma 7d, donaciones) |
| `/ruta` | todos | Ruta optimizada del día (GPS de tienda) |
| `/merma` | todos | Merma de los últimos 7 días |
| `/donaciones` | todos | Impacto social del mes |
| `/donar` | todos | Flujo guiado de donación (producto → entidad → cantidad → confirmar) |
| `/proveedores` | encargado | Ficha de proveedores con riesgo |
| `/pedido` | encargado | Sugerencia de pedido semanal |
| `/esg` | encargado | Métricas ESG: CO₂, agua, deducción fiscal |
| `/prediccion` | encargado | Predicción de merma con meteorología (próximos 5 días) |
| `/runbrief` | encargado | Generar brief manualmente ahora |
| `/citar <cat> [dias]` | encargado | Normativa citada para una categoría (ej: `/citar lacteos 2`) |
| `/tour` | todos | Explicación del sistema y los agentes |

---

## 5. Flutter app — instalar y ejecutar

```bash
cd app
flutter pub get
flutter run
```

La app se conecta a Supabase directamente (auth y realtime) y al backend FastAPI para escaneos.

La app lee sus credenciales como `--dart-define` al compilar. Para desarrollo local:

```bash
flutter run \
  --dart-define=SUPABASE_URL=https://xxxx.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=eyJ... \
  --dart-define=API_URL=http://localhost:8000/api/v1
```

En dispositivo físico sustituye `localhost` por la IP local del ordenador (ej. `192.168.1.100`).

### Pantallas de la app

| Pantalla | Descripción |
| -------- | ----------- |
| Login | Auth Supabase — email + password |
| Dashboard | KPIs, sparkline merma, comparativa tiendas, brief del día |
| Escanear | Cámara barcode → análisis IA completo con precio y acción |
| Acciones | Pendientes con foto-evidencia + historial por empleado |
| Mapa | Mapa de pasillos por urgencia + QR por sección + lista FEFO |
| Informes | Diarios / Semanales / Mensual / Merma+CSV / Proveedores / Pedidos |

---

## 6. Crear usuario demo en Supabase

1. Supabase Dashboard → **Authentication** → **Users** → **Add user**
2. Email: `encargado@supermart.es` | Password: `demo1234`
3. En **SQL Editor**, vincular el usuario a la tienda:

```sql
INSERT INTO users (id, email, role, store_id, telegram_user_id)
VALUES (
  '<uuid-del-usuario>',
  'encargado@supermart.es',
  'manager',
  'demo-store-001',
  NULL  -- Rellenar con el Telegram user ID si se usa Chuwi
);
```

---

## 7. Tests

```bash
# Tests rápidos (sin llamadas a LLM ni Supabase)
make test-fast

# Todos los tests con cobertura
make test-cov

# Solo un módulo
pytest backend/tests/test_validator.py -v
```

Total: **233 tests** en 17 archivos. Todos deterministas (sin LLM ni Supabase).
Los stubs de supabase/dotenv/anthropic están en `conftest.py` — los tests corren
en cualquier entorno sin instalar las dependencias de producción.
Los tests de integración llevan `@pytest.mark.integration` y se saltan en `test-fast`.

Los **23 tests adversariales** (`test_adversarial.py`) cubren tres vectores de ataque:
inyección de datos falsos, prompt injection en campos libres y recomendaciones
conflictivas entre agentes. Referencia: Frontiers in AI 2026 (doi:10.3389/frai.2026.1784484).

---

## 10. Evaluación cuantitativa (para el TFM)

Genera las métricas de precisión que el tribunal exige para matrícula de honor:

```bash
# Sin API key — todos los casos deterministas pasan
python -m backend.data.evaluation

# Guardar resultados en JSON para la memoria
python -m backend.data.evaluation --output eval_results.json

# Solo un componente
python -m backend.data.evaluation --component validator
```

Resultados actuales (sin API key, mocks deterministas):

| Componente | Precisión | Latencia P50 |
| ---------- | --------- | ------------ |
| evaluator | 100% | <5ms |
| price | 100% | <1ms |
| validator | 100% | <1ms |
| knowledge_base | 100% | <1ms |
| **Global** | **100%** | — |
| Baseline (sin IA) | 16.7% | — |
| **Mejora** | **+83.3 pp** | — |

Con ANTHROPIC_API_KEY, los casos que usan extended thinking muestran latencia real (P50 ~2s, P95 ~4s).

---

## 8. Observabilidad — Langfuse (opcional)

Langfuse traza cada llamada LLM con latencia, tokens, coste y cache hit rate.
Los datos aparecen en tiempo real en el dashboard de Langfuse.

1. Regístrate en [cloud.langfuse.com](https://cloud.langfuse.com) (gratis)
2. Crea un proyecto y copia las claves
3. Añade al `.env`:

   ```env
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   ```

4. Arranca el backend — cada llamada Claude aparece en Langfuse automáticamente

Sin las claves, el sistema funciona igual sin observabilidad.

---

## 9. Benchmark de modelos (para el TFM)

Genera las tablas comparativas Haiku vs Sonnet vs Opus con latencia real, tokens y coste:

```bash
# Requiere ANTHROPIC_API_KEY en .env
python -m backend.data.benchmark

# Solo escenarios de riesgo
python -m backend.data.benchmark --scenario riesgo

# Guardar resultados en JSON para el TFM
python -m backend.data.benchmark --output resultados_benchmark.json
```

El benchmark ejecuta 5 escenarios de evaluación de producto + 1 de salida estructurada
en los tres modelos y produce una tabla comparativa lista para incluir en la memoria.

---

## 10. Flujos autónomos

Los cron jobs se activan automáticamente con el servidor:

| Hora | Flujo |
| ---- | ----- |
| 07:30 | Brief diario — el Supervisor analiza la tienda y envía por Telegram |
| 12:00 | Check de mediodía — escala críticos + alerta pasillos sin revisar |
| 20:00 | Cierre — registra merma real y guarda patrones en memoria episódica |
| Cada 2h (8-20h) | Escalación de críticos — acciones con score ≥ 85 sin resolver > 4h |
| Lunes 06:00 | Informe semanal de tendencias y proveedores |
| Día 1 del mes 08:00 | Informe mensual para el dueño |

Para lanzar el brief manualmente (útil para la demo):

```bash
make brief
```

---

## 9. Import CSV desde TPV (Feature #18)

Para importar lotes desde un sistema de TPV externo, usa el endpoint REST:

```bash
curl -X POST http://localhost:8000/api/v1/import/batches \
  -H "Content-Type: application/json" \
  -d '{"csv_data": "barcode,quantity,expiry_date\n8410001000001,10,2026-06-15\n"}'
```

O desde la app: Pantalla Acciones → icono de importar (arriba derecha) → pegar CSV.

Formato del CSV:

```csv
barcode,quantity,expiry_date
8410001000001,10,2026-06-15
8410031001001,5,2026-06-10
```

También se acepta `codigo` y `cantidad` como alias de columnas.
Formato de fecha: `YYYY-MM-DD`, `DD/MM/YYYY` o `DD-MM-YYYY`.

---

## 10. Comandos útiles

```bash
make run          # Arrancar servidor (FastAPI + Chuwi + scheduler)
make seed         # Cargar datos demo completos (30d histórico)
make seed-actions # Solo acciones y brief de hoy
make test-fast    # Tests sin LLM (133 tests)
make brief        # Generar brief ahora mismo
make status       # Ver estado de la tienda demo
make logs         # Ver logs en tiempo real
make lint         # Linter Python (ruff)
make clean        # Limpiar __pycache__ y .pyc
```

---

## Estructura del proyecto

```text
mermaops/
├── backend/
│   ├── agents/          # 14 agentes IA (+ parallel_evaluator + consensus + vision + esg + predictor)
│   │   ├── supervisor.py    # Cerebro — loop agéntico con 14 herramientas
│   │   ├── evaluator.py     # Análisis de riesgo con extended thinking + consenso
│   │   ├── validator.py     # Validador adversarial + alerta pasillos sin revisar
│   │   ├── price.py         # Cálculo de descuentos con margen mínimo
│   │   ├── stock.py         # Decisiones de reposición con FEFO
│   │   ├── route.py         # Ruta diaria optimizada por pasillos
│   │   ├── reporter.py      # Brief diario, semanal y mensual
│   │   ├── notifier.py      # Notificaciones Telegram con chunking
│   │   ├── scanner.py       # Lookup OpenFoodFacts
│   │   ├── parallel_evaluator.py  # Evaluación en paralelo (ThreadPoolExecutor)
│   │   ├── consensus.py     # Votación de mayoría — 3 perspectivas + debate Jeffrey
│   │   ├── vision.py        # Análisis visual de producto con Claude Vision
│   │   ├── esg.py           # Métricas ESG: CO2, agua, deducción fiscal (Ley 49/2002)
│   │   └── predictor.py     # Predicción de merma + Open-Meteo (meteorología gratis)
│   ├── core/
│   │   ├── llm.py           # Wrapper Claude API — prompt caching + tool use
│   │   ├── database.py      # Cliente Supabase — todas las queries
│   │   ├── knowledge.py     # Knowledge base normativa alimentaria (RAG)
│   │   ├── memory.py        # Memoria episódica del Supervisor
│   │   ├── chuwi.py         # Agente Telegram conversacional (Jeffrey-style, inline keyboards)
│   │   ├── scheduler.py     # 6 cron jobs APScheduler
│   │   └── l10n.dart        # (Flutter) Multi-idioma ES/EN
│   ├── api/routes.py        # Endpoints REST para Flutter
│   ├── data/
│   │   ├── seed.py          # Súper Martínez — productos, lotes, almacén, proveedores
│   │   └── demo_actions.py  # Acciones, merma 30d, donaciones, comparativa, informes
│   └── tests/               # 133 tests unitarios en 12 archivos
├── app/                     # Flutter app
│   ├── lib/
│   │   ├── features/
│   │   │   ├── auth/        # Login Supabase
│   │   │   ├── dashboard/   # KPIs + comparativa tiendas + sparkline + brief
│   │   │   ├── scan/        # Escaneo barcode con MobileScanner
│   │   │   ├── actions/     # Pendientes + historial + foto-evidencia + import CSV
│   │   │   ├── map/         # Mapa de pasillos + QR sección + lista FEFO
│   │   │   └── reports/     # 8 tabs: Diarios/Semanales/Mensual/Merma/Proveedores/Pedidos/ESG/Predicciones
│   │   └── core/
│   │       ├── theme.dart       # Colores de urgencia
│   │       ├── router.dart      # go_router
│   │       ├── shell_scaffold.dart  # Bottom nav con badge + l10n
│   │       ├── api_service.dart # Cliente HTTP FastAPI
│   │       ├── supabase_client.dart
│   │       └── l10n.dart        # Multi-idioma ES/EN con StateNotifier
│   └── pubspec.yaml
├── docs/schema.sql          # Schema Supabase completo (todas las tablas)
├── .env.example
├── requirements.txt
├── Makefile
└── pytest.ini
```

---

## 41 features implementadas

| # | Feature | Estado |
|---|---------|--------|
| 1 | Escaneo barcode | ✅ |
| 2 | Mapa de tienda configurable | ✅ |
| 3 | Ruta del día | ✅ |
| 4 | Motor de riesgo con IA | ✅ |
| 5 | FEFO | ✅ |
| 6 | Motor de acciones diarias | ✅ |
| 7 | Reposición conectada | ✅ |
| 8 | Dashboard KPIs | ✅ |
| 9 | Agentes autónomos (6 cron jobs) | ✅ |
| 10 | IA explica el porqué | ✅ |
| 11 | Brief diario + informe semanal | ✅ |
| 12 | Canal de alertas (Telegram) | ✅ |
| 13 | Etiquetas de descuento | ✅ |
| 14 | Donación a Banco de Alimentos | ✅ |
| 15 | Comparativa entre tiendas | ✅ |
| 16 | Ficha de proveedor | ✅ |
| 17 | Export CSV merma | ✅ |
| 18 | Import CSV desde TPV | ✅ |
| 19 | API pública (Swagger /docs) + /health | ✅ |
| 20 | Foto-evidencia de retirada | ✅ |
| 21 | Alerta si sección no se revisa | ✅ |
| 22 | Historial por empleado | ✅ |
| 23 | Datos demo realistas (30d) | ✅ |
| 24 | Informe mensual para el dueño | ✅ |
| 25 | Sugerencia de pedido semanal | ✅ |
| 26 | QR de sección | ✅ |
| 27 | Multi-idioma ES + EN | ✅ |
| 28 | Spinner visible (Chuwi piensa) | ✅ |
| 29 | Análisis visual de producto (Claude Vision) | ✅ |
| 30 | Métricas ESG — CO₂, agua, deducción fiscal | ✅ |
| 31 | Predicción de merma con meteorología (Open-Meteo) | ✅ |
| 32 | Debate Jeffrey (4 agentes) para casos extremos | ✅ |
| 33 | Escalación automática de críticos por Telegram | ✅ |
| 34 | ROI / merma evitada en informes semanales y mensuales | ✅ |
| 35 | Tab ESG en app Flutter | ✅ |
| 36 | Tab Predicciones en app Flutter | ✅ |
| 37 | Flujo donación multi-step en Chuwi (/donar) | ✅ |
| 38 | Comandos /esg y /prediccion en Chuwi | ✅ |
| 39 | Think tool (Anthropic) en Supervisor — razonamiento inter-herramienta | ✅ |
| 40 | /scan /brief /merma /donaciones /proveedores /acciones como slash commands | ✅ |
| 41 | Knowledge base con estadísticas reales (Eurostat, CSRD Ómnibus I, competidores) | ✅ |
| 42 | Citations API Anthropic — agentes citan fuente exacta de cada decisión | ✅ |
| 43 | Langfuse observability — traza cada llamada LLM (latencia, tokens, coste) | ✅ |
| 44 | Benchmark Haiku/Sonnet/Opus — tablas empíricas coste/calidad/latencia | ✅ |
| 45 | Adversarial robustness — 23 tests de inyección datos, prompt injection y conflictos | ✅ |
| 46 | /stats Dashboard Telegram — KPIs en tiempo real con semáforo ROJO/AMARILLO/VERDE | ✅ |
| 47 | /citar — normativa alimentaria citada con fuente exacta (Citations API) | ✅ |

---

## DEMO-DAY CHECKLIST

### La noche anterior (30 min)

- [ ] `make run` — backend arranca sin errores
- [ ] `make brief` — brief generado y guardado en Supabase
- [ ] App Flutter abierta en el teléfono con datos del día en dashboard
- [ ] Telegram bot responde a mensajes (escribe "hola" al bot)
- [ ] `make test-fast` — todos los tests pasan

### El día de la presentación (10 min antes)

- [ ] Ordenador y teléfono en la MISMA WiFi
- [ ] `make run` arrancado (o verificar que sigue corriendo)
- [ ] Supabase tiene el brief del día en `daily_briefs`
- [ ] Tener un código de barras real para escanear
- [ ] Telegram abierto en el teléfono para mostrar a Chuwi
- [ ] App Flutter abierta en el dashboard

### Flujo de demo recomendado (4-5 minutos)

**1. Brief automático** (30s)
> "A las 7:30 llegó esto solo — sin que nadie lo pidiera"
> Mostrar el mensaje de Chuwi en Telegram con acciones priorizadas

**2. Pregunta libre a Chuwi** (45s)
> Escribir: "¿qué pasa con los lácteos esta semana?"
> El agente analiza con datos reales y responde en lenguaje natural

**3. Escaneo en vivo** (60s)
> Pantalla Escanear → escanear código de barras real
> Mostrar: pasillo, días, ACCIÓN (REBAJAR X%), precio exacto, razonamiento de Claude

**4. Dashboard** (45s)
> KPIs en tiempo real, sparkline de merma, impacto social de donaciones
> Comparativa entre tiendas

**5. ESG + Predicciones** (45s)
> App → Informes → ESG: CO₂ evitado, agua ahorrada, deducción fiscal real (Ley 49/2002)
> Informes → Predicciones: lista de productos en riesgo ANTES de que caduquen,
> con previsión meteorológica de Open-Meteo integrada. Nadie más tiene esto.

**6. Normativa citada** (30s)
> Escribe en Chuwi: `/citar pescado 1`
> Responde con la normativa exacta de seguridad alimentaria que usó para decidir,
> citando el fragmento preciso. El sistema no inventa: cita la fuente.

**7. Arquitectura** (30s)
> "14 agentes especializados. El Supervisor decide solo qué investigar.
> El Evaluador usa extended thinking real de Claude para casos críticos.
> Memoria episódica — recuerda qué pasó la semana anterior.
> Para casos extremos (score ≥ 95, valor ≥ 50€): debate de 4 agentes en cadena."

### Vincular Telegram antes de la demo

1. Escribe `/start` al bot → te da tu Telegram ID
2. En la app → Perfil → Vincular Telegram → pegar el ID
3. Ahora Chuwi te reconoce por nombre y rol

### Configuración para dispositivo físico

```bash
# Obtén tu IP local:
# Windows:
ipconfig | findstr IPv4
# Mac:
ifconfig | grep "inet "

# Lanza con IP real:
flutter run \
  --dart-define=SUPABASE_URL=https://XXX.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=eyJ... \
  --dart-define=API_URL=http://192.168.1.X:8000/api/v1
```
