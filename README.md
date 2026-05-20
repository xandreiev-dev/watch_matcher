# Watch Matcher — Smartwatch Data Pipeline

Сервис для обработки XLSX-файлов с объявлениями по смарт-часам, сопоставления моделей с эталонным каталогом и записи данных в MySQL для дальнейшей аналитики.

Поддерживаемые источники:

- **Avito** — `shop_id=2`
- **Ozon** — `shop_id=1`

Avito-flow остается базовым и не меняется. Ozon обрабатывается source-aware: отдельный `shop_id`, свои поля `tax_price`, `is_global`, `delivery_days` и более мягкая логика определения аксессуаров.

---

## Архитектура

- **Backend (FastAPI)** — обработка XLSX, matcher, экспорт и запись в БД
- **Frontend (Vue/Vite)** — UI для загрузки файлов
- **MySQL** — каталог моделей, объявления и история цен
- **FTP ingest service** — фоновый импорт Avito-файлов с FTP

---

## Pipeline Обработки

1. Загрузка XLSX через файл или URL.
2. Определение источника:
   - `Ozon_watch_*.xlsx` или Ozon-колонки -> `source=ozon`, `shop_id=1`
   - Avito-файлы -> `source=avito`, `shop_id=2`
3. Предобработка:
   - нормализация title/description
   - извлечение бренда, размера, article, URL, цены
   - source-aware accessory detection
4. Извлечение признаков:
   - family / generation / variant
   - color / warranty / material / connectivity
5. Сопоставление модели с каталогом:
   - strict model/variant match
   - strict model match без variant
   - controlled fallback
6. Экспорт результата:
   - `avito_watch_YYYY-MM-DD_new.xlsx`
   - `avito_watch_YYYY-MM-DD_old.xlsx`
   - `ozon_watch_YYYY-MM-DD_new.xlsx`
7. Подготовка и запись в БД:
   - `g_watch`
   - `g_shop_watch`
   - `g_watch_price`

---

## Ozon Импорт

Ozon XLSX может содержать дополнительные поля:

- `Article`
- `product_url`
- `shop_rating`
- `reviews_count`
- `delivery_days`
- `is_global`
- `tax_price`
- `Discount Price`
- `source_brand`

Что сохраняется:

- `Article` используется как основной article, если колонка есть
- `Discount Price` используется как итоговая цена
- `tax_price` сохраняется в `g_watch_price.tax_price`
- `is_global` нормализуется в формат БД `Y/N`
- `delivery_days` сохраняется как `days_to_delivery`
- `shop_id=1`

Для Ozon accessory-логика мягче, чем для Avito: реальные часы не отбрасываются только из-за слов `band`, `loop`, `case`, `strap`, `стекло`, `ремешок`, если в названии явно есть модель часов.

---

## Avito Импорт

Avito остается совместимым с текущим pipeline:

- `shop_id=2`
- экспорт в `avito_watch_YYYY-MM-DD_new/old.xlsx`
- FTP ingest для new/old файлов
- текущие правила matcher и записи в БД сохранены

---

## Import Layer Для Scheduler

Для почасового запуска не нужно поднимать отдельный новый matcher. Поверх текущего pipeline добавлен тонкий import-layer: он находит XLSX, скачивает файл, запускает уже существующие нормализацию/matching/db-ready шаги и при необходимости пишет результат в БД.

Основные функции для внешнего scheduler-а:

```python
from app.importers import process_avito_watch_data, process_ozon_watch_data

process_avito_watch_data(dry_run=False, force=False)
process_ozon_watch_data(dry_run=False, force=False)
```

CLI для ручной проверки:

```bash
cd backend
python main_import.py --shop avito --dry-run
python main_import.py --shop ozon --dry-run
python main_import.py --shop all --dry-run
```

`dry-run` прогоняет matcher и сохраняет output/debug XLSX, но не пишет данные в БД. Debug-файлы создаются в `tmp/`:

- `avito_watch_ready_YYYY-MM-DD_new/old.xlsx`
- `avito_watch_failed_YYYY-MM-DD_new/old.xlsx`
- `ozon_watch_ready_YYYY-MM-DD_new.xlsx`
- `ozon_watch_failed_YYYY-MM-DD_new.xlsx`

Защита от повторного импорта сделана через `watch_import_log`: один и тот же файл не импортируется повторно по `file_hash`, если не передан `force=True`.

---

## Работа С БД

Основные таблицы записи:

- `g_watch` — уникальная нормализованная модель
- `g_shop_watch` — карточка товара/объявления у магазина
- `g_watch_price` — история цен

Таблицы каталога/сопоставления:

- `g_watch_model` — эталонные модели
- `g_watch_variant` — размеры/варианты моделей

`prepare_matched_rows()` пишет в БД только строки с `match_status=matched`, валидным `article`, `URL`, `price`, брендом и моделью.

---

## Гарантия

Гарантия записывается только если явно указан срок:

- `Гарантия 12 мес` -> `360`
- `Гарантия 14 дней` -> `14`
- `Гарантия 1 год` -> `365`

Если есть только слово `гарантия/warranty` без срока, в БД пишется `NULL`. Fallback `1`, `0` или строковые значения не используются.

---

## API

### `POST /api/process`

Полная обработка XLSX.

Параметры:

- `file` — XLSX-файл
- `file_url` — ссылка на XLSX
- `is_new` — `true/new` или `false/old/used`
- `source` — опционально: `avito` или `ozon`
- `shop_id` — опционально: `1` или `2`
- `write_to_db` — `true/false`

Безопасный прогон Ozon без записи в БД:

```cmd
curl.exe -X POST http://127.0.0.1:4444/api/process -F "file=@C:\work\ozon_watch_parser\brand_exports\Ozon_watch_ru_2026-05-08.xlsx" -F "source=ozon" -F "is_new=true" -F "write_to_db=false"
```

### `POST /api/process/preview`

Предпросмотр по первым строкам без записи в БД.

### `GET /api/watch-catalog/resolve`

Точный поиск модели и варианта в `g_watch_model` / `g_watch_variant`.

Пример:

```text
/api/watch-catalog/resolve?brand=Apple&model=Watch Series 6&size_mm=44
```

Если вариантов несколько и не хватает `material/connectivity`, endpoint возвращает `ambiguous`, а не случайную запись.

### `GET /api/watch-catalog/diagnostics/variants`

Диагностика качества `g_watch_variant`:

- модели без вариантов
- дубли вариантов
- ambiguous size-группы
- подозрительные пустые варианты

Данные не изменяются, endpoint только читает каталог.

---

## Запуск

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 4444
```

Swagger:

```text
http://127.0.0.1:4444/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## FTP Ingest Service

Фоновая служба для Avito new/old файлов:

```bash
cd backend
python scripts/run_ftp_watch_ingest_service.py
```

Разовый прогон:

```bash
cd backend
python scripts/run_ftp_watch_ingest_service.py --once
```

Основные переменные окружения:

- `FTP_HOST`
- `FTP_USER`
- `FTP_PASS`
- `FTP_PORT`
- `FTP_REMOTE_DIR`
- `FTP_LOCAL_DOWNLOAD_DIR`
- `FTP_CHECK_MINUTE`
- `IS_DEBUG`

`IS_DEBUG=true` включает один отладочный прогон с повторной обработкой актуального файла и перезаписью строк за дату файла через существующий UPSERT.

---

## Логи Pipeline

Пример:

```text
[ПАЙПЛАЙН] всего=10258 | совпало=8633 | без_совпадений=1625 | тип=НОВЫЕ
[SOURCE] source=ozon shop_id=1
[БД] prepare_matched_rows funnel: start=10258 -> match_status=8633 -> ... -> article_in_url=8633
```

---

## Выходные Файлы

Файлы сохраняются в `backend/output/`:

- `avito_watch_YYYY-MM-DD_new.xlsx`
- `avito_watch_YYYY-MM-DD_old.xlsx`
- `ozon_watch_YYYY-MM-DD_new.xlsx`

Папка `backend/output/` и XLSX-файлы исключены из git.

---

## Git Safety

В репозиторий не должны попадать:

- `.env`, `.env.*`
- `*.xlsx`, `*.xls`
- `*.log`
- `backend/output/`
- `node_modules/`
- `__pycache__/`, `*.pyc`

---

## Статус

Реализован полный pipeline:

- Avito import
- Ozon import
- source-aware export
- matcher моделей/вариантов
- подготовка строк к БД
- запись в `g_watch`, `g_shop_watch`, `g_watch_price`
- диагностические endpoints каталога

Фокус проекта: точность, предсказуемость и безопасная запись в БД.
