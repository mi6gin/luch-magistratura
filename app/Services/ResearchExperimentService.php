<?php

namespace App\Services;

use Illuminate\Support\Facades\File;

class ResearchExperimentService
{
    public function __construct(private readonly BranchContext $branches) {}

    public function list(int $limit = 20): array
    {
        return collect($this->resultFiles())->take($limit)->map(function ($file): array {
            $document = $this->read($file->getPathname());

            return [
                'experiment_id' => $document['experiment_id'],
                'created_at' => $document['created_at'],
                'dataset' => $document['dataset']['dataset'] ?? 'Неизвестный набор',
                'series_count' => $document['dataset']['series_count'] ?? 0,
                'rolling_folds' => $document['rolling_folds'] ?? 1,
                'champion' => $document['champion'] ?? null,
                'results' => $document['results'] ?? [],
            ];
        })->values()->all();
    }

    public function find(string $id): ?array
    {
        if (preg_match('/^EXP-[A-Z0-9-]+$/', $id) !== 1) {
            return null;
        }
        $path = $this->directory().'/'.$id.'/result.json';

        return File::isFile($path) ? $this->read($path) : null;
    }

    private function resultFiles(): array
    {
        $directory = $this->directory();
        if (! File::isDirectory($directory)) {
            return [];
        }

        return collect(File::directories($directory))->map(fn (string $path) => new \SplFileInfo($path.'/result.json'))
            ->filter(fn (\SplFileInfo $file) => $file->isFile())->sortByDesc->getMTime()->values()->all();
    }

    private function read(string $path): array
    {
        return json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR);
    }

    private function directory(): string
    {
        return $this->branches->scopedPath((string) config('rayventory.experiments_path', storage_path('app/experiments')));
    }
}
