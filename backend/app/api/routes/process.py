from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import pandas as pd

from app.core.constants import EXTRACTION_PREVIEW_ROWS_COUNT
from app.services.excel_service import ExcelService
from app.services.watch_preprocess_service import WatchPreprocessService
from app.extractors.watch_feature_extractor import WatchFeatureExtractor
from app.matchers.watch_matcher import WatchMatcher
from app.catalog.watch_reference_catalog import WatchReferenceCatalog
from app.services.unmatched_postprocess_service import UnmatchedPostprocessService
from app.schemas.watch_features import WatchFeatures
from app.services.export_preview import WatchPreviewExporter
from app.services.watch_db_writer_service import WatchDbWriterService
from app.core.logging_config import get_logger

router = APIRouter()
logger = get_logger("process")

SHOP_ID_BY_SOURCE = {
    "ozon": 1,
    "avito": 2,
}


def first_present(row: dict, *keys: str):
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "<na>", "nat"}:
            continue
        return value
    return None


def normalize_source(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if normalized in {"ozon", "ozon.ru", "1"}:
        return "ozon"
    if normalized in {"avito", "avito.ru", "2"}:
        return "avito"
    return None


def resolve_source_and_shop_id(
    source_name: str,
    dataframe,
    source_raw: str | None,
    shop_id_raw: int | None,
) -> tuple[str, int]:
    if shop_id_raw in {1, 2}:
        source = "ozon" if shop_id_raw == 1 else "avito"
        return source, shop_id_raw

    explicit_source = normalize_source(source_raw)
    if explicit_source:
        return explicit_source, SHOP_ID_BY_SOURCE[explicit_source]

    name = (source_name or "").strip().lower()
    columns = {str(column).strip().lower() for column in dataframe.columns}

    if "ozon" in name or "source_brand" in columns or "tax_price" in columns:
        return "ozon", SHOP_ID_BY_SOURCE["ozon"]

    return "avito", SHOP_ID_BY_SOURCE["avito"]


def build_display_model(
    matched_model_name: str | None,
    family: str | None,
    generation: str | None,
    variant: str | None,
    model_candidates: list[str] | None,
) -> str | None:
    if matched_model_name:
        return matched_model_name

    if model_candidates:
        for candidate in model_candidates:
            if candidate:
                return candidate

    parts = []
    if family:
        parts.append(str(family))
    if generation:
        parts.append(str(generation))
    if variant:
        parts.append(str(variant))

    return " ".join(parts) if parts else None


def process_watch_row(
    row: dict,
    models_catalog: list[dict],
    variants_catalog: list[dict],
    source: str = "avito",
) -> dict:
    preprocessed = WatchPreprocessService.preprocess_row(row, source=source)

    features = WatchFeatureExtractor.extract(
        title=preprocessed.product_name,
        description=preprocessed.description,
        brand=preprocessed.brand,
    )

    # preprocess остаётся источником правды по бренду, size и флагам
    features.brand = preprocessed.brand
    features.size_mm = preprocessed.size_mm
    features.is_accessory = preprocessed.is_accessory
    features.is_multi_model = preprocessed.is_multi_model or features.is_multi_model

    match_result = WatchMatcher.match(
        features=features,
        models_catalog=models_catalog,
        variants_catalog=variants_catalog,
    )

    # постобработка только для unmatched
    if match_result.match_status == "unmatched":
        post = UnmatchedPostprocessService.apply(
            title=preprocessed.product_name,
            brand=preprocessed.brand,
        )

        if post["changed"]:
            post_features = WatchFeatures(
                product_name=preprocessed.product_name,
                normalized_title=post["normalized_title"],
                brand=post["brand"],
                size_mm=preprocessed.size_mm,
                all_sizes_mm=preprocessed.all_sizes_mm,
                color=features.color,
                warranty_period=features.warranty_period,
                is_accessory=preprocessed.is_accessory,
                is_multi_model=preprocessed.is_multi_model,
            )

            post_features = WatchFeatureExtractor.apply_brand_parser(post_features)

            post_match_result = WatchMatcher.match(
                features=post_features,
                models_catalog=models_catalog,
                variants_catalog=variants_catalog,
            )

            if post_match_result.match_status == "matched":
                features = post_features
                match_result = post_match_result

    if match_result.match_status == "ambiguous_multi_model":
        features.is_multi_model = True
        features.size_mm = None
        features.family = None
        features.generation = None
        features.variant = None

    display_model = build_display_model(
        matched_model_name=match_result.matched_model_name,
        family=features.family,
        generation=features.generation,
        variant=features.variant,
        model_candidates=features.model_candidates,
    )

    return {
        "Название": preprocessed.product_name,
        "normalized_title": preprocessed.normalized_title,
        "Бренд": preprocessed.brand,
        "brand_from_url": preprocessed.brand_from_url,
        "brand_match": preprocessed.brand_match,
        "article": preprocessed.article,
        "size_mm": features.size_mm,
        "all_sizes_mm": preprocessed.all_sizes_mm,
        "is_accessory": preprocessed.is_accessory,
        "is_multi_model": features.is_multi_model,
        "family": features.family,
        "generation": features.generation,
        "variant": features.variant,
        "model_candidates": features.model_candidates,
        "extracted_material": features.extracted_material,
        "extracted_connectivity": features.extracted_connectivity,
        "extracted_variant_name": features.extracted_variant_name,
        "Цвет": features.color,
        "Гарантия": features.warranty_period,
        "URL": preprocessed.product_url,
        "image_url": preprocessed.image_url,
        "shop_rating": preprocessed.shop_rating,
        "price": preprocessed.price,
        "currency": "RUB",
        "match_status": match_result.match_status,
        "matched_variant_id": match_result.matched_variant_id,
        "matched_variant_name": match_result.matched_variant_name,
        "matched_model_id": match_result.matched_model_id,
        "matched_model_name": match_result.matched_model_name,
        "match_method": match_result.match_method,
        "confidence": match_result.confidence,
        "needs_manual_review": match_result.needs_manual_review,
        "rating": first_present(row, "Звезды", "rating"),
        "review": first_present(row, "reviews_count", "Отзывы", "review"),
        "days_to_delivery": (
            first_present(row, "delivery_days", "delivery_date", "Доставка")
            if source == "ozon"
            else first_present(row, "Доставка", "delivery_days")
        ),
        "is_global": first_present(row, "is_global"),
        "tax_price": first_present(row, "tax_price"),
        "source": source,
        "display_model": display_model,
    }


def build_stats(rows: list[dict]) -> dict:
    total_rows = len(rows)
    matched_rows = sum(1 for row in rows if row.get("match_status") == "matched")
    unmatched_rows = total_rows - matched_rows

    return {
        "total_rows": total_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
    }

def build_process_logs(result: list[dict], resolved_is_new: bool) -> None:
    total = len(result)
    matched = sum(1 for row in result if row.get("match_status") == "matched")
    unmatched = total - matched

    logger.info(
        f"[ПАЙПЛАЙН] всего={total} | совпало={matched} | "
        f"без_совпадений={unmatched} | тип={'НОВЫЕ' if resolved_is_new else 'БУ'}"
    )

def resolve_is_new(
    source_name: str,
    is_new_raw: str | None,
) -> bool:
    """
    Приоритет:
    1. если is_new явно пришел с фронта -> используем его
    2. иначе пытаемся понять по имени файла
    3. если не удалось -> по умолчанию True
    """
    if is_new_raw is not None:
        value = str(is_new_raw).strip().lower()
        if value in {"true", "1", "yes", "new"}:
            return True
        if value in {"false", "0", "no", "old", "used"}:
            return False

    name = (source_name or "").strip().lower()

    if "_old.xlsx" in name or "_used.xlsx" in name or "old.xlsx" in name or "used.xlsx" in name:
        return False

    if "_new.xlsx" in name or "new.xlsx" in name:
        return True

    return True


@router.post("/preview")
async def process_preview(
    file: UploadFile | None = File(None),
    file_url: str | None = Form(""),
    is_new: str | None = Form(None),
    source: str | None = Form(None),
    shop_id: int | None = Form(None),
):
    try:
        logger.info("Запущена предпросмотрная обработка файла")
        dataframe, source_name = await get_dataframe_from_input(file, file_url)
        resolved_is_new = resolve_is_new(source_name, is_new)
        resolved_source, resolved_shop_id = resolve_source_and_shop_id(
            source_name,
            dataframe,
            source,
            shop_id,
        )

        ExcelService.validate_columns(dataframe)

        preview_df = dataframe.head(EXTRACTION_PREVIEW_ROWS_COUNT).copy()
        preview_df = preview_df.fillna("")

        models_catalog = WatchReferenceCatalog.load_models()
        variants_catalog = WatchReferenceCatalog.load_variants()

        result = []
        for _, row in preview_df.iterrows():
            row_dict = row.to_dict()
            result.append(process_watch_row(row_dict, models_catalog, variants_catalog, source=resolved_source))

        build_process_logs(result, resolved_is_new)
        logger.info(f"[SOURCE] source={resolved_source} shop_id={resolved_shop_id}")

        output_file = WatchPreviewExporter.export(
            result,
            is_new=resolved_is_new,
            source=resolved_source,
            shop_id=resolved_shop_id,
        )

        return {
            "filename": source_name,
            "is_new": resolved_is_new,
            "source": resolved_source,
            "shop_id": resolved_shop_id,
            "preview_file": output_file,
            "preview": result,
            "stats": build_stats(result),
        }

    except ValueError as exc:
        logger.warning(f"Ошибка валидации при предпросмотре: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Сбой предпросмотрной обработки: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(exc)}",
        )


@router.post("")
async def process_file(
    file: UploadFile | None = File(None),
    file_url: str | None = Form(""),
    is_new: str | None = Form(None),
    source: str | None = Form(None),
    shop_id: int | None = Form(None),
    write_to_db: bool = Form(True),
):
    try:
        logger.info("Запущена полная обработка файла")
        dataframe, source_name = await get_dataframe_from_input(file, file_url)
        resolved_is_new = resolve_is_new(source_name, is_new)
        resolved_source, resolved_shop_id = resolve_source_and_shop_id(
            source_name,
            dataframe,
            source,
            shop_id,
        )

        ExcelService.validate_columns(dataframe)

        processed_df = dataframe.copy()
        processed_df = processed_df.fillna("")

        models_catalog = WatchReferenceCatalog.load_models()
        variants_catalog = WatchReferenceCatalog.load_variants()

        result = []
        for _, row in processed_df.iterrows():
            row_dict = row.to_dict()
            result.append(process_watch_row(row_dict, models_catalog, variants_catalog, source=resolved_source))

        build_process_logs(result, resolved_is_new)
        logger.info(f"[SOURCE] source={resolved_source} shop_id={resolved_shop_id}")

        output_file = WatchPreviewExporter.export(
            result,
            is_new=resolved_is_new,
            source=resolved_source,
            shop_id=resolved_shop_id,
        )

        if write_to_db:
            import time

            start_time = time.time()
            logger.info(
                f"[БД] Начало записи | тип={'НОВЫЕ' if resolved_is_new else 'БУ'} | строк={len(result)}"
            )

            result_df = pd.DataFrame(result)

            WatchDbWriterService.prepare_and_write_watch_data_to_db(
                df_res=result_df,
                actual_date=date.today(),
                shop_id=resolved_shop_id,
                is_new=resolved_is_new,
            )

            duration = round(time.time() - start_time, 2)
            logger.info(
                f"[БД] Запись завершена | тип={'НОВЫЕ' if resolved_is_new else 'БУ'} | строк={len(result)} | время={duration}с"
            )

        return {
            "filename": source_name,
            "is_new": resolved_is_new,
            "source": resolved_source,
            "shop_id": resolved_shop_id,
            "output_file": output_file,
            "db_written": write_to_db,
            "stats": build_stats(result),
            "data": result,
        }

    except ValueError as exc:
        logger.warning(f"Ошибка валидации при полной обработке: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Сбой полной обработки: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(exc)}",
        )


async def get_dataframe_from_input(file: UploadFile | None, file_url: str | None):
    if file is not None and getattr(file, "filename", "") == "":
        file = None

    if file_url is not None:
        file_url = file_url.strip()
        if file_url == "":
            file_url = None

    if file and file_url:
        raise HTTPException(
            status_code=400,
            detail="Provide either file or file_url, not both",
        )

    if not file and not file_url:
        raise HTTPException(
            status_code=400,
            detail="Either file or file_url is required",
        )

    if file:
        if not file.filename.endswith(".xlsx"):
            raise HTTPException(
                status_code=400,
                detail="Only .xlsx files are supported",
            )

        dataframe = await ExcelService.read_excel_file(file)
        source_name = file.filename
        logger.info(f"Входные данные загружены из файла: {source_name}")
        return dataframe, source_name

    try:
        dataframe = ExcelService.read_excel_from_url(file_url)
        source_name = file_url
        logger.info(f"Входные данные загружены по URL: {source_name}")
        return dataframe, source_name
    except ValueError as exc:
        logger.warning(f"Ошибка валидации при загрузке по URL: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Не удалось загрузить файл по URL: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load file from URL: {str(exc)}",
        )
