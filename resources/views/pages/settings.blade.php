@extends('layouts.app', ['title' => 'Настройки', 'page' => 'settings', 'section' => 'CONTROL PLANE', 'heading' => 'Настройки и доступ'])
@section('content')
<div class="page-intro"><div><span class="eyebrow">ORGANIZATION CONTROL / 09</span><h2>Люди, филиалы и <strong>контроль доступа</strong></h2><p>Управляйте рабочими пространствами и отслеживайте состояние сети без смешивания данных.</p></div><span class="model-badge"><span class="pulse"></span> SECURE WORKSPACE</span></div>

@if(auth()->user()->is_admin)
<section class="branch-command-grid" id="branch-command-grid"><article class="branch-command-loading">Собираем сводку филиалов…</article></section>

<section class="settings-grid">
    <article class="panel settings-create-card">
        <div class="panel-header"><div><span class="panel-kicker">USER ONBOARDING</span><h3>Новый пользователь</h3><p>Доступ будет выдан только к активному филиалу.</p></div><span class="settings-icon">＋</span></div>
        <form id="user-create-form" class="form-grid modern-form">
            <label>Имя<input id="new-user-name" required maxlength="120" autocomplete="name" placeholder="Имя сотрудника"></label>
            <label>Email<input id="new-user-email" type="email" required autocomplete="email" placeholder="name@company.kz"></label>
            <label>Временный пароль<input id="new-user-password" type="password" minlength="12" maxlength="128" required autocomplete="new-password" placeholder="Не менее 12 символов"></label>
            <label>Роль<select id="new-user-role"><option value="analyst">Аналитик</option><option value="purchaser">Закупщик</option><option value="viewer">Наблюдатель</option><option value="admin">Администратор филиала</option></select></label>
            <button class="button primary full" type="submit">Создать пользователя <span>→</span></button>
        </form>
    </article>
    <article class="panel settings-users-card">
        <div class="panel-header"><div><span class="panel-kicker">ACCESS MATRIX</span><h3>Пользователи организации</h3><p>Текущие области доступа.</p></div><span class="live-dot">LIVE</span></div>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Пользователь</th><th>Email</th><th>Филиалы</th></tr></thead><tbody id="users-table"><tr><td colspan="3">Загрузка…</td></tr></tbody></table></div>
    </article>
</section>

<section class="panel branch-table-panel"><div class="panel-header"><div><span class="panel-kicker">NETWORK DETAIL</span><h3>Сводка по филиалам</h3><p>Операционный объём каждого изолированного пространства.</p></div></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Филиал</th><th>Товаров</th><th>Продаж</th><th>Остаток</th><th>Риск</th><th>Последние данные</th></tr></thead><tbody id="branches-summary-table"></tbody></table></div></section>
@endif

<section class="panel password-panel"><div><span class="panel-kicker">MY SECURITY</span><h3>Сменить пароль</h3><p>После обновления остальные активные сессии будут завершены.</p></div><form id="password-change-form" class="form-grid modern-form password-form"><label>Текущий пароль<input id="current-password" type="password" required autocomplete="current-password"></label><label>Новый пароль<input id="new-password" type="password" minlength="12" maxlength="128" required autocomplete="new-password"></label><label>Повторите пароль<input id="new-password-confirmation" type="password" minlength="12" maxlength="128" required autocomplete="new-password"></label><button class="button primary" type="submit">Обновить пароль</button></form></section>
@endsection
