# Rayventory

Самостоятельная система прогнозирования товарных запасов на Laravel и Python.
Приложение рассчитывает 30-дневный диапазон спроса, моделирует остатки и формирует
управленческие отчёты в PDF и PPTX.

## Возможности

- robust-прогноз `seasonal-robust-v1` с диапазоном q10-q90;
- восстановление спроса при отсутствии товара строго внутри одного SKU;
- сценарии standard, risk, optimization, trend и promo;
- рекомендации по заказу с учётом остатка, товара в пути и срока поставки;
- современный PDF-отчёт и редактируемая презентация PPTX;
- Laravel API для склада, симуляций, состояния расчётов и отчётов.
- загрузка исходных данных из проверяемого Excel-шаблона через интерфейс склада;
- очередь закупок с приоритетом, датой дефицита и объяснением каждой рекомендации;
- оценка качества данных и backtesting модели по WAPE, bias и покрытию q10-q90;
- расширяемый контур складов, поставщиков и заказов поставщикам.

## Требования

- PHP 8.2 или новее;
- Composer 2;
- Python 3.11 или новее;
- расширение PHP `pdo_sqlite`.

Python-зависимости перечислены в `requirements.txt`.

## Локальная установка на macOS и Linux

Все команды необходимо выполнять из корневой директории проекта.

На macOS PHP, Composer и Python можно установить через Homebrew:

```bash
brew install php composer python@3.12
```

Установите PHP-зависимости, создайте локальную конфигурацию и ключ приложения:

```bash
composer install
cp .env.example .env
php artisan key:generate
```

Создайте отдельное Python-окружение и установите зависимости прогнозирования:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

В `.env` укажите абсолютный путь к Python из созданного окружения:

```dotenv
ML_PYTHON=/absolute/path/to/project/.venv/bin/python
```

Например, узнать корректный путь можно командой:

```bash
pwd
```

Затем создайте рабочую SQLite-базу и запустите приложение:

```bash
php artisan rayventory:setup
php artisan serve
```

Приложение будет доступно по адресу `http://127.0.0.1:8000`.

Для уже существующей рабочей базы после обновления проекта выполните:

```bash
php artisan migrate --force
```

## Локальная установка на Windows

```powershell
composer install
Copy-Item .env.example .env
php artisan key:generate
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
php artisan rayventory:setup
php artisan serve
```

В `.env` для Windows укажите путь к Python из окружения, например:

```dotenv
ML_PYTHON=C:\path\to\project\.venv\Scripts\python.exe
```

Команда `rayventory:setup` создаёт рабочую SQLite-базу из поставляемого demo-seed.
Повторный запуск безопасен и не перезаписывает существующие данные. Для полного
сброса используйте `php artisan rayventory:setup --force`.

## Запуск из PhpStorm

Создайте конфигурацию запуска **PHP Script** со следующими параметрами:

- **PHP interpreter** — путь к установленному PHP, например `/opt/homebrew/bin/php`;
- **File** — `artisan`;
- **Arguments** — `serve`;
- **Working directory** — корневая директория проекта;
- **Interpreter options** — оставить пустым.

Параметр PHP `-c` предназначен для пути к файлу `php.ini`. Не указывайте после
него путь к исполняемому файлу PHP.

## Частые ошибки запуска

Ошибка `Failed opening required vendor/autoload.php` означает, что PHP-зависимости
ещё не установлены. Выполните в корне проекта:

```bash
composer install
```

Если команда `composer` не найдена, сначала установите Composer. На macOS:

```bash
brew install composer
```

Проверить основные компоненты можно командами:

```bash
php -v
composer --version
php -m | grep -E 'pdo_sqlite|sqlite3'
.venv/bin/python --version
php artisan route:list
```

## Docker

```bash
docker compose up --build
```

Контейнер самостоятельно устанавливает зависимости, подготавливает рабочую базу
при первом запуске и поднимает приложение на `http://localhost:8000`.

## Структура данных и ML

- `ml/predict_cli.py` — JSON CLI между Laravel и Python;
- `ml/forecasting.py` — production-прогноз и расчёт рекомендаций;
- `ml/report_generator.py` — генерация PDF и PPTX;
- `database/seed/inventory_forecast.db` — неизменяемая демонстрационная база;
- `storage/app/rayventory/inventory_forecast.db` — рабочая база приложения;
- `storage/app/reports` — сформированные отчёты.

Рабочая база и отчёты находятся в `storage` и не попадают в Git. Demo-seed содержит
синтетическую историю, поэтому приложение явно предупреждает об устаревших данных.
Перед реальным использованием замените её актуальной историей продаж.

## Загрузка данных из Excel

SQLite используется как внутреннее рабочее хранилище, но пользователю не нужно
редактировать базу вручную. Основной способ загрузки исходных данных:

1. откройте раздел **Склад**;
2. скачайте **Пустой шаблон** или откройте **Заполненный пример**;
3. прочитайте лист `Инструкция`;
4. заполните листы `Товары`, `Продажи`, `Остатки` и `Поставки`;
5. выберите `.xlsx` и нажмите **Проверить файл**;
6. изучите найденный период, склады, количество строк и предупреждения;
7. нажмите **Подтвердить импорт**, только если сводка корректна.

Пустой шаблон предназначен для рабочих данных. Отдельный заполненный пример
содержит три товара и 365 дней непрерывной истории: 1 095 строк продаж, дни без
наличия, промо, праздники, текущие остатки и ожидаемые поставки. Минимум для
базового прогноза — 90 дней на каждый SKU; для определения сезонности рекомендуется
12 месяцев. Одна строка на листе `Продажи` означает продажи одного SKU за день.

Внешним идентификатором товара служит пользовательский `SKU`, а не внутренний ID
базы. Остатки содержат склад, дату состояния и резерв. Поставки содержат номер,
ожидаемую дату, статус и поставщика.

Файл принимается только после полной проверки. Проверяются названия листов и
столбцов, типы значений, уникальность ID, связи продаж и остатков с товарами,
формат дат и наличие остатка для каждого товара. Максимальный размер — 20 МБ,
максимум — 100 000 строк на лист. Если обнаружена ошибка, импорт отменяется и
текущая рабочая база не изменяется. Загрузка файла выполняет только предварительную
проверку; запись начинается после отдельного подтверждения. Перед успешной заменой
создаётся резервная копия SQLite, а результат сохраняется в журнале импортов.

## Карта системы

```text
                                      ╱──────────────╱│
                                     ╱  Python ML   ╱ │
                                    ╱──────────────╱  │
                                    │ forecast +   │  │
                                    │ PDF / PPTX   │ ╱
                                    │──────────────│╱
                                           ▲  │
                      action + payload-b64 │  │ JSON result
                                           │  ▼
       ╱──────────────╱│             ╱──────────────╱│
      ╱   Browser    ╱ │  HTTP/JSON  ╱   Laravel   ╱ │
     ╱──────────────╱  │◄──────────►╱──────────────╱  │
     │ Blade pages  │  │            │ routes/API   │  │
     │ + app.js     │ ╱             │ + MlBridge   │ ╱
     │──────────────│╱              │──────────────│╱
                                           │  ▲
                             SQL read/write│  │ rows
                                           ▼  │
                                    ╱──────────────╱│
                                   ╱    SQLite    ╱ │
                                  ╱──────────────╱  │
                                  │ products +   │  │
                                  │ sales/stock  │ ╱
                                  │──────────────│╱
                                           │
                                           │ generated artifacts
                                           ▼
                                    ╱──────────────╱│
                                   ╱   Storage    ╱ │
                                  ╱──────────────╱  │
                                  │ jobs + PDF   │  │
                                  │ + PPTX       │ ╱
                                  │──────────────│╱
```

### Легенда

- **Browser** — пользовательский интерфейс, Blade-страницы и JavaScript-клиент;
- **Laravel** — HTTP-маршрутизация, валидация, работа с остатками и запуск ML;
- **Python ML** — прогнозирование спроса и генерация отчётов;
- **SQLite** — единый источник товаров, продаж, остатков и товара в пути;
- **Storage** — состояния расчётов и сформированные PDF/PPTX-файлы;
- `►` — направление вызова или передаваемых данных.

### Реальные потоки управления и данных

1. Браузер запрашивает показатели и остатки через `/api/dashboard-stats` и
   `/api/stock`. Laravel читает таблицы `products` и `warehouse_stock`, после чего
   возвращает JSON. Клиент отображает карточки, таблицы и графики
   ([public/js/app.js](public/js/app.js), [routes/api.php](routes/api.php),
   [ApiController.php](app/Http/Controllers/ApiController.php)).
2. Обновление остатка идёт как JSON `{product_id, quantity}` в
   `/api/stock/update`; контроллер валидирует payload и записывает значение в
   `warehouse_stock` ([ApiController.php](app/Http/Controllers/ApiController.php),
   [WarehouseStock.php](app/Models/WarehouseStock.php)).
3. Симулятор отправляет `{product_id, overrides}` в `/api/simulate` или
   `/api/simulate/start`. `MlBridge` запускает Python-процесс с действием
   `simulate` и Base64-кодированным JSON, а также передаёт `ML_DB_PATH` и
   `ML_REPORTS_PATH` ([MlBridge.php](app/Services/MlBridge.php),
   [predict_cli.py](ml/predict_cli.py), [config/rayventory.php](config/rayventory.php)).
4. Python читает из SQLite товары, историю продаж, остатки и поставки в пути,
   рассчитывает прогноз `demand/q10/q90`, остаток и safety stock, затем возвращает
   одну JSON-строку в Laravel ([forecasting.py](ml/forecasting.py)).
5. Для отчёта браузер передаёт `{type, formats}` в `/api/generate-report`.
   Python сохраняет PDF/PPTX в `storage/app/reports`, Laravel возвращает имена
   артефактов, а скачивание проходит через проверенный маршрут
   `/download/reports/{filename}` ([report_generator.py](ml/report_generator.py),
   [routes/web.php](routes/web.php), [ApiController.php](app/Http/Controllers/ApiController.php)).
6. Команда `rayventory:setup` один раз копирует поставляемый demo-seed в рабочую
   SQLite-базу; повторный запуск без `--force` не перезаписывает данные
   ([routes/console.php](routes/console.php),
   [config/database.php](config/database.php)).

## Конфигурация

В стандартной установке достаточно указать `ML_PYTHON`. При необходимости пути
можно переопределить переменными:

- `DB_DATABASE` — рабочая SQLite-база Laravel;
- `ML_DB_PATH` — SQLite-база для Python, по умолчанию совпадает с рабочей базой;
- `ML_ENGINE_PATH` — путь к Python CLI;
- `ML_REPORTS_PATH` — каталог отчётов;
- `ML_TIMEOUT` — таймаут Python-процесса в секундах.

## API

- `GET /api/dashboard-stats` — показатели склада;
- `GET /api/stock` — товары и остатки;
- `POST /api/stock/update` — обновление остатка;
- `POST /api/inventory/import/preview` — безопасная предварительная проверка Excel;
- `POST /api/inventory/import/confirm` — подтверждение проверенного импорта;
- `GET /api/purchase-plan` — план закупок, качество данных и объяснимые действия;
- `POST /api/simulate` — синхронный прогноз SKU;
- `POST /api/simulate/start` — запуск расчёта с идентификатором задачи;
- `GET /api/jobs/{jobId}` — состояние расчёта;
- `POST /api/generate-report` — создание PDF/PPTX;
- `GET /download/reports/{filename}` — безопасное скачивание отчёта.

## Проверка

```powershell
php artisan route:list
php artisan view:cache
vendor\bin\pint --test
node --check public\js\app.js
py -m compileall -q ml
```
