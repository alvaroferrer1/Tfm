# MermaOps — Resumen Ejecutivo para el Tribunal

> Una página. Lo esencial para entender el TFM en 3 minutos.

---

## Problema

El desperdicio alimentario en supermercados españoles representa entre el 2% y el 5%
de los ingresos anuales. Un supermercado mediano pierde entre 15.000 y 40.000 € al año
en productos que caducan sin venderse. Las soluciones existentes (Winnow, Orbisk) cuestan
más de 20.000 € de implantación y requieren hardware específico, lo que las hace
inaccesibles para el 95% de los establecimientos.

---

## Solución

**MermaOps** es un sistema multi-agente de IA construido sobre Claude API (Anthropic)
que gestiona la merma alimentaria desde el móvil del encargado, sin hardware adicional,
con un coste operativo de **0,80 €/mes**.

El sistema tiene dos interfaces de usuario:
- **Telegram** (@ChuwiMermaOpsBot): el agente conversacional Chuwi responde en lenguaje
  natural, monitoriza la tienda cada 30 min y envía alertas proactivas sin que nadie pregunte.
- **App Flutter** (web + móvil): dashboard con KPIs, gestión de acciones, panel de agentes,
  informes y ESG metrics.

---

## Arquitectura — 12 agentes especializados

```
Usuario → Chuwi (Sonnet) → Kuine (Opus, orquestador) → [
    Evaluador (Sonnet, extended thinking, score 0–100)
    ForkMerge  (3×Sonnet paralelo + Opus síntesis)
    Consenso   (3×Sonnet, regla 2/3)
    Validador  (Sonnet, 23 ataques adversariales)
    Predictor  (Haiku, Open-Meteo API)
    Visión     (Haiku, análisis de fotos)
    Precio     (heurístico, 0 tokens)
    Stock      (heurístico, 0 tokens)
    Notificador (alertas proactivas)
    Reportero  (Sonnet, briefs y PDFs)
]
```

**Right-sizing**: Opus solo donde hay máxima complejidad. Haiku para tareas simples.
Heurístico donde no hace falta LLM. Ahorro estimado de ~70% en tokens vs. usar Opus en todo.

---

## Resultados

| Métrica | Valor |
|---------|-------|
| Tests automatizados | **774/774** en 1,98s (sin API real) |
| Precisión vs. baseline | **100%** vs. 16,7% (+83,3 pp) |
| Ataques adversariales bloqueados | **23/23 (100%)** |
| Regla 2/3 consenso | **42/42 tests** |
| Acciones gestionadas (real) | **45** completadas |
| Merma identificada | **483,95 €** |
| Coste por brief diario (Kuine) | **~0,03 €** con prompt caching |

---

## Decisiones técnicas clave

**1. Por qué multi-agente en lugar de un único LLM**
Un agente único no permite right-sizing de modelos ni aislamiento de fallos.
La especialización permite usar el modelo correcto para cada tarea, reducir costes
y aumentar la robustez: si el Evaluador falla, Kuine sigue funcionando.

**2. Por qué extended thinking**
El Evaluador activa `thinking: adaptive` solo para scores entre 65–90 (zona de
ambigüedad). Para scores obvios (>90 o <30) lo desactiva. Resultado: misma
precisión con ~60% menos de tokens de thinking.

**3. Por qué Telegram como interfaz principal**
El encargado ya tiene Telegram. Sin app nueva, sin formación, sin fricción de adopción.
El streaming visual (texto que aparece progresivamente) da retroalimentación de que el
agente está "pensando" — diferencia perceptible vs. un chatbot convencional.

**4. Por qué el Validador adversarial**
Los modelos de lenguaje son susceptibles a prompt injection y datos maliciosos.
Sin el Validador, un input construido maliciosamente puede hacer que Kuine venda
un producto caducado o done a una entidad no verificada. El Validador bloquea
23 vectores de ataque antes de ejecutar cualquier acción en el mundo real.

---

## Cumplimiento normativo automatizado

El sistema incorpora por defecto (via RAG sobre pgvector):
- **Reglamento (CE) 178/2002** — seguridad alimentaria (nunca vender caducado)
- **Ley 7/2022** — economía circular y residuos
- **Ley 49/2002** — deducción fiscal 35% en donaciones a entidades sin ánimo de lucro
- **CSRD 2026** — reporting ESG no financiero para PYMEs (obligatorio desde 2026)

---

## Escalabilidad y coste real

| Escenario | Coste/mes estimado |
|-----------|-------------------|
| 1 tienda (demo) | **0,80 €** |
| 10 tiendas | ~8 € |
| 100 tiendas | ~80 € + infraestructura |

La arquitectura es stateless: cada tienda es un `store_id` en Supabase.
Añadir una tienda no requiere código nuevo.

---

## Lo que MermaOps NO hace

- No reemplaza al encargado: todas las decisiones pasan por confirmación humana.
- No actúa en el mundo físico de forma autónoma.
- No accede a sistemas POS o ERP sin integración explícita.

Esta delimitación es intencional y demuestra madurez técnica: los sistemas de IA
más peligrosos son los que no tienen límites claros.

---

## Líneas futuras

1. **Agente Comprador**: cerrar el ciclo completo — no solo gestionar merma
   existente, sino predecir el pedido óptimo semanal por tienda.
2. **Multi-tienda con comparativas**: actualmente 1 tienda demo; la arquitectura
   ya soporta N tiendas con un `store_id` por fila en `stores`.
3. **Integración TPV**: conectar con el punto de venta para validar que las
   rebajas registradas por el sistema realmente se vendieron.
4. **Modelo propio fine-tuneado**: con suficientes decisiones históricas,
   fine-tunear un modelo pequeño para sustituir al Evaluador y reducir coste a 0.
