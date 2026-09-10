<!doctype html>
<html lang="ru" data-theme="dark">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>{{ $title ?? 'Rayventory' }} · Rayventory</title>
    <link rel="icon" type="image/svg+xml" href="{{ asset('favicon.svg') }}">
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body data-page="{{ $page ?? '' }}">
<div class="app-shell">
    <aside class="sidebar" id="sidebar">
        <a class="brand" href="{{ route('dashboard') }}"><img class="brand-logo" src="{{ asset('logo-luch.png') }}" alt="ЛУЧ · магазин у дома"><span><b>RAYVENTORY</b><small>INTELLIGENCE OS</small></span></a>
        <div class="nav-label">Workspace</div>
        <nav class="nav">
            <a href="{{ route('dashboard') }}" class="nav-link {{ ($page ?? '') === 'dashboard' ? 'active' : '' }}"><i>◈</i><span>Обзор</span><em>01</em></a>
            <a href="{{ route('inventory') }}" class="nav-link {{ ($page ?? '') === 'inventory' ? 'active' : '' }}"><i>▤</i><span>Склад</span><em>02</em></a>
            <a href="{{ route('simulator') }}" class="nav-link {{ ($page ?? '') === 'simulator' ? 'active' : '' }}"><i>⌁</i><span>Симулятор</span><em>03</em></a>
            <a href="{{ route('purchases') }}" class="nav-link {{ ($page ?? '') === 'purchases' ? 'active' : '' }}"><i>↓</i><span>К закупке</span><em>04</em></a>
            <a href="{{ route('reports') }}" class="nav-link {{ ($page ?? '') === 'reports' ? 'active' : '' }}"><i>▧</i><span>Отчёты</span><em>05</em></a>
            <a href="{{ route('knowledge') }}" class="nav-link {{ ($page ?? '') === 'knowledge' ? 'active' : '' }}"><i>?</i><span>База знаний</span><em>06</em></a>
            <a href="{{ route('experiments') }}" class="nav-link {{ ($page ?? '') === 'experiments' ? 'active' : '' }}"><i>⌬</i><span>Эксперименты</span><em>07</em></a>
            <a href="{{ route('model-health') }}" class="nav-link {{ ($page ?? '') === 'model-health' ? 'active' : '' }}"><i>◎</i><span>Здоровье модели</span><em>08</em></a>
            <a href="{{ route('settings') }}" class="nav-link {{ ($page ?? '') === 'settings' ? 'active' : '' }}"><i>⚙</i><span>Настройки</span><em>09</em></a>
        </nav>
        <div class="sidebar-bottom"><div class="system-status"><span class="pulse"></span><span>ALL SYSTEMS<br><b>OPERATIONAL</b></span></div><div class="location">KZ / ALMATY<br><span>UTC +05:00</span></div></div>
    </aside>
    <div class="app-main">
        <header class="topbar"><button class="mobile-menu" id="mobile-menu" aria-label="Открыть меню">☰</button><div><span class="crumb">RAY OS <b>/</b> {{ $section ?? 'WORKSPACE' }}</span><h1>{{ $heading ?? 'Центр управления' }}</h1></div><div class="top-actions"><label class="branch-picker"><span>Филиал</span><select id="branch-select" aria-label="Активный филиал"></select></label>@if(auth()->user()?->is_admin)<button class="command-trigger" id="create-branch" aria-label="Добавить филиал">+</button>@endif<span class="live"><span class="pulse"></span> LIVE DATA</span><button class="command-trigger" id="command-trigger" aria-label="Открыть командную палитру"><span>⌘</span><kbd>K</kbd></button><button class="theme-toggle" id="theme-toggle" aria-label="Переключить тему">☀</button><form method="post" action="{{ route('logout') }}">@csrf<button class="user-chip" type="submit"><div class="avatar">{{ mb_strtoupper(mb_substr(auth()->user()->name, 0, 2)) }}</div><span>{{ auth()->user()->name }}<small>Выйти</small></span></button></form></div></header>
        <main class="page-content page-enter">@yield('content')</main>
    </div>
</div>
<div id="toast-container" class="toast-container"></div>
<div id="command-palette" class="command-overlay" aria-hidden="true">
    <div class="command-palette" role="dialog" aria-modal="true" aria-label="Командная палитра">
        <div class="command-search"><span>⌕</span><input id="command-search" type="search" placeholder="Куда перейти или что сделать?"><kbd>ESC</kbd></div>
        <div class="command-group"><span>Навигация</span><button data-command="/"><i>◈</i><b>Обзор</b><small>Главная аналитика</small><em>01</em></button><button data-command="/inventory"><i>▤</i><b>Склад</b><small>Остатки и доступность</small><em>02</em></button><button data-command="/simulator"><i>⌁</i><b>Симулятор</b><small>Сценарии прогноза</small><em>03</em></button><button data-command="/purchases"><i>↓</i><b>К закупке</b><small>Что и когда заказать</small><em>04</em></button><button data-command="/reports"><i>▧</i><b>Отчёты</b><small>PDF + презентации</small><em>05</em></button><button data-command="/knowledge"><i>?</i><b>База знаний</b><small>Методология Ray OS</small><em>06</em></button><button data-command="/experiments"><i>⌬</i><b>Эксперименты</b><small>Сравнение моделей</small><em>07</em></button><button data-command="/model-health"><i>◎</i><b>Здоровье модели</b><small>Свежесть и точность</small><em>08</em></button></div>
        <div class="command-hint"><span>↑↓ выбрать</span><span>↵ открыть</span><span>Esc закрыть</span></div>
    </div>
</div>
<script src="{{ asset('js/app.js') }}"></script>
@yield('scripts')
</body>
</html>
