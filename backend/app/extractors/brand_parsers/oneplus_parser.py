import re
from app.schemas.watch_features import WatchFeatures


class OnePlusParser:
    NOISE_WORDS = [
        "новые",
        "новый",
        "русский",
        "русский язык",
        "рф",
        "все цвета",
        "в наличии",
        "оригинал",
        "оригинальные",
        "гарантия",
        "умные часы",
        "смарт часы",
        "смарт-часы",
        "смартчасы",
        "часы",
        "oneplus",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\bwatch\s*\d+\s*/\s*\d+\b",
        r"\bwatch\s*\d+\s*,\s*\d+\b",
        r"\b\d{2}\s*mm\s*/\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*mm\s*,\s*\d{2}\s*mm\b",
    ]

    @classmethod
    def parse(cls, features: WatchFeatures) -> WatchFeatures:
        text = features.normalized_title or ""
        if not text:
            return features

        cleaned = cls.cleanup_text(text)

        if cls.is_multi_model(cleaned):
            features.is_multi_model = True
            return features

        parsed = cls.extract_model_fields(cleaned)

        if parsed["family"]:
            features.family = parsed["family"]

        if parsed["generation"]:
            features.generation = parsed["generation"]

        if parsed["variant"]:
            features.variant = parsed["variant"]

        model_candidates = cls.build_model_candidates(
            family=parsed["family"],
            generation=parsed["generation"],
            variant=parsed["variant"],
            size_mm=features.size_mm,
        )
        if model_candidates:
            features.model_candidates = model_candidates

        variant_name = cls.build_variant_name(
            family=parsed["family"],
            generation=parsed["generation"],
            variant=parsed["variant"],
            size_mm=features.size_mm,
        )
        if variant_name:
            features.extracted_variant_name = variant_name

        return features

    @classmethod
    def cleanup_text(cls, text: str) -> str:
        cleaned = text.lower().strip()
        cleaned = cleaned.replace("мм", "mm")
        cleaned = cleaned.replace("-", " ")
        cleaned = cleaned.replace("_", " ")
        cleaned = cleaned.replace(",", " ")
        cleaned = cleaned.replace("/", " / ")
        cleaned = cleaned.replace("(", " ")
        cleaned = cleaned.replace(")", " ")

        # OnePlus часто клеит Watch2R без пробела.
        cleaned = re.sub(r"\bwatch(\d+r)\b", r"watch \1", cleaned)
        cleaned = re.sub(r"\bwatch(\d+)\b", r"watch \1", cleaned)

        for noise in cls.NOISE_WORDS:
            cleaned = re.sub(rf"\b{re.escape(noise)}\b", " ", cleaned)

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def is_multi_model(cls, text: str) -> bool:
        if not text:
            return False

        for pattern in cls.MULTI_MODEL_PATTERNS:
            if re.search(pattern, text):
                return True

        sizes = re.findall(r"\b(43|45)\s*mm\b", text)
        if len(set(sizes)) > 1:
            return True

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = None
        generation = None
        found_variants: list[str] = []

        # Nord Watch
        if re.search(r"\bnord\s+watch\b", text):
            family = "Nord"
            return {
                "family": family,
                "generation": generation,
                "variant": None,
            }

        # Watch Lite
        if re.search(r"\bwatch\s+lite\b", text):
            family = "Watch"
            found_variants.append("Lite")
            m = re.search(r"\bwatch\s*(\d+)\s+lite\b", text)
            if m:
                generation = m.group(1)

            unique = []
            for item in found_variants:
                if item not in unique:
                    unique.append(item)

            return {
                "family": family,
                "generation": generation,
                "variant": " ".join(unique) if unique else None,
            }

        # Watch 2 / Watch 2R / Watch 3 / Watch 3 Lite
        if re.search(r"\bwatch\b", text):
            family = "Watch"

            # 2R
            m2r = re.search(r"\bwatch\s*(\d+r)\b", text)
            if m2r:
                generation = m2r.group(1).upper()
            else:
                m = re.search(r"\bwatch\s*(\d+)\b", text)
                if m:
                    generation = m.group(1)

            if re.search(r"\blite\b", text):
                found_variants.append("Lite")

        unique = []
        for item in found_variants:
            if item not in unique:
                unique.append(item)

        return {
            "family": family,
            "generation": generation,
            "variant": " ".join(unique) if unique else None,
        }

    @classmethod
    def build_model_candidates(
        cls,
        family: str | None,
        generation: str | None,
        variant: str | None,
        size_mm: int | None,
    ) -> list[str]:
        if not family:
            return []

        candidates: list[str] = []

        if family == "Nord":
            candidates.append("nord watch")

        elif family == "Watch":
            if generation and variant:
                if size_mm:
                    candidates.append(f"watch {generation.lower()} {variant.lower()} {int(size_mm)}mm")
                candidates.append(f"watch {generation.lower()} {variant.lower()}")

            if generation:
                if size_mm:
                    candidates.append(f"watch {generation.lower()} {int(size_mm)}mm")
                candidates.append(f"watch {generation.lower()}")

            if variant and not generation:
                if size_mm:
                    candidates.append(f"watch {variant.lower()} {int(size_mm)}mm")
                candidates.append(f"watch {variant.lower()}")

            candidates.append("watch")

        result: list[str] = []
        seen = set()

        for item in candidates:
            item = re.sub(r"\s+", " ", item).strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)

        return result

    @classmethod
    def build_variant_name(
        cls,
        family: str | None,
        generation: str | None,
        variant: str | None,
        size_mm: int | None,
    ) -> str | None:
        if not family:
            return None

        if family == "Nord":
            parts = ["Nord Watch"]
        else:
            parts = ["Watch"]

        if generation:
            parts.append(str(generation))

        if variant:
            parts.append(variant)

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        return " ".join(parts).strip()
