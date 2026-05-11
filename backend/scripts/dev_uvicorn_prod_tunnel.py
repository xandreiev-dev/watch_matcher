"""Локальный uvicorn с SSH-туннелем на PROD MySQL (как в mcp-mysql)."""
from __future__ import annotations

import os
import sys
from io import StringIO
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"


def _load_dotenv_path(path: Path, *, override: bool) -> None:
    if not path.is_file():
        return
    load_dotenv(stream=StringIO(path.read_text(encoding="utf-8-sig")), override=override)


_load_dotenv_path(REPO_ROOT / ".env", override=True)
_load_dotenv_path(REPO_ROOT / "mcp-mysql" / ".env", override=False)


def main() -> None:
    ssh_host = os.getenv("SSH_HOST_PROD")
    if not ssh_host:
        raise RuntimeError("В .env задайте SSH_HOST_PROD")
    ssh_port = int(os.getenv("SSH_PORT", "22") or 22)
    ssh_user = os.getenv("SSH_USER")
    ssh_password = (os.getenv("SSH_PASSWORD") or "").strip().strip('"').strip("'")
    remote = os.getenv("MYSQL_REMOTE_HOST", "127.0.0.1")
    remote_port = int(os.getenv("MYSQL_REMOTE_PORT", "3306"))
    sql_user = os.getenv("SQL_USERNAME")
    sql_password = os.getenv("SQL_PASSWORD")
    sql_database = os.getenv("SQL_DATABASE")
    if not all([ssh_user, sql_user, sql_password, sql_database]):
        raise RuntimeError("Неполные SQL/SSH переменные в .env")

    print(f"[dev] SSH {ssh_host} -> {remote}:{remote_port} MySQL user={sql_user} db={sql_database}")
    with SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_password=ssh_password,
        remote_bind_address=(remote, remote_port),
    ) as tun:
        os.environ["DB_USE_SSH"] = "false"
        os.environ["SQL_HOSTNAME"] = "127.0.0.1"
        os.environ["SQL_PORT"] = str(tun.local_bind_port)
        sys.path.insert(0, str(BACKEND))
        os.chdir(BACKEND)
        port = int(os.getenv("UVICORN_PORT", "8000"))
        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=port,
            reload=False,
        )


if __name__ == "__main__":
    main()
