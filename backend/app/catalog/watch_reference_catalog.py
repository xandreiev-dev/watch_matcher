from app.repositories.watch_reference_repository import WatchReferenceRepository
from app.normalizers.watch_reference_normalizer import WatchReferenceNormalizer


class WatchReferenceCatalog:
    @classmethod
    def load_models(cls, brand: str | None = None) -> list[dict]:
        if brand:
            rows = WatchReferenceRepository.fetch_models_by_brand(brand)
        else:
            rows = WatchReferenceRepository.fetch_all_models()

        result = []
        for row in rows:
            normalized_name = row.get("normalized_name") or ""

            parsed = WatchReferenceNormalizer.extract_family_generation_variant(
                normalized_name,
                row.get("brand"),
            )

            result.append(
                {
                    "id": row.get("id"),
                    "brand": row.get("brand"),
                    "model_name": row.get("model_name"),
                    "normalized_name": normalized_name,
                    "family": parsed.get("family"),
                    "generation": parsed.get("generation"),
                    "variant": parsed.get("variant"),
                }
            )

        return result

    @classmethod
    def load_variants(cls, brand: str | None = None) -> list[dict]:
        if brand:
            rows = WatchReferenceRepository.fetch_variants_by_brand(brand)
        else:
            rows = WatchReferenceRepository.fetch_all_variants()

        result = []
        for row in rows:
            normalized_variant_name = row.get("normalized_variant_name") or ""
            model_normalized_name = row.get("model_normalized_name") or ""

            parsed_model = WatchReferenceNormalizer.extract_family_generation_variant(
                model_normalized_name,
                row.get("brand"),
            )

            result.append(
                {
                    "id": row.get("id"),
                    "brand": row.get("brand"),
                    "model_id": row.get("model_id"),
                    "model_name": row.get("model_name"),
                    "model_normalized_name": model_normalized_name,
                    "variant_name": row.get("variant_name"),
                    "normalized_variant_name": normalized_variant_name,
                    "case_size_mm": row.get("case_size_mm"),
                    "case_material": row.get("case_material"),
                    "connectivity_type": row.get("connectivity_type"),
                    "case_material_key": row.get("case_material_key"),
                    "connectivity_key": row.get("connectivity_key"),
                    "family": parsed_model.get("family"),
                    "generation": parsed_model.get("generation"),
                    "model_variant": parsed_model.get("variant"),
                }
            )

        return result
