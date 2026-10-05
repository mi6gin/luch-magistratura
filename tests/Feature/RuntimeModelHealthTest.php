<?php

namespace Tests\Feature;

use App\Services\ModelHealthService;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class RuntimeModelHealthTest extends TestCase
{
    public function test_health_labels_metrics_with_the_evaluated_model(): void
    {
        $directory = sys_get_temp_dir().'/rayventory-runtime-health-'.bin2hex(random_bytes(5));
        config(['rayventory.model_health_path' => $directory]);

        try {
            $record = app(ModelHealthService::class)->record([
                'model' => 'local-demand-router-v1',
                'data_as_of' => now()->toDateString(),
                'quality' => ['freshness_days' => 0],
                'evaluation' => [
                    'model' => 'seasonal-robust-v1', 'wape_pct' => 25.0,
                    'sku_count' => 1, 'observations' => 28,
                ],
            ], 'manual');

            $this->assertSame('seasonal-robust-v1', $record['model']);
            $this->assertSame('local-demand-router-v1', $record['forecast_model']);
            $this->assertSame(25.0, $record['metrics']['wape_pct']);
            $this->assertTrue($record['evaluable']);
        } finally {
            File::deleteDirectory($directory);
        }
    }
}
