# MermaOps — API Reference

> FastAPI backend en puerto **8001**. Todos los endpoints bajo `/api/v1/` requieren JWT de Supabase.
> En dev sin SUPABASE_URL, `Authorization: Bearer dev-bypass` funciona para pruebas.

---

## Autenticación

```http
Authorization: Bearer <supabase_jwt_token>
```

En dev: `Authorization: Bearer dev-bypass`

---

## Escaneo

### `POST /api/v1/scan`
Escaneo completo de un producto por código de barras.

**Body**: `{"barcode": "8410001000001", "user_id": "uuid"}`

**Response**:
```json
{
  "result": "Yogur Danone — Pasillo 3. Caduca mañana. REBAJAR 30%: 0.70€. Reponer: No.",
  "barcode": "8410001000001",
  "thinking_summary": "...",
  "action_id": "uuid-o-null",
  "action_type": "rebajar",
  "product_name": "Yogur Danone",
  "days_left": 1,
  "final_action": "rebajar",
  "location": "Pasillo 3 — Estantería B — Nivel 2",
  "price_rec": "Rebajar un 30% → precio: 0.70€"
}
```
- `action_id`: si hay acción pendiente para este producto, devuelve el ID para completarla directo desde la app
- Si el producto no está en la tienda, devuelve información de la base de datos global (OpenFoodFacts)
- Rate limit: 30/min

### `POST /api/v1/scan/vision`
Análisis visual de un producto por foto.

**Body**: `{"image_base64": "...", "product_name": "", "days_left": -1, "category": ""}`

**Response**: `{"estado": "deteriorado", "confianza_pct": 78, "accion_recomendada": "...", "razonamiento": "..."}`

---

## Acciones

### `GET /api/v1/actions`
Lista de acciones pendientes ordenadas por prioridad.

**Response**: `{"actions": [{...}, ...]}`

Cada acción incluye: `id`, `action_type`, `status`, `priority_score`, `product_id`, `batch_id`, `notes`, y el batch con el producto (JOIN).

### `POST /api/v1/actions/complete`
Marca una acción como completada. Escribe automáticamente en `merma_log`.

**Body**: `{"action_id": "uuid", "completed_by": "uuid", "notes": "", "photo_url": ""}`

---

## Brief y Reportes

### `POST /api/v1/brief/run` (background)
Genera el brief diario en background. Kuine ejecuta el loop agéntico completo.

### `POST /api/v1/brief/run/sync`
Igual que el anterior pero síncrono — espera el resultado completo. Máx. 3/min.

**Response**: `{"brief": "texto del brief..."}`

### `GET /api/v1/reports/daily`
Brief diario más reciente de la tienda.

### `GET /api/v1/reports/daily-list?limit=14`
Últimos N briefs diarios (evita RLS de Supabase en la app Flutter).

**Response**: `{"briefs": [{...}]}`

### `POST /api/v1/reports/weekly`
Genera el informe semanal (Reportero).

### `POST /api/v1/reports/monthly/run`
Genera el informe mensual (Reportero).

### `GET /api/v1/reports/brief/pdf?date=YYYY-MM-DD`
Descarga el PDF del brief de un día específico.

### `GET /api/v1/reports/weekly/pdf?week_start=YYYY-MM-DD`
Descarga el PDF del informe semanal.

### `GET /api/v1/reports/monthly/pdf?month=YYYY-MM`
Descarga el PDF del informe mensual.

### `POST /api/v1/reports/analyze-pdf`
Sube un PDF y recibe análisis de Claude. Multipart form: campo `file`.

---

## Estadísticas

### `GET /api/v1/stats/overview`
Resumen ejecutivo del sistema: agentes activos, acciones pendientes, merma 30d, impacto.

### `GET /api/v1/stats/suppliers`
Estadísticas por proveedor con tasa de merma.

### `GET /api/v1/stats/donations?days=30`
Impacto social: donaciones, valor, deducción fiscal 35% (Ley 49/2002).

### `GET /api/v1/stats/comparison`
Comparativa entre tiendas (multi-store).

### `GET /api/v1/stats/order-suggestions`
Sugerencias de pedido semanal basadas en historial de merma.

### `GET /api/v1/stats/esg?days=30`
Métricas ESG: CO₂ evitado, agua ahorrada, deducción fiscal.

### `GET /api/v1/stats/benchmark?days=30`
Comparación con benchmarks de industria (WRAP 2023, FAO 2022, AECOC Spain 2023).

**Response**: `{"benchmark_score": 72, "assessment": "Por encima de la media", "store_metrics": {...}, "industry_benchmarks": {...}}`

---

## Predicción

### `GET /api/v1/predict/risk?days=7`
Predicción de riesgo de merma para los próximos N días (Predictor).

### `GET /api/v1/predict/brief?days=5`
Resumen narrativo de las predicciones.

---

## Agentes

### `GET /api/v1/agent/status`
Lista de todos los agentes con modelo, tipo y descripción.

### `GET /api/v1/agent/activity`
Timeline de actividad de las últimas 24h: intents, tools usadas, llamadas a Kuine.

### `GET /api/v1/agent/conversations?limit=20`
Conversaciones recientes de Chuwi con usuarios.

### `GET /api/v1/agent/conversations/{id}/messages`
Mensajes de una conversación específica.

### `GET /api/v1/agent/runs?limit=20`
Runs del supervisor (brief, intraday, cierre) con trace de tools.

### `GET /api/v1/agent/decisions?limit=50`
Decisiones del supervisor: qué acción creó Kuine y por qué.

### `POST /api/v1/agent/chat`
Chat directo con Chuwi desde la app Flutter (sin Telegram).

**Body**: `{"message": "¿cuántos críticos hay?", "history": [...]}`

**Response**: `{"reply": "Hay 3 productos críticos...", "tools_used": ["get_expiring_batches"]}`

---

## LLM / Costes

### `GET /api/v1/llm/stats`
Estadísticas de uso de la API de Claude: total_usd, saved_usd, calls, cache_hit_pct.

---

## Usuario

### `GET /api/v1/user/me`
Perfil del usuario autenticado (rol, store_id, telegram_linked).

### `POST /api/v1/user/link-telegram`
Vincula un Telegram user_id a la cuenta.

### `DELETE /api/v1/user/link-telegram`
Desvincula la cuenta de Telegram.

---

## Demo

### `POST /api/v1/demo/advance`
Simula el paso de N días. Resta N días a caducidades, recalcula urgencias.

**Body**: `{"days": 2, "generate_brief": false}`

### `POST /api/v1/demo/reset`
Vuelve al estado inicial (ejecuta seed).

---

## Sistema

### `GET /health`
Health check rápido (siempre 200). Para load balancers.

### `GET /api/v1/health`
Health check real con comprobación de conectividad a Supabase.

### `GET /api/v1/ping`
Ping básico. Response: `{"pong": true}`

---

## Notas

- **Rate limiting** (slowapi): `/scan` 30/min, `/brief/run/sync` 3/min, `/agent/chat` 10/min, `/scan/vision` 20/min
- **Timeout brief síncrono**: 5 minutos máximo (abort automático si supera)
- **CORS**: todos los orígenes en dev, configurable vía `CORS_ORIGINS` en producción
- **Logs**: todos los errores 500 se loguean con `logger.error` — revisar uvicorn logs para diagnóstico
