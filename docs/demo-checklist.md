# MermaOps — Guía de defensa TFM

## Estrategia de presentación (sin emulador)

```text
Terminal 1 → Backend FastAPI (localhost:8001)
Chrome     → App Flutter web (localhost:3000)
Móvil real → Telegram con @ChuwiMermaOpsBot
```

Sin emulador. Sin cables. Sin que nada falle en el peor momento.

---

## Antes de entrar (30 min antes)

```bash
# 1. Arrancar backend completo con datos cargados
make demo-defensa
# Espera a que diga "Uvicorn running on http://0.0.0.0:8001"

# 2. Verificar que responde
curl http://localhost:8001/health
# Debe decir: {"status":"ok","store_id":"demo-store-001",...}

# 3. En otro terminal — app Flutter como web en Chrome
make flutter-web
# Abre http://localhost:3000 en Chrome

# 4. Estado de la tienda — asegurate de que hay criticos para la demo
make status
# Si no hay criticos: make advance N=2

# 5. Telegram — escribe /yo para ver tu perfil con rol ENCARGADO
```

---

## Tu rol en Telegram

Antes de presentar verifica que tienes rol `manager` en Supabase:

```sql
-- En el SQL Editor de Supabase:
SELECT email, role, telegram_user_id FROM users;
UPDATE users SET role = 'manager' WHERE email = 'alvaroferrermarg@gmail.com';
```

Con rol `manager` Chuwi muestra el menú completo:

- Brief del día / Generar brief ahora
- Proveedores / Pedido semanal
- ESG / Predicciones
- Demo (avanzar tiempo)

Con rol `staff` solo ve: estado, ruta, acciones, merma, donaciones.

---

## Estructura de la presentación (20 min)

### Bloque 1 — Contexto y solución (3 min)

Qué dices:

- El desperdicio alimentario cuesta 2-5% de ingresos por tienda
- Winnow y Orbisk solo funcionan en grandes cadenas con hardware caro
- MermaOps lo resuelve con IA multi-agente, sin hardware, solo Telegram

Qué muestras en Chrome:

- Demo HTML escena S1 (el problema)
- Escena S2 (arquitectura — los 11 agentes con modelos reales)

---

### Bloque 2 — Los agentes en acción (10 min)

| Escena | Agente     | Lo que enseña                                      |
| ------ | ---------- | -------------------------------------------------- |
| S3     | Kuine      | Tool calls reales: 07:30, 156 lotes, scores, brief |
| S4     | Evaluador  | Extended thinking + score bars animados            |
| S5     | Validador  | 23 ataques adversariales con counter animado       |
| S6     | Consenso   | 3 instancias Sonnet votando en paralelo            |
| S7     | Predictor  | Tabla riesgo 5 días + datos Open-Meteo             |
| S8     | Visión IA  | Foto a análisis JSON estructurado                  |
| S9     | Chuwi      | Telegram: streaming progresivo en vivo             |

Qué dices mientras avanza la demo:

- "Kuine usa adaptive thinking — razona antes de decidir, no solo ejecuta"
- "El Validador bloquea 23 tipos de ataque adversarial — 100% neutralizados"
- "El Consenso lanza 3 instancias de Sonnet 4.6 en paralelo para casos extremos"
- "Chuwi NO es un bot. Monitoriza la tienda sola cada 30 min y avisa sin que nadie le pregunte"

---

### Bloque 3 — Demo en vivo (5 min)

1. Abrir Chrome en `localhost:3000` (app Flutter web, ya compilada)
   - Dashboard: 4 KPIs + acciones pendientes con scores
   - Tab Agentes: los 11 agentes con modelo y estado

2. Simular paso del tiempo desde terminal:

   ```bash
   make advance N=3
   ```

   El dashboard se recarga y aparecen nuevos críticos.

3. Mostrar Telegram en el móvil real:
   - "qué hay crítico ahora?" — Chuwi responde con streaming visible
   - "cuánto ahorramos esta semana?" — métricas reales de Supabase
   - Enseña `/yo` — muestra tu perfil con rol ENCARGADO visible

4. Escenas S12-S13 en el demo HTML:
   - Métricas ESG con animación (CO2, agua, deducción fiscal 35%)
   - Resultados: 439/439 tests, 100% precisión, 23/23 adversarial

---

### Bloque 4 — Resultados cuantitativos (2 min)

- "439 tests deterministas, pasan en 1.5 segundos sin conectarse a nada"
- "100% de precisión sobre baseline de 16.7% — mejora de 83 puntos porcentuales"
- "El sistema cumple CSRD — reporting ESG obligatorio para PYMEs en 2026"
- "El brief diario de Kuine cuesta 0.03 € en tokens con prompt caching activo"

---

## Si el tribunal pregunta

**"¿Por qué Claude y no GPT-4o?"**
Anthropic es el único proveedor con adaptive thinking nativo entre tool calls,
y la combinación Opus/Sonnet/Haiku que permite optimizar coste por agente según
la complejidad de la tarea. GPT-4o no tiene extended thinking nativo ni prompt
caching con los mismos ratios de ahorro.

**"¿Cómo garantizas la seguridad alimentaria?"**
El Validador bloquea cualquier acción que viole FEFO, precios por debajo del
coste, o entidades de donación no verificadas. 23 ataques adversariales testeados.
El sistema nunca actúa en el mundo físico sin confirmación del encargado.

**"¿Escala a una cadena grande?"**
Arquitectura stateless — cada tienda tiene su `store_id` en Supabase. Para 100
tiendas: 1 backend + 1 bot Telegram + n workers de Kuine. Coste marginal por
tienda: 0.80 €/mes con prompt caching activado.

**"¿Cuánto cuesta en producción?"**
El brief diario cuesta 0.03 € en tokens. La tienda demo gasta 0.80 €/mes.
ROI positivo con recuperar 1 producto evitado al mes.

**"¿Qué no hace MermaOps?"**
No reemplaza al encargado — amplifica su capacidad. Las decisiones las confirma
siempre una persona. El sistema nunca actúa en el mundo físico de forma autónoma.
Esto es madurez técnica — demuestra que entiendes los límites del sistema.

---

## Si algo falla

| Problema                  | Solución inmediata                                    |
| ------------------------- | ----------------------------------------------------- |
| Backend no responde       | `make run` en terminal nuevo                          |
| Web Flutter en blanco     | `make flutter-web` de nuevo                           |
| Chuwi no responde         | verificar `TELEGRAM_BOT_TOKEN` en `.env`              |
| Sin datos críticos        | `make advance N=2`                                    |
| Tests fallando            | `python -m pytest backend/tests/ -q` (439/439)        |

---

## Comandos en vivo durante la defensa

```bash
make advance N=1      # avanza 1 día
make advance N=3      # más dramático para la demo
make demo-reset       # vuelve al estado inicial
make brief            # fuerza brief de Kuine ahora mismo
make status           # resumen del estado actual
```

---

## Checklist ANTES de dormir

- [ ] `.env` tiene todas las credenciales correctas
- [ ] `make demo-defensa` arranca sin errores
- [ ] `curl localhost:8001/health` responde `ok`
- [ ] `make flutter-web` compila sin errores
- [ ] `localhost:3000` muestra el dashboard con datos reales
- [ ] Telegram: `/yo` muestra perfil con rol **ENCARGADO**
- [ ] Telegram: "qué hay crítico" recibe respuesta con streaming
- [ ] `python -m pytest backend/tests/ -q` — 439/439
- [ ] `make advance N=2` y `make demo-reset` funcionan
- [ ] Modo No Molestar activado en el móvil
- [ ] Chrome sin notificaciones

---

> **Punto clave para el tribunal:** MermaOps no es un prototipo de laboratorio.
> Arranca con un comando, conecta a Supabase en producción, habla por Telegram
> en tiempo real y toma decisiones sobre datos reales. Todo lo que ves es código
> real ejecutándose ahora mismo.
