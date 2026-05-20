from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from app.api.routes.process import SHOP_ID_BY_SOURCE, build_process_logs, process_watch_row
from app.catalog.watch_reference_catalog import WatchReferenceCatalog
from app.core.logging_config import get_logger
from app.db.import_log import ImportLogRecord, WatchImportLogRepository
from app.importers.file_registry import (
    calculate_file_hash,
    extract_date_from_filename,
    file_matches_source,
    infer_is_new_from_filename,
)
from app.importers.ftp_client import FtpFileInfo, WatchFtpClient, WatchFtpConfig
from app.services.excel_service import ExcelService
from app.services.export_preview import WatchPreviewExporter
from app.services.watch_db_writer_service import WatchDbWriterService

logger = get_logger("watch_import")


@dataclass
class MatcherPipelineResult:
    source: str
    shop_id: int
    filename: str
    file_date: date
    is_new: bool
    total_rows: int
    matched_rows: int
    unmatched_rows: int
    db_ready_rows: int
    db_written: bool
    output_file: str
    ready_file: str
    failed_file: str
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportRunSummary:
    source: str
    filename: str | None = None
    file_date: date | None = None
    already_imported: bool = False
    dry_run: bool = False
    total_rows: int = 0
    valid_rows: int = 0
    matched_rows: int = 0
    unmatched_rows: int = 0
    rows_inserted: int = 0
    debug_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_matcher_pipeline(
    input_file: str | Path,
    *,
    source: str,
    is_new: bool | None = None,
    actual_date: date | None = None,
    dry_run: bool = True,
    debug_dir: str | Path | None = None,
) -> MatcherPipelineResult:
    path = Path(input_file)
    normalized_source = source.strip().lower()
    shop_id = SHOP_ID_BY_SOURCE[normalized_source]
    resolved_date = actual_date or extract_date_from_filename(path.name) or date.today()
    resolved_is_new = infer_is_new_from_filename(path.name) if is_new is None else is_new

    dataframe = pd.read_excel(path)
    ExcelService.validate_columns(dataframe)

    processed_df = dataframe.fillna("").copy()
    models_catalog = WatchReferenceCatalog.load_models()
    variants_catalog = WatchReferenceCatalog.load_variants()

    rows: list[dict] = []
    for idx, row in processed_df.iterrows():
        processed_row = process_watch_row(
            row.to_dict(),
            models_catalog,
            variants_catalog,
            source=normalized_source,
        )
        processed_row["_import_row_id"] = int(idx)
        rows.append(processed_row)

    build_process_logs(rows, resolved_is_new)

    result_df = pd.DataFrame(rows)
    WatchDbWriterService.validate_input_columns(result_df)
    ready_df = WatchDbWriterService.prepare_matched_rows(result_df)
    ready_ids = set(ready_df.get("_import_row_id", pd.Series(dtype=int)).tolist())
    failed_df = result_df[~result_df["_import_row_id"].isin(ready_ids)].copy()

    output_file = WatchPreviewExporter.export(
        rows,
        is_new=resolved_is_new,
        source=normalized_source,
        shop_id=shop_id,
        output_file=_build_output_file_path(
            source=normalized_source,
            actual_date=resolved_date,
            is_new=resolved_is_new,
        ),
    )

    ready_file, failed_file = _write_debug_files(
        ready_df=ready_df,
        failed_df=failed_df,
        source=normalized_source,
        actual_date=resolved_date,
        is_new=resolved_is_new,
        debug_dir=debug_dir,
    )

    if not dry_run and not ready_df.empty:
        WatchDbWriterService.prepare_and_write_watch_data_to_db(
            df_res=result_df,
            actual_date=resolved_date,
            shop_id=shop_id,
            is_new=resolved_is_new,
        )

    matched_rows = int((result_df["match_status"] == "matched").sum())
    return MatcherPipelineResult(
        source=normalized_source,
        shop_id=shop_id,
        filename=path.name,
        file_date=resolved_date,
        is_new=resolved_is_new,
        total_rows=len(result_df),
        matched_rows=matched_rows,
        unmatched_rows=len(result_df) - matched_rows,
        db_ready_rows=len(ready_df),
        db_written=not dry_run,
        output_file=output_file,
        ready_file=ready_file,
        failed_file=failed_file,
    )


def process_all_watch_data(*, dry_run: bool = False, force: bool = False) -> list[ImportRunSummary]:
    summaries: list[ImportRunSummary] = []
    summaries.extend(process_shop_watch_data("avito", dry_run=dry_run, force=force))
    summaries.extend(process_shop_watch_data("ozon", dry_run=dry_run, force=force))
    return summaries


def process_shop_watch_data(
    source: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> list[ImportRunSummary]:
    config = WatchFtpConfig.from_env(source)
    ftp_client = WatchFtpClient(config)
    try:
        files = _pick_files_for_import(source, ftp_client.list_xlsx())
    except Exception as exc:
        summary = ImportRunSummary(source=source, dry_run=dry_run)
        summary.errors.append(str(exc))
        logger.exception(f"Не удалось получить список FTP-файлов source={source}: {exc}")
        _print_summary(summary)
        return [summary]

    if not files:
        summary = ImportRunSummary(source=source, dry_run=dry_run)
        summary.errors.append("No XLSX files found for source")
        _print_summary(summary)
        return [summary]

    summaries: list[ImportRunSummary] = []
    for file_info in files:
        summaries.append(
            _process_ftp_file(
                source=source,
                ftp_client=ftp_client,
                file_info=file_info,
                dry_run=dry_run,
                force=force,
            )
        )

    return summaries


def _process_ftp_file(
    *,
    source: str,
    ftp_client: WatchFtpClient,
    file_info: FtpFileInfo,
    dry_run: bool,
    force: bool,
) -> ImportRunSummary:
    summary = ImportRunSummary(
        source=source,
        filename=file_info.filename,
        file_date=extract_date_from_filename(file_info.filename),
        dry_run=dry_run,
    )

    try:
        local_path = ftp_client.download(file_info.filename)
        file_hash = calculate_file_hash(local_path)
        file_size = file_info.size or local_path.stat().st_size

        if not force and not dry_run and WatchImportLogRepository.was_imported(file_hash, shop=source):
            summary.already_imported = True
            _print_summary(summary)
            return summary

        pipeline_result = run_matcher_pipeline(
            local_path,
            source=source,
            is_new=infer_is_new_from_filename(file_info.filename),
            actual_date=summary.file_date,
            dry_run=dry_run,
        )

        summary.file_date = pipeline_result.file_date
        summary.total_rows = pipeline_result.total_rows
        summary.valid_rows = pipeline_result.db_ready_rows
        summary.matched_rows = pipeline_result.matched_rows
        summary.unmatched_rows = pipeline_result.unmatched_rows
        summary.rows_inserted = 0 if dry_run else pipeline_result.db_ready_rows
        summary.debug_files = [
            pipeline_result.output_file,
            pipeline_result.ready_file,
            pipeline_result.failed_file,
        ]

        if not dry_run:
            WatchImportLogRepository.save(
                ImportLogRecord(
                    shop=source,
                    filename=file_info.filename,
                    file_date=summary.file_date,
                    file_size=file_size,
                    file_hash=file_hash,
                    status="success",
                    rows_total=summary.total_rows,
                    rows_processed=summary.valid_rows,
                    rows_inserted=summary.rows_inserted,
                )
            )
    except Exception as exc:
        summary.errors.append(str(exc))
        if not dry_run:
            WatchImportLogRepository.save(
                ImportLogRecord(
                    shop=source,
                    filename=file_info.filename,
                    file_date=summary.file_date,
                    file_size=file_info.size,
                    file_hash=_fallback_error_hash(source, file_info.filename),
                    status="failed",
                    error_text=str(exc),
                )
            )
        logger.exception(f"Watch import failed source={source} file={file_info.filename}: {exc}")

    _print_summary(summary)
    return summary


def _pick_files_for_import(source: str, files: list[FtpFileInfo]) -> list[FtpFileInfo]:
    matched = [
        file_info
        for file_info in files
        if file_matches_source(file_info.filename, source)
    ]
    if not matched:
        return []

    latest_by_type: dict[bool, FtpFileInfo] = {}
    for file_info in matched:
        is_new = infer_is_new_from_filename(file_info.filename)
        current = latest_by_type.get(is_new)
        current_mdtm = current.modified_at if current else None
        if current is None or (file_info.modified_at or datetime.min) > (current_mdtm or datetime.min):
            latest_by_type[is_new] = file_info

    return [latest_by_type[key] for key in sorted(latest_by_type.keys(), reverse=True)]


def _write_debug_files(
    *,
    ready_df: pd.DataFrame,
    failed_df: pd.DataFrame,
    source: str,
    actual_date: date,
    is_new: bool,
    debug_dir: str | Path | None,
) -> tuple[str, str]:
    suffix = "new" if is_new else "old"
    root = Path(debug_dir or os.getenv("WATCH_IMPORT_DEBUG_DIR") or "tmp").resolve()
    root.mkdir(parents=True, exist_ok=True)

    ready_path = root / f"{source}_watch_ready_{actual_date}_{suffix}.xlsx"
    failed_path = root / f"{source}_watch_failed_{actual_date}_{suffix}.xlsx"

    ready_df.to_excel(ready_path, index=False)
    failed_df.to_excel(failed_path, index=False)

    return str(ready_path), str(failed_path)


def _build_output_file_path(*, source: str, actual_date: date, is_new: bool) -> str:
    suffix = "new" if is_new else "old"
    output_root = Path(
        os.getenv("WATCH_IMPORT_OUTPUT_DIR")
        or Path(__file__).resolve().parents[2] / "output"
    ).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    return str(output_root / f"{source}_watch_{actual_date}_{suffix}.xlsx")


def _print_summary(summary: ImportRunSummary) -> None:
    print("===== WATCH IMPORT SUMMARY =====")
    print(f"Shop: {summary.source}")
    print(f"Filename: {summary.filename or '-'}")
    print(f"File date: {summary.file_date or '-'}")
    print(f"Total rows: {summary.total_rows}")
    print(f"Valid rows: {summary.valid_rows}")
    print(f"Matched rows: {summary.matched_rows}")
    print(f"Unmatched rows: {summary.unmatched_rows}")
    print("Inserted watches: n/a (existing DB helper uses INSERT IGNORE)")
    print("Updated watches: n/a (existing DB helper uses INSERT IGNORE)")
    print("Inserted shop rows: n/a (existing DB helper uses UPSERT)")
    print("Updated shop rows: n/a (existing DB helper uses UPSERT)")
    print(f"Inserted prices: {summary.rows_inserted}")
    print(f"Skipped duplicates: {1 if summary.already_imported else 0}")
    print(f"Already imported: {summary.already_imported}")
    print(f"Errors: {'; '.join(summary.errors) if summary.errors else '-'}")
    print(f"Debug files: {', '.join(summary.debug_files) if summary.debug_files else '-'}")
    print("================================")


def _fallback_error_hash(source: str, filename: str) -> str:
    return hashlib.sha256(f"{source}:{filename}".encode("utf-8")).hexdigest()
