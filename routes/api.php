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
Route::get('model-health', [ApiController::class, 'modelHealth']);
Route::get('experiments', [ApiController::class, 'experiments']);
Route::get('experiments/{id}', [ApiController::class, 'experiment'])->where('id', 'EXP-[A-Z0-9-]+');
Route::post('simulate', [ApiController::class, 'simulate']);
Route::post('generate-report', [ApiController::class, 'generateReport']);
