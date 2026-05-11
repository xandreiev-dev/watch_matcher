import re
from collections import defaultdict

from fastapi import APIRouter, Query

from app.catalog.watch_reference_catalog import WatchReferenceCatalog
from app.matchers.watch_matcher import WatchMatcher

router = APIRouter()


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def normalized_key(value: object) -> str:
    return WatchMatcher.normalize_model_key(str(value or ""))


def model_matches(row: dict, requested_model: str) -> bool:
    requested = normalized_key(requested_model)
    requested_compact = compact_key(requested_model)

    candidates = {
        normalized_key(row.get("model_name")),
        normalized_key(row.get("normalized_name")),
        compact_key(row.get("model_name")),
        compact_key(row.get("normalized_name")),
    }

    return requested in candidates or requested_compact in candidates


def clean_variant(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "model_id": row.get("model_id"),
        "variant_name": row.get("variant_name"),
        "case_size_mm": row.get("case_size_mm"),
        "case_material": row.get("case_material"),
        "case_material_key": row.get("case_material_key"),
        "connectivity_type": row.get("connectivity_type"),
        "connectivity_key": row.get("connectivity_key"),
    }


def material_matches(row: dict, material: str) -> bool:
    requested = compact_key(material)
    return requested in {
        compact_key(row.get("case_material")),
        compact_key(row.get("case_material_key")),
    }


def connectivity_matches(row: dict, connectivity: str) -> bool:
    requested = compact_key(connectivity)
    return requested in {
        compact_key(row.get("connectivity_type")),
        compact_key(row.get("connectivity_key")),
    }


def is_universal_variant(row: dict) -> bool:
    return not row.get("case_material") and not row.get("case_material_key") and not row.get("connectivity_type") and not row.get("connectivity_key")


@router.get("/resolve")
def resolve_watch_reference(
    brand: str = Query(...),
    model: str = Query(...),
    size_mm: int | None = Query(None),
    material: str | None = Query(None),
    connectivity: str | None = Query(None),
) -> dict:
    models = [
        row
        for row in WatchReferenceCatalog.load_models(brand=brand)
        if model_matches(row, model)
    ]

    if not models:
        return {"status": "not_found", "reason": "model_not_found", "model": None, "variant": None}

    if len(models) > 1:
        return {
            "status": "ambiguous",
            "reason": "multiple_models",
            "models": models,
            "variant": None,
        }

    model_row = models[0]
    variants = [
        row
        for row in WatchReferenceCatalog.load_variants(brand=brand)
        if str(row.get("model_id")) == str(model_row.get("id"))
    ]

    candidates = variants
    if size_mm is not None:
        candidates = [
            row
            for row in candidates
            if row.get("case_size_mm") is not None and int(row.get("case_size_mm")) == int(size_mm)
        ]

    if material:
        candidates = [row for row in candidates if material_matches(row, material)]

    if connectivity:
        candidates = [row for row in candidates if connectivity_matches(row, connectivity)]

    if not candidates:
        return {
            "status": "matched_model_variant_not_found",
            "model": model_row,
            "variant": None,
            "variants": [clean_variant(row) for row in variants],
        }

    if len(candidates) == 1:
        return {
            "status": "matched",
            "model": model_row,
            "variant": clean_variant(candidates[0]),
        }

    if not material and not connectivity:
        universal = [row for row in candidates if is_universal_variant(row)]
        if len(universal) == 1:
            return {
                "status": "matched",
                "model": model_row,
                "variant": clean_variant(universal[0]),
            }

    return {
        "status": "ambiguous",
        "reason": "multiple_variants",
        "model": model_row,
        "variants": [clean_variant(row) for row in candidates],
    }


@router.get("/diagnostics/variants")
def diagnose_watch_variants(limit: int = Query(100, ge=1, le=1000)) -> dict:
    models = WatchReferenceCatalog.load_models()
    variants = WatchReferenceCatalog.load_variants()

    variants_by_model: dict[str, list[dict]] = defaultdict(list)
    for row in variants:
        variants_by_model[str(row.get("model_id"))].append(row)

    models_without_variants = [
        row
        for row in models
        if str(row.get("id")) not in variants_by_model
    ]

    duplicate_groups = []
    ambiguous_size_groups = []
    suspicious_variants = []

    for model_id, rows in variants_by_model.items():
        by_full_key: dict[tuple, list[dict]] = defaultdict(list)
        by_size_key: dict[object, list[dict]] = defaultdict(list)

        for row in rows:
            by_full_key[
                (
                    row.get("case_size_mm"),
                    compact_key(row.get("case_material") or row.get("case_material_key")),
                    compact_key(row.get("connectivity_type") or row.get("connectivity_key")),
                )
            ].append(row)
            by_size_key[row.get("case_size_mm")].append(row)

            if not row.get("variant_name") or row.get("case_size_mm") in {"", 0}:
                suspicious_variants.append(clean_variant(row))

        for key, grouped_rows in by_full_key.items():
            if len(grouped_rows) > 1:
                duplicate_groups.append(
                    {
                        "model_id": model_id,
                        "key": key,
                        "variants": [clean_variant(row) for row in grouped_rows],
                    }
                )

        for size, grouped_rows in by_size_key.items():
            if size is not None and len(grouped_rows) > 1:
                has_universal = any(is_universal_variant(row) for row in grouped_rows)
                if not has_universal:
                    ambiguous_size_groups.append(
                        {
                            "model_id": model_id,
                            "case_size_mm": size,
                            "variants": [clean_variant(row) for row in grouped_rows],
                        }
                    )

    return {
        "counts": {
            "models": len(models),
            "variants": len(variants),
            "models_without_variants": len(models_without_variants),
            "duplicate_variant_groups": len(duplicate_groups),
            "ambiguous_size_groups": len(ambiguous_size_groups),
            "suspicious_variants": len(suspicious_variants),
        },
        "models_without_variants": models_without_variants[:limit],
        "duplicate_variant_groups": duplicate_groups[:limit],
        "ambiguous_size_groups": ambiguous_size_groups[:limit],
        "suspicious_variants": suspicious_variants[:limit],
    }
