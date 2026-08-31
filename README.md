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

## Требования

- PHP 8.2 или новее;
- Composer 2;
- Python 3.11 или новее;
- расширение PHP `pdo_sqlite`.

Python-зависимости перечислены в `requirements.txt`.

## Локальная установка

```powershell
composer install
Copy-Item .env.example .env
php artisan key:generate
py -m pip install -r requirements.txt
php artisan rayventory:setup
php artisan serve
```

На Linux или macOS укажите `ML_PYTHON=python3` в `.env` и установите зависимости
командой `python3 -m pip install -r requirements.txt`.

Команда `rayventory:setup` создаёт рабочую SQLite-базу из поставляемого demo-seed.
Повторный запуск безопасен и не перезаписывает существующие данные. Для полного
сброса используйте `php artisan rayventory:setup --force`.

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
