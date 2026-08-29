# Rayventory

Laravel-версия системы прогнозирования товарных запасов из проекта MAGA.

Цель миграции: сохранить текущие процессы, JSON-форматы API, SQLite-базу,
Python/PyTorch-движок, симулятор и генерацию PDF-отчётов.

## Установка

```bash
composer install
cp .env.example .env
php artisan key:generate
php artisan serve
```

По умолчанию проект использует существующую базу и ML-файлы из соседнего
проекта `MAGA`. После установки PHP/Composer нужно проверить пути `DB_DATABASE`,
`ML_ENGINE_PATH` и `ML_REPORTS_PATH` в `.env`.

## API

Сохранены маршруты `/api/ai-briefing`, `/api/dashboard-stats`, `/api/stock`,
`/api/stock/update`, `/api/simulate`, `/api/generate-report` и скачивание PDF.
