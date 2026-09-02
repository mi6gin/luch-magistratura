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

Artisan::command('rayventory:cleanup', function (): int {
    $removeOlderThan = function (string $relativePath, int $cutoff): int {
        $directory = storage_path('app/'.$relativePath);
        if (! File::isDirectory($directory)) {
            return 0;
        }
        $removed = 0;
        foreach (File::files($directory) as $file) {
            if ($file->getMTime() < $cutoff && File::delete($file->getPathname())) {
                $removed++;
            }
        }

        return $removed;
    };

    $removed = $removeOlderThan('import-previews', now()->subDay()->getTimestamp());
    $removed += $removeOlderThan('ml-jobs', now()->subDays(7)->getTimestamp());
    $removed += $removeOlderThan('reports', now()->subDays(30)->getTimestamp());
    $removed += $removeOlderThan('import-history', now()->subYear()->getTimestamp());
    $removed += $removeOlderThan('model-health', now()->subYear()->getTimestamp());

    $backupDirectory = storage_path('app/import-backups');
    if (File::isDirectory($backupDirectory)) {
        $backups = collect(File::files($backupDirectory))
            ->sortByDesc(fn ($file) => $file->getMTime())
            ->slice(10);
        foreach ($backups as $backup) {
            $removed += File::delete($backup->getPathname()) ? 1 : 0;
        }
    }

    $this->info("Storage cleanup complete. Removed files: {$removed}");

    return 0;
})->purpose('Remove expired previews, jobs, reports, history and old database backups');

Schedule::command('rayventory:cleanup')->dailyAt('03:30');
