<?php

namespace App\Services;

use Illuminate\Support\Facades\File;

class ScenarioBenchmarkService
{
    public function latest(): ?array
    {
        $directory = (string) config('rayventory.scenarios_path', storage_path('app/scenarios'));
        if (! File::isDirectory($directory)) {
            return null;
        }
        $file = collect(File::directories($directory))->map(fn (string $path) => new \SplFileInfo($path.'/result.json'))
            ->filter(fn (\SplFileInfo $item): bool => $item->isFile())->sortByDesc->getMTime()->first();

        return $file instanceof \SplFileInfo
            ? json_decode((string) File::get($file->getPathname()), true, 512, JSON_THROW_ON_ERROR)
            : null;
    }
}
