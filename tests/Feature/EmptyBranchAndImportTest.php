<?php

namespace Tests\Feature;

use App\Services\InventoryExcelService;
use App\Services\MlBridge;
use Illuminate\Http\UploadedFile;
use PhpOffice\PhpSpreadsheet\IOFactory;
use PhpOffice\PhpSpreadsheet\Writer\Xlsx;
use Tests\TestCase;

class EmptyBranchAndImportTest extends TestCase
{
    public function test_empty_branch_has_an_explicit_no_data_state_without_calling_ml(): void
    {
        $ml = $this->createMock(MlBridge::class);
        $ml->expects($this->never())->method('planning');
        $ml->expects($this->never())->method('generateReport');
        $this->app->instance(MlBridge::class, $ml);

        $this->getJson('/api/purchase-plan')->assertOk()
            ->assertJsonPath('has_data', false)->assertJsonPath('actions', []);
        $this->getJson('/api/model-health')->assertOk()
            ->assertJsonPath('has_data', false)->assertJsonPath('latest', null);
        $this->postJson('/api/generate-report', ['type' => 'standard', 'formats' => ['pdf']])
            ->assertUnprocessable();
    }

    public function test_duplicate_sku_date_sales_are_rejected_in_preview(): void
    {
        $path = sys_get_temp_dir().'/duplicate-sales-'.bin2hex(random_bytes(5)).'.xlsx';
        app(InventoryExcelService::class)->createTemplate($path, true);

        try {
            $book = IOFactory::load($path);
            $sales = $book->getSheetByName('Продажи');
            $first = $sales->rangeToArray('A2:F2')[0];
            $sales->fromArray([$first], null, 'A2922');
            (new Xlsx($book))->save($path);
            $book->disconnectWorksheets();
            $file = new UploadedFile($path, 'duplicate-sales.xlsx', null, null, true);

            $response = $this->post('/api/inventory/import/preview', ['file' => $file], ['Accept' => 'application/json']);
            $response->assertUnprocessable();
            $this->assertStringContainsString('одного SKU и даты', $response->json('error'));
            $this->assertDatabaseCount('products', 0);
            $this->assertDatabaseCount('sales_history', 0);
        } finally {
            @unlink($path);
        }
    }

    public function test_import_cannot_rename_a_product_used_by_another_branch(): void
    {
        $branchId = \DB::table('branches')->insertGetId([
            'organization_id' => 1, 'name' => 'Other branch', 'code' => 'other-import',
            'active' => true, 'created_at' => now(), 'updated_at' => now(),
        ]);
        \DB::table('products')->insert(['id' => 1, 'sku' => 'SKU-1001', 'name' => 'Original catalog name', 'category' => 'Original category', 'lead_time' => 1, 'unit_price' => 100]);
        \DB::table('branch_products')->insert(['branch_id' => 1, 'product_id' => 1, 'lead_time' => 1, 'unit_price' => 100, 'active' => true, 'created_at' => now(), 'updated_at' => now()]);
        $path = sys_get_temp_dir().'/shared-catalog-'.bin2hex(random_bytes(5)).'.xlsx';
        app(InventoryExcelService::class)->createTemplate($path, true);

        try {
            $file = new UploadedFile($path, 'shared-catalog.xlsx', null, null, true);
            $response = $this->post('/api/inventory/import/preview', ['file' => $file], [
                'Accept' => 'application/json', 'X-Branch-ID' => (string) $branchId,
            ]);
            $response->assertUnprocessable();
            $this->assertStringContainsString('других филиалах', $response->json('error'));
            $this->assertDatabaseHas('products', ['id' => 1, 'name' => 'Original catalog name']);
            $this->assertDatabaseMissing('branch_products', ['branch_id' => $branchId]);
        } finally {
            @unlink($path);
        }
    }
}
