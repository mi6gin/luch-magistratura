<?php

namespace Tests;

use Illuminate\Database\Schema\Blueprint;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;
use Illuminate\Support\Facades\Schema;

abstract class TestCase extends BaseTestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        Schema::create('products', function (Blueprint $table): void {
            $table->id();
            $table->string('sku')->nullable();
            $table->string('name');
            $table->string('category')->nullable();
            $table->unsignedInteger('lead_time')->default(1);
            $table->decimal('unit_price', 14, 2)->default(0);
        });
        Schema::create('suppliers', function (Blueprint $table): void {
            $table->id();
            $table->string('name');
        });
        Schema::create('product_planning_settings', function (Blueprint $table): void {
            $table->unsignedBigInteger('product_id')->primary();
            $table->unsignedBigInteger('supplier_id')->nullable();
        });
    }

    protected function tearDown(): void
    {
        Schema::dropAllTables();
        parent::tearDown();
    }
}
