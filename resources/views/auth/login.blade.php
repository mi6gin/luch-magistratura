<!doctype html>
<html lang="ru" data-theme="dark">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="color-scheme" content="dark light">
    <title>Вход · Rayventory</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
    <link rel="stylesheet" href="{{ asset('css/auth.css') }}">
</head>
<body class="auth-page">
<main class="auth-shell">
    <section class="auth-context" aria-labelledby="product-title">
        <a class="auth-brand" href="{{ route('login') }}" aria-label="Rayventory">
            <span class="auth-brand-mark" aria-hidden="true">
                <span class="auth-brand-letter">R</span>
                <i class="auth-brand-node node-one"></i>
                <i class="auth-brand-node node-two"></i>
                <i class="auth-brand-node node-three"></i>
            </span>
            <span>RAYVENTORY</span>
        </a>
        <div class="auth-context-copy">
            <p class="eyebrow">Управление запасами</p>
            <h1 id="product-title">Единая точка контроля для каждого филиала.</h1>
            <p>Изолированные данные, прозрачные роли и контролируемые операции в одном рабочем пространстве.</p>
        </div>
        <p class="auth-security-note"><span aria-hidden="true">◆</span> Доступ защищён серверной сессией</p>
    </section>
    <section class="auth-card" aria-labelledby="login-title">
        <div class="auth-card-header">
            <p class="eyebrow">Защищённый вход</p>
            <h2 id="login-title">Добро пожаловать</h2>
            <p>Используйте учётную запись, выданную администратором системы.</p>
        </div>
        <form class="auth-form" method="post" action="{{ route('login.submit') }}" novalidate>
            @csrf
            <label class="auth-field" for="email"><span>Email</span><input id="email" name="email" type="email" value="{{ old('email') }}" autocomplete="username" inputmode="email" maxlength="255" required autofocus aria-describedby="@error('email') login-error @else email-help @enderror"><small id="email-help">Корпоративный адрес пользователя</small></label>
            <label class="auth-field" for="password"><span>Пароль</span><input id="password" name="password" type="password" autocomplete="current-password" maxlength="128" required></label>
            @error('email')<div class="auth-error" id="login-error" role="alert">{{ $message }}</div>@enderror
            <button class="button primary full auth-submit" type="submit">Войти в систему</button>
        </form>
        <p class="auth-help">Проблемы со входом? Обратитесь к администратору вашей организации.</p>
    </section>
</main>
</body>
</html>
