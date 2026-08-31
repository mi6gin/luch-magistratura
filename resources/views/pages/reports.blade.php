@extends('layouts.app', ['title' => 'Отчёты', 'page' => 'reports', 'section' => 'REPORTS', 'heading' => 'Центр отчётности'])
@section('content')
<div class="page-intro reports-intro">
    <div>
        <span class="eyebrow">DECISION CENTER / 04</span>
        <h2>Материалы для решений</h2>
        <p>Подготовьте документ и презентацию по текущим данным, прогнозному диапазону и состоянию запасов.</p>
    </div>
    <span class="reports-count"><b>5</b><small>сценариев</small></span>
</div>

<section class="panel report-toolbar">
    <div class="report-toolbar-copy">
        <span class="panel-kicker">OUTPUT FORMAT</span>
        <h3>Выберите комплект</h3>
        <p>Можно сформировать один формат или сразу оба. По умолчанию выбран полный комплект.</p>
    </div>
    <fieldset class="format-selector">
        <legend class="panel-kicker">Форматы</legend>
        <div class="format-options">
            <label class="format-option">
                <input id="report-format-pdf" data-report-format type="checkbox" value="pdf" checked>
                <span><b>PDF</b><small>Документ для чтения</small></span>
            </label>
            <label class="format-option">
                <input id="report-format-pptx" data-report-format type="checkbox" value="pptx" checked>
                <span><b>PPTX</b><small>Редактируемая презентация</small></span>
            </label>
        </div>
        <p class="format-help">Файлы будут доступны отдельно после завершения генерации.</p>
    </fieldset>
</section>

<section class="report-grid" aria-label="Сценарии отчётов">
    <article class="report-card is-primary">
        <div class="report-card-top">
            <div class="report-icon cyan">◎</div>
            <span class="signal-tag"><span class="pulse"></span> BASELINE</span>
        </div>
        <span class="panel-kicker">STANDARD / q50</span>
        <h3>Базовый контур</h3>
        <p>Сводит текущие остатки и базовый прогноз в рабочий обзор. Выводы зависят от полноты исходных данных.</p>
        <div class="report-card-meta"><span>Остатки</span><span>q10-q90</span><span>Пополнение</span></div>
        <button class="button primary report-action" data-type="standard">Подготовить комплект <span>↗</span></button>
    </article>

    <article class="report-card">
        <div class="report-card-top"><div class="report-icon red">!</div><span class="report-code">01</span></div>
        <span class="panel-kicker">RISK / q90</span>
        <h3>Риск дефицита</h3>
        <p>Показывает верхнюю границу прогнозного спроса и позиции, где стоит проверить запас.</p>
        <button class="button ghost report-action" data-type="risk">Подготовить <span>→</span></button>
    </article>

    <article class="report-card">
        <div class="report-card-top"><div class="report-icon orange">⌁</div><span class="report-code">02</span></div>
        <span class="panel-kicker">CAPITAL / q10</span>
        <h3>Проверка излишков</h3>
        <p>Использует нижнюю границу спроса для ручной проверки избыточных остатков и капитала.</p>
        <button class="button ghost report-action" data-type="optimization">Подготовить <span>→</span></button>
    </article>

    <article class="report-card">
        <div class="report-card-top"><div class="report-icon violet">◌</div><span class="report-code">03</span></div>
        <span class="panel-kicker">RANGE / TREND</span>
        <h3>Динамика спроса</h3>
        <p>Сопоставляет q10, q50 и q90, чтобы показать направление и неопределённость прогноза.</p>
        <button class="button ghost report-action" data-type="trend">Подготовить <span>→</span></button>
    </article>

    <article class="report-card">
        <div class="report-card-top"><div class="report-icon lime">%</div><span class="report-code">04</span></div>
        <span class="panel-kicker">SCENARIO / PROMO</span>
        <h3>Промо-сценарий</h3>
        <p>Добавляет промо-признак. Его эффект оценивается только по доступной истории товара.</p>
        <button class="button ghost report-action" data-type="promo">Подготовить <span>→</span></button>
    </article>
</section>

<section class="panel report-history" aria-live="polite">
    <div class="panel-header">
        <div><span class="panel-kicker">LATEST EXPORT</span><h3>Последний комплект</h3></div>
        <span id="report-status" class="updated-at">Готов к генерации</span>
    </div>
    <div id="report-result" class="report-result">
        <span class="report-result-icon">▧</span>
        <div><b>Здесь появятся готовые файлы</b><p>Каждый формат можно будет скачать отдельно.</p></div>
    </div>
</section>
@endsection
