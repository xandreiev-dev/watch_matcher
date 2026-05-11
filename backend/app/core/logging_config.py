from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger as _logger

_configured = False

logger = _logger.patch(lambda record: record["extra"].setdefault("component", "app"))


def setup_logging(service_name: str = "backend") -> None:
    global _configured
    if _configured:
        return

    level = (os.getenv("LOG_LEVEL") or "INFO").upper()
    log_to_file = (os.getenv("LOG_TO_FILE") or "1").strip().lower() not in {"0", "false", "no"}
    log_dir = Path(os.getenv("LOG_DIR") or str(Path(__file__).resolve().parents[3] / "logs")).resolve()

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[component]}</cyan> | "
            "{message}"
        ),
    )
    if log_to_file:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / f"{service_name}.log",
            level=level,
            enqueue=True,
            backtrace=False,
            diagnose=False,
            rotation="10 MB",
            retention="14 days",
            encoding="utf-8",
        )
    _configured = True
    logger.bind(component="logging").info(
        f"Логирование Loguru настроено | сервис={service_name} | уровень={level} | запись_в_файл={log_to_file}"
    )


def get_logger(component: str):
    return logger.bind(component=component)
