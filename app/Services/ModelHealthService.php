<?php

namespace App\Services;

use Illuminate\Support\Facades\File;

class ModelHealthService
{
    public function __construct(private readonly BranchContext $branches) {}

    public function record(array $plan, string $trigger, ?string $source = null): array
    {
        $evaluation = $plan['evaluation'] ?? [];
        $previous = $this->latest();
        $dataAsOf = $plan['data_as_of'] ?? null;
        $freshnessDays = (int) ($plan['quality']['freshness_days'] ?? 0);
        $wape = (float) ($evaluation['wape_pct'] ?? 0);
        $evaluable = (int) ($evaluation['sku_count'] ?? 0) > 0;
        $previousWape = $previous['evaluable'] ?? false ? (float) $previous['metrics']['wape_pct'] : null;

        $record = [
            'id' => now()->format('YmdHis').'-'.bin2hex(random_bytes(3)),
            'evaluated_at' => now()->toIso8601String(),
            'trigger' => $trigger,
            'source' => $source,
            'model' => $plan['model'] ?? 'SAFE baseline',
            'data_as_of' => $dataAsOf,
            'freshness_days' => $freshnessDays,
            'freshness_status' => $freshnessDays > 30 ? 'critical' : ($freshnessDays > 7 ? 'warning' : 'fresh'),
            'evaluable' => $evaluable,
            'metrics' => [
                'wape_pct' => $wape,
                'bias_pct' => (float) ($evaluation['bias_pct'] ?? 0),
                'coverage_pct' => (float) ($evaluation['coverage_pct'] ?? 0),
                'sku_count' => (int) ($evaluation['sku_count'] ?? 0),
                'observations' => (int) ($evaluation['observations'] ?? 0),
                'holdout_days' => (int) ($evaluation['holdout_days'] ?? 0),
            ],
            'comparison' => [
                'previous_wape_pct' => $previousWape,
                'wape_change_pct' => $previousWape === null || ! $evaluable ? null : round($wape - $previousWape, 2),
                'verdict' => $previousWape === null || ! $evaluable ? 'baseline' : ($wape <= $previousWape ? 'improved' : 'degraded'),
            ],
        ];

        $directory = $this->directory();
        File::ensureDirectoryExists($directory);
        File::put($directory.'/'.$record['id'].'.json', json_encode($record, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));

        return $record;
    }

    public function latest(): ?array
    {
        return $this->history(1)[0] ?? null;
    }

    public function history(int $limit = 12): array
    {
        $directory = $this->directory();
        if (! File::isDirectory($directory)) {
            return [];
        }

        return collect(File::files($directory))->sortByDesc->getFilename()->take($limit)
            ->map(fn ($file) => json_decode((string) File::get($file->getPathname()), true, 512, JSON_THROW_ON_ERROR))
            ->values()->all();
    }

    private function directory(): string
    {
        return $this->branches->scopedPath((string) config('rayventory.model_health_path', storage_path('app/model-health')));
    }
}
