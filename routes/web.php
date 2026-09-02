<?php

use App\Http\Controllers\ApiController;
use Illuminate\Support\Facades\Route;

Route::view('/', 'pages.dashboard')->name('dashboard');
Route::view('/inventory', 'pages.inventory')->name('inventory');
Route::view('/simulator', 'pages.simulator')->name('simulator');
Route::view('/purchases', 'pages.purchases')->name('purchases');
Route::view('/model-health', 'pages.model-health')->name('model-health');
Route::view('/reports', 'pages.reports')->name('reports');
Route::view('/knowledge', 'pages.knowledge')->name('knowledge');
Route::get('download/inventory-template', [ApiController::class, 'inventoryTemplate'])
    ->name('inventory.template');
Route::get('download/reports/{filename}', [ApiController::class, 'downloadReport'])
    ->where('filename', '[^/]+');
