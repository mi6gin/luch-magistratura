<?php

use App\Http\Controllers\ApiController;
use Illuminate\Support\Facades\Route;

Route::middleware(['web', 'auth', 'branch.access', 'audit'])->group(function (): void {
    Route::get('ai-briefing', [ApiController::class, 'aiBriefing']);
    Route::get('branches', [ApiController::class, 'branches']);
    Route::post('branches', [ApiController::class, 'createBranch']);
    Route::get('branches-summary', [ApiController::class, 'branchesSummary']);
    Route::get('users', [ApiController::class, 'users']);
    Route::post('users', [ApiController::class, 'createUser']);
    Route::post('account/password', [ApiController::class, 'changePassword']);
    Route::get('dashboard-stats', [ApiController::class, 'dashboardStats']);
    Route::get('activity-events', [ApiController::class, 'activityEvents']);
    Route::get('stock', [ApiController::class, 'stock']);
    Route::get('purchase-plan', [ApiController::class, 'purchasePlan']);
    Route::post('purchase-plan/export', [ApiController::class, 'exportPurchasePlan']);
    Route::post('stock/update', [ApiController::class, 'updateStock']);
    Route::post('inventory/import/preview', [ApiController::class, 'previewInventoryImport']);
    Route::post('inventory/import/confirm', [ApiController::class, 'confirmInventoryImport']);
    Route::get('model-health', [ApiController::class, 'modelHealth']);
    Route::get('experiments', [ApiController::class, 'experiments']);
    Route::get('experiments/{id}', [ApiController::class, 'experiment'])->where('id', 'EXP-[A-Z0-9-]+');
    Route::get('models', [ApiController::class, 'models']);
    Route::get('training-readiness', [ApiController::class, 'trainingReadiness']);
    Route::get('training-pipeline', [ApiController::class, 'trainingPipeline']);
    Route::post('training-pipeline', [ApiController::class, 'startTrainingPipeline']);
    Route::get('dataset-analysis', [ApiController::class, 'datasetAnalysis']);
    Route::get('tuning', [ApiController::class, 'tuning']);
    Route::get('scenarios', [ApiController::class, 'scenarios']);
    Route::get('research-report', [ApiController::class, 'researchReport']);
    Route::get('research-report/chart/{model}', [ApiController::class, 'researchChart'])->where('model', 'lstm|gru|transformer');
    Route::post('models/candidates', [ApiController::class, 'registerModelCandidate']);
    Route::post('models/{id}/promote', [ApiController::class, 'promoteModel'])->where('id', '[A-Za-z0-9_-]+(?:--[A-Za-z0-9_-]+)?');
    Route::post('simulate', [ApiController::class, 'simulate']);
    Route::post('generate-report', [ApiController::class, 'generateReport']);
});
