"""Script temporal: intenta varias formas de conectar a Supabase y crear el schema."""
import psycopg2
import httpx
import os, sys, json
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
PROJECT_REF = SUPABASE_URL.split("//")[-1].split(".")[0] if SUPABASE_URL else ""
DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
SQL_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "schema.sql")

POOLER_HOSTS = [
    "aws-0-eu-west-1.pooler.supabase.com",
    "aws-0-eu-west-2.pooler.supabase.com",
    "aws-0-eu-central-1.pooler.supabase.com",
    "aws-0-eu-central-1.pooler.supabase.com",
    f"db.{PROJECT_REF}.supabase.co",
]

def try_psycopg2(host, port, user, password):
    try:
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password,
            database="postgres", sslmode="require", connect_timeout=8,
        )
        return conn
    except Exception as e:
        print(f"  FAIL {host}:{port} ({type(e).__name__}: {str(e)[:60]})")
        return None

def try_http_rpc_sql(sql_statement):
    """Intenta ejecutar SQL via REST usando service_role como admin."""
    url = f"https://{PROJECT_REF}.supabase.co/rest/v1/rpc/exec_sql"
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = httpx.post(url, headers=headers, json={"sql": sql_statement}, timeout=15)
        return r.status_code, r.text[:200]
    except Exception as e:
        return None, str(e)

def run_schema(conn):
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    existing = [r[0] for r in cur.fetchall()]
    print("Tablas existentes:", existing or "(ninguna)")
    if "products" in existing:
        print("Schema ya existe — tablas listas.")
        conn.close()
        return True

    with open(SQL_PATH, encoding="utf-8") as f:
        sql = f.read()

    lines = []
    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    sql_clean = "\n".join(lines)

    statements = [s.strip() for s in sql_clean.split(";") if s.strip()]
    ok = fail = 0
    for stmt in statements:
        try:
            cur.execute(stmt)
            ok += 1
        except Exception as e:
            msg = str(e)[:80]
            if "already exists" in msg or "duplicate" in msg.lower():
                ok += 1
            else:
                print(f"  WARN: {msg}")
                fail += 1

    print(f"Schema: {ok} OK, {fail} errores")
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1")
    tables = [r[0] for r in cur.fetchall()]
    print("Tablas:", tables)
    conn.close()
    return True

def main():
    if not SERVICE_KEY:
        print("ERROR: SUPABASE_SERVICE_KEY no está en .env")
        sys.exit(1)

    print("=== MermaOps DB Setup ===")

    for host in POOLER_HOSTS:
        for port in [5432, 6543]:
            user = f"postgres.{PROJECT_REF}" if "pooler" in host else "postgres"
            print(f"Trying {host}:{port} user={user}...")
            conn = try_psycopg2(host, port, user, DB_PASSWORD)
            if conn:
                print(f"  OK: conectado a {host}:{port}")
                return run_schema(conn)

    print("\nIntentando via REST con service_role...")
    url = f"https://{PROJECT_REF}.supabase.co/rest/v1/products?limit=1"
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
    }
    try:
        r = httpx.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            print("Tablas ya existen (products accesible via REST). OK.")
            return True
        elif r.status_code == 404:
            print("Table not found via REST — schema needed but can't create via REST.")
        else:
            print(f"REST: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        print(f"REST error: {e}")

    print("\n" + "="*50)
    print("NO SE PUDO CONECTAR A POSTGRESQL DIRECTAMENTE.")
    print("Hay que crear el schema manualmente en el Supabase Dashboard:")
    print(f"  1. Abre: https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new")
    print(f"  2. Pega el contenido de docs/schema.sql")
    print(f"  3. Pulsa Run")
    print("="*50)
    return False

if __name__ == "__main__":
    main()
