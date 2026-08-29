<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\ApiController;

Route::view('/', 'pages.dashboard')->name('dashboard');
Route::view('/inventory', 'pages.inventory')->name('inventory');
Route::view('/simulator', 'pages.simulator')->name('simulator');
Route::view('/reports', 'pages.reports')->name('reports');
Route::view('/knowledge', 'pages.knowledge')->name('knowledge');
Route::get('download/reports/{filename}', [ApiController::class, 'downloadReport'])
    ->where('filename', '[^/]+');
