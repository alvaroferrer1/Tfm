"""
start_all.py — Levanta TODO MermaOps en un solo comando.

Qué hace:
  1. Verifica .env y conexión Supabase
  2. Arranca el backend FastAPI en puerto 8001 (con Chuwi/Telegram activo)
  3. Sirve la app Flutter web en puerto 3000
  4. Abre Chrome con la app
  5. Imprime la guía completa de qué probar y cómo

Uso:
    python scripts/start_all.py
    make todo
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent.parent
APP_WEB_DIR = ROOT / "app" / "build" / "web"
PORT_BACKEND = int(os.getenv("APP_PORT", "8001"))
PORT_WEB = 3000

# Cargar .env
env_path = ROOT / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

SEP = "=" * 65
C = {
    "green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
    "blue": "\033[94m", "cyan": "\033[96m", "bold": "\033[1m", "reset": "\033[0m",
}
def c(text, color): return f"{C.get(color,'')}{text}{C['reset']}"
def ok(msg): print(f"  {c('OK  ','green')}{msg}")
def fail(msg): print(f"  {c('FAIL','red')}{msg}")
def info(msg): print(f"  {c('....','blue')}{msg}")


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def check_env() -> bool:
    """Verifica variables de entorno mínimas."""
    required = ["ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "TELEGRAM_BOT_TOKEN"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        fail(f"Faltan en .env: {', '.join(missing)}")
        return False
    ok(".env completo")
    return True


def check_supabase() -> bool:
    """Ping a Supabase para verificar conexión."""
    try:
        from backend.core.database import get_db
        db = get_db()
        db.table("stores").select("id").limit(1).execute()
        ok("Supabase conectado")
        return True
    except Exception as e:
        fail(f"Supabase no responde: {str(e)[:60]}")
        return False


def start_backend() -> subprocess.Popen | None:
    """Arranca el backend si no está ya corriendo."""
    if _port_in_use(PORT_BACKEND):
        ok(f"Backend ya corriendo en :{PORT_BACKEND}")
        return None

    info(f"Arrancando backend en :{PORT_BACKEND}...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.main"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.5)
        if _port_in_use(PORT_BACKEND):
            ok(f"Backend activo en http://localhost:{PORT_BACKEND}")
            return proc
        if proc.poll() is not None:
            fail("Backend terminó inesperadamente")
            return None
    fail("Backend tardó demasiado en arrancar")
    return None


def build_web_if_needed() -> bool:
    """Compila Flutter web si no hay build o si está desactualizado."""
    if APP_WEB_DIR.exists() and (APP_WEB_DIR / "index.html").exists():
        ok(f"Build web existente en {APP_WEB_DIR.name}")
        return True

    info("Compilando Flutter web (puede tardar 30-60s)...")
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    api = os.getenv("API_URL", f"http://localhost:{PORT_BACKEND}/api/v1")

    result = subprocess.run([
        "flutter", "build", "web", "--release",
        f"--dart-define=API_URL={api}",
        f"--dart-define=SUPABASE_URL={url}",
        f"--dart-define=SUPABASE_ANON_KEY={key}",
    ], cwd=str(ROOT / "app"), capture_output=True)

    if result.returncode == 0:
        ok("Flutter web compilado")
        return True
    fail("Flutter build falló — usa: flutter build web desde app/")
    return False


def start_web_server() -> subprocess.Popen | None:
    """Sirve el build de Flutter web en puerto 3000."""
    if _port_in_use(PORT_WEB):
        ok(f"Servidor web ya activo en :{PORT_WEB}")
        return None

    info(f"Sirviendo app Flutter web en :{PORT_WEB}...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT_WEB)],
        cwd=str(APP_WEB_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    if _port_in_use(PORT_WEB):
        ok(f"App web activa en http://localhost:{PORT_WEB}")
        return proc
    fail("Servidor web no arrancó")
    return None


def print_guide() -> None:
    """Guía completa de pruebas."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot_user = "@ChuwiMermaOpsBot"

    print(f"\n{SEP}")
    print(c("  MERMAOPS — TODO LISTO", "bold"))
    print(SEP)
    print(f"""
{c("APP FLUTTER", "bold")} → http://localhost:{PORT_WEB}
  (Chrome se abrirá automáticamente)

  Login:  email + contraseña de Supabase
  Dev:    si ves pantalla de carga → espera 3-4s (carga inicial)

  Pantallas a probar:
  - Dashboard   → KPIs tiempo real (críticos, valor en riesgo)
  - Scan        → escanea un barcode o introduce uno manual
  - Acciones    → lista priorizada, pulsa Completar en una acción
  - Mapa        → pasillos con código de color urgencia
  - Informes    → briefs, merma CSV, ESG
  - Agentes     → 12 agentes con estado, conversaciones, decisiones Kuine


{c("CHUWI AGENTE TELEGRAM", "bold")} → {bot_user}
  Abre Telegram y escribe en {bot_user}:

  1. /start
     → Si no estás vinculado: Chuwi te da tu ID numérico
     → Pégalo en la app (Perfil > Vincular Telegram)

  2. Pruebas de agente real (una vez vinculado):
     "hola, cuántos críticos hay hoy?"
     "dame la ruta del día"
     "cuánto hemos perdido esta semana"
     "quiero donar al banco de alimentos"
     [foto de un producto]  → visión automática
     "ya lo rebajé"         → completa acción

  3. Prueba de jerga nueva:
     "¿qué hay que hacer ahora?"
     → Debe usar términos: fleje, lineal, FEFO, pasillo frío


{c("BACKEND API", "bold")} → http://localhost:{PORT_BACKEND}
  Docs interactivas: http://localhost:{PORT_BACKEND}/docs

  Endpoints clave (usar token: dev-bypass):
  curl -H "Authorization: Bearer dev-bypass" \\
       http://localhost:{PORT_BACKEND}/api/v1/dashboard

  curl -H "Authorization: Bearer dev-bypass" \\
       http://localhost:{PORT_BACKEND}/api/v1/reports/tfm/pdf \\
       -o MermaOps_TFM_Defensa.pdf


{c("PDF DEFENSA TFM", "bold")}
  Desde terminal:
  curl -H "Authorization: Bearer dev-bypass" \\
       http://localhost:{PORT_BACKEND}/api/v1/reports/tfm/pdf \\
       -o MermaOps_TFM_Defensa.pdf

  Incluye: portada, problema/solución, 12 agentes, métricas/ROI,
           preguntas del tribunal, estado real verificado.


{c("SIMULAR DATOS", "bold")}
  make advance N=2    → productos caducan (aparecen críticos)
  make demo-reset     → volver al estado inicial
  make brief          → generar brief ahora (sin esperar las 7:30)
  make status         → ver estado actual de la tienda


{c("VERIFICAR EN SUPABASE", "bold")} (SQL Editor):
  SELECT * FROM agent_messages ORDER BY created_at DESC LIMIT 5;
  SELECT * FROM supervisor_decisions ORDER BY created_at DESC LIMIT 5;
  SELECT * FROM actions WHERE status='pending' ORDER BY priority_score DESC;
""")
    print(c("  Ctrl+C para parar todo", "yellow"))
    print(SEP + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{c('MermaOps — Levantando todo...', 'bold')}\n")

    # 1. Verificar entorno
    if not check_env():
        print(f"\n{c('Crea el .env con las variables requeridas.', 'red')}\n")
        sys.exit(1)

    # 2. Verificar Supabase
    check_supabase()

    # 3. Backend
    backend_proc = start_backend()

    # 4. Flutter web
    web_ok = build_web_if_needed()
    web_proc = start_web_server() if web_ok else None

    # 5. Abrir Chrome
    if web_ok and _port_in_use(PORT_WEB):
        time.sleep(1)
        try:
            webbrowser.open(f"http://localhost:{PORT_WEB}")
            ok("Chrome abierto con la app Flutter")
        except Exception:
            info(f"Abre Chrome manualmente: http://localhost:{PORT_WEB}")

    # 6. Guía
    print_guide()

    # Mantener vivo mientras el usuario prueba
    try:
        procs = [p for p in [backend_proc, web_proc] if p is not None]
        if procs:
            procs[0].wait()
        else:
            # Todo ya estaba corriendo — solo mostrar la guía
            input("Pulsa Enter para salir...\n")
    except KeyboardInterrupt:
        print(f"\n{c('Parando servicios...', 'yellow')}")
        for p in [backend_proc, web_proc]:
            if p:
                p.terminate()
        print(c("MermaOps detenido.\n", "yellow"))
