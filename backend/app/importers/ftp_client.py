from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from ftplib import FTP
from pathlib import Path


def _env_for_source(source: str, name: str, default: str | None = None) -> str | None:
    source_key = source.upper()
    candidates = [
        f"{source_key}_FTP_{name}",
        f"SMARTWATCH_{source_key}_FTP_{name}",
        f"FTP_{name}",
        f"SMARTWATCH_FTP_{name}",
    ]

    for key in candidates:
        value = os.getenv(key)
        if value is not None and str(value).strip():
            return str(value).strip().strip('"').strip("'")

    return default


@dataclass(frozen=True)
class FtpFileInfo:
    filename: str
    modified_at: datetime | None
    size: int | None


@dataclass(frozen=True)
class WatchFtpConfig:
    source: str
    host: str
    port: int
    user: str
    password: str
    remote_dir: str
    local_dir: Path

    @classmethod
    def from_env(cls, source: str) -> "WatchFtpConfig":
        host = _env_for_source(source, "HOST")
        user = _env_for_source(source, "USER")
        password = _env_for_source(source, "PASS")

        if not host or not user or password is None:
            raise RuntimeError(
                f"Задайте FTP_HOST/FTP_USER/FTP_PASS или {source.upper()}_FTP_* в .env"
            )

        local_root = (
            os.getenv(f"{source.upper()}_FTP_LOCAL_DOWNLOAD_DIR")
            or os.getenv("FTP_LOCAL_DOWNLOAD_DIR")
            or os.getenv("WATCH_IMPORT_LOCAL_DIR")
            or f"tmp/ftp_{source}"
        )

        return cls(
            source=source,
            host=host,
            port=int(_env_for_source(source, "PORT", "21") or "21"),
            user=user,
            password=password,
            remote_dir=(_env_for_source(source, "REMOTE_DIR", "/") or "/").strip() or "/",
            local_dir=Path(local_root).resolve(),
        )


class WatchFtpClient:
    def __init__(self, config: WatchFtpConfig):
        self.config = config
        self.config.local_dir.mkdir(parents=True, exist_ok=True)

    def list_xlsx(self) -> list[FtpFileInfo]:
        files: list[FtpFileInfo] = []
        with self._connect() as ftp:
            for filename in ftp.nlst():
                if not filename or filename in {".", ".."}:
                    continue
                if not filename.lower().endswith(".xlsx"):
                    continue
                files.append(
                    FtpFileInfo(
                        filename=filename,
                        modified_at=self._get_modified_at(ftp, filename),
                        size=self._get_size(ftp, filename),
                    )
                )
        return files

    def download(self, filename: str) -> Path:
        target = self.config.local_dir / filename
        with self._connect() as ftp:
            with target.open("wb") as output:
                ftp.retrbinary(f"RETR {filename}", output.write)
        return target

    def _connect(self) -> FTP:
        ftp = FTP()
        ftp.connect(self.config.host, self.config.port, timeout=30)
        ftp.login(self.config.user, self.config.password)
        ftp.set_pasv(True)
        ftp.cwd(self.config.remote_dir)
        return ftp

    @staticmethod
    def _get_modified_at(ftp: FTP, filename: str) -> datetime | None:
        try:
            response = ftp.sendcmd(f"MDTM {filename}")
        except Exception:
            return None
        if not response.startswith("213 "):
            return None
        return datetime.strptime(response[4:], "%Y%m%d%H%M%S")

    @staticmethod
    def _get_size(ftp: FTP, filename: str) -> int | None:
        try:
            return int(ftp.size(filename))
        except Exception:
            return None
