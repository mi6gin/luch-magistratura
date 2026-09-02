<?php

namespace Tests\Feature;

use App\Services\InventoryExcelService;
use App\Services\MlBridge;
use App\Services\ModelHealthService;
use App\Services\ModelRegistryService;
use App\Services\ResearchExperimentService;
use App\Services\ResearchReportService;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Schema;
use PhpOffice\PhpSpreadsheet\IOFactory;
use Tests\TestCase;

class ApplicationTest extends TestCase
{
    public function test_all_workspace_pages_are_available(): void
    {
        foreach (['/', '/inventory', '/simulator', '/purchases', '/reports', '/knowledge', '/model-health', '/experiments'] as $path) {
            $this->get($path)->assertOk();
        }
    }

    public function test_model_health_compares_real_evaluation_snapshots(): void
    {
        $service = app(ModelHealthService::class);
        $directory = sys_get_temp_dir().'/rayventory-health-'.bin2hex(random_bytes(5));
        config(['rayventory.model_health_path' => $directory]);

        try {
            $first = $service->record($this->healthPlan(24.5), 'manual');
            $second = $service->record($this->healthPlan(20.0), 'excel_import', 'fresh.xlsx');

            $this->assertSame('baseline', $first['comparison']['verdict']);
            $this->assertSame('improved', $second['comparison']['verdict']);
            $this->assertSame(-4.5, $second['comparison']['wape_change_pct']);
            $this->assertCount(2, $service->history());
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_research_experiment_registry_rejects_paths_and_returns_results(): void
    {
        $directory = sys_get_temp_dir().'/rayventory-experiments-'.bin2hex(random_bytes(5));
        config(['rayventory.experiments_path' => $directory]);
        File::ensureDirectoryExists($directory.'/EXP-20260902T120000Z-ABC123');
        File::put($directory.'/EXP-20260902T120000Z-ABC123/result.json', json_encode([
            'experiment_id' => 'EXP-20260902T120000Z-ABC123',
            'created_at' => '2026-09-02T12:00:00+00:00',
            'dataset' => ['dataset' => 'UCI Online Retail II', 'series_count' => 300],
            'rolling_folds' => 3,
            'champion' => 'gru',
            'results' => [['model' => 'gru', 'metrics' => ['wape_pct' => 20.1]]],
        ], JSON_THROW_ON_ERROR));

        try {
            $service = app(ResearchExperimentService::class);
            $this->assertCount(1, $service->list());
            $this->assertSame('gru', $service->find('EXP-20260902T120000Z-ABC123')['champion']);
            $this->assertNull($service->find('../secrets'));
            $this->getJson('/api/experiments')->assertOk()->assertJsonPath('experiments.0.rolling_folds', 3);
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_research_report_exposes_summary_and_safe_charts(): void
    {
        $directory = sys_get_temp_dir().'/rayventory-report-'.bin2hex(random_bytes(5));
        config(['rayventory.research_report_path' => $directory]);
        File::ensureDirectoryExists($directory);
        File::put($directory.'/summary.json', json_encode(['best_neural' => 'gru'], JSON_THROW_ON_ERROR));
        File::put($directory.'/forecast-gru.svg', '<svg xmlns="http://www.w3.org/2000/svg"></svg>');

        try {
            $this->assertSame('gru', app(ResearchReportService::class)->latest()['best_neural']);
            $this->getJson('/api/research-report')->assertOk()->assertJsonPath('report.best_neural', 'gru');
            $this->get('/api/research-report/chart/gru')->assertOk()->assertHeader('Content-Type', 'image/svg+xml; charset=UTF-8');
            $this->get('/api/research-report/chart/unknown')->assertNotFound();
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_model_registry_blocks_incompatible_research_artifacts(): void
    {
        $root = sys_get_temp_dir().'/rayventory-registry-'.bin2hex(random_bytes(5));
        $experiments = $root.'/experiments';
        config([
            'rayventory.experiments_path' => $experiments,
            'rayventory.model_registry_path' => $root.'/registry.json',
        ]);
        File::ensureDirectoryExists($experiments.'/EXP-20260902T120000Z-ABC123');
        File::put($experiments.'/EXP-20260902T120000Z-ABC123/result.json', json_encode([
            'experiment_id' => 'EXP-20260902T120000Z-ABC123',
            'created_at' => '2026-09-02T12:00:00+00:00',
            'dataset' => ['dataset' => 'UCI Online Retail II'],
            'rolling_folds' => 3,
            'results' => [['model' => 'gru', 'metrics' => ['wape_pct' => 20.1]]],
        ], JSON_THROW_ON_ERROR));

        try {
            $registry = app(ModelRegistryService::class);
            $this->assertSame('builtin-seasonal-robust-v1', $registry->state()['production_id']);
            $candidate = $registry->registerCandidate('EXP-20260902T120000Z-ABC123', 'gru');
            $this->assertFalse($candidate['eligible']);
            $this->assertSame('candidate', $candidate['status']);
            $this->postJson('/api/models/'.$candidate['id'].'/promote', ['confirmation' => 'PROMOTE'])
                ->assertUnprocessable();
            $this->getJson('/api/models')->assertOk()
                ->assertJsonPath('production_id', 'builtin-seasonal-robust-v1');
        } finally {
            File::deleteDirectory($root);
        }
    }

    public function test_local_policy_artifact_can_pass_checks_and_be_promoted(): void
    {
        $root = sys_get_temp_dir().'/rayventory-local-policy-'.bin2hex(random_bytes(5));
        $experiments = $root.'/experiments';
        config([
            'rayventory.experiments_path' => $experiments,
            'rayventory.model_registry_path' => $root.'/registry.json',
            'rayventory.models_path' => $root.'/models',
        ]);
        File::ensureDirectoryExists($experiments.'/EXP-20260902T130000Z-ABC123');
        File::put($experiments.'/EXP-20260902T130000Z-ABC123/result.json', json_encode([
            'experiment_id' => 'EXP-20260902T130000Z-ABC123',
            'created_at' => '2026-09-02T13:00:00+00:00',
            'dataset' => ['dataset' => 'Local Rayventory inventory'],
            'rolling_folds' => 3,
            'results' => [[
                'model' => 'moving_median_28',
                'metrics' => ['wape_pct' => 20.0, 'risk_cost_pct' => 25.0],
            ], [
                'model' => 'risk_calibrated_router',
                'metrics' => ['wape_pct' => 18.2, 'risk_cost_pct' => 22.0],
                'routes' => ['smooth' => 'moving_median_28 × 1.25'],
            ]],
        ], JSON_THROW_ON_ERROR));

        try {
            $registry = app(ModelRegistryService::class);
            $candidate = $registry->registerCandidate('EXP-20260902T130000Z-ABC123', 'risk_calibrated_router');
            $this->assertTrue($candidate['eligible']);
            $this->assertFileExists($candidate['artifact_path']);
            $production = $registry->promote($candidate['id']);
            $this->assertSame('production', $production['status']);
            $this->assertSame('local-demand-router-v1', $production['name']);
        } finally {
            File::deleteDirectory($root);
        }
    }

    public function test_local_training_readiness_explains_insufficient_history(): void
    {
        $directory = sys_get_temp_dir().'/rayventory-training-jobs-'.bin2hex(random_bytes(5));
        config(['rayventory.training_jobs_path' => $directory]);
        Schema::create('sales_history', function (Blueprint $table): void {
            $table->unsignedBigInteger('product_id');
            $table->date('sale_date');
        });
        \DB::table('sales_history')->insert([
            ['product_id' => 1, 'sale_date' => '2026-08-01'],
            ['product_id' => 1, 'sale_date' => '2026-08-30'],
        ]);

        $this->getJson('/api/training-readiness')->assertOk()
            ->assertJsonPath('ready', false)
            ->assertJsonPath('series_eligible', 0)
            ->assertJsonPath('minimum_series_span_days', 30)
            ->assertJsonPath('minimum_days', 175);
        $this->postJson('/api/training-pipeline')->assertOk()
            ->assertJsonPath('pipeline.status', 'skipped');
        $this->getJson('/api/training-pipeline')->assertOk()
            ->assertJsonPath('latest.status', 'skipped');
        File::deleteDirectory($directory);
    }

    public function test_dataset_analysis_api_returns_latest_eda_profile(): void
    {
        $path = sys_get_temp_dir().'/rayventory-analysis-'.bin2hex(random_bytes(5)).'.json';
        config(['rayventory.dataset_analysis_path' => $path]);
        File::put($path, json_encode([
            'dataset' => 'Local Rayventory inventory',
            'volume' => ['series' => 3, 'rows' => 1095],
            'period' => ['days' => 365],
            'demand' => ['zero_sales_pct' => 12.5],
        ], JSON_THROW_ON_ERROR));
        try {
            $this->getJson('/api/dataset-analysis')->assertOk()
                ->assertJsonPath('analysis.volume.rows', 1095)
                ->assertJsonPath('analysis.period.days', 365);
        } finally {
            File::delete($path);
        }
    }

    public function test_tuning_api_returns_latest_comparative_result(): void
    {
        $directory = sys_get_temp_dir().'/rayventory-tuning-'.bin2hex(random_bytes(5));
        config(['rayventory.tuning_path' => $directory]);
        File::ensureDirectoryExists($directory.'/TUNE-TEST');
        File::put($directory.'/TUNE-TEST/result.json', json_encode([
            'tuning_id' => 'TUNE-TEST',
            'trials' => [['model' => 'gru', 'metrics' => ['wape_pct' => 20.0]]],
            'best_by_model' => ['gru' => ['model' => 'gru']],
        ], JSON_THROW_ON_ERROR));
        try {
            $this->getJson('/api/tuning')->assertOk()
                ->assertJsonPath('tuning.tuning_id', 'TUNE-TEST')
                ->assertJsonPath('tuning.trials.0.model', 'gru');
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_scenario_api_returns_latest_applicability_benchmark(): void
    {
        $directory = sys_get_temp_dir().'/rayventory-scenarios-'.bin2hex(random_bytes(5));
        config(['rayventory.scenarios_path' => $directory]);
        File::ensureDirectoryExists($directory.'/SCENARIO-TEST');
        File::put($directory.'/SCENARIO-TEST/result.json', json_encode([
            'benchmark_id' => 'SCENARIO-TEST',
            'scenarios' => [['scenario' => 'trend', 'winner' => 'gru']],
            'models' => ['gru' => ['mean_wape_pct' => 12.0]],
        ], JSON_THROW_ON_ERROR));
        try {
            $this->getJson('/api/scenarios')->assertOk()
                ->assertJsonPath('benchmark.benchmark_id', 'SCENARIO-TEST')
                ->assertJsonPath('benchmark.scenarios.0.scenario', 'trend');
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_inventory_import_requires_an_xlsx_file(): void
    {
        $this->postJson('/api/inventory/import/preview')->assertUnprocessable()
            ->assertJsonValidationErrors('file');
    }

    public function test_inventory_preview_explains_period_sample_and_database_impact(): void
    {
        $path = tempnam(sys_get_temp_dir(), 'rayventory-import-');
        $this->assertNotFalse($path);
        $service = app(InventoryExcelService::class);
        $service->createTemplate($path, true);

        try {
            $preview = $service->preview(new UploadedFile(
                $path,
                'example.xlsx',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                null,
                true,
            ));

            $this->assertSame(8, $preview['counts']['products']);
            $this->assertSame(2920, $preview['counts']['sales']);
            $this->assertSame(365, $preview['period']['days']);
            $this->assertNotEmpty($preview['sample']);
            $this->assertSame(0, $preview['impact']['products']['current']);
            $this->assertSame($preview['counts']['products'], $preview['impact']['products']['next']);
            $this->assertSame($preview['counts']['products'], $preview['impact']['products']['delta']);

            $book = IOFactory::load($path);
            $sales = $book->getSheetByName('Продажи')?->toArray(null, true, true, false);
            $guide = $book->getSheetByName('Инструкция');
            $this->assertNotNull($sales);
            $this->assertSame('SKU-1001', $sales[1][0]);
            $this->assertSame('SKU-1008', $sales[8][0]);
            $this->assertSame('Стабильный', $guide?->getCell('B27')->getValue());
            $this->assertSame('Праздничный', $guide?->getCell('B34')->getValue());

            $bySku = [];
            foreach (array_slice($sales, 1) as $row) {
                $bySku[$row[0]][] = $row;
            }
            $this->assertCount(365, $bySku['SKU-1006']);
            $this->assertGreaterThan(300, count(array_filter(
                $bySku['SKU-1006'],
                fn (array $row): bool => (int) $row[2] === 0,
            )));
            $this->assertGreaterThan(0, count(array_filter(
                $bySku['SKU-1004'],
                fn (array $row): bool => (int) $row[5] === 1,
            )));
            $this->assertGreaterThan(0, count(array_filter(
                $bySku['SKU-1008'],
                fn (array $row): bool => (int) $row[4] === 1,
            )));
            $book->disconnectWorksheets();
        } finally {
            if (isset($preview['token'])) {
                File::delete(storage_path('app/import-previews/'.$preview['token'].'.json'));
            }
            @unlink($path);
        }
    }

    public function test_simulation_uses_the_single_synchronous_endpoint(): void
    {
        $productId = \DB::table('products')->insertGetId([
            'sku' => 'SKU-1', 'name' => 'Товар', 'category' => 'Тест', 'lead_time' => 2, 'unit_price' => 100,
        ]);
        $ml = $this->createMock(MlBridge::class);
        $ml->expects($this->once())->method('simulate')->with($productId, [
            'is_promo' => true, 'price_change' => 0.1,
        ])->willReturn(['success' => true, 'forecast' => ['q50' => [10, 11]]]);
        $this->app->instance(MlBridge::class, $ml);

        $this->postJson('/api/simulate', [
            'product_id' => $productId,
            'overrides' => ['is_promo' => true, 'price_change' => 0.1],
        ])->assertOk()->assertJsonPath('success', true);
        $this->postJson('/api/simulate/start', ['product_id' => $productId])->assertNotFound();
    }

    public function test_purchase_export_contains_auditable_formulas(): void
    {
        $path = tempnam(sys_get_temp_dir(), 'rayventory-test-').'.xlsx';
        app(InventoryExcelService::class)->createPurchasePlanExport($path, [[
            'sku' => 'SKU-1',
            'product_name' => 'Тестовый товар',
            'supplier' => 'Поставщик',
            'best_order_date' => '2026-09-02',
            'quantity' => 12,
            'unit_price' => 500,
            'stockout_date' => '2026-09-05',
            'recommended_quantity' => 15,
        ]], 10_000);

        try {
            $book = IOFactory::load($path);
            $this->assertSame(['Сводка', 'Заказ'], $book->getSheetNames());
            $this->assertSame('=F2*G2', $book->getSheetByName('Заказ')->getCell('H2')->getValue());
            $this->assertSame("=SUM('Заказ'!H2:H2)", $book->getSheetByName('Сводка')->getCell('B8')->getValue());
            $book->disconnectWorksheets();
        } finally {
            @unlink($path);
        }
    }

    public function test_report_download_does_not_accept_nested_paths(): void
    {
        $this->get('/download/reports/not-allowed.txt')->assertNotFound();
    }

    private function healthPlan(float $wape): array
    {
        return [
            'model' => 'Rayventory robust baseline',
            'data_as_of' => now()->toDateString(),
            'quality' => ['freshness_days' => 0],
            'evaluation' => [
                'wape_pct' => $wape,
                'bias_pct' => 1.2,
                'coverage_pct' => 82.0,
                'sku_count' => 3,
                'observations' => 90,
                'holdout_days' => 30,
            ],
        ];
    }
}
