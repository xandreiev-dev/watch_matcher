import re
from app.schemas.watch_features import WatchFeatures


class HonorParser:
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
        "honor",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\b\d{2}\s*mm\s*/\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*mm\s*,\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*/\s*\d{2}\s*mm\b",
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

        # Иногда MagicWatch пишут слитно.
        cleaned = re.sub(r"\bmagicwatch\b", "magic watch", cleaned)

        # Разделяем хвосты типа X5i и 5Pro, чтобы кандидат совпал с каталогом.
        cleaned = re.sub(r"\bx(\d+)(i)\b", r"x \1\2", cleaned)
        cleaned = re.sub(r"\b(\d+)(i)\b", r"\1\2", cleaned)
        cleaned = re.sub(r"\b(\d+)(pro|ultra)\b", r"\1 \2", cleaned)

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

        sizes = re.findall(r"\b(42|46|47)\s*mm\b", text)
        if len(set(sizes)) > 1:
            return True

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = None
        generation = None
        found_variants: list[str] = []

        # Choice Watch / Choice Watch 2 Pro / Choice Watch 2i
        if re.search(r"\bchoice\s+watch\b", text):
            family = "Choice"

            m = re.search(r"\bchoice\s+watch\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\b2i\b", text):
                generation = "2i"

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

        # Magic Watch 2
        elif re.search(r"\bmagic\s+watch\b", text):
            family = "MagicWatch"

            m = re.search(r"\bmagic\s+watch\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

        # Watch GS 3 / Watch GS 4 / Watch GS 5 / Watch GS Pro
        elif re.search(r"\bwatch\s+gs\b", text):
            family = "GS"

            m = re.search(r"\bwatch\s+gs\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

        # Watch Fit
        elif re.search(r"\bwatch\s+fit\b", text):
            family = "Fit"

        # Watch ES
        elif re.search(r"\bwatch\s+es\b", text):
            family = "ES"

        # Watch X5 / Watch X5i
        elif re.search(r"\bwatch\s+x\b", text) or re.search(r"\bwatch\s+x5i\b", text):
            family = "X"

            if re.search(r"\bx5i\b", text):
                generation = "5i"
            else:
                m = re.search(r"\bwatch\s+x\s*(\d+)\b", text)
                if m:
                    generation = m.group(1)
                else:
                    m2 = re.search(r"\bwatch\s+x(\d+)\b", text)
                    if m2:
                        generation = m2.group(1)

        # Watch 4 / Watch 4 Pro / Watch 5 / Watch 5 Pro / Watch 5 Ultra
        elif re.search(r"\bwatch\b", text):
            family = "Watch"

            m = re.search(r"\bwatch\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

            if re.search(r"\bultra\b", text):
                found_variants.append("Ultra")

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

        if family == "Choice":
            if generation and variant:
                candidates.append(f"choice watch {generation} {variant.lower()}")
            if generation:
                candidates.append(f"choice watch {generation}")
            candidates.append("choice watch")

        elif family == "MagicWatch":
            if generation and size_mm:
                candidates.append(f"magicwatch {generation} {int(size_mm)}mm")
                candidates.append(f"magic watch {generation} {int(size_mm)}mm")
            if generation:
                candidates.append(f"magicwatch {generation}")
                candidates.append(f"magic watch {generation}")
            candidates.append("magicwatch")
            candidates.append("magic watch")

        elif family == "Watch":
            if generation and variant:
                candidates.append(f"watch {generation} {variant.lower()}")
            if generation:
                candidates.append(f"watch {generation}")
            candidates.append("watch")

        elif family == "ES":
            candidates.append("watch es")

        elif family == "Fit":
            candidates.append("watch fit")

        elif family == "GS":
            if generation and variant:
                candidates.append(f"watch gs {generation} {variant.lower()}")
            if generation:
                candidates.append(f"watch gs {generation}")
            if variant and not generation:
                candidates.append(f"watch gs {variant.lower()}")
            candidates.append("watch gs")

        elif family == "X":
            if generation and size_mm:
                candidates.append(f"watch x{generation} {int(size_mm)}mm")
                candidates.append(f"watch x {generation} {int(size_mm)}mm")
            if generation:
                candidates.append(f"watch x{generation}")
                candidates.append(f"watch x {generation}")
            candidates.append("watch x")

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

        if family == "Choice":
            parts = ["Choice Watch"]
        elif family == "MagicWatch":
            parts = ["MagicWatch"]
        elif family == "GS":
            parts = ["Watch GS"]
        elif family == "ES":
            parts = ["Watch ES"]
        elif family == "Fit":
            parts = ["Watch Fit"]
        elif family == "X":
            parts = ["Watch X"]
        else:
            parts = ["Watch"]

        if generation:
            parts.append(str(generation))

        if variant:
            parts.append(variant)

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        return " ".join(parts).strip()
