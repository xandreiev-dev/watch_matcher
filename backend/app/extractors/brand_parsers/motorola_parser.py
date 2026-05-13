import re
from app.schemas.watch_features import WatchFeatures


class MotorolaParser:
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
        "motorola",
        "moto",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\bwatch\s*\d+\s*/\s*\d+\b",
        r"\bwatch\s*\d+\s*,\s*\d+\b",
        r"\b\d{2,3}\s*/\s*\d{2,3}\b",
        r"\b\d{2,3}\s*,\s*\d{2,3}\b",
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
        )
        if model_candidates:
            features.model_candidates = model_candidates

        variant_name = cls.build_variant_name(
            family=parsed["family"],
            generation=parsed["generation"],
            variant=parsed["variant"],
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

        # MotoWatch часто пишут одним словом.
        cleaned = re.sub(r"\bmotowatch\b", "moto watch", cleaned)

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

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = None
        generation = None
        variant = None

        # Moto Watch Fit
        if re.search(r"\bwatch\s+fit\b", text):
            family = "Watch"
            variant = "Fit"
            return {
                "family": family,
                "generation": generation,
                "variant": variant,
            }

        # Moto Watch 40 / 70 / 100 / 120 / 150 / 200
        m = re.search(r"\bwatch\s*(40|70|100|120|150|200)\b", text)
        if m:
            family = "Watch"
            generation = m.group(1)
            return {
                "family": family,
                "generation": generation,
                "variant": variant,
            }

        # Если деталей нет, оставляем базовый Moto Watch.
        if re.search(r"\bwatch\b", text):
            family = "Watch"

        return {
            "family": family,
            "generation": generation,
            "variant": variant,
        }

    @classmethod
    def build_model_candidates(
        cls,
        family: str | None,
        generation: str | None,
        variant: str | None,
    ) -> list[str]:
        if not family:
            return []

        candidates: list[str] = []

        if family == "Watch" and variant == "Fit":
            candidates.append("moto watch fit")
            candidates.append("watch fit")

        elif family == "Watch" and generation:
            candidates.append(f"moto watch {generation}")
            candidates.append(f"watch {generation}")

        elif family == "Watch":
            candidates.append("moto watch")
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
    ) -> str | None:
        if not family:
            return None

        parts = ["Moto Watch"]

        if generation:
            parts.append(str(generation))

        if variant:
            parts.append(variant)

        return " ".join(parts).strip()
