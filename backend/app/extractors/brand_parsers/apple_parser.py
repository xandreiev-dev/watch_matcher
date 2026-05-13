import re
from app.schemas.watch_features import WatchFeatures


class AppleParser:
    NOISE_WORDS = [
        "новые",
        "новый",
        "новая",
        "новое",
        "русский",
        "русский язык",
        "рф",
        "все цвета",
        "в наличии",
        "оригинал",
        "оригинальные",
        "ориг",
        "умные часы",
        "смарт часы",
        "смарт-часы",
        "часы",
    ]

    MATERIAL_PATTERNS = [
        (r"\bstainless steel\b", "stainless steel"),
        (r"\baluminium\b", "aluminum"),
        (r"\baluminum\b", "aluminum"),
        (r"\btitanium\b", "titanium"),
        (r"\btitanum\b", "titanium"),
        (r"\bceramic\b", "ceramic"),
    ]

    CONNECTIVITY_PATTERNS = [
        (r"\bcellular\b", "cellular"),
        (r"\blte\b", "cellular"),
        (r"\besim\b", "cellular"),
        (r"\bgps\s*\+\s*cellular\b", "cellular"),
        (r"\bgps\b", "gps"),
    ]

    @classmethod
    def parse(cls, features: WatchFeatures) -> WatchFeatures:
        text = features.normalized_title
        if not text:
            return features

        cleaned = cls.cleanup_text(text)

        if cls.is_multi_model(cleaned):
            features.is_multi_model = True
            return features

        family = cls.extract_family(cleaned)
        generation = cls.extract_generation(cleaned, family)
        variant = cls.extract_legacy_variant(cleaned)

        if family:
            features.family = family

        if generation:
            features.generation = generation

        if variant:
            features.variant = variant

        model_candidates = cls.build_model_candidates(family, generation)
        extracted_material = cls.extract_material(cleaned)
        extracted_connectivity = cls.extract_connectivity(cleaned)
        extracted_variant_name = cls.build_variant_name(
            family=family,
            generation=generation,
            size_mm=features.size_mm,
            material=extracted_material,
            connectivity=extracted_connectivity,
            legacy_variant=variant,
        )

        features.model_candidates = model_candidates
        features.extracted_material = extracted_material
        features.extracted_connectivity = extracted_connectivity
        features.extracted_variant_name = extracted_variant_name

        return features

    @classmethod
    def cleanup_text(cls, text: str) -> str:
        cleaned = text.lower().strip()
        cleaned = cleaned.replace("мм", "mm")
        cleaned = cleaned.replace("-", " ")
        cleaned = cleaned.replace("_", " ")
        cleaned = cleaned.replace(",", " ")
        cleaned = cleaned.replace("(", " ")
        cleaned = cleaned.replace(")", " ")
        cleaned = cleaned.replace("+", " ")

        for noise in cls.NOISE_WORDS:
            cleaned = re.sub(rf"\b{re.escape(noise)}\b", " ", cleaned)

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def is_multi_model(cls, text: str) -> bool:
        if not text:
            return False

        if re.search(r"\b(ultra|series|se)\b.*\/.*\b(ultra|series|se)\b", text):
            return True

        if re.search(r"\bseries\s+\d+\s*/\s*(series\s+)?\d+\b", text):
            return True

        if re.search(r"\bs\d+\s*/\s*s?\d+\b", text):
            return True

        if re.search(r"\bwatch\s+\d+\s*/\s*\d+\b", text):
            return True

        if re.search(r"\bultra\s+\d+\s*/\s*(ultra\s+)?\d+\b", text):
            return True

        if re.search(r"\bse\s+\d+\s*/\s*(se\s+)?\d+\b", text):
            return True

        sizes = re.findall(r"\b\d{2}mm\b", text)
        if len(set(sizes)) > 1:
            return True

        return False

    @classmethod
    def extract_family(cls, text: str) -> str | None:
        if re.search(r"\bultra\b", text):
            return "Ultra"

        if re.search(r"\bse\b", text):
            return "SE"

        if re.search(r"\bseries\b", text):
            return "Series"

        if re.search(r"\bs\d{1,2}\b", text):
            return "Series"

        # У Ozon встречается WatchS11 без пробела.
        if re.search(r"\bwatch\s*s?\s*\d{1,2}\b", text):
            return "Series"

        return None

    @classmethod
    def extract_generation(cls, text: str, family: str | None) -> str | None:
        if not family:
            return None

        if family == "Ultra":
            match = re.search(r"\bultra\s*(\d{1,2})\b", text)
            if match:
                return match.group(1)
            return None

        if family == "SE":
            match = re.search(r"\bse\s*(\d{1,2})\b", text)
            if match:
                return match.group(1)
            return None

        if family == "Series":
            match = re.search(r"\bseries\s*(\d{1,2})\b", text)
            if match:
                return match.group(1)

            match = re.search(r"\bs(\d{1,2})\b", text)
            if match:
                return match.group(1)

            match = re.search(r"\bwatch\s*s?\s*(\d{1,2})\b", text)
            if match:
                return match.group(1)

        return None

    @classmethod
    def extract_legacy_variant(cls, text: str) -> str | None:
        found: list[str] = []

        if re.search(r"\btitanium\b", text) or re.search(r"\btitanum\b", text):
            found.append("Titanium")

        if re.search(r"\bstainless steel\b", text):
            found.append("Stainless Steel")

        if re.search(r"\baluminium\b", text) or re.search(r"\baluminum\b", text):
            found.append("Aluminum")

        if re.search(r"\bceramic\b", text):
            found.append("Ceramic")

        if re.search(r"\bnike\b", text):
            found.append("Nike")

        if re.search(r"\bhermes\b", text):
            found.append("Hermes")

        if re.search(r"\bsport\b", text):
            found.append("Sport")

        unique = []
        for item in found:
            if item not in unique:
                unique.append(item)

        return " ".join(unique) if unique else None

    @classmethod
    def build_model_candidates(cls, family: str | None, generation: str | None) -> list[str]:
        if not family:
            return []

        candidates: list[str] = []

        if family == "Series" and generation:
            candidates.append(f"watch series {generation}")

        elif family == "Ultra":
            if generation:
                candidates.append(f"watch ultra {generation}")
            else:
                candidates.append("watch ultra")

        elif family == "SE":
            if generation:
                candidates.append(f"watch se {generation}")
            else:
                candidates.append("watch se")

        unique = []
        for item in candidates:
            if item not in unique:
                unique.append(item)

        return unique

    @classmethod
    def extract_material(cls, text: str) -> str | None:
        for pattern, value in cls.MATERIAL_PATTERNS:
            if re.search(pattern, text):
                return value
        return None

    @classmethod
    def extract_connectivity(cls, text: str) -> str | None:
        # сначала cellular/LTE, потом GPS
        for pattern, value in cls.CONNECTIVITY_PATTERNS:
            if re.search(pattern, text):
                return value
        return None

    @classmethod
    def build_variant_name(
        cls,
        family: str | None,
        generation: str | None,
        size_mm: int | None,
        material: str | None,
        connectivity: str | None,
        legacy_variant: str | None,
    ) -> str | None:
        parts: list[str] = []

        if family == "Series" and generation:
            parts.append(f"Watch Series {generation}")
        elif family == "Ultra":
            if generation:
                parts.append(f"Watch Ultra {generation}")
            else:
                parts.append("Watch Ultra")
        elif family == "SE":
            if generation:
                parts.append(f"Watch SE {generation}")
            else:
                parts.append("Watch SE")

        if size_mm:
            parts.append(f"{size_mm}mm")

        if material:
            if material == "aluminum":
                parts.append("Aluminum")
            elif material == "stainless steel":
                parts.append("Stainless Steel")
            elif material == "titanium":
                parts.append("Titanium")
            elif material == "ceramic":
                parts.append("Ceramic")

        if connectivity:
            if connectivity == "cellular":
                parts.append("Cellular")
            elif connectivity == "gps":
                parts.append("GPS")

        if legacy_variant:
            for chunk in legacy_variant.split():
                if chunk not in parts:
                    parts.append(chunk)

        result = " ".join(parts).strip()
        return result if result else None
