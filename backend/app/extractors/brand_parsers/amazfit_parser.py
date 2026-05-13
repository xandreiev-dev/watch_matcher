import re
from app.schemas.watch_features import WatchFeatures


class AmazfitParser:
    NOISE_WORDS = [
        "новые",
        "новый",
        "русский",
        "русский язык",
        "рф",
        "ростест",
        "рст",
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
        "smart watch",
        "smartwatch",
        "smart",
        "watch",
        "amazfit",
        "фирмы",
        "женские",
        "модель",
        "premium",
        "new",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\b\d{2}\s*mm\s*[,/]\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*mm\s+and\s+\d{2}\s*mm\b",
        r"\b\d{2}\s*/\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*,\s*\d{2}\b",
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
            raw_text=cleaned,
        )
        if model_candidates:
            features.model_candidates = model_candidates

        variant_name = cls.build_variant_name(
            family=parsed["family"],
            generation=parsed["generation"],
            variant=parsed["variant"],
            size_mm=features.size_mm,
            raw_text=cleaned,
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
        cleaned = cleaned.replace("+", " ")
        cleaned = cleaned.replace(",", " ")
        cleaned = cleaned.replace("/", " ")
        cleaned = cleaned.replace("(", " ")
        cleaned = cleaned.replace(")", " ")
        cleaned = cleaned.replace(":", " ")
        cleaned = cleaned.replace("  ", " ")

        # gtr3 -> gtr 3, gts2 -> gts 2, bip3 -> bip 3
        cleaned = re.sub(r"\b(gtr|gts|bip|pop|active|balance|falcon|cheetah|stratos|verge)(\d+)\b", r"\1 \2", cleaned)

        # T-Rex часто приезжает слитно, приводим к одному виду.
        cleaned = re.sub(r"\bt[\s\-]*rex\b", "t rex", cleaned)

        for noise in cls.NOISE_WORDS:
            cleaned = re.sub(rf"\b{re.escape(noise)}\b", " ", cleaned)

        cleaned = re.sub(r"\ba\d{3,5}\b", " ", cleaned)  # a1914 / a2211 / a2323
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def is_multi_model(cls, text: str) -> bool:
        if not text:
            return False

        for pattern in cls.MULTI_MODEL_PATTERNS:
            if re.search(pattern, text):
                return True

        sizes = re.findall(r"\b(42|44|45|46|47|48|49)\s*mm\b", text)
        if len(set(sizes)) > 1:
            return True

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = None
        generation = None
        found_variants: list[str] = []

        # Active / Active 2 / Active 2 Square / Active Edge
        if re.search(r"\bactive\b", text):
            family = "Active"

            m = re.search(r"\bactive\s*(\d{1,2})\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bsquare\b", text):
                found_variants.append("Square")

            if re.search(r"\bedge\b", text):
                found_variants.append("Edge")

        # Balance / Balance 2
        elif re.search(r"\bbalance\b", text):
            family = "Balance"

            m = re.search(r"\bbalance\s*(\d{1,2})\b", text)
            if m:
                generation = m.group(1)

        # Bip / Bip 3 / Bip 6 / Bip U Pro / Bip S
        elif re.search(r"\bbip\b", text):
            family = "Bip"

            m = re.search(r"\bbip\s*(\d{1,2})\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bu\b", text):
                found_variants.append("U")

            if re.search(r"\bs\b", text):
                found_variants.append("S")

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

        # Cheetah / Cheetah Pro / Cheetah Square / Cheetah Round
        elif re.search(r"\bcheetah\b", text):
            family = "Cheetah"

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

            if re.search(r"\bsquare\b", text):
                found_variants.append("Square")

            if re.search(r"\bround\b", text):
                found_variants.append("Round")

        # Falcon
        elif re.search(r"\bfalcon\b", text):
            family = "Falcon"

        # GTR / GTR 2 / GTR 3 / GTR 4 / GTR Mini
        elif re.search(r"\bgtr\b", text):
            family = "GTR"

            m = re.search(r"\bgtr\s*(\d{1,2})\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\blimited edition\b", text):
                found_variants.append("Limited Edition")

            if re.search(r"\bmini\b", text):
                found_variants.append("Mini")

        # GTS / GTS 2 / GTS 3 / GTS 4 / GTS 4 Mini
        elif re.search(r"\bgts\b", text):
            family = "GTS"

            m = re.search(r"\bgts\s*(\d{1,2})\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bmini\b", text):
                found_variants.append("Mini")

        # Pop / Pop 3S
        elif re.search(r"\bpop\b", text):
            family = "Pop"

            m = re.search(r"\bpop\s*(\d{1,2})\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\b3s\b", text):
                generation = "3"
                found_variants.append("S")

        # T-Rex / T-Rex 3 / T-Rex 3 Pro / T-Rex Ultra
        elif re.search(r"\bt rex\b", text):
            family = "T-Rex"

            m = re.search(r"\bt rex\s*(\d{1,2})\b", text)
            if m:
                generation = m.group(1)

            if re.search(r"\bpro\b", text):
                found_variants.append("Pro")

            if re.search(r"\bultra\b", text):
                found_variants.append("Ultra")

        # Verge
        elif re.search(r"\bverge\b", text):
            family = "Verge"

        # Stratos
        elif re.search(r"\bstratos\b", text):
            family = "Stratos"

        unique_variants = []
        for item in found_variants:
            if item not in unique_variants:
                unique_variants.append(item)

        variant = " ".join(unique_variants) if unique_variants else None

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
        raw_text: str,
    ) -> list[str]:
        candidates: list[str] = []

        if not family:
            return []

        if family == "Active":
            if generation and variant:
                candidates.append(f"active {generation} {variant.lower()}")
            if generation:
                candidates.append(f"active {generation}")
            if variant and not generation:
                candidates.append(f"active {variant.lower()}")
            candidates.append("active")

        elif family == "Balance":
            if generation:
                candidates.append(f"balance {generation}")
            candidates.append("balance")

        elif family == "Bip":
            if generation and variant:
                candidates.append(f"bip {generation} {variant.lower()}")
            if generation:
                candidates.append(f"bip {generation}")
            if variant and not generation:
                candidates.append(f"bip {variant.lower()}")
            candidates.append("bip")

        elif family == "Cheetah":
            if variant:
                candidates.append(f"cheetah {variant.lower()}")
            candidates.append("cheetah")

        elif family == "Falcon":
            candidates.append("falcon")

        elif family == "GTR":
            if generation and variant:
                candidates.append(f"gtr {generation} {variant.lower()}")
            if generation:
                candidates.append(f"gtr {generation}")
            if variant and not generation:
                candidates.append(f"gtr {variant.lower()}")
            candidates.append("gtr")

        elif family == "GTS":
            if generation and variant:
                candidates.append(f"gts {generation} {variant.lower()}")
            if generation:
                candidates.append(f"gts {generation}")
            if variant and not generation:
                candidates.append(f"gts {variant.lower()}")
            candidates.append("gts")

        elif family == "Pop":
            if generation and variant:
                candidates.append(f"pop {generation}{variant.lower()}")
                candidates.append(f"pop {generation} {variant.lower()}")
            if generation:
                candidates.append(f"pop {generation}")
            candidates.append("pop")

        elif family == "T-Rex":
            if generation and variant:
                candidates.append(f"t rex {generation} {variant.lower()}")
                candidates.append(f"t-rex {generation} {variant.lower()}")
            if generation:
                candidates.append(f"t rex {generation}")
                candidates.append(f"t-rex {generation}")
            if variant and not generation:
                candidates.append(f"t rex {variant.lower()}")
                candidates.append(f"t-rex {variant.lower()}")
            candidates.append("t rex")
            candidates.append("t-rex")

        elif family == "Verge":
            candidates.append("verge")

        elif family == "Stratos":
            candidates.append("stratos")

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
        raw_text: str,
    ) -> str | None:
        parts: list[str] = []

        if family:
            parts.append(family)

        if generation:
            parts.append(str(generation))

        if variant:
            parts.append(variant)

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        result = " ".join(parts).strip()
        return result if result else None
