"""
Crea los 3 usuarios de demo para MermaOps en Supabase.

Requiere SUPABASE_SERVICE_KEY en .env (la key de service_role, no la anon).
Puedes encontrarla en: Supabase Dashboard → Settings → API → service_role.

Usuarios creados:
  encargado@mermaops.es / Encargado2024!  → rol: staff   (encargado de tienda)
  supervisor@mermaops.es / Supervisor2024! → rol: manager (supervisor de zona)
  admin@mermaops.es / Admin2024!          → rol: admin   (acceso completo)

Uso: python scripts/create_demo_users.py
"""
import os
import sys
from pathlib import Path

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

try:
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
STORE_ID = os.getenv("STORE_ID", "demo-store-001")

if not SUPABASE_URL or not SERVICE_KEY:
    print("❌ Necesitas SUPABASE_URL y SUPABASE_SERVICE_KEY en tu .env")
    print("   Encuéntralas en: Supabase Dashboard → Settings → API → service_role")
    sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("❌ Instala supabase: pip install supabase")
    sys.exit(1)

admin_client = create_client(SUPABASE_URL, SERVICE_KEY)

DEMO_USERS = [
    {
        "email": "encargado@mermaops.es",
        "password": "Encargado2024!",
        "role": "staff",
        "full_name": "Carlos García",
    },
    {
        "email": "supervisor@mermaops.es",
        "password": "Supervisor2024!",
        "role": "manager",
        "full_name": "Ana Martínez",
    },
    {
        "email": "admin@mermaops.es",
        "password": "Admin2024!",
        "role": "admin",
        "full_name": "Director TFM",
    },
]


def _upsert_public_user(user_id: str, email: str, role: str) -> None:
    admin_client.table("users").upsert({
        "id": user_id,
        "email": email,
        "role": role,
        "store_id": STORE_ID,
    }).execute()


for u in DEMO_USERS:
    email = u["email"]
    print(f"\n→ {email} ({u['role']})...", end=" ", flush=True)
    try:
        res = admin_client.auth.admin.create_user({
            "email": email,
            "password": u["password"],
            "email_confirm": True,
            "user_metadata": {
                "full_name": u["full_name"],
                "role": u["role"],
            },
        })
        user_id = res.user.id
        _upsert_public_user(user_id, email, u["role"])
        print(f"✅ creado (ID: {str(user_id)[:8]}...)")
    except Exception as e:
        err = str(e)
        if "already been registered" in err or "already exists" in err or "already registered" in err:
            print("ya existe — actualizando rol...", end=" ", flush=True)
            try:
                # List users to find the existing one
                page = admin_client.auth.admin.list_users()
                existing = next(
                    (x for x in page if getattr(x, "email", "") == email), None
                )
                if existing:
                    _upsert_public_user(str(existing.id), email, u["role"])
                    print(f"✅ rol actualizado a '{u['role']}'")
                else:
                    print("❌ no encontrado en auth.users")
            except Exception as e2:
                print(f"❌ {e2}")
        else:
            print(f"❌ {err[:120]}")

print("\n")
print("┌──────────────────────────────────────────────────────────────────┐")
print("│              Credenciales de demo — MermaOps TFM                │")
print("├─────────────┬────────────────────────────────┬──────────────────┤")
print("│ Rol         │ Email                          │ Contraseña       │")
print("├─────────────┼────────────────────────────────┼──────────────────┤")
for u in DEMO_USERS:
    rol = {"staff": "Encargado", "manager": "Supervisor", "admin": "Admin"}[u["role"]]
    print(f"│ {rol:<11} │ {u['email']:<30} │ {u['password']:<16} │")
print("└─────────────┴────────────────────────────────┴──────────────────┘")
print()
print("✓ Usa estos datos con los botones de acceso rápido en la pantalla")
print("  de login de la app, o escríbelos manualmente.")
print()
print("Acceso por rol:")
print("  Encargado  → Dashboard, Escanear, Acciones, Mapa")
print("  Supervisor → + Informes, Agentes IA")
print("  Admin      → + Control Demo")
