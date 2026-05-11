"""
Копирует справочник часов TEST -> PROD по SSH:
  g_watch_model -> g_watch_variant -> g_watch_variant_source

Ожидает в корне репозитория .env с:
  SSH_HOST_TEST, SSH_HOST_PROD, SSH_PORT, SSH_USER, SSH_PASSWORD
  SQL_HOSTNAME (удалённый bind, обычно 127.0.0.1), SQL_PORT (обычно 3306)
  SQL_USERNAME, SQL_PASSWORD, SQL_DATABASE

Запуск из корня репозитория:
  .venv\\Scripts\\python backend\\scripts\\sync_watch_catalog_test_to_prod.py
"""
from __future__ import annotations

import os
import sys
from io import StringIO
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from sshtunnel import SSHTunnelForwarder

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TABLES_ORDER = (
    "g_watch_model",
    "g_watch_variant",
    "g_watch_variant_source",
)


def _load_env() -> None:
    root_env = REPO_ROOT / ".env"
    if root_env.is_file():
        load_dotenv(stream=StringIO(root_env.read_text(encoding="utf-8-sig")))
    mcp = REPO_ROOT / "mcp-mysql" / ".env"
    if mcp.is_file():
        load_dotenv(stream=StringIO(mcp.read_text(encoding="utf-8-sig")), override=False)


def _ssh_mysql(ssh_host: str) -> tuple[SSHTunnelForwarder, pymysql.connections.Connection]:
    ssh_port = int(os.getenv("SSH_PORT", "22") or 22)
    ssh_user = os.getenv("SSH_USER")
    ssh_password = (os.getenv("SSH_PASSWORD") or "").strip().strip('"').strip("'")
    remote_host = os.getenv("MYSQL_REMOTE_HOST", "127.0.0.1")
    remote_port = int(os.getenv("MYSQL_REMOTE_PORT", "3306") or 3306)
    sql_user = os.getenv("SQL_USERNAME")
    sql_password = os.getenv("SQL_PASSWORD")
    sql_database = os.getenv("SQL_DATABASE")
    for name, val in (
        ("SSH_USER", ssh_user),
        ("SQL_USERNAME", sql_user),
        ("SQL_PASSWORD", sql_password),
        ("SQL_DATABASE", sql_database),
    ):
        if not val:
            raise RuntimeError(f"В .env не задан {name}")
    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_password=ssh_password,
        remote_bind_address=(remote_host, remote_port),
    )
    tunnel.start()
    conn = pymysql.connect(
        host="127.0.0.1",
        user=sql_user,
        password=sql_password,
        db=sql_database,
        port=tunnel.local_bind_port,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    return tunnel, conn


def _insertable_columns(conn: pymysql.connections.Connection, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        rows = cur.fetchall()
    out: list[str] = []
    for r in rows:
        if not isinstance(r, dict):
            raise RuntimeError("Ожидается DictCursor для SHOW COLUMNS")
        extra = (r.get("Extra") or "").upper()
        if "GENERATED" in extra:
            continue
        out.append(r["Field"])
    return out


def _fetch_all(conn: pymysql.connections.Connection, table: str, cols: list[str]) -> list[dict]:
    col_sql = ", ".join(f"`{c}`" for c in cols)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {col_sql} FROM `{table}` ORDER BY `id`")
        return list(cur.fetchall())


def _upsert_batch(
    conn: pymysql.connections.Connection, table: str, cols: list[str], rows: list[dict], batch: int = 300
) -> int:
    if not rows:
        return 0
    pk = "id"
    non_pk = [c for c in cols if c != pk]
    placeholders = ", ".join([f"%({c})s" for c in cols])
    col_list = ", ".join(f"`{c}`" for c in cols)
    upd = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in non_pk) if non_pk else f"`{pk}`=`{pk}`"
    sql = f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {upd}"
    n = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch):
            chunk = rows[i : i + batch]
            cur.executemany(sql, chunk)
            n += len(chunk)
    return n


def main() -> None:
    _load_env()
    test_host = os.getenv("SSH_HOST_TEST")
    prod_host = os.getenv("SSH_HOST_PROD")
    if not test_host or not prod_host:
        raise RuntimeError("В .env нужны SSH_HOST_TEST (TEST) и SSH_HOST_PROD (PROD), без подстановки SSH_HOST.")

    rh = os.getenv("MYSQL_REMOTE_HOST", "127.0.0.1")
    rp = os.getenv("MYSQL_REMOTE_PORT", "3306")
    t_tunnel, t_conn = None, None
    p_tunnel, p_conn = None, None
    try:
        print(f"[sync] TEST SSH {test_host} -> remote MySQL {rh}:{rp}")
        t_tunnel, t_conn = _ssh_mysql(test_host)
        print(f"[sync] PROD SSH {prod_host} -> remote MySQL {rh}:{rp}")
        p_tunnel, p_conn = _ssh_mysql(prod_host)

        with p_conn.cursor() as cur:
            cur.execute("SET SESSION foreign_key_checks=0")
            cur.execute("SET SESSION unique_checks=0")
        p_conn.commit()

        total = 0
        for table in TABLES_ORDER:
            cols = _insertable_columns(t_conn, table)
            rows = _fetch_all(t_conn, table, cols)
            print(f"[sync] {table}: read {len(rows)} rows (insertable cols: {len(cols)})")
            n = _upsert_batch(p_conn, table, cols, rows)
            p_conn.commit()
            print(f"[sync] {table}: upserted {n}")
            total += n

        with p_conn.cursor() as cur:
            cur.execute("SET SESSION foreign_key_checks=1")
            cur.execute("SET SESSION unique_checks=1")
        p_conn.commit()
        print(f"[sync] done, total row operations: {total}")
        for table in TABLES_ORDER:
            with t_conn.cursor() as c:
                c.execute(f"SELECT COUNT(*) AS n FROM `{table}`")
                nt = int(c.fetchone()["n"])
            with p_conn.cursor() as c:
                c.execute(f"SELECT COUNT(*) AS n FROM `{table}`")
                np = int(c.fetchone()["n"])
            ok = "OK" if nt == np else "MISMATCH"
            print(f"[sync] verify {table}: test={nt} prod={np} {ok}")
    finally:
        for c in (p_conn, t_conn):
            if c:
                try:
                    c.close()
                except Exception:
                    pass
        for tun in (p_tunnel, t_tunnel):
            if tun:
                try:
                    tun.stop()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
