from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path


NEURAL = {"lstm", "gru", "transformer"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _forecast_svg(model: str, preview: dict, path: Path) -> None:
    actual = preview["actual"]
    predicted = preview["q50"]
    low = preview["q10"]
    high = preview["q90"]
    values = actual + predicted + low + high
    maximum = max(max(values), 1)
    width, height, left, top, plot_w, plot_h = 920, 420, 60, 55, 820, 300

    def points(series):
        return " ".join(
            f"{left + index * plot_w / max(len(series) - 1, 1):.1f},{top + plot_h - value / maximum * plot_h:.1f}"
            for index, value in enumerate(series)
        )

    band = points(low) + " " + " ".join(reversed(points(high).split()))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#08131d"/><text x="60" y="30" fill="#ffffff" font-family="Arial" font-size="20" font-weight="700">{html.escape(model.upper())}: факт и прогноз</text>
<text x="880" y="30" fill="#91a9b7" text-anchor="end" font-family="Arial" font-size="13">{html.escape(str(preview['series_id']))}, горизонт 28 дней</text>
<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#385466"/><line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#385466"/>
<polygon points="{band}" fill="#46e6ff" opacity="0.14"/><polyline points="{points(actual)}" fill="none" stroke="#ff7440" stroke-width="3"/><polyline points="{points(predicted)}" fill="none" stroke="#46e6ff" stroke-width="3"/>
<text x="60" y="392" fill="#ff7440" font-family="Arial" font-size="13">● Факт</text><text x="145" y="392" fill="#46e6ff" font-family="Arial" font-size="13">● Q50 прогноз</text><text x="285" y="392" fill="#91a9b7" font-family="Arial" font-size="13">полоса — Q10…Q90</text>
</svg>'''
    path.write_text(svg, encoding="utf-8")


def build_research_report(experiment_path: Path, scenarios_path: Path, scalability_path: Path, output_dir: Path) -> dict:
    experiment, scenarios, scalability = map(_load, (experiment_path, scenarios_path, scalability_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    neural_results = [item for item in experiment["results"] if item["model"] in NEURAL]
    neural_ranked = sorted(neural_results, key=lambda item: item["metrics"]["wape_pct"])
    overall = sorted(experiment["results"], key=lambda item: item["metrics"]["wape_pct"])
    fastest_neural = min(neural_results, key=lambda item: item["training_seconds"])
    simplest_neural = min(neural_results, key=lambda item: item["parameter_count"])
    largest_scale = scalability["results"][-1]
    scale_models = {item["model"]: item for item in largest_scale["models"]}
    scale_fastest = min(scale_models.values(), key=lambda item: item["training_seconds"])
    scenario_recommendations = [{
        "scenario": item["scenario"],
        "recommended_neural": item["best_neural"],
        "overall_winner": item["winner"],
    } for item in scenarios["scenarios"]]
    for result in neural_results:
        preview = result.get("forecast_preview")
        if preview:
            _forecast_svg(result["model"], preview, output_dir / f"forecast-{result['model']}.svg")
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment_id": experiment["experiment_id"],
        "dataset": experiment["dataset"]["dataset"],
        "rolling_folds": experiment["rolling_folds"],
        "overall_winner": overall[0]["model"],
        "best_neural": neural_ranked[0]["model"],
        "ranking": [{
            "model": item["model"], "wape_pct": item["metrics"]["wape_pct"],
            "wape_std": item["metrics"].get("wape_pct_std", 0),
            "training_seconds": item["training_seconds"], "parameter_count": item["parameter_count"],
        } for item in overall],
        "scenario_recommendations": scenario_recommendations,
        "scalability": scalability["results"],
        "recommendations": [
            f"Точность: на загруженном Excel использовать {overall[0]['model']}, пока нейросеть не покажет меньший WAPE на трёх rolling-окнах.",
            f"Лучшая нейросеть для этого набора — {neural_ranked[0]['model']} с WAPE {neural_ranked[0]['metrics']['wape_pct']:.2f}%.",
            f"Производительность: быстрее всех на Excel обучается {fastest_neural['model']} ({fastest_neural['training_seconds']:.3f} с).",
            f"Сложность: минимальное число параметров у {simplest_neural['model']} ({simplest_neural['parameter_count']}).",
            f"Масштабирование: на {largest_scale['series']} рядах быстрее обучается {scale_fastest['model']} ({scale_fastest['training_seconds']:.3f} с); Transformer применять только при подтверждённом выигрыше точности.",
            "Гибкость: для сезонности, тренда, промо и внешних факторов выбирать архитектуру по сценарной таблице, а не назначать одну модель всем SKU.",
        ],
        "conclusion": (
            f"Для набора «{experiment['dataset']['dataset']}» минимальную ошибку показала модель {overall[0]['model']}; "
            f"среди нейросетей — {neural_ranked[0]['model']}. Выбор архитектуры следует выполнять по типу спроса, "
            "а не по сложности модели: итоговый кандидат обязан устойчиво превосходить baseline на нескольких временных окнах."
        ),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Итог исследовательского сравнения", "", summary["conclusion"], "",
        "## Точность, производительность и сложность", "",
        "| Модель | WAPE, % | σ WAPE | Обучение, с | Параметры |", "|---|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {item['model']} | {item['wape_pct']:.4f} | {item['wape_std']:.4f} | {item['training_seconds']:.3f} | {item['parameter_count']} |"
        for item in summary["ranking"]
    )
    lines += ["", "## Рекомендации по сценариям", "", "| Сценарий | Лучшая нейросеть | Общий победитель |", "|---|---|---|"]
    lines.extend(f"| {item['scenario']} | {item['recommended_neural']} | {item['overall_winner']} |" for item in scenario_recommendations)
    lines += ["", "## Практические рекомендации", ""]
    lines.extend(f"- {item}" for item in summary["recommendations"])
    lines += ["", "## Масштабируемость", "", "| Рядов | Строк | Полное время, с | Пиковая память процесса, МБ |", "|---:|---:|---:|---:|"]
    lines.extend(
        f"| {item['series']} | {item['rows']} | {item['wall_seconds']:.3f} | {item['process_peak_memory_mb']:.2f} |"
        for item in scalability["results"]
    )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
