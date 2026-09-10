<?php

namespace App\Jobs;

use App\Services\BranchContext;
use App\Services\LocalModelPipelineService;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;

class RunLocalTrainingPipeline implements ShouldQueue
{
    use Queueable;

    public int $timeout = 3600;

    public function __construct(public readonly string $pipelineId, public readonly int $branchId) {}

    public function handle(LocalModelPipelineService $pipeline, BranchContext $branches): void
    {
        $branches->resolve($this->branchId);
        $pipeline->execute($this->pipelineId);
    }
}
