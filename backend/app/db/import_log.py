from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.db import get_db_connection
from app.core.logging_config import get_logger

logger = get_logger("import_log")


CREATE_WATCH_IMPORT_LOG_SQL = """
CREATE TABLE IF NOT EXISTS watch_import_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    shop VARCHAR(32) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_date DATE NULL,
    file_size BIGINT NULL,
    file_hash CHAR(64) NOT NULL,
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(32) NOT NULL,
    rows_total INT NULL,
    rows_processed INT NULL,
    rows_inserted INT NULL,
    error_text TEXT NULL,
    UNIQUE KEY uq_watch_import_log_file_hash (file_hash),
    KEY idx_watch_import_log_shop_date (shop, file_date),
    KEY idx_watch_import_log_filename (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""".strip()


@dataclass(frozen=True)
class ImportLogRecord:
    shop: str
    filename: str
    file_date: date | None
    file_size: int | None
    file_hash: str
    status: str
    rows_total: int | None = None
    rows_processed: int | None = None
    rows_inserted: int | None = None
    error_text: str | None = None


class WatchImportLogRepository:
    @classmethod
    def was_imported(cls, file_hash: str, *, shop: str) -> bool:
        query = """
        SELECT id
        FROM watch_import_log
        WHERE file_hash = %s AND shop = %s AND status = 'success'
        LIMIT 1
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, (file_hash, shop))
                    return cursor.fetchone() is not None
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                f"Не удалось проверить watch_import_log; импорт не блокирую: {exc}"
            )
            return False

    @classmethod
    def save(cls, record: ImportLogRecord) -> None:
        query = """
        INSERT INTO watch_import_log
        (shop, filename, file_date, file_size, file_hash, status, rows_total, rows_processed, rows_inserted, error_text)
        VALUES
        (%(shop)s, %(filename)s, %(file_date)s, %(file_size)s, %(file_hash)s, %(status)s, %(rows_total)s, %(rows_processed)s, %(rows_inserted)s, %(error_text)s)
        ON DUPLICATE KEY UPDATE
            imported_at = CURRENT_TIMESTAMP,
            status = VALUES(status),
            rows_total = VALUES(rows_total),
            rows_processed = VALUES(rows_processed),
            rows_inserted = VALUES(rows_inserted),
            error_text = VALUES(error_text)
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, record.__dict__)
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"Не удалось записать watch_import_log: {exc}")
