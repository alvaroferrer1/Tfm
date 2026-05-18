"""
MermaOps — Script de arranque y verificación.

Uso:
    python scripts/start.py           # arranca backend + muestra guía completa
    python scripts/start.py --check   # solo verifica, no arranca
    python scripts/start.py --seed    # verifica + carga datos demo + arranca
"""
from __future__ import annotations

import os
import sys
import time
import json
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

env_path = ROOT / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

SEP = "=" * 60

def _c(text: str, color: str) -> str:
    codes = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
             "blue": "\033[94m", "bold": "\033[1m", "reset": "\033[0m"}
    return f"{codes.get(color,'')}{text}{codes['reset']}"


def _ok(msg: str) -> None:
    print(f"  {_c('OK', 'green')}  {msg}")

def _fail(msg: str) -> None:
    print(f"  {_c('FAIL', 'red')}  {msg}")

def _warn(msg: str) -> None:
    print(f"  {_c('WARN', 'yellow')}  {msg}")

def _info(msg: str) -> None:
    print(f"  {_c('....', 'blue')}  {msg}")


# ── 1. Verificar .env ─────────────────────────────────────────────────────────

def check_env() -> bool:
    print(f"\n{SEP}\n  Variables de entorno\n{SEP}")
    ok = True
    required = {
        "ANTHROPIC_API_KEY": "Claude API",
        "SUPABASE_URL": "URL del proyecto Supabase",
        "SUPABASE_KEY": "API key de Supabase",
        "TELEGRAM_BOT_TOKEN": "Token del bot de Telegram",
        "STORE_ID": "ID de la tienda demo",
    }
    for var, desc in required.items():
        val = os.getenv(var, "")
        if val:
            masked = val[:10] + "..." if len(val) > 10 else val
            _ok(f"{var} = {masked}  ({desc})")
        else:
            _fail(f"{var} no definida  — {desc}")
            ok = False

    port = os.getenv("APP_PORT", "")
    if port == "8001":
        _ok("APP_PORT = 8001")
    elif not port:
        _warn("APP_PORT no definida — el backend usará 8001 por defecto")
    else:
        _warn(f"APP_PORT = {port}  (se recomienda 8001 en Windows)")

    return ok


# ── 2. Verificar Supabase ─────────────────────────────────────────────────────

def check_supabase() -> bool:
    print(f"\n{SEP}\n  Supabase — conexión y tablas\n{SEP}")
    try:
        from backend.core.database import get_db
        db = get_db()
        t0 = time.monotonic()
        r = db.table("stores").select("id,name").limit(1).execute()
        ms = round((time.monotonic() - t0) * 1000)
        if r.data:
            _ok(f"Conexión OK — {ms}ms — tienda: {r.data[0].get('name','?')}")
        else:
            _warn("Conexión OK pero tabla 'stores' vacía — ejecuta: make seed")
    except Exception as e:
        _fail(f"No se puede conectar a Supabase: {e}")
        return False

    tablas = ["agent_conversations", "agent_messages", "agent_sessions",
              "telegram_users", "supervisor_decisions", "agent_runs"]
    todas_ok = True
    for t in tablas:
        try:
            db.table(t).select("id").limit(1).execute()
            _ok(f"Tabla {t}")
        except Exception:
            _fail(f"Tabla {t} no existe — ejecuta: supabase db push")
            todas_ok = False
    return todas_ok


# ── 3. Verificar Telegram ─────────────────────────────────────────────────────

def check_telegram() -> dict:
    print(f"\n{SEP}\n  Telegram Bot\n{SEP}")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        _fail("TELEGRAM_BOT_TOKEN no definido")
        return {}

    try:
        import urllib.request
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=8
        ) as resp:
            data = json.loads(resp.read())
        if data.get("ok"):
            bot = data["result"]
            username = bot.get("username", "?")
            bot_id = bot.get("id", "?")
            _ok(f"Bot activo: @{username} (id={bot_id})")
            return {"username": username, "id": bot_id}
        else:
            _fail(f"Token inválido: {data.get('description','?')}")
            return {}
    except Exception as e:
        _fail(f"No se puede conectar a Telegram API: {e}")
        return {}


# ── 4. Verificar backend (si ya está corriendo) ───────────────────────────────

def check_backend_running() -> bool:
    port = os.getenv("APP_PORT", "8001")
    try:
        import urllib.request
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/ping", timeout=2
        ) as resp:
            data = json.loads(resp.read())
            return bool(data.get("pong"))
    except Exception:
        return False


# ── 5. Cargar datos demo ──────────────────────────────────────────────────────

def seed_demo() -> None:
    print(f"\n{SEP}\n  Cargando datos demo\n{SEP}")
    _info("Ejecutando seed (productos + lotes + acciones + brief)...")
    result = subprocess.run(
        [sys.executable, "-m", "backend.data.seed"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120
    )
    if result.returncode == 0:
        _ok("Datos demo cargados")
    else:
        _fail(f"Error en seed: {result.stderr[-200:]}")


# ── 6. Arrancar backend ───────────────────────────────────────────────────────

def start_backend() -> subprocess.Popen:
    port = os.getenv("APP_PORT", "8001")
    print(f"\n{SEP}\n  Arrancando backend en puerto {port}\n{SEP}")
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.main"],
        cwd=str(ROOT),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # Esperar hasta que responda (máx 15s)
    for i in range(30):
        time.sleep(0.5)
        if check_backend_running():
            _ok(f"Backend corriendo en http://127.0.0.1:{port}")
            return proc
        if proc.poll() is not None:
            _fail("El proceso del backend terminó inesperadamente — revisa el log")
            sys.exit(1)

    _warn("El backend tardó en arrancar. Comprueba los logs arriba.")
    return proc


# ── 7. Guía de pruebas ────────────────────────────────────────────────────────

def print_test_guide(bot_info: dict) -> None:
    port = os.getenv("APP_PORT", "8001")
    store_id = os.getenv("STORE_ID", "demo-store-001")
    bot_username = bot_info.get("username", "TU_BOT")

    print(f"\n{SEP}")
    print(_c("  SISTEMA LISTO — Guia de pruebas", "bold"))
    print(SEP)

    print(f"""
{_c("BACKEND", "bold")} — http://127.0.0.1:{port}
  curl http://127.0.0.1:{port}/api/v1/ping
  curl http://127.0.0.1:{port}/api/v1/health
  curl http://127.0.0.1:{port}/api/v1/agent/status
  curl http://127.0.0.1:{port}/api/v1/dashboard
  Docs: http://127.0.0.1:{port}/docs

{_c("TELEGRAM — @" + bot_username, "bold")}
  1. Abre Telegram y busca @{bot_username}
  2. Escribe /start
     → Si NO estas vinculado: Chuwi te muestra tu ID numerico
     → Si SI estas vinculado: Chuwi te saluda con el menu

  PRUEBA BASICA (usuario no vinculado):
  → Escribe cualquier mensaje
  → Resultado esperado: Chuwi te bloquea y te muestra tu ID

  PRUEBA AGENTE (usuario vinculado):
  → "hola, cuantos criticos hay?"
  → Chuwi muestra (...escribiendo...) mientras consulta la BD
  → Responde con datos reales de Supabase

  PRUEBA HERRAMIENTAS:
  → "cuanto hemos perdido esta semana"   → usa get_merma_stats
  → "dame la ruta de hoy"               → usa get_daily_route
  → "quiero donar al banco de alimentos" → inicia flujo de donacion
  → Envia una FOTO de un producto       → Chuwi analiza con Vision
  → Envia una NOTA DE VOZ               → Chuwi transcribe y responde

  PRUEBA KUINE (solo encargados):
  → "generar brief del dia"  o  cmd:runbrief desde el menu
  → Chuwi delega a Kuine, tarda 30-90s, genera brief completo

{_c("FLUTTER APP", "bold")}
  Opcion 1 — emulador Android (recomendado en Windows):
    make flutter-run
    (imprime el comando con --dart-define ya rellenos)

  Opcion 2 — comando manual (sustituye IP por tu IP local):
    cd app
    flutter run \\
      --dart-define=SUPABASE_URL={os.getenv('SUPABASE_URL','https://xxx.supabase.co')} \\
      --dart-define=SUPABASE_ANON_KEY={os.getenv('SUPABASE_KEY','eyJ...')[:20]}... \\
      --dart-define=API_URL=http://TU_IP_LOCAL:{port}/api/v1

  IP local en Windows:  ipconfig | findstr IPv4

  PANTALLAS A PROBAR:
  Dashboard   → KPIs en tiempo real (criticos, valor en riesgo, merma)
  Scan        → Escaner de camara o introduce barcode manual
  Acciones    → Lista priorizada. Pulsa "Completar" en una accion
  Mapa        → Pasillos con codigo de color por urgencia
  Informes    → Briefs diarios, merma CSV, proveedores, ESG
  Agentes     → 4 tabs: estado 11 agentes, conversaciones, runs Kuine, decisiones
  Perfil      → Vincula tu cuenta de Telegram (pega el ID numerico)

{_c("VERIFICACION SUPABASE", "bold")} — pega en el SQL Editor:
  -- Ultimas conversaciones con Chuwi
  SELECT telegram_user_id, message_count, last_message_at
  FROM agent_conversations ORDER BY last_message_at DESC LIMIT 5;

  -- Mensajes con intent y tools
  SELECT role, intent_tag, tools_used, agent_source, created_at
  FROM agent_messages ORDER BY created_at DESC LIMIT 10;

  -- Sesiones activas
  SELECT telegram_user_id, messages_count, tools_called, kuine_calls
  FROM agent_sessions ORDER BY session_start DESC LIMIT 5;

  -- Decisiones de Kuine
  SELECT decision_type, score, reason, created_at
  FROM supervisor_decisions ORDER BY created_at DESC LIMIT 5;

  -- Usuarios de Telegram (vinculados y no vinculados)
  SELECT telegram_user_id, telegram_username, status, last_seen_at
  FROM telegram_users ORDER BY last_seen_at DESC LIMIT 10;

{_c("COMANDOS UTILES", "bold")}
  make check          → diagnostico completo del sistema
  make seed           → cargar/recargar datos demo
  make advance N=2    → simular que pasaron 2 dias (productos caducan)
  make demo-reset     → volver al estado inicial
  make brief          → forzar generacion de brief ahora
  make test           → correr 323 tests
""")
    print(SEP)
    print(_c("  Ctrl+C para parar el backend", "yellow"))
    print(SEP + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    only_check = "--check" in args
    do_seed = "--seed" in args

    print(f"\n{_c('MermaOps — Arranque del sistema', 'bold')}")
    print(f"Directorio: {ROOT}\n")

    env_ok = check_env()
    if not env_ok:
        print(f"\n{_c('BLOQUEADO: faltan variables de entorno en .env', 'red')}")
        print("Crea el archivo .env en la raiz del proyecto con las variables indicadas.")
        print("Ver plantilla: cat .env.example\n")
        sys.exit(1)

    sb_ok = check_supabase()
    bot_info = check_telegram()

    if only_check:
        print(f"\n{_c('Verificacion completada.', 'bold')}")
        sys.exit(0 if (sb_ok and bot_info) else 1)

    if do_seed:
        seed_demo()

    if check_backend_running():
        port = os.getenv("APP_PORT", "8001")
        _ok(f"Backend ya estaba corriendo en puerto {port}")
        print_test_guide(bot_info)
        sys.exit(0)

    proc = start_backend()
    print_test_guide(bot_info)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print(f"\n{_c('Backend detenido.', 'yellow')}\n")
        proc.terminate()
