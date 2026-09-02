<?php

return [
    'python' => env('ML_PYTHON', 'py'),
    'engine_path' => env('ML_ENGINE_PATH', base_path('ml/predict_cli.py')),
    'database_path' => env(
        'ML_DB_PATH',
        env('DB_DATABASE', storage_path('app/rayventory/inventory_forecast.db')),
    ),
    'reports_path' => env('ML_REPORTS_PATH', storage_path('app/reports')),
    'experiments_path' => env('ML_EXPERIMENTS_PATH', storage_path('app/experiments')),
    'model_registry_path' => env('ML_MODEL_REGISTRY_PATH') ?: storage_path('app/model-registry/registry.json'),
    'models_path' => env('ML_MODELS_PATH') ?: storage_path('app/models'),
    'training_jobs_path' => env('ML_TRAINING_JOBS_PATH') ?: storage_path('app/training-jobs'),
    'research_python' => env('ML_RESEARCH_PYTHON') ?: env('ML_PYTHON', 'py'),
    'training_timeout' => env('ML_TRAINING_TIMEOUT', 3600),
    'local_training_data_path' => env('ML_LOCAL_DATA_PATH') ?: base_path('data/processed/local-inventory'),
    'timeout' => env('ML_TIMEOUT', 120),
];
