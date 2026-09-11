<?php

return [
    'driver' => env('HASH_DRIVER', 'argon2id'),
    'bcrypt' => [
        'rounds' => (int) env('BCRYPT_ROUNDS', 12),
        'verify' => (bool) env('HASH_VERIFY_ALGORITHM', false),
        'limit' => null,
    ],
    'argon' => [
        'memory' => (int) env('ARGON_MEMORY', 65536),
        'threads' => (int) env('ARGON_THREADS', 1),
        'time' => (int) env('ARGON_TIME', 4),
        // Verify legacy bcrypt hashes once, then rehash them with Argon2id.
        'verify' => (bool) env('HASH_VERIFY_ALGORITHM', false),
    ],
    'rehash_on_login' => true,
];
