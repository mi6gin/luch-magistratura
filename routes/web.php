<?php

use App\Http\Controllers\ApiController;
use App\Http\Controllers\AuthController;
use Illuminate\Support\Facades\Route;

Route::middleware('guest')->group(function (): void {
    Route::get('/login', [AuthController::class, 'form'])->name('login');
    Route::post('/login', [AuthController::class, 'login'])->name('login.submit');
});
Route::middleware(['auth', 'branch.access'])->group(function (): void {
    Route::view('/', 'pages.dashboard')->name('dashboard');
    Route::view('/inventory', 'pages.inventory')->name('inventory');
    Route::view('/simulator', 'pages.simulator')->name('simulator');
    Route::view('/purchases', 'pages.purchases')->name('purchases');
    Route::view('/model-health', 'pages.model-health')->name('model-health');
    Route::view('/experiments', 'pages.experiments')->name('experiments');
    Route::view('/reports', 'pages.reports')->name('reports');
    Route::view('/knowledge', 'pages.knowledge')->name('knowledge');
    Route::get('/settings', [AuthController::class, 'settings'])->name('settings');
    Route::get('download/inventory-template', [ApiController::class, 'inventoryTemplate'])
        ->name('inventory.template');
    Route::get('download/reports/{filename}', [ApiController::class, 'downloadReport'])
        ->where('filename', '[^/]+');
    Route::post('/logout', [AuthController::class, 'logout'])->name('logout');
});
