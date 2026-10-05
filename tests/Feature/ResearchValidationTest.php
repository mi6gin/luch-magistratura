<?php

namespace Tests\Feature;

use App\Services\ModelRegistryService;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class ResearchValidationTest extends TestCase
{
    public function test_validation_results_are_visible_but_cannot_be_promoted(): void
    {
        $root = sys_get_temp_dir().'/rayventory-validation-'.bin2hex(random_bytes(5));
        $id = 'EXP-20261005T120000Z-ABC123';
        config([
            'rayventory.experiments_path' => $root.'/experiments',
            'rayventory.model_registry_path' => $root.'/registry.json',
            'rayventory.models_path' => $root.'/models',
        ]);
        $directory = $root.'/experiments/branches/1/'.$id;
        File::ensureDirectoryExists($directory);
        File::put($directory.'/result.json', json_encode([
            'experiment_id' => $id,
            'created_at' => '2026-10-05T12:00:00+00:00',
            'dataset' => ['dataset' => 'Local Rayventory inventory', 'series_count' => 5],
            'rolling_folds' => 3,
            'evaluation_split' => 'validation',
            'reserved_test_period' => ['evaluated' => false],
            'champion' => 'adaptive_demand_router',
            'results' => [
                ['model' => 'seasonal_naive_7', 'metrics' => ['wape_pct' => 20]],
                ['model' => 'adaptive_demand_router', 'routes' => ['smooth' => 'moving_median_28'],
                    'metrics' => ['wape_pct' => 10, 'evaluation_split' => 'validation']],
            ],
        ], JSON_THROW_ON_ERROR));

        try {
            $this->getJson('/api/experiments')->assertOk()
                ->assertJsonPath('experiments.0.evaluation_split', 'validation')
                ->assertJsonPath('experiments.0.reserved_test_period.evaluated', false);
            $candidate = app(ModelRegistryService::class)->registerCandidate($id, 'adaptive_demand_router');
            $this->assertFalse($candidate['eligible']);
            $check = collect($candidate['checks'])->firstWhere('code', 'test_evaluation');
            $this->assertFalse($check['passed']);
            $this->postJson('/api/models/'.$candidate['id'].'/promote', ['confirmation' => 'PROMOTE'])
                ->assertUnprocessable();
            $this->assertSame('builtin-seasonal-robust-v1', app(ModelRegistryService::class)->state()['production_id']);
        } finally {
            File::deleteDirectory($root);
        }
    }
}
