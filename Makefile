# MermaOps — comandos de desarrollo
.PHONY: install run seed test test-fast lint clean

# Setup interactivo completo (primera vez)
setup:
	python scripts/setup_supabase.py

# Instalar dependencias
install:
	pip install -r requirements.txt

# Arrancar el servidor FastAPI (modo desarrollo)
run:
	python -m backend.main

# Cargar datos demo en Supabase (productos + lotes + acciones + brief)
seed:
	python -m backend.data.seed

# Solo acciones y brief (sin recrear productos)
seed-actions:
	python -m backend.data.demo_actions

# Tests completos
test:
	pytest backend/tests/ -v --tb=short

# Tests rápidos (sin los que necesitan LLM/red)
test-fast:
	pytest backend/tests/ -v --tb=short -m "not integration"

# Tests con cobertura
test-cov:
	pytest backend/tests/ --cov=backend --cov-report=term-missing

# Linter
lint:
	python -m flake8 backend/ --max-line-length=100 --ignore=E501,W503

# Limpiar __pycache__
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .tmp/

# Ver logs del servidor en tiempo real
logs:
	tail -f .tmp/mermaops.log 2>/dev/null || echo "Sin archivo de log"

# Generar brief manual (para testing sin esperar las 07:30)
brief:
	python -c "from backend.agents.supervisor import run_daily_brief; print(run_daily_brief('demo-store-001'))"

# Estado de la tienda demo
status:
	python -c "
from backend.core.database import get_pending_actions, get_batches_expiring_soon, get_latest_brief
store = 'demo-store-001'
pending = get_pending_actions(store)
batches = get_batches_expiring_soon(store, days=7)
brief = get_latest_brief(store)
print(f'Acciones pendientes: {len(pending)}')
print(f'Lotes proximos a caducar: {len(batches)}')
print(f'Ultimo brief: {brief[\"date\"] if brief else \"ninguno\"}')
"
