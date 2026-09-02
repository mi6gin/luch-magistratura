<?php

namespace App\Services;

use Illuminate\Support\Facades\File;

class DatasetAnalysisService
{
    public function latest(): ?array
    {
        $path = (string) config('rayventory.dataset_analysis_path', storage_path('app/dataset-analysis/latest.json'));

        return File::isFile($path)
            ? json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR)
            : null;
    }
}
