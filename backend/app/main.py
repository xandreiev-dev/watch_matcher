import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.core.env_bootstrap import load_repo_env
from app.core.logging_config import get_logger, setup_logging

load_repo_env()
setup_logging("backend-api")
logger = get_logger("main")

# Прогрев SSH/БД и atexit — как импорт db в smart_price_tracker/main.py через common_funcs
import app.core.db  # noqa: F401

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.process import router as process_router
from app.api.routes.watch_catalog import router as watch_catalog_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(process_router, prefix="/api/process", tags=["process"])
app.include_router(watch_catalog_router, prefix="/api/watch-catalog", tags=["watch-catalog"])
logger.info("Маршрут /api/process успешно зарегистрирован")


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import os
    import uvicorn

    _reload = os.getenv("UVICORN_RELOAD", "0").lower() not in ("0", "false", "no")
    uvicorn.run("app.main:app", host="127.0.0.1", port=4444, reload=_reload)
