<?php

namespace Tests\Feature;

use App\Jobs\RunLocalTrainingPipeline;
use App\Services\LocalModelPipelineService;
use App\Services\LocalTrainingService;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class LocalTrainingReadinessTest extends TestCase
{
    public function test_readiness_matches_three_rolling_fold_history_boundary(): void
    {
        foreach ([175 => false, 261 => false, 262 => true] as $days => $ready) {
            DB::table('sales_history')->where('branch_id', $this->branchId)->delete();
            $this->insertHistory($days);
            $readiness = app(LocalTrainingService::class)->readiness();

            $this->assertSame($ready, $readiness['ready'], "History length: {$days}");
            $this->assertSame($ready ? 1 : 0, $readiness['series_eligible']);
            $this->assertSame(262, $readiness['minimum_days']);
            $this->assertSame(262, $readiness['minimum_observations']);
            $this->assertSame(3, $readiness['rolling_folds']);
        }
    }

    public function test_long_span_with_sparse_observations_is_not_ready_or_queued(): void
    {
        $this->insertHistory(365, sparse: true);
        $directory = sys_get_temp_dir().'/rayventory-sparse-training-'.bin2hex(random_bytes(5));
        config(['rayventory.training_jobs_path' => $directory]);
        Queue::fake();

        try {
            $readiness = app(LocalTrainingService::class)->readiness();
            $this->assertSame(365, $readiness['minimum_series_span_days']);
            $this->assertFalse($readiness['ready']);
            $status = app(LocalModelPipelineService::class)->schedule();
            $this->assertSame('skipped', $status['status']);
            Queue::assertNothingPushed();
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_ready_pipeline_is_queued_once_with_branch_and_pipeline_id(): void
    {
        $this->insertHistory(262);
        $directory = sys_get_temp_dir().'/rayventory-queued-training-'.bin2hex(random_bytes(5));
        config(['rayventory.training_jobs_path' => $directory]);
        Queue::fake();

        try {
            $pipeline = app(LocalModelPipelineService::class);
            $status = $pipeline->schedule('manual');
            $this->assertSame('queued', $status['status']);
            Queue::assertPushed(RunLocalTrainingPipeline::class, function (RunLocalTrainingPipeline $job) use ($status): bool {
                return $job->pipelineId === $status['id'] && $job->branchId === $this->branchId;
            });
            $this->assertSame($status, $pipeline->schedule('excel_import'));
            Queue::assertPushed(RunLocalTrainingPipeline::class, 1);
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_known_stockout_on_last_day_blocks_training_queue(): void
    {
        $this->insertHistory(262);
        DB::table('sales_history')->where('sale_date', '2025-09-19')->update(['in_stock' => 0]);
        $directory = sys_get_temp_dir().'/rayventory-censored-training-'.bin2hex(random_bytes(5));
        config(['rayventory.training_jobs_path' => $directory]);
        Queue::fake();

        try {
            $readiness = app(LocalTrainingService::class)->readiness();
            $this->assertFalse($readiness['ready']);
            $this->assertSame(1, $readiness['series_eligible']);
            $this->assertSame(2, $readiness['test_folds_available']);
            $this->assertSame(0, $readiness['test_fold_checks'][2]['series_uncensored']);
            $this->assertStringContainsString('дефицит', $readiness['message']);
            $this->assertSame('skipped', app(LocalModelPipelineService::class)->schedule()['status']);
            Queue::assertNothingPushed();
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_unknown_availability_does_not_censor_a_test_fold(): void
    {
        // Imported or external SQLite sources can preserve unknown availability.
        Schema::table('sales_history', fn ($table) => $table->boolean('in_stock')->nullable()->change());
        $this->insertHistory(262);
        DB::table('sales_history')->where('sale_date', '2025-09-19')->update(['in_stock' => null]);

        $readiness = app(LocalTrainingService::class)->readiness();
        $this->assertTrue($readiness['ready']);
        $this->assertSame(3, $readiness['test_folds_available']);
    }

    public function test_different_uncensored_skus_can_supply_different_test_folds(): void
    {
        $this->insertHistory(262);
        $this->insertHistory(262, productId: 2);
        DB::table('sales_history')->where('product_id', 1)->where('sale_date', '2025-09-19')->update(['in_stock' => 0]);
        DB::table('sales_history')->where('product_id', 2)->where('sale_date', '2025-07-25')->update(['in_stock' => 0]);

        $readiness = app(LocalTrainingService::class)->readiness();
        $this->assertTrue($readiness['ready']);
        $this->assertSame(2, $readiness['series_eligible']);
        $this->assertSame(3, $readiness['test_folds_available']);
        $this->assertSame([1, 2, 1], array_column($readiness['test_fold_checks'], 'series_uncensored'));
    }

    public function test_censored_earliest_fold_is_blocked_even_if_latest_fold_is_clean(): void
    {
        $this->insertHistory(262);
        DB::table('sales_history')->where('sale_date', '2025-07-25')->update(['in_stock' => 0]);

        $readiness = app(LocalTrainingService::class)->readiness();
        $this->assertFalse($readiness['ready']);
        $this->assertSame(2, $readiness['test_folds_available']);
        $this->assertSame(0, $readiness['test_fold_checks'][0]['series_uncensored']);
        $this->assertSame(1, $readiness['test_fold_checks'][2]['series_uncensored']);
    }

    public function test_database_queue_reservation_exceeds_training_job_timeout(): void
    {
        $job = new RunLocalTrainingPipeline('TRAIN-CONFIG-TEST', $this->branchId);
        $this->assertGreaterThan($job->timeout, config('queue.connections.database.retry_after'));
        $this->assertSame('database', config('queue.default'));
        $this->assertSame('database', config('queue.connections.database.driver'));
        $this->assertNull(config('queue.connections.database.connection'));
        $this->assertSame('jobs', config('queue.connections.database.table'));
        $this->assertSame('sync', config('queue.connections.sync.driver'));
        $this->assertSame('database-uuids', config('queue.failed.driver'));
    }

    private function insertHistory(int $days, bool $sparse = false, int $productId = 1): void
    {
        $start = CarbonImmutable::parse('2025-01-01');
        $offsets = $sparse ? [0, $days - 1] : range(0, $days - 1);
        $rows = array_map(fn (int $day): array => [
            'branch_id' => $this->branchId, 'product_id' => $productId,
            'sale_date' => $start->addDays($day)->toDateString(),
            'quantity_sold' => 10, 'in_stock' => 1,
        ], $offsets);
        DB::table('sales_history')->insert($rows);
    }
}
