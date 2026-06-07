# MermaOps — Guía de operaciones (dale esto a Claude antes de pedir)

> Pega el bloque relevante al principio de tu mensaje para que Claude actúe directo sin gastar tokens diagnosticando.

---

## ARRANCAR EL SISTEMA

```
Contexto: Backend FastAPI en :8001, Flutter en Chrome.
Comando: make arranca
Si el backend ya corre, no lo toques. Solo lanza Flutter en Chrome.
API_URL para Chrome: http://localhost:8001/api/v1
```

---

## ARREGLAR UN ERROR (pega el error exacto)

```
Contexto: MermaOps, Python 3.14, FastAPI, Flutter/Dart.
Error: <pega aquí el traceback o mensaje de error completo>
Archivo y línea si lo sabes: <ej: backend/agents/supervisor.py:142>
Arréglalo sin cambiar más de lo necesario.
```

---

## AÑADIR FEATURE EN FLUTTER

```
Contexto: app Flutter en app/lib/features/. Usa Supabase directamente o
la API REST en api_service.dart. Sigue el patrón de pantallas existentes.
Tarea: <describe qué hacer>
No expliques, implementa directamente.
```

---

## AÑADIR ENDPOINT EN EL BACKEND

```
Contexto: FastAPI, rutas en backend/api/routes.py y routes_demo.py.
Auth con Supabase JWT en header Authorization.
Tarea: <describe el endpoint>
Sigue el patrón de los endpoints existentes. Sin tests nuevos salvo que lo pida.
```

---

## AÑADIR/MODIFICAR AGENTE

```
Contexto: agentes en backend/agents/. Usan Anthropic SDK (claude-sonnet-4-6
o claude-haiku-4-5-20251001). Sin LLM: heurístico en price.py y stock.py.
Agente a modificar: <nombre>
Tarea: <describe qué cambiar>
```

---

## TESTS

```
Contexto: 800 tests en backend/tests/, sin conexión real a Supabase ni API.
Todos los mocks están en conftest.py.
Comando para correr: python -m pytest backend/tests/ -q
Si fallan, pega la salida de pytest aquí: <salida>
```

---

## BASE DE DATOS / SUPABASE

```
Contexto: Supabase PostgreSQL. Migraciones en supabase/migrations/.
Tablas principales: stores, products, batches, actions, merma_log,
agent_conversations, agent_messages, agent_sessions, telegram_users,
supervisor_decisions, agent_runs.
Tarea: <describe el cambio de schema o query>
Si es migración nueva, crea el archivo SQL en supabase/migrations/.
```

---

## TELEGRAM / CHUWI

```
Contexto: bot @ChuwiMermaOpsBot, código en backend/core/chuwi.py.
Arranca como thread en backend/main.py al iniciar el backend.
Usa polling (no webhook). Para verificar que está activo: make arranca
(si da error 409 Conflict en get_updates, el polling ya corre — eso es OK).
Tarea: <describe qué cambiar en el comportamiento del bot>
```

---

## SCHEDULER / TAREAS AUTOMÁTICAS

```
Contexto: APScheduler en backend/core/scheduler.py, zona Europe/Madrid.
Trabajos actuales: 07:00 predicción, 07:30 brief, 12:00 check mediodía,
16:00 retrospectiva, 20:00 cierre, lunes semanal, día 1 mensual,
cada 2h escalación críticos, cada 30min monitor donaciones.
Tarea: <añadir/modificar trabajo>
```

---

## DEMO / DEFENSA

```
Contexto: datos demo en tienda "demo-store-001".
Comandos útiles:
  make advance N=1    → avanza 1 día en la simulación
  make demo-reset     → vuelve al estado inicial
  make demo-prep      → prepara 10min antes de la defensa
  make brief          → genera brief manual ahora (sin esperar 07:30)
  make seed           → recarga todos los datos demo
```

---

## ROLES DE USUARIO

```
Roles: staff (encargado), manager (supervisor), admin.
El rol se asigna en Supabase → tabla users → campo role.
El registro libre crea usuarios con rol 'staff' por defecto.
Para cambiar a manager/admin: edita directamente en Supabase Dashboard.
```

---

## REGLAS FIJAS (no negociables)

- Puerto backend: 8001 (no 8000)
- Flutter siempre en Chrome para desarrollo, no emulador Android
- No commits hasta que el usuario diga "sube" o "commit"
- No push a GitHub hasta "sube a GitHub"
- No credenciales en código — todo por .env
- Tests deben seguir >= 800/800 después de cada cambio
- No inventar capacidades — solo implementar lo que está conectado
