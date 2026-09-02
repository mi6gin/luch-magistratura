<?php

namespace App\Services;

use Illuminate\Support\Facades\File;

class ResearchReportService
{
    public function latest(): ?array
    {
        $path = $this->directory().'/summary.json';

        return File::isFile($path)
            ? json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR)
            : null;
    }

    public function chart(string $model): ?string
    {
        if (! in_array($model, ['lstm', 'gru', 'transformer'], true)) {
            return null;
        }
        $path = $this->directory().'/forecast-'.$model.'.svg';

        return File::isFile($path) ? (string) File::get($path) : null;
    }

    private function directory(): string
    {
        return (string) config('rayventory.research_report_path', storage_path('app/research-report/latest'));
    }
}
