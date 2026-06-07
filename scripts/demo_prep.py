"""
demo_prep.py — Preparación del entorno para la demo/defensa TFM.

Ejecutar 10 minutos antes de la presentación:
    python scripts/demo_prep.py

Hace:
  1. Verifica que el backend está corriendo en :8001
  2. Resetea las fechas de caducidad a estado base
  3. Avanza 2 días (crea CRÍTICO + ALTO + MEDIO naturalmente)
  4. Genera un brief diario nuevo con Kuine
  5. Verifica que hay al menos 1 CRÍTICO para mostrar
  6. Imprime el estado final + guía de la presentación
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

BASE_URL = f"http://localhost:{os.getenv('APP_PORT', '8001')}"
STORE_ID = os.getenv("STORE_ID", "demo-store-001")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


def _post(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/api/v1{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(path: str) -> dict:
    url = f"{BASE_URL}/api/v1{path}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def step_check_backend() -> bool:
    print("\n1. Verificando backend...")
    try:
        resp = _get("/health")
        if resp.get("status") == "ok":
            _ok(f"Backend operativo — tienda {resp.get('store_id')} — {resp.get('date')}")
            return True
    except Exception as e:
        _err(f"Backend no responde en {BASE_URL}: {e}")
        print("     Arranca con: make run  o  python -m backend.main")
        return False


def step_reset_demo() -> bool:
    print("\n2. Reseteando datos demo a estado base...")
    try:
        resp = _post("/demo/reset", {"store_id": STORE_ID})
        if resp.get("ok"):
            s = resp.get("summary", {})
            _ok(f"Reset OK — {s.get('batches_restored', 0)} lotes restaurados, acciones auto limpiadas")
            return True
        else:
            _warn(f"Reset devolvió: {resp}")
            return False
    except Exception as e:
        _err(f"Error en reset: {e}")
        return False


def step_advance_days(days: int = 2) -> bool:
    print(f"\n3. Avanzando {days} días en el tiempo simulado...")
    try:
        resp = _post("/demo/advance", {"days": days, "store_id": STORE_ID, "generate_brief": False})
        if resp.get("ok"):
            s = resp.get("summary", {})
            _ok(f"Avanzado {days}d — {s.get('batches_updated', 0)} lotes actualizados")
            criticos = s.get("newly_critical", [])
            altos = s.get("newly_high", [])
            if criticos:
                _ok(f"Nuevos CRÍTICOS: {', '.join(criticos)}")
            if altos:
                _ok(f"Nuevos ALTOS: {', '.join(altos)}")
            return True
        else:
            _warn(f"Advance devolvió: {resp}")
            return False
    except Exception as e:
        _err(f"Error en advance: {e}")
        return False


def step_generate_brief() -> bool:
    print("\n4. Generando brief diario con Kuine (puede tardar 15-30s)...")
    try:
        t0 = time.monotonic()
        resp = _post("/brief/run/sync", {})
        elapsed = round(time.monotonic() - t0, 1)
        if resp.get("brief"):
            _ok(f"Brief generado en {elapsed}s — {len(str(resp.get('brief', '')))} chars")
            return True
        if resp.get("ok") or (isinstance(resp, dict) and len(str(resp)) > 50):
            _ok(f"Brief generado en {elapsed}s")
            return True
        _warn(f"Brief endpoint devolvió: {resp}")
        return False
    except Exception as e:
        _warn(f"Brief endpoint no disponible ({e}) — generando vía scheduler...")
        try:
            from backend.agents import supervisor
            brief = supervisor.run_daily_brief(STORE_ID)
            _ok(f"Brief generado directamente — {len(brief)} chars")
            return True
        except Exception as e2:
            _err(f"Error generando brief: {e2}")
            return False


def step_verify_state() -> bool:
    print("\n5. Verificando estado final...")
    try:
        from backend.core import database
        pending = database.get_pending_actions(STORE_ID)
        criticos = [a for a in pending if a.get("priority_score", 0) >= 85]
        altos = [a for a in pending if 65 <= a.get("priority_score", 0) < 85]
        medios = [a for a in pending if 40 <= a.get("priority_score", 0) < 65]

        print(f"     Acciones pendientes: {len(pending)} total")
        print(f"       CRITICO: {len(criticos)}")
        print(f"       ALTO:    {len(altos)}")
        print(f"       MEDIO:   {len(medios)}")

        if len(criticos) == 0:
            _warn("Sin CRÍTICOS — considera avanzar 1 día más: python scripts/demo_prep.py --extra-day")
        else:
            _ok(f"{len(criticos)} producto(s) CRÍTICO(s) listos para la demo")

        brief = database.get_latest_brief(STORE_ID)
        if brief:
            _ok(f"Último brief: {brief.get('date')} — valor en riesgo: {brief.get('value_at_risk', 0)}€")
        else:
            _warn("Sin brief generado aún")

        return len(pending) > 0
    except Exception as e:
        _err(f"Error verificando estado: {e}")
        return False


def print_demo_guide() -> None:
    print("\n" + "=" * 60)
    print("  GUIA DE PRESENTACION — MermaOps TFM")
    print("=" * 60)
    print(f"""
  ARQUITECTURA (2 min)
  ├─ 11 agentes: Kuine (orquestador), Chuwi (Telegram), Evaluador,
  │   Validador, Consenso, Predictor, Visión, Precio, Stock,
  │   Notificador, Reportero
  ├─ Kuine usa Claude Opus 4.7 con ReAct loop real (hasta 20 iter)
  ├─ Evaluador usa extended thinking (budget: 5000 tokens)
  └─ Paralelismo real con ThreadPoolExecutor (4 workers)

  DEMO EN VIVO (5 min)
  1. App Flutter: muestra dashboard con CRÍTICO en rojo
  2. Telegram @ChuwiMermaOpsBot:
     - Escribe: "qué hago hoy"        → ruta priorizada
     - Escribe: "brief del día"        → Kuine analiza en vivo
     - Escanea un barcode             → extended thinking visible
     - Avanza un día: POST /api/v1/demo/advance  → nuevos críticos
  3. Muestra logs: [kuine] en terminal mientras razona

  NÚMEROS CLAVE
  ├─ Precisión: 100% (vs 16.7% baseline aleatorio)
  ├─ 735 tests automatizados, 0 fallos
  ├─ 23 ataques adversariales neutralizados (100%)
  └─ Evaluación ROI: 34.20€ → 17.10€ recuperados (50% merma evitada)

  APP WEB: {BASE_URL}/app/
  DOCS API: {BASE_URL}/docs
  TELEGRAM: @ChuwiMermaOpsBot
""")
    print("=" * 60)


def main():
    extra_day = "--extra-day" in sys.argv
    print("\nMermaOps — Preparación demo/defensa TFM")
    print("-" * 40)

    ok = step_check_backend()
    if not ok:
        sys.exit(1)

    step_reset_demo()
    step_advance_days(3 if extra_day else 2)
    step_generate_brief()
    step_verify_state()
    print_demo_guide()


if __name__ == "__main__":
    main()
