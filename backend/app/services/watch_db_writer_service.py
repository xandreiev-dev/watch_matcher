import re
from datetime import date
from typing import Optional

import pandas as pd

from app.core.db import get_db_connection
from app.core.logging_config import get_logger

logger = get_logger("db_writer")

MAX_WARRANTY_YEARS = 5
MAX_WARRANTY_MONTHS = MAX_WARRANTY_YEARS * 12
MAX_WARRANTY_DAYS = MAX_WARRANTY_YEARS * 365


SHOP_NAMES = {
    1: "Озон",
    2: "Авито",
    3: "WB",
    4: "Яндекс",
    5: "Али",
}


def is_missing_value(value: object) -> bool:
    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def generate_insert_on_duplicate(table_name: str, columns: list[str]) -> str:
    columns_str = ", ".join(columns)
    placeholders = ", ".join([f"%({col})s" for col in columns])
    update_str = ", ".join([f"{col} = VALUES({col})" for col in columns])

    query = f"""
    INSERT INTO {table_name}
    ({columns_str})
    VALUES
    ({placeholders})
    ON DUPLICATE KEY UPDATE
    {update_str}
    """
    return query.strip()


def bulk_insert(query: str, records: list[dict]) -> None:
    if not records:
        return

    cleaned_records = []
    for record in records:
        cleaned = {}
        for key, value in record.items():
            if is_missing_value(value):
                cleaned[key] = None
            else:
                cleaned[key] = value
        cleaned_records.append(cleaned)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.executemany(query, cleaned_records)
        conn.commit()
    finally:
        conn.close()


def select_df(query: str) -> pd.DataFrame:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
        return pd.DataFrame(rows)
    finally:
        conn.close()


class WatchDbWriterService:
    @classmethod
    def validate_input_columns(cls, df_res: pd.DataFrame) -> None:
        required_columns = [
            "Бренд",
            "article",
            "URL",
            "image_url",
            "price",
            "match_status",
            "matched_model_name",
            "size_mm",
        ]

        missing = [col for col in required_columns if col not in df_res.columns]
        if missing:
            raise ValueError(
                f"Для записи в БД не хватает обязательных колонок: {missing}"
            )
        
    @classmethod
    def normalize_brand(cls, brand: str | None) -> str | None:
        if not brand:
            return None
        return str(brand).strip()

    @classmethod
    def normalize_model_for_db(cls, model_name: str | None) -> str | None:
        """
        Храним model без пробелов, как просил Дмитрий.
        Пример:
        Galaxy Watch5 Pro -> galaxywatch5pro
        Watch GT 5 Pro -> watchgt5pro
        """
        if not model_name:
            return None

        value = str(model_name).strip().lower()
        value = value.replace("ё", "е")
        value = value.replace("+", "plus")
        value = re.sub(r"[\s\-/_,()]+", "", value)
        value = re.sub(r"[^a-z0-9]", "", value)

        return value or None

    @classmethod
    def normalize_size(cls, size_mm: object) -> int:
        """
        В БД size хранится числом:
        46, 41, 51
        если размер отсутствует -> 0
        """
        if pd.isna(size_mm) or size_mm is None or size_mm == "":
            return 0

        try:
            return int(size_mm)
        except Exception:
            return 0

    @classmethod
    def extract_review_number(cls, value: object) -> Optional[int]:
        if pd.isna(value) or value is None:
            return None

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)

        digits = re.sub(r"[^\d]", "", str(value))
        if not digits:
            return None

        try:
            return int(digits)
        except Exception:
            return None

    @classmethod
    def convert_warranty_to_days(cls, value: object) -> Optional[int]:
        if is_missing_value(value):
            return None

        text = str(value).lower().strip()
        if not text:
            return None

        text = text.replace("ё", "е")

        # Store only explicit warranty durations in days; mentions without a term stay NULL.
        match = re.search(
            r"(\d+)\s*"
            r"(дн(?:ей|я)?|день|дня|дней|days?|"
            r"мес(?:яц(?:ев|а)?)?|months?|"
            r"год|года|лет|years?)",
            text,
        )
        if match:
            num = int(match.group(1))
            unit = match.group(2)

            if num <= 0:
                return None

            if unit.startswith("дн") or unit in {"день", "дня", "дней"} or "day" in unit:
                return num if num <= MAX_WARRANTY_DAYS else None
            if unit.startswith("мес") or "month" in unit:
                return num * 30 if num <= MAX_WARRANTY_MONTHS else None
            if unit.startswith("год") or unit == "лет" or "year" in unit:
                return num * 365 if num <= MAX_WARRANTY_YEARS else None

        return None

    @classmethod
    def convert_days_to_delivery(cls, value: object) -> Optional[int]:
        if pd.isna(value) or value is None:
            return None

        text = str(value).strip()
        match = re.search(r"(\d+)", text)
        if not match:
            return None

        try:
            return int(match.group(1))
        except Exception:
            return None

    @classmethod
    def clean_color(cls, value: object) -> Optional[str]:
        if pd.isna(value) or value is None:
            return None

        text = str(value).strip()
        if not text or text == "—":
            return None

        return text[:40]

    @classmethod
    def normalize_is_global(cls, value: object) -> str:
        if is_missing_value(value):
            return "N"

        text = str(value).strip().lower()
        if text in {"y", "yes", "true", "1", "да", "global", "глобальная", "глобальный"}:
            return "Y"

        return "N"

    @classmethod
    def prepare_matched_rows(cls, df_res: pd.DataFrame) -> pd.DataFrame:
        df = df_res.copy()
        start_count = len(df)

        df = df[df["match_status"] == "matched"].copy()
        after_match_status = len(df)
        df = df[df["matched_model_name"].notna()].copy()
        after_model_name = len(df)
        df = df[df["Бренд"].notna()].copy()
        after_brand = len(df)
        df = df[df["article"].notna()].copy()
        after_article = len(df)
        df = df[df["URL"].notna()].copy()
        after_url = len(df)
        df = df[df["price"].notna()].copy()
        after_price_present = len(df)

        df["brand"] = df["Бренд"].apply(cls.normalize_brand)
        df["model"] = df["matched_model_name"].apply(cls.normalize_model_for_db)
        df["size"] = df["size_mm"].apply(cls.normalize_size)

        df["product_url"] = df["URL"].astype(str).str.strip()
        df["image_url"] = df["image_url"]
        df["article"] = df["article"].astype(str).str.strip()

        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df["rating"] = None

        if "shop_rating" in df.columns:
            df["shop_rating"] = pd.to_numeric(df["shop_rating"], errors="coerce")
        else:
            df["shop_rating"] = None

        if "review" in df.columns:
            df["review"] = df["review"].apply(cls.extract_review_number)
        else:
            df["review"] = None

        if "Гарантия" in df.columns:
            df["warranty_period"] = df["Гарантия"].apply(cls.convert_warranty_to_days)
        else:
            df["warranty_period"] = None

        if "days_to_delivery" in df.columns:
            df["days_to_delivery"] = df["days_to_delivery"].apply(cls.convert_days_to_delivery)
        else:
            df["days_to_delivery"] = None

        if "Цвет" in df.columns:
            df["color"] = df["Цвет"].apply(cls.clean_color)
        else:
            df["color"] = None

        if "is_global" in df.columns:
            df["is_global"] = df["is_global"].apply(cls.normalize_is_global)
        else:
            df["is_global"] = "N"

        if "currency" in df.columns:
            df["currency"] = df["currency"].fillna("RUB")
        else:
            df["currency"] = "RUB"

        if "tax_price" in df.columns:
            df["tax_price"] = pd.to_numeric(df["tax_price"], errors="coerce")
        else:
            df["tax_price"] = None
        df["ali_affiliate_url"] = None

        df = df[df["brand"].notna() & (df["brand"] != "")]
        after_normalized_brand = len(df)
        df = df[df["model"].notna() & (df["model"] != "")]
        after_normalized_model = len(df)
        df = df[df["product_url"].notna() & (df["product_url"] != "")]
        after_product_url = len(df)
        df = df[df["article"].notna() & (df["article"] != "")]
        after_article_text = len(df)
        df = df[df["price"].notna()]
        after_price_numeric = len(df)

        df = df[df.apply(lambda row: str(row["article"]) in str(row["product_url"]), axis=1)].copy()
        after_article_in_url = len(df)

        logger.info(
            "[БД] prepare_matched_rows funnel: "
            f"start={start_count} -> match_status={after_match_status} -> matched_model={after_model_name} "
            f"-> brand={after_brand} -> article={after_article} -> url={after_url} "
            f"-> price_present={after_price_present} -> normalized_brand={after_normalized_brand} "
            f"-> normalized_model={after_normalized_model} -> product_url={after_product_url} "
            f"-> article_text={after_article_text} -> price_numeric={after_price_numeric} "
            f"-> article_in_url={after_article_in_url}"
        )

        return df

    @classmethod
    def insert_g_watch(cls, df_ready: pd.DataFrame) -> None:
        df_watch = df_ready[["brand", "model", "size"]].drop_duplicates().copy()

        query = """
        INSERT IGNORE INTO g_watch (brand, model, size)
        VALUES (%(brand)s, %(model)s, %(size)s)
        """

        columns = ["brand", "model", "size"]

        records = (
            df_watch[columns]
            .replace({pd.NA: None})
            .where(pd.notnull(df_watch[columns]), None)
            .to_dict(orient="records")
        )

        bulk_insert(query, records)

    @classmethod
    def attach_watch_id(cls, df_ready: pd.DataFrame) -> pd.DataFrame:
        g_watch_df = select_df("SELECT id, brand, model, size FROM g_watch")

        if g_watch_df.empty:
            raise ValueError("g_watch пустая после вставки")

        df_ready = df_ready.copy()
        g_watch_df = g_watch_df.copy()

        for col in ["brand", "model"]:
            df_ready[col] = df_ready[col].astype(str).str.strip().str.lower()
            g_watch_df[col] = g_watch_df[col].astype(str).str.strip().str.lower()

        df_ready["size"] = pd.to_numeric(df_ready["size"], errors="coerce").fillna(0).astype(int)
        g_watch_df["size"] = pd.to_numeric(g_watch_df["size"], errors="coerce").fillna(0).astype(int)

        df_merged = df_ready.merge(
            g_watch_df[["id", "brand", "model", "size"]],
            how="inner",
            on=["brand", "model", "size"],
        ).rename(columns={"id": "watch_id"})

        return df_merged

    @classmethod
    def insert_g_shop_watch(cls, df_ready: pd.DataFrame, shop_id: int) -> None:
        df_ready = df_ready.copy()
        df_ready["shop_id"] = shop_id

        columns = [
            "watch_id",
            "shop_id",
            "product_url",
            "image_url",
            "rating",
            "shop_rating",
            "review",
            "is_global",
            "warranty_period",
            "color",
            "article",
            "days_to_delivery",
            "ali_affiliate_url",
        ]

        query = generate_insert_on_duplicate("g_shop_watch", columns)

        records = (
            df_ready[columns]
            .where(pd.notnull(df_ready[columns]), None)
            .to_dict(orient="records")
        )

        bulk_insert(query, records)

    @classmethod
    def attach_shop_watch_id(cls, df_ready: pd.DataFrame, shop_id: int) -> pd.DataFrame:
        g_shop_watch_df = select_df(
            "SELECT id AS shop_watch_id, watch_id, shop_id, article FROM g_shop_watch"
        )

        df_ready = df_ready.copy()
        g_shop_watch_df = g_shop_watch_df.copy()

        df_ready["shop_id"] = shop_id
        df_ready["article"] = df_ready["article"].astype(str).str.strip()
        g_shop_watch_df["article"] = g_shop_watch_df["article"].astype(str).str.strip()

        df_merged = df_ready.merge(
            g_shop_watch_df,
            how="inner",
            on=["watch_id", "shop_id", "article"],
        )

        return df_merged

    @classmethod
    def insert_g_watch_price(
        cls,
        df_ready: pd.DataFrame,
        actual_date: date,
        is_new: bool,
    ) -> None:
        df_ready = df_ready.copy()
        df_ready["actual_date"] = actual_date
        df_ready["is_new"] = "Y" if is_new else "N"

        columns = [
            "shop_watch_id",
            "price",
            "tax_price",
            "currency",
            "actual_date",
            "is_new",
        ]

        query = generate_insert_on_duplicate("g_watch_price", columns)

        records = (
            df_ready[columns]
            .where(pd.notnull(df_ready[columns]), None)
            .to_dict(orient="records")
        )

        bulk_insert(query, records)

        logger.info(
            f"[БД] цены записаны: {len(records)} | "
            f"магазин={SHOP_NAMES.get(df_ready['shop_id'].iloc[0], 'неизвестно')} | "
            f"тип={'НОВЫЕ' if is_new else 'БУ'}"
        )

    @classmethod
    def prepare_and_write_watch_data_to_db(
        cls,
        df_res: pd.DataFrame,
        actual_date: date,
        shop_id: int,
        is_new: bool,
    ) -> None:
        cls.validate_input_columns(df_res)
        df_ready = cls.prepare_matched_rows(df_res)

        logger.info(f"[БД] строк после подготовки: {len(df_ready)}")

        if df_ready.empty:
            logger.warning("Нет строк для записи в БД")
            return

        cls.insert_g_watch(df_ready)
        df_ready = cls.attach_watch_id(df_ready)

        logger.info(f"[БД] строк после привязки идентификатора watch_id: {len(df_ready)}")

        if df_ready.empty:
            logger.warning("После объединения с g_watch не осталось строк")
            return

        cls.insert_g_shop_watch(df_ready, shop_id=shop_id)
        df_ready = cls.attach_shop_watch_id(df_ready, shop_id=shop_id)

        logger.info(f"[БД] строк после привязки идентификатора shop_watch_id: {len(df_ready)}")

        if df_ready.empty:
            logger.warning("После объединения с g_shop_watch не осталось строк")
            return

        cls.insert_g_watch_price(
            df_ready=df_ready,
            actual_date=actual_date,
            is_new=is_new,
        )

    @classmethod
    def prepare_and_write_watch_new_and_used_to_db(
        cls,
        df_new: pd.DataFrame,
        df_used: pd.DataFrame,
        actual_date: date,
        shop_id: int = 2,
    ) -> None:
        logger.info("=== Запись НОВЫХ часов ===")
        cls.prepare_and_write_watch_data_to_db(
            df_res=df_new,
            actual_date=actual_date,
            shop_id=shop_id,
            is_new=True,
        )

        logger.info("=== Запись Б/У часов ===")
        cls.prepare_and_write_watch_data_to_db(
            df_res=df_used,
            actual_date=actual_date,
            shop_id=shop_id,
            is_new=False,
        )
