<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('products')) {
            Schema::create('products', function (Blueprint $table): void {
                $table->id();
                $table->string('sku', 80)->nullable()->index();
                $table->string('name');
                $table->string('category')->nullable();
                $table->unsignedInteger('lead_time')->default(1);
                $table->decimal('unit_price', 14, 2)->default(0);
            });
        }
        if (! Schema::hasTable('sales_history')) {
            Schema::create('sales_history', function (Blueprint $table): void {
                $table->unsignedBigInteger('product_id')->index();
                $table->date('sale_date')->index();
                $table->integer('quantity_sold')->default(0);
                $table->boolean('in_stock')->default(true);
                $table->boolean('is_holiday')->default(false);
                $table->boolean('is_promo')->default(false);
            });
        }
        if (! Schema::hasTable('warehouse_stock')) {
            Schema::create('warehouse_stock', function (Blueprint $table): void {
                $table->unsignedBigInteger('product_id')->primary();
                $table->integer('current_quantity')->default(0);
                $table->string('warehouse')->nullable();
                $table->date('as_of_date')->nullable();
                $table->integer('reserved_quantity')->default(0);
            });
        }
        if (! Schema::hasTable('warehouse_in_transit')) {
            Schema::create('warehouse_in_transit', function (Blueprint $table): void {
                $table->unsignedBigInteger('product_id')->primary();
                $table->integer('in_transit_quantity')->default(0);
                $table->string('order_number')->nullable();
                $table->date('expected_date')->nullable();
                $table->string('status')->nullable();
                $table->string('supplier')->nullable();
            });
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('warehouse_in_transit');
        Schema::dropIfExists('warehouse_stock');
        Schema::dropIfExists('sales_history');
        Schema::dropIfExists('products');
    }
};
