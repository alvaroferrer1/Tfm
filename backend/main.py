"""Entry point — FastAPI + APScheduler + Chuwi (Telegram)."""
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api import routes
from backend.api.limiter import limiter
from backend.core.scheduler import build_scheduler

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mermaops")

STORE_ID = os.getenv("STORE_ID", "demo-store-001")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"MermaOps iniciando — tienda: {STORE_ID} — {date.today()}")

    # Observabilidad LLM — activa si LANGFUSE_PUBLIC_KEY presente en .env
    from backend.core.llm import _init_langfuse
    _init_langfuse()

    scheduler = build_scheduler(STORE_ID)
    scheduler.start()
    logger.info("Scheduler activo con 7 trabajos autónomos")

    chuwi_thread = threading.Thread(target=_start_chuwi, daemon=True, name="chuwi")
    chuwi_thread.start()

    yield

    scheduler.shutdown(wait=False)
    logger.info("MermaOps detenido")


def _start_chuwi() -> None:
    import asyncio
    # Python 3.10+ requiere event loop explícito en threads no-principal
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        from backend.core.chuwi import run
        run()
    except Exception as e:
        logger.error(f"[chuwi] Error fatal: {e}", exc_info=True)
    finally:
        try:
            loop.close()
        except Exception:
            pass


app = FastAPI(
    title="MermaOps API",
    description=(
        "Sistema multi-agente de IA para reducción de merma alimentaria en supermercados españoles. "
        "Arquitectura: 12 agentes especializados coordinados por Kuine (Claude Opus 4.7, 16 tools). "
        "Interfaces: app Flutter + Telegram (@ChuwiMermaOpsBot). "
        "Técnicas: ReAct loop, extended thinking, prompt caching, fork-merge, consenso 2/3. "
        "Precisión: 100% vs 16.7% baseline aleatorio. "
        "Seguridad: 23/23 ataques adversariales neutralizados. "
        "Tests: 800/800 deterministas, sin conexión real a Supabase ni API keys."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Limiter registrado en el estado de la app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        logger.error(f"[http-{exc.status_code}] {request.method} {request.url.path} — {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "Error interno del servidor. Inténtalo de nuevo en unos segundos."},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"[unhandled] {request.method} {request.url.path} — {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor. Inténtalo de nuevo en unos segundos."},
    )

# CORS — en producción restringe a los orígenes reales.
# CORS_ORIGINS=https://app.mermaops.com,https://admin.mermaops.com
_raw_origins = os.getenv("CORS_ORIGINS", "")
_app_env = os.getenv("APP_ENV", "dev")
if _raw_origins:
    _allowed_origins: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]
elif _app_env == "dev":
    _allowed_origins = ["*"]  # solo en dev local
else:
    # En producción sin CORS_ORIGINS configurado: bloquear todo origen externo
    # — fuerza que el operador configure explícitamente los orígenes permitidos
    _allowed_origins = []
_allow_credentials = bool(_allowed_origins) and _allowed_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(routes.router, prefix="/api/v1")

# Flutter web — servido desde /app/ cuando existe el build
_web_dir = Path(__file__).parent.parent / "app" / "build" / "web"
if _web_dir.exists():
    app.mount("/app", StaticFiles(directory=str(_web_dir), html=True), name="flutter_web")


@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "store_id": STORE_ID,
        "date": date.today().isoformat(),
        "version": "1.0.0",
    }


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "8001"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("APP_ENV", "dev") == "dev",
        log_level="info",
    )
