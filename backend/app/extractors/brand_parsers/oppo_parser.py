import re
from app.schemas.watch_features import WatchFeatures


class OppoParser:
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
        "oppo",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\bwatch\s*\d+\s*/\s*\d+\b",
        r"\bwatch\s*\d+\s*,\s*\d+\b",
        r"\bwatch\s*x\d+\s*/\s*x\d+\b",
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

        # Ozon/Avito иногда клеят WatchX2 без пробела.
        cleaned = re.sub(r"\bwatchx(\d+)\b", r"watch x\1", cleaned)
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

        sizes = re.findall(r"\b(41|42|46)\s*mm\b", text)
        if len(set(sizes)) > 1:
            return True

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = None
        generation = None
        found_variants: list[str] = []

        # Watch Free
        if re.search(r"\bwatch\s+free\b", text):
            family = "Watch"
            found_variants.append("Free")

        # Watch SE
        elif re.search(r"\bwatch\s+se\b", text):
            family = "Watch"
            found_variants.append("SE")

        # Watch S
        elif re.search(r"\bwatch\s+s\b", text):
            family = "Watch"
            found_variants.append("S")

        # Watch X / X2 / X2 Mini / X3
        elif re.search(r"\bwatch\s+x\b", text) or re.search(r"\bwatch\s+x\d+\b", text):
            family = "Watch"

            m = re.search(r"\bwatch\s+x(\d+)\b", text)
            if m:
                generation = m.group(1)
                found_variants.append("X")
            else:
                found_variants.append("X")

            if re.search(r"\bmini\b", text):
                found_variants.append("Mini")

        # Watch 2 / 3 / 3 Pro / 4 Pro
        elif re.search(r"\bwatch\s*\d+\b", text):
            family = "Watch"
            m = re.search(r"\bwatch\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

        # Если линейку не уточнили, оставляем базовый Watch.
        elif re.search(r"\bwatch\b", text):
            family = "Watch"

        unique = []
        for item in found_variants:
            if item not in unique:
                unique.append(item)

        variant = " ".join(unique) if unique else None

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

        candidates: list[str] = []

        if family == "Watch":
            if variant == "Free":
                candidates.append("watch free")

            elif variant == "SE":
                candidates.append("watch se")

            elif variant == "S":
                candidates.append("watch s")

            elif variant and "X" in variant:
                if generation and "Mini" in (variant or ""):
                    if size_mm:
                        candidates.append(f"watch x{generation} mini {int(size_mm)}mm")
                        candidates.append(f"watch x {generation} mini {int(size_mm)}mm")
                    candidates.append(f"watch x{generation} mini")
                    candidates.append(f"watch x {generation} mini")
                elif generation:
                    if size_mm:
                        candidates.append(f"watch x{generation} {int(size_mm)}mm")
                        candidates.append(f"watch x {generation} {int(size_mm)}mm")
                    candidates.append(f"watch x{generation}")
                    candidates.append(f"watch x {generation}")
                else:
                    candidates.append("watch x")

            elif generation and variant:
                if size_mm:
                    candidates.append(f"watch {generation} {variant.lower()} {int(size_mm)}mm")
                candidates.append(f"watch {generation} {variant.lower()}")

            elif generation:
                if size_mm:
                    candidates.append(f"watch {generation} {int(size_mm)}mm")
                candidates.append(f"watch {generation}")

            if family == "Watch":
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

        parts = ["Watch"]

        if variant == "Free":
            parts.append("Free")

        elif variant == "SE":
            parts.append("SE")

        elif variant == "S":
            parts.append("S")

        elif variant and variant.startswith("X"):
            parts.append("X")
            if generation:
                parts[-1] = f"X{generation}"
            if variant == "X Mini":
                parts.append("Mini")

        else:
            if generation:
                parts.append(str(generation))
            if variant:
                parts.append(variant)

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        return " ".join(parts).strip()
