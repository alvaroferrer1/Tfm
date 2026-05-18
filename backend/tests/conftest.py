"""
Fixtures compartidas para todos los tests.
Los agentes se testean sin red: ni Supabase ni Anthropic API.

El bloque sys.modules al principio inyecta stubs mínimos de supabase/realtime
antes de cualquier import del backend, para que los tests que parchean
database.* puedan importar los módulos sin necesitar la librería instalada.
"""
import sys
from unittest.mock import MagicMock

# ── Stubs de dependencias externas ────────────────────────────────────────────
# Permite importar backend.core.database (y cualquier agente que lo use)
# sin que supabase esté instalado. Los tests individuales parchean las
# funciones concretas (patch("backend.agents.esg.database.get_merma_history"))
# así que este stub nunca se llama realmente.

for _mod in ("realtime", "supabase", "dotenv", "python_dotenv"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# dotenv.load_dotenv must be callable and return nothing
sys.modules["dotenv"].load_dotenv = lambda *a, **kw: None

# Stub mínimo de anthropic para que llm.py importe sin API key
if "anthropic" not in sys.modules:
    _anthropic_stub = MagicMock()
    _anthropic_stub.Anthropic = MagicMock
    sys.modules["anthropic"] = _anthropic_stub

# Stub de telegram para que chuwi.py importe en los tests
for _tg_mod in (
    "telegram", "telegram.constants", "telegram.ext",
    "python_telegram_bot",
):
    if _tg_mod not in sys.modules:
        sys.modules[_tg_mod] = MagicMock()

# ── Imports normales ──────────────────────────────────────────────────────────
from datetime import date, timedelta
import pytest


@pytest.fixture
def today():
    return date.today()


@pytest.fixture
def product_panaderia():
    return {
        "id": "p-001",
        "name": "Baguette artesana",
        "category": "panaderia",
        "price": 1.20,
        "cost": 0.45,
        "pasillo": "1",
        "estanteria": "1",
        "nivel": "1",
        "alert_days_1": 1,
        "alert_days_2": 1,
    }


@pytest.fixture
def product_carne():
    return {
        "id": "p-008",
        "name": "Carne picada mixta 500g",
        "category": "carne",
        "price": 4.20,
        "cost": 2.10,
        "pasillo": "3",
        "estanteria": "1",
        "nivel": "1",
        "alert_days_1": 3,
        "alert_days_2": 1,
    }


@pytest.fixture
def product_pescado():
    return {
        "id": "p-011",
        "name": "Merluza en rodajas 500g",
        "category": "pescado",
        "price": 7.90,
        "cost": 4.20,
        "pasillo": "4",
        "estanteria": "1",
        "nivel": "1",
        "alert_days_1": 2,
        "alert_days_2": 1,
    }


@pytest.fixture
def batch_expiring_today(today, product_panaderia):
    return {
        "id": "b-001",
        "product_id": product_panaderia["id"],
        "expiry_date": today.isoformat(),
        "quantity": 8,
        "status": "active",
    }


@pytest.fixture
def batch_expiring_tomorrow(today, product_carne):
    return {
        "id": "b-003",
        "product_id": product_carne["id"],
        "expiry_date": (today + timedelta(days=1)).isoformat(),
        "quantity": 12,
        "status": "active",
    }


@pytest.fixture
def batch_expiring_3days(today, product_pescado):
    return {
        "id": "b-006",
        "product_id": product_pescado["id"],
        "expiry_date": (today + timedelta(days=3)).isoformat(),
        "quantity": 4,
        "status": "active",
    }


@pytest.fixture
def batch_expiring_7days(today):
    return {
        "id": "b-014",
        "product_id": "p-012",
        "expiry_date": (today + timedelta(days=7)).isoformat(),
        "quantity": 7,
        "status": "active",
    }
