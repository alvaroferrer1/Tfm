"""
run_app.py — Lanza backend + emulador Android + app Flutter en un solo comando.

Uso:
    python scripts/run_app.py
    make app

Lee credenciales de .env automáticamente.
"""
from __future__ import annotations
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"

# Flutter puede no estar en el PATH del proceso Python — búscalo explícitamente
def _flutter_exe() -> str:
    import shutil
    found = shutil.which("flutter")
    if found:
        return found
    candidates = [
        r"C:\scr\flutter\bin\flutter.bat",
        r"C:\flutter\bin\flutter.bat",
        Path.home() / "flutter" / "bin" / "flutter.bat",
    ]
    for c in candidates:
        if Path(c).exists():
            return str(c)
    return "flutter"  # fallback — fallará con mensaje claro

def _load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        print("ERROR: .env no encontrado en", ROOT)
        sys.exit(1)
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

def _backend_running() -> bool:
    port = os.getenv("APP_PORT", "8001")
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
        return True
    except Exception:
        return False

def _start_backend():
    port = os.getenv("APP_PORT", "8001")
    if _backend_running():
        print(f"  Backend ya activo en puerto {port}")
        return
    print(f"  Arrancando backend en puerto {port}...")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "0.0.0.0", "--port", port, "--no-access-log"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(12):
        time.sleep(1)
        if _backend_running():
            print(f"  Backend OK — http://127.0.0.1:{port}/health")
            return
    print("  AVISO: backend tardando en arrancar, continuando...")

def _emulator_id() -> str | None:
    """Devuelve el device ID del emulador si está activo."""
    try:
        out = subprocess.check_output([_flutter_exe(), "devices"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "emulator" in line.lower() and "android" in line.lower():
                parts = line.split("•")
                if len(parts) >= 2:
                    return parts[1].strip()
    except Exception:
        pass
    return None

def _launch_emulator():
    if _emulator_id():
        print(f"  Emulador ya activo: {_emulator_id()}")
        return
    print("  Lanzando emulador Pixel_8a...")
    subprocess.Popen(
        [_flutter_exe(), "emulators", "--launch", "Pixel_8a"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print("  Esperando que arranque el emulador (hasta 60s)...")
    for i in range(60):
        time.sleep(1)
        if i % 10 == 9:
            print(f"  ... {i+1}s")
        if _emulator_id():
            print(f"  Emulador listo: {_emulator_id()}")
            return
    print("  AVISO: emulador tardando, continuando...")

def _run_flutter(device_id: str):
    supabase_url  = os.getenv("SUPABASE_URL", "")
    supabase_key  = os.getenv("SUPABASE_ANON_KEY", "")
    port          = os.getenv("APP_PORT", "8001")

    if not supabase_url or "YOUR_PROJECT" in supabase_url:
        print("ERROR: SUPABASE_URL no configurado en .env")
        sys.exit(1)
    if not supabase_key or "YOUR_ANON" in supabase_key:
        print("ERROR: SUPABASE_ANON_KEY no configurado en .env")
        sys.exit(1)

    cmd = [
        _flutter_exe(), "run",
        "-d", device_id,
        f"--dart-define=SUPABASE_URL={supabase_url}",
        f"--dart-define=SUPABASE_ANON_KEY={supabase_key}",
        f"--dart-define=API_URL=http://10.0.2.2:{port}/api/v1",
    ]
    print(f"\n  flutter run -d {device_id}")
    print(f"    SUPABASE_URL      = {supabase_url}")
    print(f"    SUPABASE_ANON_KEY = {supabase_key[:20]}...")
    print(f"    API_URL           = http://10.0.2.2:{port}/api/v1\n")
    subprocess.run(cmd, cwd=str(APP_DIR))

def main():
    print("\n" + "=" * 55)
    print("  MermaOps — Arranque completo")
    print("=" * 55)

    _load_env()
    _start_backend()
    _launch_emulator()

    device_id = _emulator_id()
    if not device_id:
        print("\nNo se encontró emulador. Opciones:")
        print("  1. Abre Android Studio > Device Manager > Launch Pixel_8a")
        print("  2. Conecta un móvil Android real por USB con depuración USB activada")
        print("  3. Ejecuta: flutter emulators --launch Pixel_8a")
        devices_out = subprocess.check_output([_flutter_exe(), "devices"], text=True, stderr=subprocess.DEVNULL)
        print("\nDispositivos disponibles:\n" + devices_out)
        sys.exit(1)

    _run_flutter(device_id)

if __name__ == "__main__":
    main()
