"""Entry point — FastAPI + APScheduler + Chuwi (Telegram)."""
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import date

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    logger.info("Scheduler activo con 4 trabajos autónomos")

    chuwi_thread = threading.Thread(target=_start_chuwi, daemon=True, name="chuwi")
    chuwi_thread.start()

    yield

    scheduler.shutdown(wait=False)
    logger.info("MermaOps detenido")


def _start_chuwi() -> None:
    try:
        from backend.core.chuwi import run
        run()
    except Exception as e:
        logger.error(f"[chuwi] Error fatal: {e}", exc_info=True)


app = FastAPI(
    title="MermaOps API",
    description="Sistema inteligente de reducción de merma para supermercados",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Limiter registrado en el estado de la app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — en producción restringe a los orígenes reales.
# CORS_ORIGINS=https://app.mermaops.com,https://admin.mermaops.com
_raw_origins = os.getenv("CORS_ORIGINS", "")
_allowed_origins: list[str] = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(routes.router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "store_id": STORE_ID,
        "date": date.today().isoformat(),
        "version": "1.0.0",
    }


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("APP_ENV", "dev") == "dev",
        log_level="info",
    )
