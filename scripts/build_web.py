"""
build_web.py — Compila la app Flutter para web y la sirve en localhost:3000.

Lee las credenciales del .env en la raíz del proyecto.
Evita el problema de cut -d= -f2 que trunca claves base64 con = al final.

Uso:
    python scripts/build_web.py          # build + serve
    python scripts/build_web.py --build  # solo build
    python scripts/build_web.py --serve  # solo serve (si ya compiló)
"""
from __future__ import annotations
import os
import sys
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent.parent
APP_DIR = ROOT / "app"
WEB_DIR = APP_DIR / "build" / "web"
PORT = 3000


def load_env(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def build(env: dict[str, str]) -> bool:
    supabase_url = env.get("SUPABASE_URL", "")
    supabase_key = env.get("SUPABASE_KEY", "")
    api_url = env.get("API_URL", "http://localhost:8001/api/v1")

    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL y SUPABASE_KEY deben estar en el .env")
        return False

    print(f"Compilando Flutter web...")
    print(f"  API_URL      = {api_url}")
    print(f"  SUPABASE_URL = {supabase_url[:40]}...")
    print()

    cmd = [
        "flutter", "build", "web",
        "--release",
        f"--dart-define=API_URL={api_url}",
        f"--dart-define=SUPABASE_URL={supabase_url}",
        f"--dart-define=SUPABASE_ANON_KEY={supabase_key}",
    ]

    result = subprocess.run(cmd, cwd=APP_DIR)
    if result.returncode != 0:
        print("\nERROR: flutter build web falló.")
        return False

    print(f"\nBuild completado: {WEB_DIR}")
    return True


def serve() -> None:
    if not WEB_DIR.exists():
        print(f"ERROR: {WEB_DIR} no existe. Ejecuta primero: python scripts/build_web.py --build")
        sys.exit(1)

    print(f"\nSirviendo en http://localhost:{PORT}")
    print("Abre Chrome en esa URL. Ctrl+C para parar.\n")
    os.chdir(WEB_DIR)
    subprocess.run([sys.executable, "-m", "http.server", str(PORT)])


if __name__ == "__main__":
    args = sys.argv[1:]
    env = load_env(ROOT / ".env")

    only_build = "--build" in args
    only_serve = "--serve" in args

    if only_serve:
        serve()
    elif only_build:
        if not build(env):
            sys.exit(1)
    else:
        if build(env):
            serve()
        else:
            sys.exit(1)
