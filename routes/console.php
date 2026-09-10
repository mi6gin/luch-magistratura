<?php

use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Schedule;

Artisan::command('rayventory:setup {--force : Replace the existing working database}', function (): int {
    $source = database_path('seed/inventory_forecast.db');
    $target = (string) config('database.connections.sqlite.database');

    if ($target === ':memory:') {
        $this->error('A persistent SQLite path is required for Rayventory.');

        return 1;
    }

    if (File::isFile($target) && ! $this->option('force')) {
        $this->info("Working database already exists: {$target}");
        $this->call('migrate', ['--force' => true]);
        $this->call('db:seed', ['--force' => true]);

        return 0;
    }

    File::ensureDirectoryExists(dirname($target));
    if (File::isFile($source)) {
        if (! File::copy($source, $target)) {
            $this->error("Unable to create working database: {$target}");

            return 1;
        }
    } else {
        File::put($target, '');
    }

    $this->info("Working database is ready: {$target}");
    $this->call('migrate', ['--force' => true]);
    $this->call('db:seed', ['--force' => true]);

    return 0;
})->purpose('Create and seed the working SQLite database');

Artisan::command('rayventory:cleanup', function (): int {
    $removeDirectoryOlderThan = function (string $directory, int $cutoff): int {
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
    $removeOlderThan = fn (string $relativePath, int $cutoff): int => $removeDirectoryOlderThan(storage_path('app/'.$relativePath), $cutoff);

    $removed = $removeOlderThan('import-previews', now()->subDay()->getTimestamp());
    $removed += $removeOlderThan('ml-jobs', now()->subDays(7)->getTimestamp());
    $removed += $removeOlderThan('reports', now()->subDays(30)->getTimestamp());
    $removed += $removeOlderThan('import-history', now()->subYear()->getTimestamp());
    $removed += $removeOlderThan('model-health', now()->subYear()->getTimestamp());
    $removed += $removeOlderThan('training-jobs', now()->subDays(30)->getTimestamp());

    foreach (File::glob(storage_path('app/branches/*')) ?: [] as $branchDirectory) {
        $removed += $removeDirectoryOlderThan($branchDirectory.'/import-previews', now()->subDay()->getTimestamp());
        $removed += $removeDirectoryOlderThan($branchDirectory.'/import-history', now()->subYear()->getTimestamp());
    }
    foreach (['reports' => 30, 'training-jobs' => 30, 'model-health' => 365] as $root => $days) {
        foreach (File::glob(storage_path('app/'.$root.'/branches/*')) ?: [] as $branchDirectory) {
            $removed += $removeDirectoryOlderThan($branchDirectory, now()->subDays($days)->getTimestamp());
        }
    }

    $backupDirectory = storage_path('app/import-backups');
    if (File::isDirectory($backupDirectory)) {
        $backups = collect(File::files($backupDirectory))
            ->sortByDesc(fn ($file) => $file->getMTime())
            ->slice(10);
        foreach ($backups as $backup) {
            $removed += File::delete($backup->getPathname()) ? 1 : 0;
        }
    }
    foreach (File::glob(storage_path('app/branches/*/import-backups')) ?: [] as $directory) {
        foreach (collect(File::files($directory))->sortByDesc(fn ($file) => $file->getMTime())->slice(10) as $file) {
            $removed += File::delete($file->getPathname()) ? 1 : 0;
        }
    }

    $this->info("Storage cleanup complete. Removed files: {$removed}");

    return 0;
})->purpose('Remove expired previews, jobs, reports, history and old database backups');

Schedule::command('rayventory:cleanup')->dailyAt('03:30');
