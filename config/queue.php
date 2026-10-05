<?php

return [
    'default' => env('QUEUE_CONNECTION', 'database'),

    // Laravel merges other framework queue connections and job failure options.
    // Replacing a connection requires keeping its complete set of options here.
    'connections' => [
        'database' => [
            'driver' => 'database',
            'connection' => env('DB_QUEUE_CONNECTION'),
            'table' => env('DB_QUEUE_TABLE', 'jobs'),
            'queue' => env('DB_QUEUE', 'default'),
            // Reserve a running training job beyond its 3600-second timeout.
            'retry_after' => (int) env('DB_QUEUE_RETRY_AFTER', 3660),
            'after_commit' => false,
        ],
    ],
];
