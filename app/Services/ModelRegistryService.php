<?php

namespace App\Services;

use Illuminate\Support\Facades\File;
use InvalidArgumentException;
use JsonException;

class ModelRegistryService
{
    public function __construct(private readonly ResearchExperimentService $experiments) {}

    public function state(): array
    {
        $path = $this->path();
        if (! File::isFile($path)) {
            return $this->initialState();
        }

        try {
            $state = json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException) {
            return [
                ...$this->initialState(),
                'warning' => 'Реестр повреждён. Активирован безопасный baseline.',
            ];
        }

        return is_array($state) ? $state : $this->initialState();
    }

    public function registerCandidate(string $experimentId, string $model): array
    {
        $experiment = $this->experiments->find($experimentId);
        if ($experiment === null) {
            throw new InvalidArgumentException('Эксперимент не найден.');
        }
        $result = collect($experiment['results'] ?? [])->firstWhere('model', $model);
        if (! is_array($result)) {
            throw new InvalidArgumentException('Модель отсутствует в выбранном эксперименте.');
        }

        $id = $experimentId.'--'.preg_replace('/[^a-z0-9_-]+/i', '-', $model);
        $folds = (int) ($experiment['rolling_folds'] ?? 1);
        $localDataset = ($experiment['dataset']['dataset'] ?? null) === 'Local Rayventory inventory';
        $policyCompatible = in_array($model, ['adaptive_demand_router', 'risk_calibrated_router'], true)
            && $this->validRoutes($result['routes'] ?? []);
        $runtimeCompatible = $localDataset && $policyCompatible;
        $artifact = $runtimeCompatible ? $this->packagePolicy($id, $experimentId, $model, $result['routes']) : null;
        $checks = [
            ['code' => 'rolling_folds', 'passed' => $folds >= 3, 'message' => "Rolling-окон: {$folds}; требуется минимум 3."],
            ['code' => 'finite_wape', 'passed' => is_numeric($result['metrics']['wape_pct'] ?? null) && is_finite((float) $result['metrics']['wape_pct']), 'message' => 'WAPE должен быть конечным числом.'],
            ['code' => 'runtime_compatible', 'passed' => $runtimeCompatible, 'message' => $runtimeCompatible ? 'Артефакт поддерживается production runtime.' : 'Исследовательский артефакт пока не поддерживается production runtime.'],
        ];
        $candidate = [
            'id' => $id,
            'name' => $runtimeCompatible ? 'local-demand-router-v1' : $model,
            'source_model' => $model,
            'status' => 'candidate',
            'experiment_id' => $experimentId,
            'dataset' => $experiment['dataset']['dataset'] ?? 'Неизвестный набор',
            'registered_at' => now()->toIso8601String(),
            'metrics' => $result['metrics'] ?? [],
            'checks' => $checks,
            'eligible' => collect($checks)->every(fn (array $check): bool => $check['passed']),
            'artifact_path' => $artifact,
        ];

        $state = $this->state();
        $state['models'] = collect($state['models'])->reject(fn (array $item): bool => $item['id'] === $id)->push($candidate)->values()->all();
        $this->save($state);

        return $candidate;
    }

    public function promote(string $id): array
    {
        $state = $this->state();
        $candidate = collect($state['models'])->firstWhere('id', $id);
        if (! is_array($candidate)) {
            throw new InvalidArgumentException('Кандидат не найден.');
        }
        if (! ($candidate['eligible'] ?? false)) {
            throw new InvalidArgumentException('Публикация заблокирована: кандидат не прошёл обязательные проверки.');
        }

        $state['models'] = collect($state['models'])->map(function (array $item) use ($id): array {
            if (($item['status'] ?? null) === 'production') {
                $item['status'] = 'archived';
            }
            if ($item['id'] === $id) {
                $item['status'] = 'production';
                $item['promoted_at'] = now()->toIso8601String();
            }

            return $item;
        })->values()->all();
        $state['production_id'] = $id;
        $this->save($state);

        return collect($state['models'])->firstWhere('id', $id);
    }

    private function initialState(): array
    {
        return [
            'production_id' => 'builtin-seasonal-robust-v1',
            'fallback_id' => 'builtin-seasonal-robust-v1',
            'models' => [[
                'id' => 'builtin-seasonal-robust-v1',
                'name' => 'seasonal-robust-v1',
                'status' => 'production',
                'registered_at' => null,
                'metrics' => [],
                'checks' => [],
                'eligible' => true,
            ]],
        ];
    }

    private function save(array $state): void
    {
        $path = $this->path();
        File::ensureDirectoryExists(dirname($path));
        $temporary = $path.'.tmp-'.bin2hex(random_bytes(6));
        File::put($temporary, json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR), true);
        rename($temporary, $path);
    }

    private function validRoutes(array $routes): bool
    {
        if ($routes === []) {
            return false;
        }

        return collect($routes)->every(fn (mixed $route): bool => is_string($route)
            && preg_match('/^(seasonal_naive_7|moving_median_28|croston_sba)( × (?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))?$/', $route) === 1);
    }

    private function packagePolicy(string $id, string $experimentId, string $sourceModel, array $routes): string
    {
        $directory = rtrim((string) config('rayventory.models_path', storage_path('app/models')), '/').'/'.$id;
        File::ensureDirectoryExists($directory);
        $path = $directory.'/manifest.json';
        File::put($path, json_encode([
            'schema_version' => 1,
            'runtime' => 'local-demand-router-v1',
            'experiment_id' => $experimentId,
            'source_model' => $sourceModel,
            'routes' => $routes,
            'created_at' => now()->toIso8601String(),
        ], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR), true);

        return $path;
    }

    private function path(): string
    {
        return (string) config('rayventory.model_registry_path', storage_path('app/model-registry/registry.json'));
    }
}
