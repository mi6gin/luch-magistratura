@extends('layouts.app', ['title' => 'Симулятор', 'page' => 'simulator', 'section' => 'SCENARIO LAB', 'heading' => 'Лаборатория сценариев'])
@section('content')
<div class="page-intro"><div><span class="eyebrow">WHAT-IF ENGINE / 03</span><h2>Измените условие — <strong>увидьте будущее</strong></h2><p>Параметры пересчитывают спрос, диапазон неопределённости и траекторию остатка без изменения рабочих данных.</p></div><span class="model-badge"><span class="pulse"></span> LIVE RECALC</span></div>

<section class="simulation-kpis" id="simulation-kpis">
    <article><span>Спрос за 30 дней</span><b id="sim-demand-total">—</b><small>медианный сценарий</small></article>
    <article><span>Остаток к концу</span><b id="sim-stock-end">—</b><small>расчётное значение</small></article>
    <article><span>Диапазон спроса</span><b id="sim-demand-range">—</b><small>q10 → q90</small></article>
    <article><span>Качество данных</span><b id="sim-quality">—</b><small id="sim-quality-note">ожидаем расчёт</small></article>
</section>

<section class="sim-layout dynamic-simulator">
    <article class="panel sim-controls">
        <div class="panel-header"><div><span class="panel-kicker">INPUT PARAMETERS</span><h3>Настройка сценария</h3><p>Изменения применяются автоматически.</p></div><span class="auto-badge">AUTO</span></div>
        <label class="field-label">Выберите товар<select id="sim-product"></select></label>
        <label class="switch-row"><span><b>Промо-признак</b><small>Используется измеренный эффект акций</small></span><input id="sim-promo" type="checkbox"><i></i></label>
        <label class="field-label is-disabled">Изменение цены <output id="price-label">Недоступно</output><input id="sim-price" class="range" type="range" min="-50" max="50" step="5" value="0" aria-describedby="price-hint" disabled><small id="price-hint" class="field-hint">Эластичность появится после накопления истории цен.</small></label>
        <div class="scenario-note"><span>✦</span><p>Сценарий локален и не изменяет остатки или заказы филиала.</p></div>
        <button class="button primary full" id="run-simulation">Пересчитать сейчас <span>↗</span></button>
    </article>
    <article class="panel chart-panel">
        <div class="panel-header"><div><span class="panel-kicker">OUTPUT / 30 DAYS</span><h3>Траектория спроса и запаса</h3><p id="simulation-status">Выберите товар — расчёт запустится автоматически</p></div><div class="chart-modes" role="group" aria-label="Режим графика"><button class="is-active" data-chart-mode="all">Всё</button><button data-chart-mode="demand">Спрос</button><button data-chart-mode="stock">Запас</button></div></div>
        <div class="large-chart"><canvas id="simulation-chart"></canvas><div class="chart-empty" id="chart-empty"><span>⌁</span><b>Строим цифровой сценарий</b><small>Расчёт начнётся после загрузки товара</small></div></div>
        <div class="timeline-hint"><span>←</span><p>Наведите на любую дату, чтобы сравнить спрос, границы прогноза и остаток.</p><span>→</span></div>
    </article>
</section>
@endsection
