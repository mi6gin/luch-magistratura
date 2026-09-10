<?php

namespace App\Services;

use Illuminate\Support\Facades\File;

class DatasetAnalysisService
{
    public function __construct(private readonly BranchContext $branches) {}

    public function latest(): ?array
    {
        $base = (string) config('rayventory.dataset_analysis_path', storage_path('app/dataset-analysis/latest.json'));
        $path = $this->branches->scopedPath(dirname($base)).'/'.basename($base);

        return File::isFile($path)
            ? json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR)
            : null;
    }
}
