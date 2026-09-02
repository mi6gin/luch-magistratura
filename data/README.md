# Исследовательские данные

Сырые наборы и производные выборки не коммитятся в Git. Основной источник —
[M5 Forecasting Accuracy](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data).

1. Примите правила соревнования Kaggle и создайте API token в настройках аккаунта.
   Сохраните полученный `kaggle.json` в `~/.kaggle/kaggle.json` и ограничьте права
   командой `chmod 600 ~/.kaggle/kaggle.json`.
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
