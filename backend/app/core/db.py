"""MySQL через pymysql; SSH — как smart_price_tracker/db/common_funcs.py (get_ssh_tunnel + lock + is_active)."""
from __future__ import annotations

import atexit
import threading

import pymysql
from pymysql.cursors import DictCursor
from sshtunnel import SSHTunnelForwarder

from app.core.db_settings import (
    DB_USE_SSH,
    SSH_HOST,
    SSH_PORT,
    SSH_USER,
    SSH_PASSWORD,
    SQL_USERNAME,
    SQL_PASSWORD,
    SQL_DATABASE,
    direct_mysql_address,
    remote_bind_address,
)
from app.core.logging_config import get_logger

logger = get_logger("db")

tunnel: SSHTunnelForwarder | None = None
_tunnel_lock = threading.Lock()


def get_ssh_tunnel() -> SSHTunnelForwarder:
    rh, rp = remote_bind_address()
    if not SSH_HOST:
        raise RuntimeError("Задайте SSH_HOST или SSH_HOST_PROD в .env при DB_USE_SSH=true")
    if not SSH_USER or SSH_PASSWORD is None:
        raise RuntimeError("Нужны SSH_USER и SSH_PASSWORD в .env")
    t = SSHTunnelForwarder(
        (SSH_HOST, SSH_PORT),
        ssh_username=SSH_USER,
        ssh_password=SSH_PASSWORD,
        remote_bind_address=(rh, rp),
        set_keepalive=30,
    )
    t.start()
    logger.info(f"SSH-туннель поднят: {SSH_HOST}:{SSH_PORT} -> {rh}:{rp}")
    return t


def get_db_connection():
    """Новое соединение; при SSH держит/пересоздаёт глобальный туннель."""
    global tunnel
    if DB_USE_SSH:
        with _tunnel_lock:
            if tunnel is None or not getattr(tunnel, "is_active", False):
                try:
                    if tunnel:
                        try:
                            tunnel.stop()
                        except Exception:
                            pass
                except Exception:
                    pass
                tunnel = get_ssh_tunnel()
            port = tunnel.local_bind_port
        host = "127.0.0.1"
    else:
        host, port = direct_mysql_address()
    return pymysql.connect(
        host=host,
        port=port,
        user=SQL_USERNAME,
        password=SQL_PASSWORD,
        database=SQL_DATABASE,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


@atexit.register
def _shutdown_tunnel():
    global tunnel
    if tunnel is not None:
        try:
            tunnel.stop()
            logger.info("SSH-туннель остановлен")
        except Exception:
            pass
        tunnel = None


def _warmup_ssh():
    if not DB_USE_SSH or not SSH_HOST:
        return
    try:
        c = get_db_connection()
        c.close()
        logger.info("Прогрев БД через SSH выполнен")
    except Exception as e:
        logger.exception(f"Ошибка прогрева БД через SSH: {e}")


_warmup_ssh()
