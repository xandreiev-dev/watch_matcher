import re
from app.schemas.watch_features import WatchFeatures


class VivoParser:
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
        "vivo",
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
        cleaned = cleaned.replace(",", " ")
        cleaned = cleaned.replace("/", " / ")

        # iqoowatch → iqoo watch
        cleaned = re.sub(r"\biqoowatch\b", "iqoo watch", cleaned)

        # watch2 → watch 2
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

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = None
        generation = None
        variant = None

        # iQOO Watch
        if re.search(r"\biqoo\s+watch\b", text):
            family = "IQOO"

            # GT версия
            if re.search(r"\bgt\b", text):
                variant = "GT"

                m = re.search(r"\bgt\s*(\d+)\b", text)
                if m:
                    generation = m.group(1)

            return {
                "family": family,
                "generation": generation,
                "variant": variant,
            }

        # Watch GT
        if re.search(r"\bwatch\s+gt\b", text):
            family = "Watch"
            variant = "GT"

            m = re.search(r"\bgt\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            return {
                "family": family,
                "generation": generation,
                "variant": variant,
            }

        # Watch 2 / 3 / 5
        if re.search(r"\bwatch\s*\d+\b", text):
            family = "Watch"

            m = re.search(r"\bwatch\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            return {
                "family": family,
                "generation": generation,
                "variant": None,
            }

        # Просто Watch
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
        size_mm: int | None,
    ) -> list[str]:

        if not family:
            return []

        candidates = []

        # iQOO
        if family == "IQOO":
            if variant == "GT":
                if generation:
                    candidates.append(f"iqoo watch gt {generation}")
                    candidates.append(f"watch gt {generation}")
                candidates.append("iqoo watch gt")

            candidates.append("iqoo watch")

        # Watch GT
        elif variant == "GT":
            if generation:
                candidates.append(f"watch gt {generation}")
            candidates.append("watch gt")

        # Watch 2 / 3 / 5
        elif generation:
            if size_mm:
                candidates.append(f"watch {generation} {int(size_mm)}mm")
            candidates.append(f"watch {generation}")

        # Если точного кандидата нет, оставляем более общий.
        candidates.append("watch")

        # Убираем пустые и дублирующиеся варианты.
        result = []
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

        parts = []

        if family == "IQOO":
            parts.append("iQOO Watch")
        else:
            parts.append("Watch")

        if variant == "GT":
            parts.append("GT")

        if generation:
            parts.append(str(generation))

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        return " ".join(parts).strip()
