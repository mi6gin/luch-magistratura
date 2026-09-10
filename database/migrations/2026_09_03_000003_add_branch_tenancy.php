<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('organizations', function (Blueprint $table): void {
            $table->id();
            $table->string('name');
            $table->string('code', 40)->unique();
            $table->timestamps();
        });
        Schema::create('branches', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('organization_id')->constrained()->cascadeOnDelete();
            $table->string('name');
            $table->string('code', 40);
            $table->boolean('active')->default(true);
            $table->timestamps();
            $table->unique(['organization_id', 'code']);
        });

        $now = now();
        $organizationId = DB::table('organizations')->insertGetId([
            'name' => 'ЛУЧ', 'code' => 'luch', 'created_at' => $now, 'updated_at' => $now,
        ]);
        $branchId = DB::table('branches')->insertGetId([
            'organization_id' => $organizationId, 'name' => 'Основной филиал',
            'code' => 'main', 'active' => true, 'created_at' => $now, 'updated_at' => $now,
        ]);

        Schema::create('users', function (Blueprint $table): void {
            $table->id();
            $table->string('name');
            $table->string('email')->unique();
            $table->string('password');
            $table->boolean('is_admin')->default(false);
            $table->rememberToken();
            $table->timestamps();
        });
        Schema::create('branch_user', function (Blueprint $table): void {
            $table->foreignId('branch_id')->constrained()->cascadeOnDelete();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('role', 20)->default('viewer');
            $table->primary(['branch_id', 'user_id']);
        });
        Schema::create('audit_logs', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('branch_id')->nullable()->index();
            $table->foreignId('user_id')->nullable()->index();
            $table->string('method', 10);
            $table->string('path');
            $table->unsignedSmallInteger('status');
            $table->string('ip', 45)->nullable();
            $table->timestamp('created_at')->useCurrent();
        });

        Schema::create('branch_products', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('branch_id')->constrained()->cascadeOnDelete();
            $table->unsignedBigInteger('product_id');
            $table->unsignedInteger('lead_time')->default(1);
            $table->decimal('unit_price', 14, 2)->default(0);
            $table->boolean('active')->default(true);
            $table->timestamps();
            $table->unique(['branch_id', 'product_id']);
        });
        foreach (DB::table('products')->get() as $product) {
            DB::table('branch_products')->insert([
                'branch_id' => $branchId,
                'product_id' => $product->id,
                'lead_time' => max(1, (int) ($product->lead_time ?? 1)),
                'unit_price' => max(0, (float) ($product->unit_price ?? 0)),
                'active' => true, 'created_at' => $now, 'updated_at' => $now,
            ]);
        }

        Schema::table('sales_history', function (Blueprint $table): void {
            $table->foreignId('branch_id')->nullable()->index();
        });
        DB::table('sales_history')->whereNull('branch_id')->update(['branch_id' => $branchId]);
        Schema::table('sales_history', function (Blueprint $table): void {
            $table->unique(['branch_id', 'product_id', 'sale_date'], 'sales_branch_product_date_unique');
        });
        Schema::table('products', function (Blueprint $table): void {
            $table->unique('sku');
        });

        $this->rebuildScopedTable('warehouse_stock', $branchId, function (Blueprint $table): void {
            $table->id();
            $table->foreignId('branch_id')->index();
            $table->unsignedBigInteger('product_id')->index();
            $table->integer('current_quantity')->default(0);
            $table->string('warehouse')->nullable();
            $table->date('as_of_date')->nullable();
            $table->integer('reserved_quantity')->default(0);
            $table->unique(['branch_id', 'product_id', 'warehouse'], 'stock_branch_product_warehouse_unique');
        });
        $this->rebuildScopedTable('warehouse_in_transit', $branchId, function (Blueprint $table): void {
            $table->id();
            $table->foreignId('branch_id')->index();
            $table->unsignedBigInteger('product_id')->index();
            $table->integer('in_transit_quantity')->default(0);
            $table->string('order_number')->nullable();
            $table->date('expected_date')->nullable();
            $table->string('status')->nullable();
            $table->string('supplier')->nullable();
            $table->unique(['branch_id', 'order_number', 'product_id'], 'transit_branch_order_product_unique');
        });

        foreach (['inventory_snapshots', 'purchase_orders', 'warehouses', 'suppliers'] as $table) {
            Schema::table($table, function (Blueprint $blueprint): void {
                $blueprint->foreignId('branch_id')->nullable()->index();
            });
            DB::table($table)->whereNull('branch_id')->update(['branch_id' => $branchId]);
        }
        Schema::rename('product_planning_settings', 'product_planning_settings_pre_branches');
        Schema::create('product_planning_settings', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('branch_id')->index();
            $table->unsignedBigInteger('product_id')->index();
            $table->foreignId('supplier_id')->nullable()->constrained()->nullOnDelete();
            $table->unsignedInteger('safety_stock_days')->default(14);
            $table->unsignedInteger('target_cover_days')->default(45);
            $table->unsignedInteger('minimum_order_quantity')->default(1);
            $table->unsignedInteger('pack_size')->default(1);
            $table->boolean('replenishable')->default(true);
            $table->timestamps();
            $table->unique(['branch_id', 'product_id']);
        });
        foreach (DB::table('product_planning_settings_pre_branches')->get() as $row) {
            $values = (array) $row;
            $values['branch_id'] = $branchId;
            DB::table('product_planning_settings')->insert($values);
        }
        Schema::drop('product_planning_settings_pre_branches');
    }

    private function rebuildScopedTable(string $name, int $branchId, Closure $definition): void
    {
        $legacy = $name.'_pre_branches';
        Schema::rename($name, $legacy);
        Schema::create($name, $definition);
        foreach (DB::table($legacy)->get() as $row) {
            $values = (array) $row;
            unset($values['id']);
            $values['branch_id'] = $branchId;
            DB::table($name)->insert($values);
        }
        Schema::drop($legacy);
    }

    public function down(): void
    {
        throw new RuntimeException('Branch tenancy migration is intentionally irreversible. Restore a backup instead.');
    }
};
