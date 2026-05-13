import re
from app.schemas.watch_features import WatchFeatures


class SamsungParser:
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
        "часы",
        "smart watch",
        "smartwatch",
        "galaxy",
        "samsung",
    ]

    MULTI_MODEL_PATTERNS = [
        r"\b\d{2}\s*mm\s*[,/]\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*mm\s+and\s+\d{2}\s*mm\b",
        r"\b\d{2}\s*/\s*\d{2}\s*mm\b",
        r"\b\d{2}\s*,\s*\d{2}\b",
        r"\b40mm\s*[,/]\s*44mm\b",
        r"\b42mm\s*[,/]\s*46mm\b",
        r"\b43mm\s*[,/]\s*47mm\b",
        r"\b40\s*[,/]\s*44\s*mm\b",
        r"\b42\s*[,/]\s*46\s*mm\b",
        r"\b43\s*[,/]\s*47\s*mm\b",
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

        material = cls.extract_material(cleaned)
        if material:
            features.extracted_material = material

        connectivity = cls.extract_connectivity(cleaned)
        if connectivity:
            features.extracted_connectivity = connectivity

        variant_name = cls.build_variant_name(
            family=parsed["family"],
            generation=parsed["generation"],
            variant=parsed["variant"],
            size_mm=features.size_mm,
            material=material,
            connectivity=connectivity,
        )
        if variant_name:
            features.extracted_variant_name = variant_name

        return features

    @classmethod
    def cleanup_text(cls, text: str) -> str:
        cleaned = text.lower().strip()
        cleaned = cleaned.replace("мм", "mm")
        cleaned = cleaned.replace("-", " ")
        cleaned = cleaned.replace("+", " ")
        cleaned = cleaned.replace("wi fi", "wifi")
        cleaned = cleaned.replace("wi-fi", "wifi")
        cleaned = cleaned.replace("4g", "lte")
        cleaned = cleaned.replace("3g", "lte")

        for noise in cls.NOISE_WORDS:
            cleaned = re.sub(rf"\b{re.escape(noise)}\b", " ", cleaned)

        cleaned = re.sub(r"[()]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def is_multi_model(cls, text: str) -> bool:
        if not text:
            return False

        for pattern in cls.MULTI_MODEL_PATTERNS:
            if re.search(pattern, text):
                return True

        # Примеры: "watch 8 40mm 44mm", "watch8 40 44"
        sizes = re.findall(r"\b(40|41|42|43|44|45|46|47)\s*mm\b", text)
        if len(set(sizes)) > 1:
            return True

        # Если в тексте явно несколько поколений
        generations = re.findall(r"\bwatch\s*(\d{1,2})\b", text)
        if len(set(generations)) > 1:
            return True

        connectivity = {
            "lte" if value == "cellular" else value
            for value in re.findall(r"\b(wifi|lte|cellular)\b", text)
        }
        if len(connectivity) > 1:
            return True

        return False

    @classmethod
    def extract_model_fields(cls, text: str) -> dict:
        family = None
        generation = None
        variants: list[str] = []

        # ---- FAMILY + GENERATION ----
        # Fit3 / Fit 3
        fit_match = re.search(r"\bfit\s*(\d{1,2})\b", text)
        if fit_match:
            family = "Fit"
            generation = fit_match.group(1)

        # Active2 / Active 2 / Active
        elif re.search(r"\bactive\b", text):
            family = "Active"
            active_match = re.search(r"\bactive\s*(\d{1,2})\b", text)
            if active_match:
                generation = active_match.group(1)


        # Gear
        elif re.search(r"\bgear\b", text):
            family = "Gear"

            # Gear S2 / Gear S3
            gear_s_match = re.search(r"\bgear\s+(s\d)\b", text)
            if gear_s_match:
                generation = gear_s_match.group(1).upper()

            # Gear 2 Neo
            elif re.search(r"\bgear\s+2\s+neo\b", text):
                generation = "2"
                variants.append("Neo")

            # Gear Live
            elif re.search(r"\bgear\s+live\b", text):
                variants.append("Live")

            # Gear Sport
            elif re.search(r"\bgear\s+sport\b", text):
                variants.append("Sport")


        # Watch8 / Watch 8 / Watch FE / Watch Ultra / Watch Classic
        elif re.search(r"\bwatch\b", text) or re.search(r"\bwatch\d+\b", text):
            family = "Watch"

            watch_match = re.search(r"\bwatch\s*(\d{1,2})\b", text)
            if watch_match:
                generation = watch_match.group(1)
            else:
                watch_compact_match = re.search(r"\bwatch(\d{1,2})\b", text)
                if watch_compact_match:
                    generation = watch_compact_match.group(1)

        # ---- VARIANTS ----
        if re.search(r"\bultra(?:\b|\d)", text):
            variants.append("Ultra")

        if re.search(r"\bclassic\b", text):
            variants.append("Classic")

        if re.search(r"\bpro\b", text):
            variants.append("Pro")

        if re.search(r"\bfe\b", text):
            variants.append("FE")

        if re.search(r"\bfrontier\b", text):
            variants.append("Frontier")

        if re.search(r"\bsport\b", text):
            variants.append("Sport")

        # Neo только для Gear 2 Neo и подобных
        if re.search(r"\bneo\b", text):
            variants.append("Neo")

        # Live только для Gear Live
        if re.search(r"\blive\b", text):
            variants.append("Live")

        variant = cls.unique_join(variants)

        return {
            "family": family,
            "generation": generation,
            "variant": variant,
        }

    @classmethod
    def extract_material(cls, text: str) -> str | None:
        if re.search(r"\btitanium\b", text):
            return "titanium"

        if re.search(r"\baluminum\b", text) or re.search(r"\baluminium\b", text):
            return "aluminum"

        if re.search(r"\bstainless steel\b", text):
            return "stainless steel"

        return None

    @classmethod
    def extract_connectivity(cls, text: str) -> str | None:
        if re.search(r"\blte\b", text) or re.search(r"\bcellular\b", text) or re.search(r"\bсотов", text):
            return "lte"

        if re.search(r"\bbluetooth\b", text):
            return "bluetooth"

        if re.search(r"\bgps\b", text):
            return "gps"

        if re.search(r"\bwifi\b", text):
            return "wifi"

        return None

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

        if family == "Watch":
            if variant and not generation:
                candidates.append(f"galaxy watch {variant.lower()}")
                candidates.append(f"watch {variant.lower()}")

            if generation and not variant:
                candidates.append(f"galaxy watch {generation}")
                candidates.append(f"galaxy watch{generation}")
                candidates.append(f"watch {generation}")
                candidates.append(f"watch{generation}")

            if generation and variant:
                candidates.append(f"galaxy watch {generation} {variant.lower()}")
                candidates.append(f"galaxy watch{generation} {variant.lower()}")
                candidates.append(f"watch {generation} {variant.lower()}")
                candidates.append(f"watch{generation} {variant.lower()}")

                if "Ultra" in variant:
                    # Ultra must not silently degrade to a regular Galaxy Watch generation.
                    candidates.append("galaxy watch ultra")
                    candidates.append("watch ultra")
                else:
                    candidates.append(f"galaxy watch {generation}")
                    candidates.append(f"galaxy watch{generation}")
                    candidates.append(f"watch {generation}")
                    candidates.append(f"watch{generation}")

            if not generation and not variant:
                candidates.append("galaxy watch")
                candidates.append("watch")

        elif family == "Active":
            if generation and variant:
                candidates.append(f"galaxy watch active {generation} {variant.lower()}")
                candidates.append(f"galaxy watch active{generation} {variant.lower()}")
                candidates.append(f"watch active {generation} {variant.lower()}")
                candidates.append(f"watch active{generation} {variant.lower()}")

            if generation:
                candidates.append(f"galaxy watch active {generation}")
                candidates.append(f"galaxy watch active{generation}")
                candidates.append(f"watch active {generation}")
                candidates.append(f"watch active{generation}")

            candidates.append("galaxy watch active")
            candidates.append("watch active")

        elif family == "Fit":
            if generation and variant:
                candidates.append(f"galaxy fit {generation} {variant.lower()}")
                candidates.append(f"galaxy fit{generation} {variant.lower()}")
                candidates.append(f"fit {generation} {variant.lower()}")
                candidates.append(f"fit{generation} {variant.lower()}")

            if generation:
                candidates.append(f"galaxy fit {generation}")
                candidates.append(f"galaxy fit{generation}")
                candidates.append(f"fit {generation}")
                candidates.append(f"fit{generation}")

            candidates.append("galaxy fit")
            candidates.append("fit")

        elif family == "Gear":
            gen = generation.lower() if generation else None
            var = variant.lower() if variant else None

            if gen and var:
                candidates.append(f"gear {gen} {var}")

            if gen:
                candidates.append(f"gear {gen}")

            if var:
                candidates.append(f"gear {var}")

            candidates.append("gear")

        result: list[str] = []
        seen = set()

        for item in candidates:
            item = re.sub(r"\s+", " ", item).strip().lower()
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
        material: str | None,
        connectivity: str | None,
    ) -> str | None:
        parts: list[str] = []

        if family == "Watch":
            parts.append("Watch")
        elif family == "Active":
            parts.append("Watch Active")
        elif family == "Fit":
            parts.append("Fit")
        elif family == "Gear":
            parts.append("Gear")
        elif family:
            parts.append(family)

        if generation:
            # Active2 часто без пробела в БД
            if family == "Active":
                if parts:
                    parts[-1] = f"{parts[-1]}{generation}"
            else:
                parts.append(generation)

        if variant:
            parts.append(variant)

        if size_mm:
            parts.append(f"{int(size_mm)}mm")

        if material:
            pretty_material = {
                "titanium": "Titanium",
                "aluminum": "Aluminum",
                "stainless steel": "Stainless Steel",
            }.get(material, material.title())
            parts.append(pretty_material)

        if connectivity:
            pretty_connectivity = {
                "lte": "LTE",
                "wifi": "WiFi",
                "gps": "GPS",
                "bluetooth": "Bluetooth",
            }.get(connectivity, connectivity.upper())
            parts.append(pretty_connectivity)

        result = " ".join(parts).strip()
        return result if result else None

    @classmethod
    def unique_join(cls, items: list[str]) -> str | None:
        unique: list[str] = []
        for item in items:
            if item not in unique:
                unique.append(item)
        return " ".join(unique) if unique else None
