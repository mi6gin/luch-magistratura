# Rayventory

Rayventory — локальная многопользовательская система прогнозирования товарных
запасов для сети филиалов. Веб-часть написана на Laravel 12, прогнозирование и
отчёты — на Python, хранилище — SQLite.
Node.js и сборка фронтенда не нужны: интерфейс состоит из Blade-шаблонов,
обычного JavaScript и CSS в `public/`.

Этот README — единая инструкция по установке, эксплуатации, тестированию и
ориентации в коде. Перед началом работы рекомендуется ознакомиться с краткой
сводкой и использовать приведённые ниже готовые команды.

## Основные сведения и соглашения

- Корень проекта содержит `artisan`, `composer.json` и каталог `ml/`.
- Требуются PHP 8.2+, Composer 2, Python 3.11+ и PHP-расширения
  `pdo_sqlite`, `sqlite3`, `mbstring`, `zip`, `gd`.
- Проверенное CI-окружение: PHP 8.5 и Python 3.12.
- Обычное приложение: `.venv` + `requirements.txt`.
- Все Python-тесты и исследования: `.venv-ml` + `requirements-ml.txt`.
  Расширенный набор включает runtime-зависимости, PyTorch, Kaggle и `openpyxl`.
- `vendor/`, виртуальные окружения, рабочая база и артефакты исключены из Git.
- Не редактировать `database/seed/inventory_forecast.db`: это неизменяемый
  demo-seed. Рабочая база находится в
  `storage/app/rayventory/inventory_forecast.db`.
- `php artisan rayventory:setup` не заменяет существующую базу. Вариант
  `--force` уничтожает локально импортированные данные и требует явного согласия.
- PHPUnit использует SQLite `:memory:` и не меняет рабочую базу.
- Данные, импорт, прогнозы, модели и отчёты изолированы по филиалам.
- После `rayventory:setup` создаётся локальный администратор. До запуска команды
  задайте уникальный пароль через `RAYVENTORY_ADMIN_PASSWORD`.
- Не запускать `train`, `tune`, `scenarios` или `scale`, если задача этого не
  требует: операции могут быть долгими. Для обычной проверки есть быстрый набор.
- В проекте нет npm-зависимостей и отдельного build-шага для CSS/JS.

## Карта проекта

```text
Browser (Blade + public/js + public/css)
                 │ HTTP/JSON
                 ▼
Laravel routes → ApiController → Services / Eloquent
                 │ subprocess          │ SQL
                 ▼                     ▼
          ml/predict_cli.py           SQLite
                 │
                 ▼
       forecast / PDF / PPTX / JSON → storage/app
```

| Путь | Назначение |
|---|---|
| `routes/web.php` | Страницы и безопасная выдача файлов |
| `routes/api.php` | JSON API |
| `app/Http/Controllers/ApiController.php` | Валидация и координация сервисов |
| `app/Services/BranchContext.php` | Проверенный контекст активного филиала |
| `app/Services/MlBridge.php` | Запуск Python с филиальным контекстом |
| `app/Services/InventoryExcelService.php` | Шаблон, preview и импорт Excel |
| `app/Services/ModelRegistryService.php` | Реестр candidate/production-моделей |
| `app/Services/LocalModelPipelineService.php` | Фоновый локальный ML-конвейер |
| `ml/predict_cli.py` | Стабильный JSON CLI production runtime |
| `ml/forecasting.py` | Прогноз и рекомендации по закупке |
| `ml/report_generator.py` | PDF- и PPTX-отчёты |
| `ml/runtime_model.py` | Загрузка опубликованной runtime-модели |
| `ml/research_cli.py` | CLI исследовательского контура |
| `ml/research/` | Данные, метрики, baseline, нейросети, эксперименты |
| `database/migrations/` | Схема рабочей базы |
| `database/seed/inventory_forecast.db` | Версионируемая demo-база |
| `tests/Feature/ApplicationTest.php` | Интеграционные тесты Laravel |
| `ml/tests/` | Python-тесты |

## Установка с чистого клона

Все команды выполняются из корня репозитория.

### macOS

```bash
brew install php composer python@3.12
php -v
composer --version
python3.12 --version
php -m | grep -E 'pdo_sqlite|sqlite3|mbstring|zip|gd'
```

```bash
composer install --no-interaction --prefer-dist
cp .env.example .env
php artisan key:generate
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

В `.env` замените стандартное Windows-значение абсолютным путём:

```dotenv
ML_PYTHON=/absolute/path/to/luch-magistratura/.venv/bin/python
```

Путь к корню показывает `pwd`. Затем:

```bash
php artisan rayventory:setup
php artisan serve
```

Первый вход выполняется значениями из `.env`:

```dotenv
RAYVENTORY_ADMIN_EMAIL=admin@rayventory.local
RAYVENTORY_ADMIN_PASSWORD=<уникальный пароль длиной не менее 12 символов>
```

Обязательно задайте пароль до первого запуска вне личного компьютера.

Сайт откроется на <http://127.0.0.1:8000>. Для фонового обучения во втором
терминале:

```bash
php artisan queue:work --sleep=2 --tries=1 --timeout=3600
```

Для выполнения расписания очистки в разработке:

```bash
php artisan schedule:work
```

### Linux

Установите PHP 8.2+, Composer, Python 3.11+, SQLite и PHP-расширения
`pdo_sqlite`, `mbstring`, `zip`, `gd`. Затем повторите команды macOS, заменив
`python3.12` доступным интерпретатором версии 3.11 или новее.

### Windows PowerShell

```powershell
composer install --no-interaction --prefer-dist
Copy-Item .env.example .env
php artisan key:generate
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
php artisan rayventory:setup
php artisan serve
```

В `.env`:

```dotenv
ML_PYTHON=C:\absolute\path\to\luch-magistratura\.venv\Scripts\python.exe
```

### PhpStorm

Конфигурация **PHP Script**:

- PHP interpreter: установленный PHP;
- File: `artisan`;
- Arguments: `serve`;
- Working directory: корень репозитория;
- Interpreter options: пусто.

Параметр PHP `-c` означает путь к `php.ini`, а не путь к интерпретатору.

## Минимальная среда для работы с кодом

Если задача не требует запуска сайта, `.env` и рабочую базу создавать не нужно:

```bash
composer install --no-interaction --prefer-dist
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
git status --short --branch
```

После работы снова проверить `git status`. Не удалять и не перезаписывать
пользовательские изменения в грязном рабочем дереве.

## Проверки

### Быстрый обязательный набор

```bash
composer test
vendor/bin/pint --test
.venv/bin/python -m compileall -q ml
```

На момент написания ожидается не менее `20 tests, 101 assertions`. `phpunit.xml`
задаёт отдельный тестовый `APP_KEY` и использует SQLite `:memory:`.

### Полный Python-набор

```bash
python3.12 -m venv .venv-ml
.venv-ml/bin/python -m pip install -r requirements-ml.txt
.venv-ml/bin/python -m compileall -q ml
.venv-ml/bin/python -m unittest discover -s ml/tests -p 'test_*.py' -v
```

При запуске всех тестов только из `.venv` Excel-тесты не найдут `openpyxl`, а
тест нейросетевых архитектур будет пропущен без PyTorch. Используйте `.venv-ml`.

### Дополнительные проверки

```bash
composer validate --strict
composer audit --locked --no-interaction
php artisan route:list --except-vendor
```

`composer validate --strict` сейчас предупреждает только об отсутствии поля
`license` в `composer.json`.

### Эквивалент CI

`.github/workflows/quality.yml` использует PHP 8.5 и Python 3.12:

```bash
composer install --no-interaction --prefer-dist
python3.12 -m venv .venv-ml
.venv-ml/bin/python -m pip install -r requirements-ml.txt
composer test
vendor/bin/pint --test
.venv-ml/bin/python -m compileall -q ml
.venv-ml/bin/python -m unittest discover -s ml/tests -p 'test_*.py'
docker build -t rayventory-ci .
```

Тестовый ключ хранится только в `phpunit.xml` и не используется приложением.

## Docker

Compose требует существующий `.env`:

```bash
cp .env.example .env
docker compose run --rm app php artisan key:generate --force
docker compose up --build
```

В контейнере `ML_PYTHON=python3` уже задан. `app` ставит Composer-зависимости,
создаёт/мигрирует базу и слушает порт 8000; `worker` обрабатывает очередь. Проект
монтируется в `/var/www/html`. Изменение системных или Python-зависимостей требует
пересборки.

```bash
docker compose ps
docker compose logs -f app
docker compose logs -f worker
docker compose down
```

Последняя команда останавливает контейнеры без удаления локальной рабочей базы.

## Переменные окружения

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `APP_KEY` | Шифрование Laravel | генерируется `key:generate` |
| `DB_CONNECTION` | Драйвер | `sqlite` |
| `DB_DATABASE` | Рабочая база | `storage/app/rayventory/inventory_forecast.db` |
| `QUEUE_CONNECTION` | Фоновые задачи | `database` |
| `SESSION_LIFETIME` | Таймаут неактивной сессии | `120` минут |
| `SESSION_EXPIRE_ON_CLOSE` | Завершать сессию при закрытии браузера | `true` |
| `SESSION_ENCRYPT` | Шифровать содержимое сессии | `true` |
| `SESSION_SECURE_COOKIE` | Передавать cookie только по HTTPS | локально `false`, production `true` |
| `SESSION_SAME_SITE` | Защита cookie от межсайтовых запросов | `lax` |
| `HASH_DRIVER` | Хеширование паролей | `argon2id` |
| `RAYVENTORY_ADMIN_EMAIL` | Email первого администратора | `admin@rayventory.local` |
| `RAYVENTORY_ADMIN_PASSWORD` | Пароль первого администратора | заменить перед установкой |
| `ML_PYTHON` | Python runtime | в шаблоне `py`; локально указать `.venv` |
| `ML_RESEARCH_PYTHON` | Python исследований | fallback на `ML_PYTHON` |
| `ML_ENGINE_PATH` | Production CLI | `ml/predict_cli.py` |
| `ML_DB_PATH` | База для Python | fallback на `DB_DATABASE` |
| `ML_REPORTS_PATH` | PDF/PPTX | `storage/app/reports` |
| `ML_MODEL_REGISTRY_PATH` | Реестр моделей | `storage/app/model-registry/registry.json` |
| `ML_MODELS_PATH` | Runtime-артефакты | `storage/app/models` |
| `ML_LOCAL_DATA_PATH` | Локальный датасет | `data/processed/local-inventory` |
| `ML_DATASET_ANALYSIS_PATH` | EDA-профиль | `storage/app/dataset-analysis/latest.json` |
| `ML_TUNING_PATH` | Результаты tuning | `storage/app/tuning` |
| `ML_SCENARIOS_PATH` | Сценарные benchmark | `storage/app/scenarios` |
| `ML_TRAINING_TIMEOUT` | Таймаут обучения | `3600` секунд |
| `ML_TIMEOUT` | Таймаут runtime | `120` секунд |

После изменения `.env`:

```bash
php artisan config:clear
```

## База и пользовательские данные

```bash
php artisan rayventory:setup
```

Команда создаёт каталог, копирует demo-seed только при отсутствии рабочей базы и
применяет миграции. Для существующей базы:

```bash
php artisan migrate --force
```

Полный сброс является разрушительным:

```bash
php artisan rayventory:setup --force
```

### Филиалы и пользователи

Администратор создаёт филиал кнопкой `+` рядом с переключателем филиала. Раздел
`/settings` создаёт пользователей выбранного филиала и назначает роль:

- `admin` — управление организацией и любые действия;
- `analyst` — импорт, прогнозы, обучение и модели;
- `purchaser` — просмотр и выгрузка плана закупок;
- `viewer` — только чтение.

Каждый API-запрос содержит `X-Branch-ID`; сервер проверяет членство пользователя,
а не доверяет идентификатору из браузера. Изменяющие запросы записываются в
`audit_logs`.

### Безопасность production

- Публикуйте приложение только за HTTPS и задайте `APP_ENV=production`,
  `APP_DEBUG=false`, `SESSION_SECURE_COOKIE=true`.
- Создайте новый `APP_KEY` на целевом сервере и не копируйте его в Git.
- Укажите уникальный `RAYVENTORY_ADMIN_PASSWORD` до первого запуска миграций;
  production-seeder отклоняет отсутствующий или слишком короткий пароль.
- Пароли хешируются Argon2id; новые пароли должны содержать не менее 12 символов,
  буквы обоих регистров, цифру и специальный символ.
- Вход ограничен пятью неудачными попытками в минуту для пары email/IP. Успешные
  и неуспешные попытки фиксируются в серверном журнале без открытого email.
- Cookie сессии имеет флаги `HttpOnly` и `SameSite`, содержимое сессии шифруется,
  идентификатор обновляется после входа и смены пароля. Постоянный `remember me`
  намеренно отключён.
- Для публичного размещения дополнительно необходимы MFA, централизованный сбор
  и оповещения по журналам, резервное копирование, ротация секретов и проверка
  reverse proxy. Эти меры зависят от инфраструктуры и не заменяются кодом формы.

### Excel-импорт

Пользовательский импорт через `/inventory`:

1. скачать пустой шаблон или заполненный пример;
2. заполнить `Товары`, `Продажи`, `Остатки`, `Поставки`;
3. загрузить `.xlsx` до 20 МБ;
4. проверить preview и влияние на базу;
5. отдельно подтвердить импорт.

Preview не изменяет базу. Подтверждение заменяет продажи и остатки только
активного филиала и никогда не удаляет данные остальных филиалов. Одновременные
импорты одного филиала блокируются. Перед заменой создаётся резервная копия.
Внешний идентификатор товара — общий SKU, а не внутренний ID SQLite.

Очистка временных артефактов:

```bash
php artisan rayventory:cleanup
```

Команда удаляет просроченные previews, jobs, отчёты и историю, сохраняя десять
последних резервных копий. Scheduler запускает её ежедневно в 03:30.

## Production ML runtime

Laravel запускает `ml/predict_cli.py` отдельным процессом. Действия:

```text
simulate  — прогноз одного товара с overrides
planning  — общий план закупок
report    — создание PDF/PPTX
```

Обмен выполняется одной JSON-строкой, payload обычно передаётся в Base64. Нельзя
добавлять отладочный вывод в stdout CLI: это сломает JSON-протокол. Диагностику
направлять в stderr.

Laravel передаёт `ML_BRANCH_ID`; Python фильтрует `branch_products`, продажи,
остатки и поставки до построения прогноза. Артефакты моделей и отчётов хранятся
в филиальных подкаталогах.

Встроенная модель — `seasonal-robust-v1` с диапазоном q10–q90. При повреждённом
или несовместимом реестре runtime возвращается к baseline с предупреждением.

## Исследовательский ML-контур

Исследования отделены от runtime, чтобы обычный запуск не требовал PyTorch.
Создайте `.venv-ml` по инструкции тестирования и задайте:

```dotenv
ML_RESEARCH_PYTHON=/absolute/path/to/luch-magistratura/.venv-ml/bin/python
```

```bash
.venv-ml/bin/python ml/research_cli.py --help
.venv-ml/bin/python ml/research_cli.py <command> --help
```

Команды: `prepare-m5`, `prepare-uci`, `prepare-local`, `prepare-excel`, `analyze`,
`tune`, `scenarios`, `train`, `scale`, `report`.

### Локальная SQLite

Минимум для SKU — 175 дней, рекомендуется 365:

```bash
.venv-ml/bin/python ml/research_cli.py prepare-local
.venv-ml/bin/python ml/research_cli.py train \
  --data data/processed/local-inventory/local_inventory.csv.gz \
  --manifest data/processed/local-inventory/manifest.json
```

SQLite открывается только для чтения; производные файлы идут в `data/processed/`.

### UCI Online Retail II

```bash
curl -L -o /tmp/online-retail-ii.zip \
  'https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip'
mkdir -p data/raw/uci-online-retail
unzip /tmp/online-retail-ii.zip -d data/raw/uci-online-retail
.venv-ml/bin/python ml/research_cli.py prepare-uci --series 300 --seed 42
.venv-ml/bin/python ml/research_cli.py analyze \
  --data data/processed/uci-online-retail/uci_online_retail_subset.csv.gz \
  --manifest data/processed/uci-online-retail/manifest.json
.venv-ml/bin/python ml/research_cli.py train
```

### Excel без изменения рабочей базы

```bash
.venv-ml/bin/python ml/research_cli.py prepare-excel \
  --source rayventory_filled_example.xlsx
.venv-ml/bin/python ml/research_cli.py train \
  --data data/processed/excel-inventory/excel_inventory.csv.gz \
  --manifest data/processed/excel-inventory/manifest.json \
  --models lstm gru transformer --epochs 30 --patience 5 --folds 3
```

### Tuning и сценарии

```bash
# Smoke
.venv-ml/bin/python ml/research_cli.py tune \
  --preset smoke --epochs 3 --folds 1

# Длительные полные запуски
.venv-ml/bin/python ml/research_cli.py tune \
  --preset full --epochs 30 --patience 5 --folds 3
.venv-ml/bin/python ml/research_cli.py scenarios \
  --models lstm gru transformer --epochs 30 --patience 5 --folds 3
```

`scale` проверяет 10/100/300 рядов. `report` объединяет эксперименты, сценарии и
масштабирование в Markdown и SVG.

Сравниваются seasonal naive, медиана 28 дней, Croston-SBA, адаптивные baseline и
LSTM/GRU/Transformer. Нормализация строится только по train каждого rolling-окна,
выбор маршрута — по validation, финальные метрики — по более позднему test. Нельзя
допускать утечку будущих данных при изменении pipeline.

## Реестр и публикация моделей

Candidate проверяется на минимум трёх rolling-окнах, корректность метрик,
локальное происхождение данных и совместимость с runtime. Модель на UCI нельзя
публиковать в production. Локальные роутеры упаковываются в
`local-demand-router-v1`. Публикация требует явного `PROMOTE`, предыдущая версия
архивируется.

После Excel-импорта при достаточной истории очередь создаёт приватный датасет,
оценивает baseline, регистрирует candidate и ждёт ручной публикации. Для этого
должен работать `queue:work`.

## API

| Метод и путь | Назначение |
|---|---|
| `GET/POST /api/branches` | Список/создание филиалов |
| `GET /api/branches-summary` | Центральная сводка |
| `GET/POST /api/users` | Пользователи и роли |
| `GET /api/dashboard-stats` | Показатели склада |
| `GET /api/stock` | Товары и остатки |
| `POST /api/stock/update` | Обновить остаток |
| `GET /api/purchase-plan` | Рассчитать закупки |
| `POST /api/purchase-plan/export` | Скачать план Excel |
| `POST /api/simulate` | Синхронная симуляция |
| `POST /api/generate-report` | Создать PDF/PPTX |
| `POST /api/inventory/import/preview` | Проверить Excel |
| `POST /api/inventory/import/confirm` | Подтвердить импорт |
| `GET /api/model-health` | Последняя оценка модели |
| `GET /api/training-readiness` | Готовность локальных данных |
| `GET/POST /api/training-pipeline` | Статус/запуск pipeline |
| `GET /api/experiments` | Эксперименты |
| `GET /api/models` | Реестр моделей |
| `POST /api/models/candidates` | Создать candidate |
| `POST /api/models/{id}/promote` | Опубликовать модель |
| `GET /api/dataset-analysis` | EDA-профиль |
| `GET /api/tuning` | Последний tuning |
| `GET /api/scenarios` | Последний benchmark |
| `GET /api/research-report` | Исследовательский отчёт |

Актуальный список: `php artisan route:list --except-vendor`.

## Локальные артефакты

| Каталог | Содержимое |
|---|---|
| `storage/app/rayventory/` | Рабочая SQLite |
| `storage/app/branches/{id}/` | Preview, история и backup импорта филиала |
| `storage/app/reports/branches/{id}/` | PDF/PPTX филиала |
| `storage/app/model-health/branches/{id}/` | Снимки backtesting |
| `storage/app/model-registry/branches/{id}/` | Реестр моделей |
| `storage/app/models/branches/{id}/` | Runtime-артефакты |
| `storage/app/training-jobs/branches/{id}/` | Состояния обучения |
| `storage/app/experiments/branches/{id}/` | Эксперименты |
| `storage/app/tuning/branches/{id}/` | Tuning |
| `storage/app/scenarios/branches/{id}/` | Benchmarks |
| `storage/app/research-report/branches/{id}/` | Сводки и графики |
| `data/raw/` | Внешние данные |
| `data/processed/` | Производные наборы |

Не коммитить реальные складские данные, отчёты, модели, `.env`, ключи, токены и
пользовательские Excel-файлы.

## Типичные ошибки

`Failed opening required vendor/autoload.php`:

```bash
composer install --no-interaction --prefer-dist
```

`MissingAppKeyException` при запуске сайта:

```bash
test -f .env || cp .env.example .env
php artisan key:generate
```

В PHPUnit используется отдельный безопасный ключ из `phpunit.xml`.

`Could not open input file: artisan`: команда запущена не из корня проекта.

Проблемы Python:

```bash
.venv/bin/python --version
.venv/bin/python -c 'import numpy, pandas, matplotlib, reportlab, pptx'
php artisan config:clear
```

`No module named openpyxl` или `torch`: нужен `.venv-ml` с
`requirements-ml.txt`.

Проблемы SQLite:

```bash
php -m | grep -E 'pdo_sqlite|sqlite3'
php artisan rayventory:setup
```

Очередь остаётся в `queued`: запустить `php artisan queue:work` и проверить
`storage/logs/laravel.log`.

## Безопасный порядок изменений

1. Проверить `git status --short --branch`.
2. Читать только относящиеся к задаче route/controller/service/test.
3. Не трогать demo-seed и пользовательские артефакты.
4. Внести минимальное изменение и обновить тест.
5. Запустить PHPUnit, Pint и релевантные Python-тесты.
6. Проверить diff и отсутствие временных файлов в Git.

При изменении контракта Laravel ↔ Python синхронно проверять `MlBridge`,
`predict_cli.py`, JavaScript-клиент и тесты. При изменении схемы добавлять новую
миграцию, не переписывать существующую рабочую базу вручную.
