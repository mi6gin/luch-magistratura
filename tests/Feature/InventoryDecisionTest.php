<?php

namespace Tests\Feature;

use App\Services\MlBridge;
use App\Services\ModelRegistryService;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class InventoryDecisionTest extends TestCase
{
    public function test_research_winner_without_working_forecast_evidence_is_blocked(): void
    {
        $root = sys_get_temp_dir().'/rayventory-runtime-proof-'.bin2hex(random_bytes(5));
        $id = 'EXP-20261031T120000Z-ABC123';
        config([
            'rayventory.experiments_path' => $root.'/experiments',
            'rayventory.model_registry_path' => $root.'/registry.json',
            'rayventory.models_path' => $root.'/models',
        ]);
        $directory = $root.'/experiments/branches/1/'.$id;
        File::ensureDirectoryExists($directory);
        try {
            File::put($directory.'/result.json', json_encode([
                'experiment_id' => $id,
                'dataset' => ['dataset' => 'Local Rayventory inventory'],
                'rolling_folds' => 3,
                'results' => [[
                    'model' => 'adaptive_demand_router',
                    'routes' => ['smooth' => 'moving_median_28'],
                    'metrics' => ['wape_pct' => 1.0],
                ]],
            ], JSON_THROW_ON_ERROR));
            $candidate = app(ModelRegistryService::class)->registerCandidate($id, 'adaptive_demand_router');
            $this->assertFalse($candidate['eligible']);
            $this->assertFalse(collect($candidate['checks'])->firstWhere('code', 'beats_baseline')['passed']);
        } finally {
            File::deleteDirectory($root);
        }
    }

    public function test_export_rejects_partial_packs_even_if_client_submits_them(): void
    {
        \DB::table('products')->insert(['id' => 1, 'sku' => 'PACK-1', 'name' => 'Pack item', 'category' => 'Test', 'lead_time' => 1, 'unit_price' => 100]);
        \DB::table('branch_products')->insert(['branch_id' => 1, 'product_id' => 1, 'lead_time' => 1, 'unit_price' => 100, 'active' => true, 'created_at' => now(), 'updated_at' => now()]);
        \DB::table('sales_history')->insert(['branch_id' => 1, 'product_id' => 1, 'sale_date' => today()->toDateString(), 'quantity_sold' => 1, 'in_stock' => true, 'is_holiday' => false, 'is_promo' => false]);
        $ml = $this->createMock(MlBridge::class);
        $ml->method('planning')->willReturn(['success' => true, 'actions' => [[
            'product_id' => 1, 'order_quantity' => 120,
            'planning' => ['pack_size' => 24, 'minimum_order_quantity' => 100],
        ]]]);
        $this->app->instance(MlBridge::class, $ml);
        foreach ([99, 100, 119] as $quantity) {
            $this->postJson('/api/purchase-plan/export', ['items' => [['product_id' => 1, 'quantity' => $quantity]]])
                ->assertUnprocessable()
                ->assertJsonPath('message', 'Количество нарушает минимальную партию или кратность упаковки.');
        }
    }
}
