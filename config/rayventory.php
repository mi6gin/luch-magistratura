<?php

return [
    'python' => env('ML_PYTHON', 'py'),
    'engine_path' => env('ML_ENGINE_PATH', base_path('../MAGA/engine/predict_cli.py')),
    'reports_path' => env('ML_REPORTS_PATH', base_path('../MAGA/reports')),
    'timeout' => env('ML_TIMEOUT', 120),
];
