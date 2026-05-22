# MermaOps — comandos de desarrollo
.PHONY: install run seed test test-fast lint clean check migrate demo-ready hero

# Arrancar el sistema con guia de pruebas (verifica + arranca + guia)
start:
	python scripts/start.py

# Solo verificar sin arrancar
verify:
	python scripts/start.py --check

# Diagnostico completo del sistema
check:
	python scripts/check_all.py

# Aplicar migraciones a Supabase
migrate:
	supabase db push

# Verificar migraciones (sin aplicar)
migrate-dry:
	supabase db push --dry-run

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

# Avanza N días en la simulación (para la demo en vivo)
# Uso: make advance N=2  (por defecto N=1)
advance:
	python -m backend.data.advance_demo --days $(or $(N),1)

# Vuelve al estado inicial del día de hoy
demo-reset:
	python -m backend.data.advance_demo --reset

# Arrancar app Flutter con credenciales desde .env
# Requiere: flutter instalado, emulador Android o dispositivo conectado
flutter-run:
	python scripts/run_app.py

# Lanza backend + emulador + app Flutter todo en un comando
app:
	python scripts/run_app.py

# ─────────────────────────────────────────────────────────────────────────────
# WEB — Compilar y servir la app Flutter como web (sin emulador)
# Estrategia para la defensa: backend local + web en Chrome + Telegram en móvil
# ─────────────────────────────────────────────────────────────────────────────
flutter-web:
	python scripts/build_web.py

# ─────────────────────────────────────────────────────────────────────────────
# DEMO DEFENSA — arranca TODO para la presentación sin emulador:
#   Terminal 1: make demo-defensa  (backend + web)
#   Móvil real: Telegram con @ChuwiMermaOpsBot
# ─────────────────────────────────────────────────────────────────────────────
demo-defensa:
	@echo ""
	@echo "=== MermaOps — Demo defensa TFM ==="
	@echo ""
	@python scripts/start.py --seed
	@echo ""
	@echo "Siguiente paso: make flutter-web (en otro terminal)"
	@echo "Móvil: escribe en @ChuwiMermaOpsBot para activar Chuwi"

# ─────────────────────────────────────────────────────────────────────────────
# DEMO — ejecutar esto la mañana de la presentación
#   1. Verifica .env + Supabase + Telegram
#   2. Carga datos si las tablas están vacías (seed automático)
#   3. Arranca el backend en puerto 8001
#   4. Imprime el comando flutter run con las credenciales ya rellenas
# ─────────────────────────────────────────────────────────────────────────────
demo-ready:
	python scripts/start.py --seed

# Regenerar la imagen hero del README
hero:
	python scripts/generate_hero.py

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
