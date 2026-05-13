import re
from app.schemas.watch_features import WatchFeatures


class GarminParser:
    FAMILIES = [
        "forerunner",
        "fenix",
        "enduro",
        "epix",
        "instinct",
        "venu",
        "vivoactive",
        "vivomove",
        "vivosmart",
        "tactix",
        "marq",
        "descent",
        "quatix",
        "approach",
        "lily",
        "swim",
        "d2",
    ]

    FAMILY_DISPLAY = {
        "forerunner": "Forerunner",
        "fenix": "Fenix",
        "enduro": "Enduro",
        "epix": "Epix",
        "instinct": "Instinct",
        "venu": "Venu",
        "vivoactive": "Vivoactive",
        "vivomove": "Vivomove",
        "vivosmart": "Vivosmart",
        "tactix": "Tactix",
        "marq": "Marq",
        "descent": "Descent",
        "quatix": "Quatix",
        "approach": "Approach",
        "lily": "Lily",
        "swim": "Swim",
        "d2": "D2",
    }

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
        "smart watch",
        "smartwatch",
        "garmin",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\b\d{2}\s*mm\s*/\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*mm\s*,\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*/\s*\d{2}\s*mm\b",
        r"\b[a-z]?\d+[a-z]?\s*/\s*[a-z]?\d+[a-z]?\b",
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
            features.family = cls.FAMILY_DISPLAY.get(parsed["family"], parsed["family"].title())

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

        for noise in cls.NOISE_WORDS:
            cleaned = re.sub(rf"\b{re.escape(noise)}\b", " ", cleaned)

        # mk3i / mk2s / 255s / 265s не трогаем
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def is_multi_model(cls, text: str) -> bool:
        if not text:
            return False

        for pattern in cls.MULTI_MODEL_PATTERNS:
            if re.search(pattern, text):
                return True

        size_hits = re.findall(r"\b\d{2}\s*mm\b", text)
        if len(set(size_hits)) > 1:
            return True

        # forerunner 970 / 570
        if re.search(r"/", text):
            family_hits = [
                family for family in cls.FAMILIES
                if re.search(rf"\b{re.escape(family)}\b", text)
            ]
            if len(set(family_hits)) > 1:
                return True

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = cls.extract_family(text)
        generation = cls.extract_generation(text, family)
        variant = cls.extract_variant(text, family, generation)

        return {
            "family": family,
            "generation": generation,
            "variant": variant,
        }

    @classmethod
    def extract_family(cls, text: str) -> str | None:
        for family in cls.FAMILIES:
            if re.search(rf"\b{re.escape(family)}\b", text):
                return family
        return None

    @classmethod
    def extract_generation(cls, text: str, family: str | None) -> str | None:
        if not family:
            return None

        if family == "marq":
            m = re.search(r"\bmarq\s+(adventurer|athlete|aviator|captain|commander|golfer)\b", text)
            if m:
                role = m.group(1).title()
                gen = None
                g = re.search(r"\bgen\s*(\d+)\b", text)
                if g:
                    gen = f"Gen {g.group(1)}"
                return f"{role} {gen}".strip() if gen else role

        if family == "d2":
            m = re.search(r"\bd2\s+(air\s*x10|mach\s*1(?:\s*pro)?)\b", text)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).title()

        if family == "descent":
            m = re.search(r"\bdescent\s+(mk\d+i?|g\d|x\d+i?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "approach":
            m = re.search(r"\bapproach\s+([sgx]?\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "quatix":
            m = re.search(r"\bquatix\s+(\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "tactix":
            m = re.search(r"\btactix\s+(\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "fenix":
            # Отдельный короткий кейс для Fenix E.
            if re.search(r"\bfenix\s+e\b", text):
                return "E"

            m = re.search(r"\bfenix\s+(\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "epix":
            if re.search(r"\bgen\s*2\b", text):
                return "Gen 2"

        if family == "instinct":
            if re.search(r"\bcrossover\b", text):
                return "Crossover"
            if re.search(r"\be\b", text):
                return "E"
            m = re.search(r"\binstinct\s+(\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "forerunner":
            m = re.search(r"\bforerunner\s+(\d+[a-z]*|x1)\b", text)
            if m:
                return m.group(1).upper()

        if family == "venu":
            if re.search(r"\bvenu\s+sq\b", text):
                return "SQ"
            if re.search(r"\bvenu\s+x1\b", text):
                return "X1"
            m = re.search(r"\bvenu\s+(\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "vivoactive":
            m = re.search(r"\bvivoactive\s+(\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "vivomove":
            m = re.search(r"\bvivomove\s+(hr|luxe|sport|style|trend)\b", text)
            if m:
                return m.group(1).title()

        if family == "vivosmart":
            m = re.search(r"\bvivosmart\s+(\d+[a-z]?)\b", text)
            if m:
                return m.group(1).upper()

        if family == "lily":
            m = re.search(r"\blily\s+(\d+)\b", text)
            if m:
                return m.group(1)

        if family == "swim":
            m = re.search(r"\bswim\s+(\d+)\b", text)
            if m:
                return m.group(1)

        if family == "enduro":
            m = re.search(r"\benduro\s+(\d+)\b", text)
            if m:
                return m.group(1)

        return None

    @classmethod
    def extract_variant(cls, text: str, family: str | None, generation: str | None) -> str | None:
        found: list[str] = []

        if re.search(r"\bsapphire\s+solar\b", text):
            found.append("Sapphire Solar")
            text = re.sub(r"\bsapphire\s+solar\b", " ", text)

        if re.search(r"\bamoled\s+sapphire\b", text):
            found.append("AMOLED Sapphire")
            text = re.sub(r"\bamoled\s+sapphire\b", " ", text)

        if re.search(r"\bsolar\b", text):
            found.append("Solar")

        if re.search(r"\bsapphire\b", text):
            found.append("Sapphire")

        if re.search(r"\bamoled\b", text):
            found.append("AMOLED")

        if re.search(r"\bpro\b", text):
            found.append("Pro")

        if re.search(r"\bmusic\b", text):
            found.append("Music")

        if re.search(r"\bballistics\b", text):
            found.append("Ballistics")

        if re.search(r"\btactical\b", text):
            found.append("Tactical")

        if re.search(r"\bclassic\b", text):
            found.append("Classic")

        if re.search(r"\bactive\b", text) and family == "lily":
            found.append("Active")

        if re.search(r"\bsport\b", text) and family in {"lily", "vivomove"}:
            found.append("Sport")

        unique = []
        for item in found:
            if item not in unique:
                unique.append(item)

        return " ".join(unique) if unique else None

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

        family_text = family.lower()
        candidates: list[str] = []

        if family == "marq":
            if generation:
                candidates.append(f"marq {generation.lower()}")
                # Если поколение не вытащили, пробуем общий вариант.
                gen_less = re.sub(r"\s+gen\s+\d+", "", generation.lower())
                if gen_less != generation.lower():
                    candidates.append(f"marq {gen_less}")

        elif family == "d2":
            if generation:
                candidates.append(f"d2 {generation.lower()}")

        elif family in {"descent", "approach", "quatix", "tactix", "forerunner", "vivoactive", "vivosmart", "swim", "enduro"}:
            if generation and variant:
                candidates.append(f"{family_text} {generation.lower()} {variant.lower()}")
            if generation:
                candidates.append(f"{family_text} {generation.lower()}")
            if variant and not generation:
                candidates.append(f"{family_text} {variant.lower()}")
            candidates.append(family_text)

        elif family == "fenix":
            if generation == "E":
                candidates.append("fenix e")
            else:
                if generation and variant:
                    candidates.append(f"fenix {generation.lower()} {variant.lower()}")
                if generation:
                    candidates.append(f"fenix {generation.lower()}")
                if variant and not generation:
                    candidates.append(f"fenix {variant.lower()}")
            candidates.append("fenix")

        elif family == "epix":
            if generation == "Gen 2":
                if variant:
                    candidates.append(f"epix gen 2 {variant.lower()}")
                candidates.append("epix gen 2")
            if variant and generation != "Gen 2":
                candidates.append(f"epix {variant.lower()}")
            candidates.append("epix")

        elif family == "instinct":
            if generation == "Crossover":
                if variant:
                    candidates.append(f"instinct crossover {variant.lower()}")
                candidates.append("instinct crossover")
            elif generation == "E":
                candidates.append("instinct e")
            else:
                if generation and variant:
                    candidates.append(f"instinct {generation.lower()} {variant.lower()}")
                if generation:
                    candidates.append(f"instinct {generation.lower()}")
            if variant and generation not in {"Crossover", "E"} and not generation:
                candidates.append(f"instinct {variant.lower()}")
            candidates.append("instinct")

        elif family == "venu":
            if generation == "SQ":
                if variant:
                    candidates.append(f"venu sq {variant.lower()}")
                candidates.append("venu sq 2" if "2" in (variant or "") else "venu sq")
                candidates.append("venu sq")
            elif generation == "X1":
                candidates.append("venu x1")
            else:
                if generation and variant:
                    candidates.append(f"venu {generation.lower()} {variant.lower()}")
                if generation:
                    candidates.append(f"venu {generation.lower()}")
            candidates.append("venu")

        elif family == "vivomove":
            if generation:
                candidates.append(f"vivomove {generation.lower()}")
            candidates.append("vivomove")

        elif family == "lily":
            if generation and variant:
                candidates.append(f"lily {generation.lower()} {variant.lower()}")
            if generation:
                candidates.append(f"lily {generation.lower()}")
            if variant and not generation:
                candidates.append(f"lily {variant.lower()}")
            candidates.append("lily")

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

        parts: list[str] = [cls.FAMILY_DISPLAY.get(family, family.title())]

        if generation:
            parts.append(generation)

        if variant:
            parts.append(variant)

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        return " ".join(parts).strip() if parts else None
