"""
pre_defensa.py — Ejecutar esto 30 MINUTOS antes de entrar al tribunal.

Hace TODO automáticamente:
  1. Verifica conexión a Supabase
  2. Avanza la demo 1 día para tener productos críticos frescos
  3. Genera el brief de hoy (en background, ~60s)
  4. Verifica que Telegram está activo
  5. Imprime el resumen de estado para mostrar en la defensa

Uso:
    python scripts/pre_defensa.py
    make pre-defensa
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

SEP = "=" * 60
OK  = "\033[92m✓\033[0m"
ERR = "\033[91m✗\033[0m"
INF = "\033[94m→\033[0m"

def section(title): print(f"\n{SEP}\n  {title}\n{SEP}")
def ok(msg):  print(f"  {OK}  {msg}")
def err(msg): print(f"  {ERR}  {msg}")
def info(msg):print(f"  {INF}  {msg}")


# ── 1. Supabase ───────────────────────────────────────────────────────────────
section("1/5  Supabase")
try:
    from backend.core.database import get_db, get_pending_actions, get_latest_brief
    db = get_db()
    store = db.table("stores").select("name").eq("id", "demo-store-001").execute()
    ok(f"Conectado — tienda: {store.data[0]['name']}")
except Exception as e:
    err(f"Supabase no responde: {e}")
    sys.exit(1)


# ── 2. Avanzar 1 día ─────────────────────────────────────────────────────────
section("2/5  Avanzar demo 1 día")
try:
    from backend.data.advance_demo import advance
    r = advance(1, store_id="demo-store-001", generate_brief=False)
    ok(f"Demo avanzada: {r.get('batches_updated',0)} lotes actualizados")
    if r.get("newly_critical"):
        ok(f"Nuevos críticos: {', '.join(r['newly_critical'][:3])}")
    elif r.get("newly_high"):
        info(f"Nuevos altos: {', '.join(r['newly_high'][:3])}")
except Exception as e:
    err(f"advance_demo falló: {e}")


# ── 3. Brief de hoy ──────────────────────────────────────────────────────────
section("3/5  Brief del día")
from datetime import date
brief = get_latest_brief("demo-store-001")
if brief and str(brief.get("date","")) == str(date.today()):
    ok(f"Brief ya existe para hoy ({brief['date']}) — {brief.get('actions_count',0)} acciones")
else:
    info("Generando brief (Kuine con IA — ~60s)...")
    import threading
    brief_done = threading.Event()
    brief_result = {}

    def _gen():
        try:
            from backend.agents.supervisor import run_daily_brief
            brief_result["text"] = run_daily_brief("demo-store-001")
        except Exception as ex:
            brief_result["error"] = str(ex)
        finally:
            brief_done.set()

    t = threading.Thread(target=_gen, daemon=True)
    t.start()

    # Mostrar progreso cada 10s
    elapsed = 0
    while not brief_done.wait(timeout=10):
        elapsed += 10
        print(f"    [{elapsed}s] Kuine analizando productos...", end="\r")
    print()

    if "error" in brief_result:
        err(f"Error generando brief: {brief_result['error'][:80]}")
    else:
        ok(f"Brief generado correctamente")


# ── 4. Telegram ──────────────────────────────────────────────────────────────
section("4/5  Telegram bot")
try:
    import asyncio
    from telegram import Bot
    async def check_bot():
        bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN",""))
        info_b = await bot.get_me()
        return info_b.username
    username = asyncio.run(check_bot())
    ok(f"Bot activo: @{username}")
except Exception as e:
    if "Conflict" in str(e) or "409" in str(e):
        ok("Bot activo (polling en ejecución — 409 esperado)")
    else:
        err(f"Telegram error: {e}")


# ── 5. Estado final ──────────────────────────────────────────────────────────
section("5/5  Estado para la defensa")
pending = get_pending_actions("demo-store-001")
critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
high     = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
brief    = get_latest_brief("demo-store-001")
runs     = db.table("agent_runs").select("id").eq("store_id","demo-store-001").execute()
decisions= db.table("supervisor_decisions").select("id").eq("store_id","demo-store-001").execute()

print(f"""
  Acciones pendientes : {len(pending):>3}  ({len(critical)} CRÍTICAS, {len(high)} altas)
  Último brief        : {brief['date'] if brief else 'NINGUNO ← PROBLEMA'}
  Runs de Kuine en BD : {len(runs.data):>3}
  Decisiones en BD    : {len(decisions.data):>3}
""")

if len(critical) == 0:
    info("Sin críticos — ejecuta: make advance N=2")
elif len(critical) >= 2:
    ok(f"{len(critical)} productos críticos listos para la demo")

if not brief or str(brief.get("date","")) != str(date.today()):
    err("BRIEF NO ES DE HOY — regenera antes de entrar")
else:
    ok("Brief de hoy ✓ — listo para mostrar")

print(f"\n{SEP}")
print("  SISTEMA LISTO PARA LA DEFENSA")
print(f"  Backend  →  http://localhost:8001/health")
print(f"  App      →  make arranca (Chrome)")
print(f"  Telegram →  @ChuwiMermaOpsBot")
print(f"{SEP}\n")
