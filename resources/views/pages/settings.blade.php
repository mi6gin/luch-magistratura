@extends('layouts.app')

@section('content')
@if(auth()->user()->is_admin)
<section class="panel" style="padding:24px">
    <h2>Новый пользователь активного филиала</h2>
    <form id="user-create-form" class="form-grid">
        <label>Имя<input id="new-user-name" required maxlength="120"></label>
        <label>Email<input id="new-user-email" type="email" required></label>
        <label>Временный пароль<input id="new-user-password" type="password" minlength="10" required></label>
        <label>Роль<select id="new-user-role"><option value="analyst">Аналитик</option><option value="purchaser">Закупщик</option><option value="viewer">Наблюдатель</option><option value="admin">Администратор филиала</option></select></label>
        <button class="primary-button" type="submit">Создать пользователя</button>
    </form>
</section>
<section class="panel" style="padding:24px;margin-top:20px"><h2>Пользователи организации</h2><div class="table-wrap"><table><thead><tr><th>Имя</th><th>Email</th><th>Филиалы</th></tr></thead><tbody id="users-table"></tbody></table></div></section>
<section class="panel" style="padding:24px;margin-top:20px"><h2>Сводка по филиалам</h2><div class="table-wrap"><table><thead><tr><th>Филиал</th><th>Товаров</th><th>Строк продаж</th><th>Остаток</th></tr></thead><tbody id="branches-summary-table"></tbody></table></div></section>
@endif
<section class="panel" style="padding:24px;margin-top:20px"><h2>Сменить мой пароль</h2><form id="password-change-form" class="form-grid"><label>Текущий пароль<input id="current-password" type="password" required></label><label>Новый пароль<input id="new-password" type="password" minlength="12" required></label><label>Повторите пароль<input id="new-password-confirmation" type="password" minlength="12" required></label><button class="primary-button" type="submit">Обновить пароль</button></form></section>
@endsection
