import re
from app.schemas.watch_features import WatchFeatures


class XiaomiParser:
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
        "xiaomi",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\bwatch\s*\d+\s*/\s*\d+\b",
        r"\bwatch\s*\d+\s*,\s*\d+\b",
        r"\bwatch\s+s\d+\s*/\s*s\d+\b",
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

        # watch2 -> watch 2, s2 -> s 2
        cleaned = re.sub(r"\bwatch(\d+)\b", r"watch \1", cleaned)
        cleaned = re.sub(r"\bs(\d+)\b", r"s \1", cleaned)
        cleaned = re.sub(r"\bh(\d+)\b", r"h \1", cleaned)

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

        # Mi Watch ...
        if re.search(r"\bmi\s+watch\b", text):
            family = "Mi"

            if re.search(r"\blite\b", text):
                found_variants.append("Lite")

            if re.search(r"\brevolve\b", text):
                found_variants.append("Revolve")

            if re.search(r"\bactive\b", text):
                found_variants.append("Active")

            if re.search(r"\bcolor\b", text):
                found_variants.append("Color")

            if re.search(r"\bsports?\b", text):
                found_variants.append("Sports")

        # Poco Watch
        elif re.search(r"\bpoco\s+watch\b", text):
            family = "Poco"

        # Redmi Watch ...
        elif re.search(r"\bredmi\s+watch\b", text):
            family = "Redmi"

            m = re.search(r"\bredmi\s+watch\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\blite\b", text):
                found_variants.append("Lite")

            if re.search(r"\bactive\b", text):
                found_variants.append("Active")

            if re.search(r"\besim\b", text):
                found_variants.append("eSIM")

            if re.search(r"\bmove\b", text):
                found_variants.append("Move")

        # Xiaomi Watch Color / Color 2
        elif re.search(r"\bwatch\s+color\b", text):
            family = "Watch"

            if re.search(r"\bcolor\s*2\b", text):
                generation = "Color 2"
            else:
                generation = "Color"

        # Xiaomi Watch H1 / H1 E
        elif re.search(r"\bwatch\s+h\b", text):
            family = "Watch"

            m = re.search(r"\bwatch\s+h\s*(\d+)\b", text)
            if m:
                generation = f"H{m.group(1)}"

            if re.search(r"\be\b", text):
                found_variants.append("E")

        # Xiaomi Watch S1 / S1 Active / S1 Pro / S2 / S3 / S4 / S4 Sport
        elif re.search(r"\bwatch\s+s\b", text):
            family = "Watch"

            m = re.search(r"\bwatch\s+s\s*(\d+)\b", text)
            if m:
                generation = f"S{m.group(1)}"

            if re.search(r"\bactive\b", text):
                found_variants.append("Active")

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

            if re.search(r"\bsport\b", text):
                found_variants.append("Sport")

        # Xiaomi Watch 2 / Watch 2 Pro / Watch 5
        elif re.search(r"\bwatch\s*\d+\b", text):
            family = "Watch"

            m = re.search(r"\bwatch\s*(\d+)\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

        # Просто Watch
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

        candidates = []

        # Mi
        if family == "Mi":
            if variant:
                if size_mm:
                    candidates.append(f"mi watch {variant.lower()} {int(size_mm)}mm")
                candidates.append(f"mi watch {variant.lower()}")
            candidates.append("mi watch")

        # Poco
        elif family == "Poco":
            candidates.append("poco watch")

        # Redmi
        elif family == "Redmi":
            if generation and variant:
                if size_mm:
                    candidates.append(f"redmi watch {generation} {variant.lower()} {int(size_mm)}mm")
                candidates.append(f"redmi watch {generation} {variant.lower()}")

            if generation:
                if size_mm:
                    candidates.append(f"redmi watch {generation} {int(size_mm)}mm")
                candidates.append(f"redmi watch {generation}")

            if variant and not generation:
                candidates.append(f"redmi watch {variant.lower()}")

            candidates.append("redmi watch")

        # Если деталей нет, оставляем общий Xiaomi Watch.
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

        if family == "Mi":
            parts = ["Mi Watch"]
        elif family == "Redmi":
            parts = ["Redmi Watch"]
        elif family == "Poco":
            parts = ["Poco Watch"]
        else:
            parts = ["Watch"]

        if generation:
            parts.append(str(generation))

        if variant:
            parts.append(variant)

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        return " ".join(parts).strip()
