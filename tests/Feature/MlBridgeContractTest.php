<?php

namespace Tests\Feature;

use App\Services\MlBridge;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class MlBridgeContractTest extends TestCase
{
    public function test_simulation_sends_an_object_for_empty_and_populated_overrides(): void
    {
        $script = tempnam(sys_get_temp_dir(), 'rayventory-json-contract-');
        $this->assertNotFalse($script);
        File::put($script, <<<'PHP'
<?php
$payload = json_decode(base64_decode($argv[3]), false, 512, JSON_THROW_ON_ERROR);
echo json_encode([
    'success' => true,
    'overrides_is_object' => is_object($payload->overrides),
    'overrides_keys' => array_keys((array) $payload->overrides),
    'product_id' => $payload->product_id,
], JSON_THROW_ON_ERROR);
PHP);
        config(['rayventory.python' => PHP_BINARY, 'rayventory.engine_path' => $script]);

        try {
            $empty = app(MlBridge::class)->simulate(1);
            $this->assertTrue($empty['success']);
            $this->assertTrue($empty['overrides_is_object']);
            $this->assertSame([], $empty['overrides_keys']);
            $populated = app(MlBridge::class)->simulate(1, ['is_promo' => true]);
            $this->assertTrue($populated['overrides_is_object']);
            $this->assertSame(['is_promo'], $populated['overrides_keys']);
        } finally {
            File::delete($script);
        }
    }
}
