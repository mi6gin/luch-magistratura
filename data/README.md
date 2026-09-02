# Исследовательские данные

## Основной набор: UCI Online Retail II

Основной контур использует открытый набор
[UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
с лицензией CC BY 4.0. Аккаунт и API-токен не нужны.

```bash
curl -L -o /tmp/online-retail-ii.zip "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
mkdir -p data/raw/uci-online-retail
unzip /tmp/online-retail-ii.zip -d data/raw/uci-online-retail
.venv-ml/bin/python ml/research_cli.py prepare-uci --series 300 --seed 42
```

Импортёр исключает отменённые счета, возвраты, нулевую цену и служебные товарные
коды, агрегирует транзакции Великобритании в ежедневные ряды, добавляет дни без
продаж как нули и рассчитывает цену без использования будущего при обучении.

## Дополнительный набор: M5

Сырые наборы и производные выборки не коммитятся в Git. Дополнительный источник —
[M5 Forecasting Accuracy](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data).

1. Примите правила соревнования Kaggle и создайте API token в настройках аккаунта.
   Новый строковый токен сохраните без JSON и кавычек в `~/.kaggle/access_token`,
   затем выполните `chmod 600 ~/.kaggle/access_token`. Формат `kaggle.json`
   используется только для legacy-ключа `username/key`.
2. Скачайте и распакуйте данные:

```bash
kaggle competitions download -c m5-forecasting-accuracy -p data/raw/m5
unzip data/raw/m5/m5-forecasting-accuracy.zip -d data/raw/m5
```

3. Создайте воспроизводимую стратифицированную подвыборку:

```bash
.venv-ml/bin/python ml/research_cli.py prepare-m5 --series 300 --seed 42
```

Команда создаёт `data/processed/m5/m5_subset.csv.gz` и `manifest.json` с
источником, периодом, размером выборки и границами train/validation/test.
