<?php

namespace Tests\Feature;

use App\Services\InventoryExcelService;
use App\Services\MlBridge;
use App\Services\ModelHealthService;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\File;
use PhpOffice\PhpSpreadsheet\IOFactory;
use Tests\TestCase;

class ApplicationTest extends TestCase
{
    public function test_all_workspace_pages_are_available(): void
    {
        foreach (['/', '/inventory', '/simulator', '/purchases', '/reports', '/knowledge', '/model-health'] as $path) {
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

            $this->assertGreaterThanOrEqual(365, $preview['period']['days']);
            $this->assertNotEmpty($preview['sample']);
            $this->assertSame(0, $preview['impact']['products']['current']);
            $this->assertSame($preview['counts']['products'], $preview['impact']['products']['next']);
            $this->assertSame($preview['counts']['products'], $preview['impact']['products']['delta']);
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
