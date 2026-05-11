from __future__ import annotations

import argparse
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.core.env_bootstrap import load_repo_env
from app.core.logging_config import setup_logging
from app.services.ftp_watch_ingest_service import FtpIngestConfig, FtpWatchIngestService


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сервис FTP-импорта часов: НОВЫЕ/БУ -> матчинг -> запись в БД"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Выполнить только один проход",
    )
    return parser.parse_args()


def main() -> None:
    load_repo_env()
    setup_logging("ftp-watch-ingest")
    args = build_args()
    config = FtpIngestConfig.from_env()
    service = FtpWatchIngestService(config)
    if args.once:
        service.run_once()
        return
    service.run_forever()


if __name__ == "__main__":
    main()
