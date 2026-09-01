<?php

use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Schedule;

Artisan::command('rayventory:setup {--force : Replace the existing working database}', function (): int {
    $source = database_path('seed/inventory_forecast.db');
    $target = (string) config('database.connections.sqlite.database');

    if (! File::isFile($source)) {
        $this->error("Seed database not found: {$source}");

        return 1;
    }

    if ($target === ':memory:') {
        $this->error('A persistent SQLite path is required for Rayventory.');

        return 1;
    }

    if (File::isFile($target) && ! $this->option('force')) {
        $this->info("Working database already exists: {$target}");
        $this->call('migrate', ['--force' => true]);

        return 0;
    }

    File::ensureDirectoryExists(dirname($target));
    if (! File::copy($source, $target)) {
        $this->error("Unable to create working database: {$target}");

        return 1;
    }

    $this->info("Working database is ready: {$target}");
    $this->call('migrate', ['--force' => true]);

    return 0;
})->purpose('Create the working SQLite database from the bundled demo seed');

Schedule::call(fn () => null)->daily();
