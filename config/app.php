<?php

return [
    'name' => env('APP_NAME', 'Rayventory'),
    'env' => env('APP_ENV', 'production'),
    'debug' => (bool) env('APP_DEBUG', false),
    'url' => env('APP_URL', 'http://localhost'),
    'timezone' => 'Asia/Almaty',
    'locale' => 'ru',
    'fallback_locale' => 'ru',
    'key' => env('APP_KEY'),
    'cipher' => 'AES-256-CBC',
    'maintenance' => ['driver' => 'file'],
];
