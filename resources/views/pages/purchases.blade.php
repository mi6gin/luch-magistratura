@extends('layouts.app', ['title' => 'К закупке', 'page' => 'purchases', 'section' => 'REPLENISH', 'heading' => 'План закупок'])
@section('content')

<div class="page-intro purchases-intro">
    <div><span class="eyebrow">DEMAND → SUPPLY → ACTION / 04</span><h2>Что и когда заказать</h2><p>Приоритетный список закупок с объяснением расчёта, рисками и качеством исходных данных.</p></div>
    <button class="button primary" id="refresh-purchases">↻ Пересчитать</button>
</div>

<section class="metric-grid purchase-metrics">
    <article class="metric-card"><span>К заказу</span><strong id="purchase-units" class="loading-value">—</strong><small>единиц товара</small></article>
    <article class="metric-card"><span>Бюджет</span><strong id="purchase-value" class="loading-value">—</strong><small>рекомендуемый заказ</small></article>
    <article class="metric-card"><span>SKU в риске</span><strong id="purchase-risk" class="loading-value">—</strong><small>могут закончиться</small></article>
    <article class="metric-card"><span>Качество данных</span><strong id="purchase-quality" class="loading-value">—</strong><small id="purchase-quality-note">проверяем историю</small></article>
</section>

<section class="panel quality-panel">
    <div class="panel-header"><div><span class="panel-kicker">DATA CONFIDENCE</span><h3>Насколько можно доверять плану</h3></div><span class="updated-at" id="purchase-data-date">данные проверяются</span></div>
    <div class="quality-grid" id="quality-grid"></div>
    <div class="import-warnings hidden" id="purchase-warnings"></div>
</section>

<section class="panel purchase-panel">
    <div class="panel-header"><div><span class="panel-kicker">ACTION QUEUE</span><h3>Очередь закупок</h3><p>Сначала показаны позиции с риском дефицита и наибольшим объёмом вложений.</p></div><select id="purchase-filter"><option value="all">Все позиции</option><option value="order">Только к заказу</option><option value="risk">Только риск дефицита</option><option value="low-quality">Низкая уверенность</option></select></div>
    <div class="table-scroll"><table class="data-table purchase-table"><thead><tr><th>SKU / товар</th><th>На складе</th><th>В пути</th><th>Дней запаса</th><th>Заказать</th><th>Сумма</th><th>Дефицит</th><th>Уверенность</th><th></th></tr></thead><tbody id="purchase-rows"><tr><td colspan="9">Рассчитываем план закупок…</td></tr></tbody></table></div>
</section>

<div class="drawer-backdrop purchase-explainer" id="purchase-explainer" aria-hidden="true">
    <div class="modal purchase-explainer-card"><button class="modal-close" id="purchase-explainer-close" aria-label="Закрыть">×</button><span class="panel-kicker">RECOMMENDATION EXPLAINER</span><h3 id="explain-name">Расчёт рекомендации</h3><div id="explain-content"></div></div>
</div>
@endsection
