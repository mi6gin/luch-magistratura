@extends('layouts.app', ['title' => 'Обзор', 'page' => 'dashboard', 'section' => 'LIVE OPERATIONS', 'heading' => 'Центр управления'])
@section('content')
<div class="page-intro command-intro">
    <div><span class="eyebrow">{{ now()->locale('ru')->isoFormat('dddd · DD MMM YYYY') }} / LIVE</span><h2>Пульс вашего <strong>филиала</strong></h2><p>От спроса до поставки — риски, капитал и решения в одном живом контуре.</p></div>
    <div class="intro-actions"><button class="button ghost" id="presentation-mode">◫ Режим презентации</button><a href="{{ route('simulator') }}" class="button primary">Открыть симулятор <span>↗</span></a></div>
</div>

<section class="hero-grid"><article class="hero-card command-hero">
    <div class="hero-mesh" aria-hidden="true"></div><div class="hero-orbit orbit-one"></div><div class="hero-orbit orbit-two"></div>
    <div class="hero-copy"><span class="signal-tag"><span class="pulse"></span> MODEL BRIEFING / LIVE</span><h3 id="briefing">Система анализирует последние данные...</h3><p>Риски пересчитываются по фактическим остаткам и прогнозному диапазону выбранного филиала.</p><a href="#operations-map" class="text-link">Исследовать сигналы <span>↓</span></a></div>
    <div class="hero-stat"><span>RISK INDEX</span><b id="risk-index">--</b><small>stock exposure</small><i class="risk-ring" aria-hidden="true"></i></div>
</article></section>

<section class="metric-grid live-metrics">
    <article class="metric-card cyan" data-tilt><div class="metric-top"><span>Стоимость склада</span><i>◇</i></div><b id="total" class="loading-value">—</b><small><strong>LIVE</strong> капитал в запасах</small><span class="metric-spark" aria-hidden="true"></span></article>
    <article class="metric-card orange" data-tilt><div class="metric-top"><span>Зона риска</span><i>!</i></div><b id="critical" class="loading-value">—</b><small>требуют решения сейчас</small><span class="metric-spark risk" aria-hidden="true"></span></article>
    <article class="metric-card lime" data-tilt><div class="metric-top"><span>Контур прогноза</span><i>✦</i></div><b id="model-status">SAFE</b><small>q10—q90 · контроль baseline</small><span class="metric-spark model" aria-hidden="true"></span></article>
    <article class="metric-card violet" data-tilt><div class="metric-top"><span>Горизонт</span><i>◷</i></div><b>30<sup>дней</sup></b><small>скользящее окно решений</small><span class="metric-spark time" aria-hidden="true"></span></article>
</section>

<section class="operations-grid" id="operations-map">
    <article class="panel inventory-map-panel">
        <div class="panel-header"><div><span class="panel-kicker">01 / INVENTORY CONSTELLATION</span><h3>Живая карта запасов</h3><p>Размер — стоимость позиции, цвет — уровень риска. Нажмите на узел для симуляции.</p></div><div class="map-legend"><span><i class="ok"></i> норма</span><span><i class="watch"></i> внимание</span><span><i class="danger"></i> риск</span></div></div>
        <div class="inventory-map" id="inventory-map"><div class="map-radar" aria-hidden="true"></div><p class="map-empty">Строим карту филиала…</p></div>
    </article>
    <article class="panel activity-panel">
        <div class="panel-header"><div><span class="panel-kicker">02 / EVENT STREAM</span><h3>Центр событий</h3><p>Что изменилось и где требуется внимание.</p></div><span class="live-dot">LIVE</span></div>
        <div class="activity-stream" id="activity-stream"><div class="activity-skeleton"></div><div class="activity-skeleton"></div><div class="activity-skeleton"></div></div>
    </article>
</section>

<section class="panel decision-flow-panel">
    <div class="panel-header"><div><span class="panel-kicker">03 / DECISION PIPELINE</span><h3>От сигнала к действию</h3><p>Каждый этап использует результат предыдущего и сохраняет объяснение решения.</p></div><a href="{{ route('purchases') }}" class="button ghost">Открыть очередь <span>→</span></a></div>
    <div class="decision-flow" id="decision-flow">
        <article class="is-complete"><i>01</i><span><b>Продажи</b><small>фактическая история</small></span></article><em>→</em>
        <article class="is-complete"><i>02</i><span><b>Прогноз</b><small>q10 · q50 · q90</small></span></article><em>→</em>
        <article class="is-active"><i>03</i><span><b>Остаток</b><small id="flow-stock">проверяем</small></span></article><em>→</em>
        <article><i>04</i><span><b>Риск</b><small id="flow-risk">проверяем</small></span></article><em>→</em>
        <article><i>05</i><span><b>Заказ</b><small>очередь действий</small></span></article>
    </div>
</section>

<section class="content-grid dashboard-panels">
    <article class="panel panel-wide"><div class="panel-header"><div><span class="panel-kicker">04 / PRIORITY QUEUE</span><h3>Состояние склада</h3><p>Позиции с минимальным остатком показаны первыми.</p></div><a href="{{ route('inventory') }}" class="button ghost">Весь склад <span>→</span></a></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Товар</th><th>Категория</th><th>Остаток</th><th>Сигнал</th><th></th></tr></thead><tbody id="dashboard-stock"></tbody></table></div></article>
    <article class="panel"><div class="panel-header"><div><span class="panel-kicker">05 / CAPITAL MIX</span><h3>Капитал по категориям</h3></div></div><div class="donut-wrap"><canvas id="category-chart"></canvas><div class="donut-core"><small>КАТЕГОРИИ</small><b id="category-count">—</b></div></div></article>
</section>

<section class="quick-actions"><span class="panel-kicker">QUICK ACTIONS</span><div><a href="{{ route('inventory') }}" class="quick-card"><i>＋</i><span><b>Обновить остатки</b><small>Синхронизация склада</small></span><em>→</em></a><a href="{{ route('reports') }}" class="quick-card"><i>▧</i><span><b>Новый отчёт</b><small>PDF + презентация</small></span><em>→</em></a><a href="{{ route('simulator') }}" class="quick-card"><i>⌁</i><span><b>Проверить сценарий</b><small>Диапазон спроса и остатки</small></span><em>→</em></a></div></section>
<button class="presentation-exit" id="presentation-exit">Закрыть презентацию ×</button>
@endsection
