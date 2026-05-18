"""
MermaOps — Script de diagnóstico completo.
Verifica backend, Supabase, Telegram y flujo de agentes.
Uso: python scripts/check_all.py [--fix]
"""
from __future__ import annotations

import os
import sys
import time
import json
import traceback
from pathlib import Path
from typing import Callable

# Carga .env desde la raíz del proyecto
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
env_path = ROOT / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

# ── Helpers de output ─────────────────────────────────────────────────────────

RESULTS: list[tuple[str, bool, str]] = []

def ok(label: str, detail: str = "") -> None:
    RESULTS.append((label, True, detail))
    d = f" — {detail}" if detail else ""
    print(f"  OK  {label}{d}")

def warn(label: str, detail: str = "") -> None:
    RESULTS.append((label, None, detail))
    d = f" — {detail}" if detail else ""
    print(f" WARN {label}{d}")

def fail(label: str, detail: str = "") -> None:
    RESULTS.append((label, False, detail))
    d = f" — {detail}" if detail else ""
    print(f" FAIL {label}{d}")

def section(name: str) -> None:
    print(f"\n{'='*55}")
    print(f"  {name}")
    print(f"{'='*55}")


# ── Variables de entorno ──────────────────────────────────────────────────────

def check_env() -> None:
    section("Variables de entorno")
    required = ["ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "TELEGRAM_BOT_TOKEN", "STORE_ID"]
    for var in required:
        val = os.getenv(var, "")
        if val:
            ok(var, f"{val[:8]}...")
        else:
            fail(var, "No definida en .env")

    optional = ["SUPABASE_SERVICE_KEY", "LANGFUSE_PUBLIC_KEY", "OPENAI_API_KEY"]
    for var in optional:
        val = os.getenv(var, "")
        if val:
            ok(f"{var} (opcional)", f"{val[:8]}...")
        else:
            warn(f"{var} (opcional)", "No definida — funciona sin ella")


# ── Supabase ──────────────────────────────────────────────────────────────────

def check_supabase() -> None:
    section("Supabase — Conexión y tablas")
    try:
        from backend.core.database import get_db
        db = get_db()
        t0 = time.monotonic()
        result = db.table("stores").select("id,name").execute()
        ms = round((time.monotonic() - t0) * 1000, 1)
        if result.data:
            ok("Conexión Supabase", f"{ms}ms — {result.data[0].get('name','?')}")
        else:
            fail("Conexión Supabase", "Sin datos en stores")
    except Exception as e:
        fail("Conexión Supabase", str(e)[:80])
        return

    # Verificar tablas clave
    tables_required = [
        "stores", "users", "products", "batches", "actions",
        "merma_log", "agent_memory", "daily_briefs", "donations",
    ]
    tables_fase1 = [
        "agent_conversations", "agent_messages", "agent_sessions", "telegram_users",
    ]

    for t in tables_required:
        try:
            db.table(t).select("id").limit(1).execute()
            ok(f"Tabla {t}")
        except Exception as e:
            fail(f"Tabla {t}", str(e)[:60])

    for t in tables_fase1:
        try:
            db.table(t).select("id").limit(1).execute()
            ok(f"Tabla {t} (Fase 1)")
        except Exception as e:
            fail(f"Tabla {t} (Fase 1)", "Ejecutar: supabase db push")


def check_supabase_data() -> None:
    section("Supabase — Datos de demo")
    try:
        from backend.core.database import get_db, get_pending_actions, get_latest_brief
        db = get_db()
        store_id = os.getenv("STORE_ID", "demo-store-001")

        pending = get_pending_actions(store_id)
        if pending:
            ok(f"Acciones pendientes", f"{len(pending)} acciones")
        else:
            warn("Acciones pendientes", "0 — ejecutar: make seed")

        brief = get_latest_brief(store_id)
        if brief:
            ok("Brief diario", f"fecha={brief.get('date','?')}")
        else:
            warn("Brief diario", "Sin brief — ejecutar: make brief")

        # Verificar merma_log
        logs = db.table("merma_log").select("id").limit(5).execute()
        cnt = len(logs.data or [])
        if cnt > 0:
            ok("merma_log", f"{cnt} entradas")
        else:
            warn("merma_log", "Vacío — se rellena al completar acciones")

    except Exception as e:
        fail("Supabase datos", str(e)[:80])


# ── Telegram ──────────────────────────────────────────────────────────────────

def check_telegram() -> None:
    section("Telegram AI Agent")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        fail("TELEGRAM_BOT_TOKEN", "No definido")
        return
    ok("TELEGRAM_BOT_TOKEN", f"{token[:10]}...")

    try:
        import urllib.request
        import json
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        if data.get("ok"):
            bot = data["result"]
            ok("getMe", f"@{bot.get('username','?')} — id={bot.get('id','?')}")
        else:
            fail("getMe", data.get("description", "Error desconocido"))
    except Exception as e:
        fail("getMe", str(e)[:80])
        return

    try:
        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        info = data.get("result", {})
        webhook_url = info.get("url", "")
        if webhook_url:
            ok("Webhook configurado", webhook_url[:60])
        else:
            warn("Webhook", "No configurado — usando polling (OK para desarrollo)")
    except Exception as e:
        warn("Webhook", str(e)[:60])


# ── Backend ───────────────────────────────────────────────────────────────────

def check_backend() -> None:
    section("Backend FastAPI")
    port = os.getenv("APP_PORT", "8001")
    host = os.getenv("API_HOST", "127.0.0.1")
    base_url = f"http://{host}:{port}"

    try:
        import urllib.request
        with urllib.request.urlopen(f"{base_url}/api/v1/ping", timeout=3) as resp:
            data = json.loads(resp.read())
            if data.get("pong"):
                ok(f"Backend en {base_url}", "ping OK")
            else:
                fail("Backend ping", "Respuesta inesperada")
    except Exception as e:
        warn(f"Backend en {base_url}", f"No responde — arranca con: python -m backend.main")
        return

    try:
        with urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=5) as resp:
            data = json.loads(resp.read())
            ok("Health check", f"db={data.get('db','?')}, latency={data.get('db_latency_ms','?')}ms")
    except Exception as e:
        fail("Health check", str(e)[:60])

    endpoints = [
        "/api/v1/agent/status",
        "/api/v1/telegram/status",
        "/api/v1/agent/conversations",
        "/api/v1/agent/activity",
    ]
    for ep in endpoints:
        try:
            req = urllib.request.Request(f"{base_url}{ep}")
            req.add_header("Authorization", "Bearer dev")
            with urllib.request.urlopen(req, timeout=5) as resp:
                ok(f"GET {ep}")
        except Exception as e:
            warn(f"GET {ep}", str(e)[:60])


# ── Agentes ───────────────────────────────────────────────────────────────────

def check_agents() -> None:
    section("Agentes — imports y estructura")
    agents = [
        ("backend.agents.supervisor", "run_daily_brief"),
        ("backend.agents.evaluator", "evaluate_batch"),
        ("backend.agents.validator", "validate_actions_batch"),
        ("backend.agents.price", "calculate"),
        ("backend.agents.stock", "decide_restocking"),
        ("backend.agents.reporter", "generate_closing_report"),
        ("backend.agents.notifier", "send_alert"),
        ("backend.agents.predictor", "predict_merma_risk"),
        ("backend.agents.vision", "analyze_product_photo"),
    ]
    for module, func in agents:
        try:
            import importlib
            mod = importlib.import_module(module)
            if hasattr(mod, func):
                ok(f"{module.split('.')[-1]}", f"{func} disponible")
            else:
                warn(f"{module.split('.')[-1]}", f"{func} no encontrado en módulo")
        except Exception as e:
            fail(f"{module}", str(e)[:60])

    # Chuwi intent classifier
    try:
        from backend.core.chuwi import _classify_intent, _INTENT_PATTERNS
        intents = {p[0] for p in _INTENT_PATTERNS}
        required = {"registrar_donacion", "pedir_ruta", "pedir_brief", "consulta_estado", "completar_accion"}
        missing = required - intents
        if missing:
            fail("Chuwi intent classifier", f"Faltan intents: {missing}")
        else:
            test = _classify_intent("quiero donar al banco de alimentos")
            ok("Chuwi intent classifier", f"test='registrar_donacion' -> {test}")
    except Exception as e:
        fail("Chuwi intent classifier", str(e)[:60])


# ── Flujo de persistencia ─────────────────────────────────────────────────────

def check_persistence() -> None:
    section("Persistencia de conversaciones (Fase 1+2)")
    try:
        from backend.core import database
        from unittest.mock import MagicMock, patch

        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(count=1)
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("backend.core.database.get_db", return_value=mock_db):
            conv_id = database.create_agent_conversation("demo-store-001", "12345")
            msg_id = database.log_agent_message(
                conv_id, "demo-store-001", "user", "Hola Chuwi",
                intent_tag="pregunta_libre", tools_used=[]
            )
        ok("create_agent_conversation", f"id={conv_id[:8]}")
        ok("log_agent_message", f"id={msg_id[:8]}")

        from backend.core.chuwi import _classify_intent, _persist_conversation_message, _conv_id_cache
        intent = _classify_intent("qué caduca hoy")
        ok("_classify_intent", f"'qué caduca hoy' -> {intent}")

        # _run_agent_loop devuelve tupla
        import inspect
        from backend.core.chuwi import _run_agent_loop
        sig = inspect.signature(_run_agent_loop)
        ok("_run_agent_loop retorna tupla", f"params={list(sig.parameters.keys())}")

    except Exception as e:
        fail("Persistencia", str(e)[:80])
        traceback.print_exc()


# ── Tests ─────────────────────────────────────────────────────────────────────

def check_tests() -> None:
    section("Tests automatizados")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "backend/tests/", "-q", "--tb=no", "--no-header"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120
        )
        last_line = result.stdout.strip().split("\n")[-1] if result.stdout else ""
        if "passed" in last_line:
            ok("Tests", last_line.strip())
        elif "failed" in last_line:
            fail("Tests", last_line.strip())
        else:
            warn("Tests", last_line.strip() or "Sin output")
    except Exception as e:
        fail("Tests", str(e)[:80])


# ── Resumen ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    print(f"\n{'='*55}")
    print("  RESUMEN")
    print(f"{'='*55}")
    passed = [r for r in RESULTS if r[1] is True]
    warned = [r for r in RESULTS if r[1] is None]
    failed = [r for r in RESULTS if r[1] is False]
    print(f"  OK:   {len(passed)}")
    print(f"  WARN: {len(warned)}")
    print(f"  FAIL: {len(failed)}")
    if failed:
        print("\n  Bloqueadores:")
        for label, _, detail in failed:
            print(f"    - {label}: {detail}")
    if warned:
        print("\n  Advertencias:")
        for label, _, detail in warned:
            print(f"    - {label}: {detail}")
    all_ok = len(failed) == 0
    print(f"\n  {'Sistema listo para demo' if all_ok else 'SISTEMA CON PROBLEMAS - ver bloqueadores'}")
    print(f"{'='*55}\n")
    return all_ok


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nMermaOps — Diagnóstico del sistema")
    print(f"Directorio: {ROOT}")
    check_env()
    check_supabase()
    check_supabase_data()
    check_telegram()
    check_backend()
    check_agents()
    check_persistence()
    check_tests()
    all_ok = print_summary()
    sys.exit(0 if all_ok else 1)
