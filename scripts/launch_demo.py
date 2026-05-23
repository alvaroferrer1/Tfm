#!/usr/bin/env python3
"""
launch_demo.py — Arranca TODO para la demo TFM en un solo comando.

Uso:
    python scripts/launch_demo.py
    make demo

Hace:
    1. Carga .env con las credenciales
    2. Comprueba si el backend ya está corriendo (:8001)
    3. Si no, lo arranca en background
    4. Espera hasta que /health responda
    5. Abre hyperframes_demo/demo.html en el navegador
    6. Imprime la guía de presentación completa
"""
import os
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_HTML = ROOT / "hyperframes_demo" / "demo.html"
BACKEND_PORT = int(os.getenv("APP_PORT", 8001))


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        print("❌  No se encontró .env")
        print("    Crea uno con: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY,")
        print("    TELEGRAM_BOT_TOKEN, STORE_ID, APP_PORT=8001")
        sys.exit(1)
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def check_backend():
    import urllib.request
    try:
        url = f"http://localhost:{BACKEND_PORT}/health"
        with urllib.request.urlopen(url, timeout=2):
            return True
    except Exception:
        return False


def start_backend():
    env = os.environ.copy()
    return subprocess.Popen(
        [sys.executable, "-m", "backend.main"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_backend(timeout=35):
    print(f"  Esperando backend en :{BACKEND_PORT}", end="", flush=True)
    for _ in range(timeout):
        if check_backend():
            print(" ✅")
            return True
        time.sleep(1)
        print(".", end="", flush=True)
    print(" ❌  timeout")
    return False


def print_guide():
    store = os.getenv("STORE_ID", "demo-store-001")
    sep = "─" * 62
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          MermaOps — GUÍA DE PRESENTACIÓN TFM 2026           ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Backend:   http://localhost:{BACKEND_PORT}/health{' ' * (32 - len(str(BACKEND_PORT)))}║")
    print(f"║  Demo:      hyperframes_demo/demo.html (abierto en Chrome)  ║")
    print(f"║  Telegram:  @ChuwiMermaOpsBot                               ║")
    print(f"║  Tienda:    {store:<49}║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  TECLADO EN LA DEMO:                                         ║")
    print("║    ESPACIO    pausa / play                                   ║")
    print("║    ← →        escena anterior / siguiente                    ║")
    print("║    F          pantalla completa                              ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  ESCENAS (15 en total):                                      ║")
    print("║  S01  El problema — 1.3M toneladas residuos España           ║")
    print("║  S02  Arquitectura — 11 agentes especializados               ║")
    print("║  S03  Kuine en acción — loop agéntico real 07:30            ║")
    print("║  S04  Evaluador — extended thinking + scores                 ║")
    print("║  S05  Validador — 23/23 ataques adversariales bloqueados     ║")
    print("║  S06  Consenso — 3 instancias votando en paralelo            ║")
    print("║  S07  Predictor — Open-Meteo + historial 30 días            ║")
    print("║  S08  Visión IA — foto de producto → JSON estructurado       ║")
    print("║  S09  Chuwi — streaming + memoria episódica                  ║")
    print("║  S10  ★ APP + TELEGRAM JUNTOS — momento impactante ★        ║")
    print("║  S11  ★ RED DE 11 AGENTES — arquitectura completa ★         ║")
    print("║  S12  Simulador temporal — avanzar días en vivo              ║")
    print("║  S13  ESG — impacto social y fiscal Ley 49/2002              ║")
    print("║  S14  Evaluación cuantitativa — 439 tests / 100%             ║")
    print("║  S15  FIN                                                    ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  TELEGRAM — frases de demostración:                         ║")
    print("║    'qué hay crítico ahora'                                   ║")
    print("║    'cuánto ahorramos esta semana'                            ║")
    print("║    'analiza merluza fresca'                                  ║")
    print("║    'dame el resumen del día'                                 ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  SIMULADOR (en otro terminal):                               ║")
    print("║    make advance N=3   → simula 3 días → nuevos CRÍTICOS      ║")
    print("║    make demo-reset    → vuelve al estado inicial             ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def main():
    print()
    print("  MermaOps — Demo TFM 2026")
    print()

    load_env()

    if check_backend():
        print(f"✅  Backend ya corriendo en :{BACKEND_PORT}")
        backend_proc = None
    else:
        print(f"🚀  Arrancando backend en :{BACKEND_PORT}...")
        backend_proc = start_backend()
        if not wait_for_backend(35):
            print("\n❌  El backend no arrancó. Comprueba las credenciales en .env")
            print("    Prueba: python -m backend.main")
            if backend_proc:
                backend_proc.terminate()
            sys.exit(1)

    if not DEMO_HTML.exists():
        print(f"❌  No se encuentra {DEMO_HTML}")
        sys.exit(1)

    demo_url = DEMO_HTML.as_uri()
    print(f"🌐  Abriendo demo en el navegador...")
    webbrowser.open(demo_url)
    time.sleep(0.5)

    print_guide()

    if backend_proc:
        print("⚡  Backend corriendo. Ctrl+C para detener todo.")
        try:
            backend_proc.wait()
        except KeyboardInterrupt:
            print("\n🛑  Deteniendo backend...")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_proc.kill()
            print("✅  Demo finalizada.")


if __name__ == "__main__":
    main()
