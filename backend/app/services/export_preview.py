from datetime import datetime
from pathlib import Path

import pandas as pd


SHOP_ID_BY_SOURCE = {
    "avito": 2,
    "ozon": 1,
}


class WatchPreviewExporter:
    @classmethod
    def export(
        cls,
        rows: list[dict],
        is_new: bool,
        source: str = "avito",
        shop_id: int | None = None,
        output_file: str | None = None,
    ) -> str:
        """
        Сохраняет полный результат обработки с сохранением логики источника.
        """
        today = datetime.now().date()
        normalized_source = (source or "avito").strip().lower()
        resolved_shop_id = shop_id or SHOP_ID_BY_SOURCE.get(normalized_source, SHOP_ID_BY_SOURCE["avito"])
        prepared_rows = []

        for row in rows:
            model_display = cls._build_display_model(row)

            prepared_row = {
                "Название": row.get("Название"),
                "normalized_title": row.get("normalized_title"),
                "Бренд": row.get("Бренд"),
                "brand_from_url": row.get("brand_from_url"),
                "brand_match": row.get("brand_match"),
                "article": row.get("article"),
                "size_mm": row.get("size_mm"),
                "all_sizes_mm": row.get("all_sizes_mm"),
                "is_accessory": row.get("is_accessory"),
                "is_multi_model": row.get("is_multi_model"),
                "family": row.get("family"),
                "generation": row.get("generation"),
                "variant": row.get("variant"),
                "model_candidates": row.get("model_candidates"),
                "extracted_material": row.get("extracted_material"),
                "extracted_connectivity": row.get("extracted_connectivity"),
                "extracted_variant_name": row.get("extracted_variant_name"),
                "Цвет": row.get("Цвет"),
                "Гарантия": row.get("Гарантия"),
                "URL": row.get("URL"),
                "image_url": row.get("image_url"),
                "shop_rating": row.get("shop_rating"),
                "rating": row.get("rating"),
                "review": cls._get_review_value(row),
                "days_to_delivery": cls._get_delivery_value(row),
                "price": row.get("price"),
                "currency": "RUB",
                "actual_date": today,
                "is_new": 1 if is_new else 0,
                "match_status": row.get("match_status"),
                "matched_variant_id": row.get("matched_variant_id"),
                "matched_variant_name": row.get("matched_variant_name"),
                "matched_model_id": row.get("matched_model_id"),
                "matched_model_name": row.get("matched_model_name"),
                "match_method": row.get("match_method"),
                "confidence": row.get("confidence"),
                "needs_manual_review": row.get("needs_manual_review"),
                "shop_id": resolved_shop_id,
                "display_model": model_display,
            }

            # Ozon-колонки держим отдельно, чтобы не менять привычный Avito export.
            if normalized_source == "ozon":
                prepared_row.update(
                    {
                        "source": row.get("source") or normalized_source,
                        "is_global": row.get("is_global"),
                        "tax_price": row.get("tax_price"),
                    }
                )

            prepared_rows.append(prepared_row)

        df = pd.DataFrame(prepared_rows)

        if output_file is None:
            suffix = "new" if is_new else "old"
            output_file = f"output/{normalized_source}_watch_{today}_{suffix}.xlsx"

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(output_path, index=False)

        print(f"Preview saved to {output_path.resolve()}")
        return str(output_path.resolve())

    @classmethod
    def _build_display_model(cls, row: dict) -> str | None:
        if row.get("matched_model_name"):
            return row["matched_model_name"]

        model_candidates = row.get("model_candidates") or []
        if isinstance(model_candidates, list) and model_candidates:
            return model_candidates[0]

        parts = []
        if row.get("family"):
            parts.append(str(row["family"]))
        if row.get("generation"):
            parts.append(str(row["generation"]))
        if row.get("variant"):
            parts.append(str(row["variant"]))

        return " ".join(parts) if parts else None

    @classmethod
    def _get_review_value(cls, row: dict):
        return (
            row.get("review")
            or row.get("reviews")
            or row.get("reviews_count")
            or row.get("review_count")
        )

    @classmethod
    def _get_delivery_value(cls, row: dict):
        return (
            row.get("days_to_delivery")
            or row.get("delivery")
            or row.get("delivery_days")
        )
