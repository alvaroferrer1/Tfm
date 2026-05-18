#!/usr/bin/env python3
"""
MermaOps — Setup interactivo de Supabase.

Ejecutar desde la raíz del proyecto:
    python scripts/setup_supabase.py

Hace:
  1. Verifica / crea el fichero .env con las credenciales
  2. Testea la conexión a Supabase
  3. Aplica el schema (docs/schema.sql) — seguro de re-ejecutar
  4. Crea el bucket 'evidence' si no existe
  5. Siembra los datos demo (seed.py + demo_actions.py)
  6. Imprime el checklist final de verificación
"""
from __future__ import annotations

import os
import sys
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Colores ──────────────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

ok   = lambda t: print(_c("92", f"  ✓ {t}"))
err  = lambda t: print(_c("91", f"  ✗ {t}"))
info = lambda t: print(_c("94", f"  → {t}"))
warn = lambda t: print(_c("93", f"  ⚠ {t}"))
h1   = lambda t: print(_c("1;96", f"\n{'━'*60}\n  {t}\n{'━'*60}"))


# ── 1. .env ───────────────────────────────────────────────────────────────────

_ENV_VARS = [
    ("ANTHROPIC_API_KEY",   "Clave API de Anthropic (https://console.anthropic.com)", True),
    ("SUPABASE_URL",        "URL de tu proyecto Supabase (https://xxxx.supabase.co)", True),
    ("SUPABASE_KEY",        "anon/public key de Supabase (Settings → API)", True),
    ("TELEGRAM_BOT_TOKEN",  "Token del bot de Telegram (BotFather → /newbot)", True),
    ("TELEGRAM_CHAT_ID",    "Chat ID del grupo Telegram (dejar vacío si no tienes)", False),
    ("STORE_ID",            "ID de la tienda demo", False),
    ("APP_ENV",             "Entorno (development / production)", False),
    ("APP_PORT",            "Puerto del servidor FastAPI", False),
    ("STORE_LAT",           "Latitud de la tienda (para previsión meteorológica)", False),
    ("STORE_LON",           "Longitud de la tienda", False),
]

_DEFAULTS = {
    "STORE_ID": "demo-store-001",
    "APP_ENV": "development",
    "APP_PORT": "8000",
    "STORE_LAT": "40.4168",
    "STORE_LON": "-3.7038",
    "TELEGRAM_CHAT_ID": "",
}


def step_env() -> dict[str, str]:
    h1("PASO 1 — Configuración de credenciales (.env)")

    env_path = ROOT / ".env"
    existing: dict[str, str] = {}

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip().strip('"').strip("'")
        ok(f".env encontrado en {env_path}")
    else:
        warn(".env no existe — lo crearemos ahora")

    values: dict[str, str] = dict(existing)

    for key, label, required in _ENV_VARS:
        current = values.get(key, _DEFAULTS.get(key, ""))
        if current:
            display = current[:8] + "***" if "KEY" in key or "TOKEN" in key else current
            info(f"{key} = {display}  (Enter para mantener)")
        else:
            if required:
                warn(f"{key} no configurado — {label}")
            else:
                info(f"{key} (opcional) — {label}")

        prompt = f"  {key}: "
        try:
            entered = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if entered:
            values[key] = entered
        elif not current and key in _DEFAULTS:
            values[key] = _DEFAULTS[key]
            info(f"Usando valor por defecto: {_DEFAULTS[key]}")
        elif required and not (current or entered):
            err(f"{key} es obligatorio. Añádelo manualmente a .env después.")

    # Escribir .env
    lines = ["# MermaOps — generado por setup_supabase.py\n"]
    for key, label, _ in _ENV_VARS:
        if key in values and values[key]:
            lines.append(f"{key}={values[key]}\n")
    env_path.write_text("".join(lines), encoding="utf-8")
    ok(f".env guardado en {env_path}")

    # Cargar para el resto del script
    for k, v in values.items():
        os.environ.setdefault(k, v)

    return values


# ── 2. Conexión Supabase ──────────────────────────────────────────────────────

def step_test_connection(values: dict) -> object:
    h1("PASO 2 — Verificando conexión a Supabase")

    url = values.get("SUPABASE_URL", "")
    key = values.get("SUPABASE_KEY", "")

    if not url or not key:
        err("SUPABASE_URL o SUPABASE_KEY no configurados. Salta este paso.")
        return None

    try:
        from supabase import create_client
        client = create_client(url, key)
        # Ping con una tabla que siempre existe en Supabase
        client.table("stores").select("id").limit(1).execute()
        ok("Conexión a Supabase correcta")
        return client
    except ImportError:
        err("supabase-py no instalado. Ejecuta: pip install -r requirements.txt")
        return None
    except Exception as e:
        msg = str(e)
        if "relation" in msg and "does not exist" in msg:
            warn("Conexión OK, pero las tablas no existen aún (normal — paso 3 las crea)")
            try:
                from supabase import create_client
                return create_client(url, key)
            except Exception:
                return None
        err(f"Error de conexión: {e}")
        return None


# ── 3. Schema SQL ─────────────────────────────────────────────────────────────

def step_schema(client) -> bool:
    h1("PASO 3 — Aplicando schema de base de datos")

    schema_path = ROOT / "docs" / "schema.sql"
    if not schema_path.exists():
        err(f"No se encuentra {schema_path}")
        return False

    sql = schema_path.read_text(encoding="utf-8")

    if client is None:
        warn("Sin cliente Supabase — no se puede aplicar el schema automáticamente.")
        print(textwrap.dedent("""
          Aplícalo manualmente:
            1. Abre tu proyecto en https://supabase.com
            2. SQL Editor → New query
            3. Pega el contenido de docs/schema.sql y ejecuta
        """))
        return False

    # Supabase REST API no permite ejecutar SQL arbitrario directamente.
    # Usamos el cliente de administración si tenemos service_role key,
    # o avisamos al usuario que lo haga manualmente en el SQL Editor.
    info("El schema debe aplicarse en el SQL Editor de Supabase.")
    info("Abriendo instrucciones...")

    print(textwrap.dedent(f"""
      ┌─────────────────────────────────────────────────────────┐
      │  Para aplicar el schema:                                │
      │  1. Abre: {(values.get('SUPABASE_URL','https://supabase.com') + '/sql').ljust(42)}│
      │  2. Pega el contenido de docs/schema.sql                │
      │  3. Haz clic en "Run"                                   │
      │                                                         │
      │  El schema es idempotente (IF NOT EXISTS / ON CONFLICT) │
      │  Se puede re-ejecutar sin riesgo.                       │
      └─────────────────────────────────────────────────────────┘
    """))

    try:
        resp = input("  ¿Ya has ejecutado el schema en Supabase? [s/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    if resp == "s":
        # Verificar que las tablas existen
        try:
            client.table("stores").select("id").limit(1).execute()
            ok("Tabla 'stores' detectada — schema aplicado correctamente")
            return True
        except Exception as e:
            err(f"Las tablas no responden: {e}")
            return False
    else:
        warn("Schema pendiente de aplicar. Continúa los demás pasos y aplícalo cuando puedas.")
        return False


# ── 4. Bucket de evidencias ───────────────────────────────────────────────────

def step_bucket(client) -> None:
    h1("PASO 4 — Bucket de almacenamiento 'evidence'")

    if client is None:
        warn("Sin cliente — no se puede crear el bucket automáticamente.")
        info("Crea el bucket 'evidence' (público) en Supabase → Storage.")
        return

    try:
        buckets = client.storage.list_buckets()
        names = [b.name if hasattr(b, "name") else b.get("name", "") for b in buckets]
        if "evidence" in names:
            ok("Bucket 'evidence' ya existe")
            return
    except Exception:
        pass

    try:
        client.storage.create_bucket("evidence", options={"public": True})
        ok("Bucket 'evidence' creado (público)")
    except Exception as e:
        msg = str(e)
        if "already exists" in msg.lower() or "duplicate" in msg.lower():
            ok("Bucket 'evidence' ya existe")
        else:
            warn(f"No se pudo crear el bucket automáticamente: {e}")
            info("Crea 'evidence' manualmente en Supabase → Storage → New bucket (public: true)")


# ── 5. Seed de datos demo ─────────────────────────────────────────────────────

def step_seed(values: dict) -> None:
    h1("PASO 5 — Datos demo (Super Martínez)")

    if not values.get("SUPABASE_URL") or not values.get("SUPABASE_KEY"):
        warn("Sin credenciales Supabase — no se pueden sembrar datos.")
        return

    try:
        resp = input("  ¿Quieres cargar los datos demo? (productos, lotes, acciones, historial 30d) [S/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if resp == "n":
        info("Seed omitido.")
        return

    env = {**os.environ, **{k: v for k, v in values.items() if v}}

    seed_scripts = [
        (ROOT / "backend" / "data" / "seed.py", "Productos, lotes, almacén, proveedores"),
        (ROOT / "backend" / "data" / "demo_actions.py", "Acciones, merma 30d, donaciones, comparativa, informes"),
    ]

    for script_path, description in seed_scripts:
        if not script_path.exists():
            warn(f"No se encuentra {script_path.name} — saltando")
            continue
        info(f"Ejecutando {script_path.name} — {description}")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            ok(f"{script_path.name} completado")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines()[-5:]:
                    print(f"    {line}")
        else:
            err(f"{script_path.name} falló (código {result.returncode})")
            if result.stderr.strip():
                for line in result.stderr.strip().splitlines()[-8:]:
                    print(f"    {_c('91', line)}")


# ── 6. Flutter pub get ────────────────────────────────────────────────────────

def step_flutter() -> None:
    h1("PASO 6 — Flutter: instalar dependencias")

    app_dir = ROOT / "app"
    if not app_dir.exists():
        warn("Directorio 'app/' no encontrado — saltando Flutter")
        return

    try:
        resp = input("  ¿Ejecutar 'flutter pub get' ahora? [S/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if resp == "n":
        info("flutter pub get omitido. Ejecuta manualmente: cd app && flutter pub get")
        return

    result = subprocess.run(
        ["flutter", "pub", "get"],
        cwd=str(app_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        ok("flutter pub get completado")
    else:
        err("flutter pub get falló")
        if result.stderr.strip():
            print(f"    {result.stderr.strip()[:300]}")
        info("Asegúrate de tener Flutter SDK en el PATH")


# ── 7. Checklist final ────────────────────────────────────────────────────────

def step_checklist(values: dict) -> None:
    h1("CHECKLIST FINAL")

    url = values.get("SUPABASE_URL", "")
    store_id = values.get("STORE_ID", "demo-store-001")

    print(textwrap.dedent(f"""
  Pasos manuales que pueden quedar pendientes:

  □  Aplicar docs/schema.sql en Supabase SQL Editor
       {url}/sql

  □  Crear usuario de prueba en Supabase:
       Authentication → Users → Add user
       Email: encargado@supermart.es | Password: demo1234
       Luego en SQL Editor:
         INSERT INTO users (id, email, role, store_id)
         VALUES ('<uuid>', 'encargado@supermart.es', 'manager', '{store_id}');

  □  Telegram: añadir el bot al grupo y anotar el chat_id
       https://api.telegram.org/bot<TOKEN>/getUpdates

  □  Iniciar el backend:
       make run   (o: python -m uvicorn backend.api.main:app --reload)

  □  Iniciar la app Flutter (con IP real si es dispositivo físico):
       cd app
       flutter run \\
         --dart-define=SUPABASE_URL={url or 'https://xxxx.supabase.co'} \\
         --dart-define=SUPABASE_ANON_KEY=eyJ... \\
         --dart-define=API_URL=http://TU_IP:8000/api/v1

  □  Generar el brief de demo:
       make brief
    """))

    ok("Setup completado. Consulta SETUP.md para más detalles.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(_c("1;96", "\n  MermaOps — Setup interactivo\n"))
    print("  Este script configura el entorno desde cero.")
    print("  Pulsa Enter para aceptar los valores actuales.\n")

    global values
    values = step_env()
    client = step_test_connection(values)
    step_schema(client)
    step_bucket(client)
    step_seed(values)
    step_flutter()
    step_checklist(values)


if __name__ == "__main__":
    main()
