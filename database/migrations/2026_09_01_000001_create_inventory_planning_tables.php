<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasColumn('products', 'sku')) {
            Schema::table('products', fn (Blueprint $table) => $table->string('sku', 80)->nullable()->index());
        }

        Schema::create('warehouses', function (Blueprint $table): void {
            $table->id();
            $table->string('code', 40)->unique();
            $table->string('name');
            $table->boolean('active')->default(true);
            $table->timestamps();
        });

        Schema::create('suppliers', function (Blueprint $table): void {
            $table->id();
            $table->string('name');
            $table->string('currency', 3)->default('KZT');
            $table->unsignedInteger('default_lead_time_days')->default(7);
            $table->decimal('minimum_order_value', 14, 2)->default(0);
            $table->timestamps();
        });

        Schema::create('inventory_snapshots', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('product_id');
            $table->foreignId('warehouse_id')->constrained()->cascadeOnDelete();
            $table->date('snapshot_date');
            $table->integer('available_quantity')->default(0);
            $table->integer('reserved_quantity')->default(0);
            $table->timestamps();
            $table->unique(['product_id', 'warehouse_id', 'snapshot_date'], 'inventory_snapshot_unique');
        });

        Schema::create('product_planning_settings', function (Blueprint $table): void {
            $table->unsignedBigInteger('product_id')->primary();
            $table->foreignId('supplier_id')->nullable()->constrained()->nullOnDelete();
            $table->unsignedInteger('safety_stock_days')->default(14);
            $table->unsignedInteger('target_cover_days')->default(45);
            $table->unsignedInteger('minimum_order_quantity')->default(1);
            $table->unsignedInteger('pack_size')->default(1);
            $table->boolean('replenishable')->default(true);
            $table->timestamps();
        });

        Schema::create('purchase_orders', function (Blueprint $table): void {
            $table->id();
            $table->string('order_number', 80)->unique();
            $table->foreignId('supplier_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('warehouse_id')->nullable()->constrained()->nullOnDelete();
            $table->string('status', 30)->default('draft');
            $table->date('ordered_at')->nullable();
            $table->date('expected_at')->nullable();
            $table->date('received_at')->nullable();
            $table->timestamps();
        });

        Schema::create('purchase_order_lines', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('purchase_order_id')->constrained()->cascadeOnDelete();
            $table->unsignedBigInteger('product_id');
            $table->unsignedInteger('ordered_quantity');
            $table->unsignedInteger('received_quantity')->default(0);
            $table->decimal('unit_cost', 14, 2)->default(0);
            $table->date('expected_at')->nullable();
            $table->timestamps();
            $table->unique(['purchase_order_id', 'product_id'], 'purchase_order_product_unique');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('purchase_order_lines');
        Schema::dropIfExists('purchase_orders');
        Schema::dropIfExists('product_planning_settings');
        Schema::dropIfExists('inventory_snapshots');
        Schema::dropIfExists('suppliers');
        Schema::dropIfExists('warehouses');
        if (Schema::hasColumn('products', 'sku')) {
            Schema::table('products', fn (Blueprint $table) => $table->dropColumn('sku'));
        }
    }
};
