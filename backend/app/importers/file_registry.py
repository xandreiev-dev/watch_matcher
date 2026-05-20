from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path


def calculate_file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def extract_date_from_filename(filename: str) -> date | None:
    ymd = re.search(r"(\d{8})", filename)
    if ymd:
        return datetime.strptime(ymd.group(1), "%Y%m%d").date()

    dmy = re.search(r"(\d{2})_(\d{2})_(\d{4})", filename)
    if dmy:
        day, month, year = dmy.groups()
        return date(int(year), int(month), int(day))

    iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if iso:
        year, month, day = iso.groups()
        return date(int(year), int(month), int(day))

    return None


def infer_is_new_from_filename(filename: str, default: bool = True) -> bool:
    value = filename.lower()
    if "_old" in value or "_used" in value or "old" in value or "used" in value:
        return False
    if "_new" in value or "new" in value:
        return True
    return default


def file_matches_source(filename: str, source: str) -> bool:
    value = filename.lower()
    source_value = source.lower()

    if source_value == "ozon":
        return "ozon" in value

    if source_value == "avito":
        return "avito" in value or "ozon" not in value

    return source_value in value
