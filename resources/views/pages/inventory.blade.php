@extends('layouts.app', ['title' => 'Склад', 'page' => 'inventory', 'section' => 'INVENTORY', 'heading' => 'Управление складом'])
@section('content')
<div class="page-intro"><div><span class="eyebrow">INVENTORY CONTROL / 02</span><h2>Остатки и доступность</h2><p>Контролируйте запасы в реальном времени и быстро фиксируйте изменения.</p></div><button class="button primary" id="refresh-inventory">↻ Синхронизировать</button></div>
<section class="panel excel-import-panel">
    <div class="excel-import-copy">
        <span class="panel-kicker">DATA ONBOARDING / EXCEL</span>
        <h3>Подключите свои данные</h3>
        <p>Начните с пустого шаблона или изучите заполненный пример за 12 месяцев. После загрузки мы сначала покажем период, найденные данные и предупреждения — ничего не изменится без вашего подтверждения.</p>
        <div class="excel-steps"><span><b>1</b> Подготовить Excel</span><span><b>2</b> Проверить превью</span><span><b>3</b> Подтвердить импорт</span></div>
    </div>
    <div class="excel-import-actions">
        <a class="button ghost" href="{{ route('inventory.template') }}">↓ Пустой шаблон</a>
        <a class="button ghost" href="{{ route('inventory.template', ['example' => 1]) }}">↗ Заполненный пример</a>
        <label class="button primary excel-file-button" for="inventory-excel">Выбрать Excel</label>
        <input id="inventory-excel" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden>
        <button class="button primary" id="import-inventory" disabled>Проверить файл</button>
        <small id="excel-file-name">Файл не выбран · максимум 20 МБ</small>
    </div>
</section>
<section class="panel import-preview hidden" id="import-preview" aria-live="polite">
    <div class="panel-header"><div><span class="panel-kicker">IMPORT REVIEW / SAFE MODE</span><h3>Проверьте данные перед заменой</h3><p id="import-period"></p></div><span class="status-pill" id="import-quality">ГОТОВО</span></div>
    <div class="import-preview-metrics" id="import-preview-metrics"></div>
    <div class="import-warnings hidden" id="import-warnings"></div>
    <div class="import-impact"><b>Что изменится после подтверждения</b><div id="import-impact-grid"></div></div>
    <div class="import-sample"><b>Пример распознанных товаров</b><div class="table-scroll"><table class="data-table"><thead><tr><th>SKU</th><th>Название</th><th>Категория</th><th>Срок поставки</th><th>Цена</th></tr></thead><tbody id="import-sample-rows"></tbody></table></div></div>
    <div class="import-mapping"><b>Сопоставление колонок</b><p>Все обязательные поля распознаны по заголовкам шаблона. На этом этапе база ещё не изменена.</p></div>
    <div class="import-confirm-row"><span>Подтверждение заменит текущие товары, продажи, остатки и поставки. Перед заменой будет создана резервная копия.</span><button class="button primary" id="confirm-inventory-import">Подтвердить импорт</button></div>
</section>
<section class="inventory-toolbar"><div class="search-box"><span>⌕</span><input id="stock-search" type="search" placeholder="Поиск товара или категории..."></div><select id="stock-filter"><option value="all">Все статусы</option><option value="risk">Требуют внимания</option><option value="ok">В норме</option></select><span class="result-count" id="result-count">Загрузка...</span></section>
<section class="panel inventory-panel"><div class="panel-header"><div><span class="panel-kicker">WAREHOUSE / CURRENT SNAPSHOT</span><h3>Каталог запасов</h3></div><span class="updated-at">● обновляется автоматически</span></div><div class="table-scroll"><table class="data-table inventory-table"><thead><tr><th>Товар</th><th>Категория</th><th>Цена за ед.</th><th>Lead time</th><th>Остаток</th><th>Статус</th><th></th></tr></thead><tbody id="inventory-stock"></tbody></table></div></section>
<div class="drawer-backdrop" id="stock-modal"><div class="modal"><button class="modal-close" onclick="closeStockModal()">×</button><span class="eyebrow">STOCK UPDATE</span><h3 id="modal-name">Изменение остатка</h3><p>Новое значение будет сразу отражено в прогнозах.</p><label>Текущее количество<input id="modal-qty" type="number" min="0"></label><button class="button primary full" id="modal-save">Сохранить изменения <span>→</span></button></div></div>
@endsection
