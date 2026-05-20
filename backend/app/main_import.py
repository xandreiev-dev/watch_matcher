from __future__ import annotations

import argparse

from app.core.env_bootstrap import load_repo_env
from app.core.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Avito/Ozon smartwatch XLSX files")
    parser.add_argument("--shop", choices=["avito", "ozon", "all"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    load_repo_env()
    setup_logging("watch-import")

    from app.importers import (
        process_all_watch_data,
        process_avito_watch_data,
        process_ozon_watch_data,
    )

    if args.shop == "avito":
        process_avito_watch_data(dry_run=args.dry_run, force=args.force)
    elif args.shop == "ozon":
        process_ozon_watch_data(dry_run=args.dry_run, force=args.force)
    else:
        process_all_watch_data(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
