<?php

use App\Http\Controllers\ApiController;
use Illuminate\Support\Facades\Route;

Route::get('ai-briefing', [ApiController::class, 'aiBriefing']);
Route::get('dashboard-stats', [ApiController::class, 'dashboardStats']);
Route::get('stock', [ApiController::class, 'stock']);
Route::get('purchase-plan', [ApiController::class, 'purchasePlan']);
Route::post('purchase-plan/export', [ApiController::class, 'exportPurchasePlan']);
Route::post('stock/update', [ApiController::class, 'updateStock']);
Route::post('inventory/import/preview', [ApiController::class, 'previewInventoryImport']);
Route::post('inventory/import/confirm', [ApiController::class, 'confirmInventoryImport']);
Route::post('simulate', [ApiController::class, 'simulate']);
Route::post('simulate/start', [ApiController::class, 'startSimulation']);
Route::get('jobs/{jobId}', [ApiController::class, 'job']);
Route::post('generate-report', [ApiController::class, 'generateReport']);
