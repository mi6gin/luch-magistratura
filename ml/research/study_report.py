"""Publish the completed frozen study, figures and runnable neural examples."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .dataset import FEATURES, load_experiment_data, normalize_from_train
from .demo import predict
from .experiment import run_experiment
from .metrics import point_metrics, segment_metrics
from .models import build_model, require_torch
from .study import MODELS, write
from .trainer import TrainingConfig


def neural(document: dict, model: str) -> dict:
    return next(r for r in document["folds"][0]["results"] if r["model"] == model)


def mean_std(values) -> dict:
    numbers = np.asarray(list(values), dtype=float)
    return {"mean": float(numbers.mean()), "std": float(numbers.std(ddof=1)) if len(numbers) > 1 else 0.0}


def export_forecasts(root: Path, destination: Path, study: dict) -> dict:
    """Recompute frozen forecasts for export, never fit or select anything."""
    torch, _ = require_torch()
    manifest = json.loads((root / "data/100/manifest.json").read_text(encoding="utf-8"))
    cache = {}
    for history in {90, *(d["config"]["history_days"] for d in study["final"])}:
        _, scales, _, _, test = load_experiment_data(str(root / "data/100/data.csv.gz"), manifest, history, 28)
        cache[history] = (scales, test)
    common = cache[90][1]
    segments = {}
    for document in study["final"]:
        config = document["config"]
        name = document["results"][-1]["model"]
        checkpoint = torch.load(root / "artifacts" / document["experiment_id"] / "fold-1" / f"{name}.pt",
                                map_location="cpu", weights_only=True)
        model = build_model(name, checkpoint["feature_count"], config["history_days"], 28,
                            config["hidden_size"], checkpoint["quantile_parameterization"])
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        scales, test = cache[config["history_days"]]
        if test[2] != common[2]:
            raise ValueError("Final forecasts do not share the same test origins")
        with torch.no_grad():
            predictions = np.concatenate([model(torch.from_numpy(test[0][i:i + config["batch_size"]])).numpy()
                                           for i in range(0, len(test[0]), config["batch_size"])])
        factors = np.asarray([scales.sales[series] for series in test[2]])[:, None]
        actual = test[1] * factors
        predictions = predictions * factors[..., None]
        stored = neural(document, name)["metrics"]["wape_pct"]
        if abs(point_metrics(actual, predictions[..., 1])["wape_pct"] - stored) > 0.001:
            raise ValueError("Exported predictions disagree with the frozen test result")
        key = f"{name}-{config['seed']}"
        segments[key] = segment_metrics(actual, predictions[..., 1], common[0][..., 0])
        dates = pd.date_range(pd.Timestamp(manifest["validation_end"]) + pd.Timedelta(days=1), periods=28)
        frame = pd.DataFrame({"series_id": np.repeat(test[2], 28), "date": np.tile(dates, len(test[2])),
                              "actual": actual.ravel(), **{f"q{q}": predictions[..., index].ravel()
                                                          for index, q in enumerate((10, 50, 90))}})
        directory = destination / "forecasts"
        directory.mkdir(parents=True, exist_ok=True)
        frame.to_csv(directory / f"{key}.csv.gz", index=False, compression="gzip")
    return segments


def publish(root: Path, destination: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    study = json.loads((root / "study.json").read_text(encoding="utf-8"))
    protocol = study["protocol"]
    study["tuning"] = [json.loads((root / "results" / f"tune-{index:02d}.json").read_text(encoding="utf-8"))
                       for index in range(1, len(protocol["tuning"]["trials"]) + 1)]
    project = Path(__file__).resolve().parents[2]
    study["code_sha256"] = {str(path.relative_to(project)).replace("\\", "/"): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                             for path in sorted((project / "ml").rglob("*.py"))}
    study["code_sha256_normalization"] = "LF line endings"
    study["installed_packages"] = sorted(
        ({"name": d.metadata["Name"], "version": d.version} for d in importlib.metadata.distributions()),
        key=lambda d: d["name"].lower())
    destination.mkdir(parents=True, exist_ok=True)
    public_data = destination / "data"
    public_data.mkdir(parents=True, exist_ok=True)
    for size in (100, 300):
        shutil.copyfile(root / f"data/{size}/data.csv.gz", public_data / f"{size}.csv.gz")
        data_manifest = json.loads((root / f"data/{size}/manifest.json").read_text(encoding="utf-8"))
        write(public_data / f"{size}.manifest.json", {**data_manifest, "files": {"data": f"{size}.csv.gz"}})
    baseline_path = root / "baseline-final.json"
    if not baseline_path.exists():
        baseline = run_experiment(root / "data/100/data.csv.gz", root / "data/100/manifest.json",
                                  root / "artifacts", [], TrainingConfig(history_days=90), folds=1)
        write(baseline_path, baseline)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    common_segments = export_forecasts(root, destination, study)
    study["common_history_segment_metrics"] = common_segments
    from .analysis import analyze_dataset
    profile = analyze_dataset(root / "data/100/data.csv.gz", root / "data/100/manifest.json",
                              destination / "data-profile.json")
    study["common_baselines"] = baseline
    write(destination / "study.json", study)
    write(destination / "protocol.json", protocol)
    pd.DataFrame({"id": protocol["excluded_pilot_ids"]}).to_csv(destination / "pilot-exclusions.csv", index=False)
    summary = {"final": [], "scenarios": [], "scaling": [], "baseline_history_days": 90}
    for model in MODELS:
        documents = [d for d in study["final"] if d["results"][-1]["model"] == model]
        runs = [neural(d, model) for d in documents]
        summary["final"].append({
            "model": model, "seeds": [d["config"]["seed"] for d in documents],
            "config": study["selection"][model]["config"],
            "metrics": {key: mean_std(r["metrics"][key] for r in runs)
                        for key in ("wape_pct", "mae", "rmse", "bias_pct", "risk_cost_pct", "coverage_pct")},
            "training_seconds": mean_std(r["training_seconds"] for r in runs),
            "inference_ms": mean_std(r["metrics"]["inference_ms"] for r in runs),
            "peak_memory_mb": mean_std(d["resource_measurement"]["peak_memory_mb"] for d in documents),
            "parameter_count": runs[0]["parameter_count"],
            "segments": {label: {key: mean_std(common_segments[f"{model}-{d['config']['seed']}"][label][key] for d in documents)
                                  for key in ("wape_pct", "bias_pct")}
                         for label in common_segments[f"{model}-42"]},
        })
    for scenario in protocol["scenarios"]["names"]:
        for model in MODELS:
            runs = [neural(r["experiment"], model) for r in study["scenarios"]
                    if r["scenario"] == scenario and r["model"] == model]
            summary["scenarios"].append({"scenario": scenario, "model": model,
                                         "wape_pct": mean_std(r["metrics"]["wape_pct"] for r in runs)})
    summary["scenario_baselines"] = {
        scenario: [r for r in next(item["experiment"] for item in study["scenarios"]
                                   if item["scenario"] == scenario and item["model"] == "lstm" and item["seed"] == 42)["results"]
                   if r["model"] not in MODELS]
        for scenario in protocol["scenarios"]["names"]}
    for size in protocol["scale"]["sizes"]:
        for model in MODELS:
            documents = [r["experiment"] for r in study["scaling"] if r["series"] == size and r["model"] == model]
            runs = [neural(d, model) for d in documents]
            summary["scaling"].append({"series": size, "model": model,
                                        "training_seconds": mean_std(r["training_seconds"] for r in runs),
                                        "inference_ms": mean_std(r["metrics"]["inference_ms"] for r in runs),
                                        "peak_memory_mb": mean_std(d["resource_measurement"]["peak_memory_mb"] for d in documents)})
    summary["baselines"] = baseline["results"]
    write(destination / "summary.json", summary)

    labels = [r["model"] for r in baseline["results"]] + list(MODELS)
    means = [r["metrics"]["wape_pct"] for r in baseline["results"]] + [r["metrics"]["wape_pct"]["mean"] for r in summary["final"]]
    errors = [0] * len(baseline["results"]) + [r["metrics"]["wape_pct"]["std"] for r in summary["final"]]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(labels, means, xerr=errors, color=["#8796a8"] * len(baseline["results"]) + ["#3987ca"] * 3)
    ax.set_xlabel("Test WAPE (%), lower is better; error bars: seed sample SD")
    fig.tight_layout()
    fig.savefig(destination / "accuracy.svg")
    fig.savefig(destination / "accuracy.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for model in MODELS:
        runs = [r for r in summary["scaling"] if r["model"] == model]
        for ax, key, label in zip(axes, ("training_seconds", "peak_memory_mb"), ("Training seconds (3 epochs)", "Whole process peak RAM (MB)")):
            ax.errorbar([r["series"] for r in runs], [r[key]["mean"] for r in runs],
                        yerr=[r[key]["std"] for r in runs], marker="o", label=model)
            ax.set_xlabel("Series count")
            ax.set_ylabel(label)
            ax.legend()
    fig.tight_layout()
    fig.savefig(destination / "scaling.svg")
    fig.savefig(destination / "scaling.png", dpi=160)
    plt.close(fig)

    # Freeze one public input, with train-derived normalization, for all three prototypes.
    frame = pd.read_csv(root / "data/100/data.csv.gz", parse_dates=["date"], dtype={"id": str})
    manifest = json.loads((root / "data/100/manifest.json").read_text(encoding="utf-8"))
    normalized, scales = normalize_from_train(frame, manifest["train_end"])
    series = sorted(frame["id"].unique())[0]
    history = normalized.loc[normalized["id"].eq(series) & normalized["date"].le(pd.Timestamp(manifest["validation_end"]))].tail(90)
    demo_dir = destination / "demo"
    example_path = demo_dir / "example.json"
    write(example_path, {"series_id": series, "source": manifest["source"], "features": list(FEATURES),
                         "forecast_start": (pd.Timestamp(manifest["validation_end"]) + pd.Timedelta(days=1)).date().isoformat(),
                         "sales_scale": scales.sales[series], "normalized_history": history[list(FEATURES)].to_numpy().tolist()})
    for model in MODELS:
        document = next(d for d in study["final"] if d["config"]["seed"] == 42 and d["results"][-1]["model"] == model)
        checkpoint = root / "artifacts" / document["experiment_id"] / "fold-1" / f"{model}.pt"
        shutil.copyfile(checkpoint, demo_dir / f"{model}.pt")
        forecast = predict(demo_dir / f"{model}.pt", example_path)
        preview = neural(document, model)["metrics"]["forecast_preview"]
        if forecast["series_id"] != preview["series_id"] or not np.allclose(forecast["q50"], preview["q50"], atol=0.002):
            raise ValueError("Published demo differs from evaluated checkpoint")
        write(demo_dir / f"{model}-forecast.json", forecast)
        fig, ax = plt.subplots(figsize=(8, 3))
        days = np.arange(1, 29)
        ax.plot(days, preview["actual"], label="Observed sales", color="#303b46")
        ax.plot(days, forecast["q50"], label=f"{model} q50", color="#3987ca")
        ax.fill_between(days, forecast["q10"], forecast["q90"], alpha=0.2, label="q10–q90")
        ax.set(xlabel="Forecast day", ylabel="Sales units", title=f"Public UCI SKU {series}; seed 42 (prespecified)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(destination / f"forecast-{model}.svg")
        fig.savefig(destination / f"forecast-{model}.png", dpi=160)
        plt.close(fig)

    def fmt(value):
        return f"{value['mean']:.2f} ± {value['std']:.2f}"
    lines = ["# Основное исследование по ИУП", "",
             "Результаты сформированы из фактически завершённых запусков. Протокол зафиксирован до итогового test.", "",
             "100 товаров, 739 дней, train до 16.09.2011, validation до 11.11.2011, test 12.11–09.12.2011.",
             f"Нулевые дневные продажи: {profile['demand']['zero_sales_pct']:.2f}%. Это преимущественно редкий нерегулярный спрос. [Профиль набора](data-profile.json) описывает полный период после завершения эксперимента и не используется для выбора SKU или параметров.",
             "24 validation-конфигурации, максимум 20 эпох, patience 4; seeds итоговой оценки 42, 43, 44.",
             "Среднее ± выборочное стандартное отклонение описывает разброс seeds на одном test, не доверительный интервал переноса на другой склад.", "",
             "## Точность и производительность", "",
             "| Модель | WAPE % | Bias % | Coverage % | Обучение, с | Inference, мс | RAM, MB | Параметры |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in baseline["results"]:
        lines.append(f"| {r['model']} | {r['metrics']['wape_pct']:.2f} | {r['metrics']['bias_pct']:.2f} | — | — | — | — | 0 |")
    for r in summary["final"]:
        lines.append(f"| {r['model']} | {fmt(r['metrics']['wape_pct'])} | {fmt(r['metrics']['bias_pct'])} | {fmt(r['metrics']['coverage_pct'])} | {fmt(r['training_seconds'])} | {fmt(r['inference_ms'])} | {fmt(r['peak_memory_mb'])} | {r['parameter_count']} |")
    lines += ["", "Baseline оценивается при общей истории 90 дней; архитектурная история выбирается по validation. Полные MAE, RMSE, risk cost и сегменты: [summary.json](summary.json).",
              "Все прогнозы итоговых девяти checkpoint экспортированы в `forecasts/`; совпадение WAPE с зафиксированными результатами проверено. Это повторный inference сохранённых весов для экспорта, без нового обучения или подбора. Дополнительные сегментные таблицы используют общую историю 90 дней для классификации всех архитектур.",
              "Покрытие нужно сопоставлять с номинальными 80%. Положительный q10 исключает нулевые продажи из интервала, поэтому для редкого спроса эта параметризация может быть непригодна. Низкое покрытие означает, что интервалы нельзя применять как откалиброванный уровень сервиса; это выявленное ограничение прототипов, требующее отдельного будущего исследования.",
              "", "![Test comparison](accuracy.svg)", "", "## Гибкость: контролируемые сценарии", "",
              "Синтетические данные, 12 товаров × 540 дней, три seeds обучения. Будущие акции/цены не передаются модели; причинный эффект акции не оценивается.", "",
              "| Сценарий | LSTM WAPE % | GRU WAPE % | Transformer WAPE % | Лучший baseline | WAPE % |", "|---|---:|---:|---:|---|---:|"]
    for scenario in protocol["scenarios"]["names"]:
        best_baseline = min(summary["scenario_baselines"][scenario], key=lambda r: r["metrics"]["wape_pct"])
        lines.append("| " + scenario + " | " + " | ".join(fmt(next(r for r in summary["scenarios"] if r["scenario"] == scenario and r["model"] == model)["wape_pct"]) for model in MODELS)
                     + f" | {best_baseline['model']} | {best_baseline['metrics']['wape_pct']:.2f} |")
    lines += ["", "## Масштабируемость", "", "Фиксированные три эпохи, два seeds, свежий процесс на каждый замер, два CPU-потока. RAM включает интерпретатор, библиотеки и данные. Это измерение ресурсов, а не оценка точности после полного обучения.", "",
              "| Ряды | Модель | Обучение, с | RAM, MB |", "|---:|---|---:|---:|"]
    for r in summary["scaling"]:
        lines.append(f"| {r['series']} | {r['model']} | {fmt(r['training_seconds'])} | {fmt(r['peak_memory_mb'])} |")
    lines += ["", "![Scaling](scaling.svg)", "", "## Выбор модели", ""]
    ranking = sorted([(r["model"], r["metrics"]["wape_pct"]) for r in baseline["results"]] + [(r["model"], r["metrics"]["wape_pct"]["mean"]) for r in summary["final"]], key=lambda r: r[1])
    lines += [f"На данном test минимальный WAPE у **{ranking[0][0]}** ({ranking[0][1]:.2f}%). Это результат сравнения на одной выборке, а не гарантия для нового склада.",
              "Выбирать рабочую модель нужно по будущему validation конкретного склада, учитывать Bias, тип спроса, стоимость дефицита и вычислительные ограничения. Превосходство нейросети над baseline не является обязательным условием корректного исследования.", "",
              "Сегменты спроса и разброс seeds следует смотреть вместе с общей метрикой. При плохом покрытии интервала закупочные решения по q90 требуют отдельной калибровки и проверки уровня сервиса.", "",
              "Прототипы прогнозируют медиану q50, что при большом числе нулей может приводить к сильному недопрогнозу суммарного объёма. Для закупочной задачи с асимметричной стоимостью нужен отдельно выбранный и проверенный уровень прогноза. Победа по симметричной WAPE не доказывает оптимальность для закупок.", "",
              "## Демонстрация и воспроизведение", "",
              "Три сохранённых checkpoint и общий пример находятся в `demo/`. Пример содержит только публичные товарные данные UCI и нормализованную историю; данные покупателей не включены.", "",
              "```powershell", ".venv-ml\\Scripts\\python.exe -m ml.research.demo --checkpoint docs/research/full-study/demo/lstm.pt --example docs/research/full-study/demo/example.json",
              "# Аналогично gru.pt и transformer.pt", "```", "",
              "Источник: Chen, D. (2012), Online Retail II, DOI 10.24432/C5CG6D, CC BY 4.0. Веса и преобразованный пример получены в данном проекте.",
              "Полные результаты и loss curves: [study.json](study.json). Правила: [protocol.json](protocol.json). Теория и ограничения: [методология](../../RESEARCH_METHODOLOGY.md).", "",
              "Для полного повторения скачайте официальный `online_retail_II.xlsx`, установите `requirements-ml.txt` и запустите:", "", "```powershell",
              ".venv-ml\\Scripts\\python.exe -m ml.research.study --source data/raw/uci-online-retail/online_retail_II.xlsx --pilot docs/research/full-study/pilot-exclusions.csv --output storage/app/repeated-iup-study",
              ".venv-ml\\Scripts\\python.exe -m ml.research.study_report --study storage/app/repeated-iup-study --output docs/research/repeated-study", "```", "",
              "Запуски возобновляются из сохранённых результатов; изменение уже выполненной конфигурации отклоняется. Для нового протокола используйте новый каталог.", "",
              "## Пределы выводов", "", "Измеряются продажи одного магазина, доступность товара неизвестна. Предварительные SKU исключены, однако календарь и магазин общие. Внешняя валидация, GPU и промышленная нагрузка не проверены. Синтетические сценарии не заменяют реальные акции. Административные пункты ИУП и допуск к защите этим отчётом не подтверждаются."]
    best_neural = min(summary["final"], key=lambda r: r["metrics"]["wape_pct"]["mean"])
    fastest = min(summary["final"], key=lambda r: r["training_seconds"]["mean"])
    smallest = min(summary["final"], key=lambda r: r["parameter_count"])
    recommendations = [
        f"Среди нейросетей минимальный средний test WAPE у {best_neural['model']} ({fmt(best_neural['metrics']['wape_pct'])}%). Это кандидат для дальнейшей проверки точности, а не основание заменить лучший baseline.",
        f"При ограничении CPU-бюджета первым кандидатом для проверки на данном окружении будет {fastest['model']}: среднее обучение {fastest['training_seconds']['mean']:.2f} с. Нельзя переносить этот порядок скорости на GPU без измерений.",
        f"По размеру модели минимален {smallest['model']}: {smallest['parameter_count']} параметров. Меньшее число параметров не гарантирует меньшую RAM всего процесса или более быстрое обучение.",
    ]
    for scenario in protocol["scenarios"]["names"]:
        best = min((r for r in summary["scenarios"] if r["scenario"] == scenario), key=lambda r: r["wape_pct"]["mean"])
        recommendations.append(f"В синтетическом сценарии {scenario} лучший средний WAPE среди нейросетей у {best['model']} ({fmt(best['wape_pct'])}%). Для реального сценария нужен отдельный хронологический validation.")
    insertion = lines.index("## Демонстрация и воспроизведение")
    lines[insertion:insertion] = ["Рекомендации, непосредственно следующие из измерений:", ""] + [f"- {r}" for r in recommendations] + [""]
    capped = sum(neural(d, d["results"][-1]["model"])["epochs"] == d["config"]["max_epochs"] for d in study["final"])
    lines += ["", f"Лимита эпох достигли {capped} из {len(study['final'])} финальных запусков. Это сравнение при заранее ограниченном бюджете 20 эпох, а не доказательство достижения предельной точности или сходимости архитектур. Вывод о превосходстве baseline относится именно к этому протоколу."]
    lines += ["", "Обезличенные товарные ряды публичного UCI для 100 и 300 SKU включены в `data/` под лицензией источника CC BY 4.0. Исходный XLSX нужен для полного воспроизведения очистки и отбора, но обучение выбранных прототипов можно повторить по этим рядам. Целостность и полнота материалов проверяются командой:",
              "", "```powershell", ".venv-ml\\Scripts\\python.exe -m ml.research.verify_study --report docs/research/full-study", "```"]
    (destination / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    # Git checks out these text artifacts with LF on both Windows and Linux.
    for path in destination.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json", ".svg", ".csv"}:
            data = path.read_bytes()
            normalized = data.replace(b"\r\n", b"\n")
            if path.suffix == ".svg":
                normalized = b"\n".join(line.rstrip(b" \t") for line in normalized.split(b"\n"))
            if normalized != data:
                path.write_bytes(normalized)
    write(destination / "SHA256SUMS.json", {
        str(path.relative_to(destination)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(destination.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    publish(args.study.resolve(), args.output.resolve())
