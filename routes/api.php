<?php

use App\Http\Controllers\ApiController;
use Illuminate\Support\Facades\Route;

Route::get('ai-briefing', [ApiController::class, 'aiBriefing']);
Route::get('dashboard-stats', [ApiController::class, 'dashboardStats']);
Route::get('stock', [ApiController::class, 'stock']);
Route::post('stock/update', [ApiController::class, 'updateStock']);
Route::post('simulate', [ApiController::class, 'simulate']);
Route::post('simulate/start', [ApiController::class, 'startSimulation']);
Route::get('jobs/{jobId}', [ApiController::class, 'job']);
Route::post('generate-report', [ApiController::class, 'generateReport']);
