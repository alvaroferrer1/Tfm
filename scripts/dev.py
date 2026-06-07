"""
dev.py — Arranca MermaOps para desarrollo en Chrome. Un comando, cero tokens.

  make arranca   ← esto
  make para      ← mata todo

Qué hace:
  1. Si el backend NO está en :8001, lo arranca en segundo plano.
  2. Lanza flutter run -d chrome con la URL correcta.
  3. Abre Chrome automáticamente.

No hace diagnósticos, no gasta tokens, no pregunta nada.
"""
from __future__ import annotations

import os
import subprocess
import sys
import socket
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
APP_DIR = ROOT / "app"
PORT = int(os.getenv("APP_PORT", "8001"))

env_path = ROOT / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)
    except ImportError:
        pass


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_backend():
    if _port_open(PORT):
        print(f"[OK] Backend ya en :{PORT}")
        return
    print(f"[..] Arrancando backend en :{PORT}...")
    log_file = open(ROOT / ".tmp" / "backend.log", "w") if (ROOT / ".tmp").exists() else subprocess.DEVNULL
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=ROOT,
        stdout=log_file,
        stderr=log_file,
    )
    for _ in range(20):
        time.sleep(1)
        if _port_open(PORT):
            print(f"[OK] Backend listo en :{PORT}")
            return
    print("[!!] Backend tardó más de 20s — revisa .tmp/backend.log")


def run_flutter():
    api_url = f"http://localhost:{PORT}/api/v1"
    print(f"[..] Flutter run -d chrome → {api_url}")
    subprocess.run(
        ["flutter", "run", "-d", "chrome",
         f"--dart-define=API_URL={api_url}"],
        cwd=APP_DIR,
    )


if __name__ == "__main__":
    (ROOT / ".tmp").mkdir(exist_ok=True)
    start_backend()
    run_flutter()
