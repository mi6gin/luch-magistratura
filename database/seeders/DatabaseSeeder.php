<?php

namespace Database\Seeders;

use App\Models\Branch;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

class DatabaseSeeder extends Seeder
{
    public function run(): void
    {
        $adminPassword = config('rayventory.admin_password');
        if (app()->environment('production') && (! is_string($adminPassword) || strlen($adminPassword) < 12)) {
            throw new \RuntimeException('RAYVENTORY_ADMIN_PASSWORD must be explicitly set to at least 12 characters in production.');
        }
        $adminPassword = $adminPassword ?: 'ChangeMe123!';
        $user = User::firstOrCreate(
            ['email' => config('rayventory.admin_email')],
            ['name' => 'Ray Admin', 'password' => $adminPassword, 'is_admin' => true],
        );
        foreach (Branch::pluck('id') as $branchId) {
            $user->branches()->syncWithoutDetaching([$branchId => ['role' => 'admin']]);
        }
        if (DB::table('products')->exists()) {
            return;
        }

        $branchId = (int) Branch::orderBy('id')->value('id');
        $products = [
            ['sku' => 'SKU-1001', 'name' => 'Молоко 3,2% 1 л', 'category' => 'Молочные продукты', 'lead_time' => 2, 'unit_price' => 620],
            ['sku' => 'SKU-1002', 'name' => 'Хлеб пшеничный 500 г', 'category' => 'Хлеб и выпечка', 'lead_time' => 1, 'unit_price' => 280],
            ['sku' => 'SKU-1003', 'name' => 'Яблоки Голден 1 кг', 'category' => 'Фрукты и овощи', 'lead_time' => 3, 'unit_price' => 890],
            ['sku' => 'SKU-1004', 'name' => 'Кофе зерновой 500 г', 'category' => 'Бакалея', 'lead_time' => 7, 'unit_price' => 4200],
            ['sku' => 'SKU-1005', 'name' => 'Мороженое пломбир', 'category' => 'Замороженные продукты', 'lead_time' => 4, 'unit_price' => 550],
            ['sku' => 'SKU-1006', 'name' => 'Фильтр для принтера', 'category' => 'Расходные материалы', 'lead_time' => 14, 'unit_price' => 6800],
            ['sku' => 'SKU-1007', 'name' => 'Батарейки AA, 4 шт.', 'category' => 'Хозяйственные товары', 'lead_time' => 10, 'unit_price' => 1450],
            ['sku' => 'SKU-1008', 'name' => 'Шоколад подарочный', 'category' => 'Кондитерские изделия', 'lead_time' => 5, 'unit_price' => 2300],
        ];
        $start = Carbon::today()->subDays(364);
        foreach ($products as $index => $product) {
            $id = DB::table('products')->insertGetId($product);
            DB::table('branch_products')->insert([
                'branch_id' => $branchId, 'product_id' => $id, 'lead_time' => $product['lead_time'],
                'unit_price' => $product['unit_price'], 'active' => true, 'created_at' => now(), 'updated_at' => now(),
            ]);
            $rows = [];
            for ($day = 0; $day < 365; $day++) {
                $date = $start->copy()->addDays($day);
                $weekly = $date->isWeekend() ? 5 : 0;
                $promo = $index === 3 && $day % 28 < 5;
                $quantity = max(0, 8 + $index * 2 + $weekly + ($promo ? 15 : 0) + (($day * ($index + 3)) % 5) - 2);
                if ($index === 5) {
                    $quantity = $day % 12 === 0 ? 10 : 0;
                }
                $rows[] = [
                    'branch_id' => $branchId, 'product_id' => $id, 'sale_date' => $date->toDateString(),
                    'quantity_sold' => $quantity, 'in_stock' => true, 'is_holiday' => false, 'is_promo' => $promo,
                ];
            }
            DB::table('sales_history')->insert($rows);
            DB::table('warehouse_stock')->insert([
                'branch_id' => $branchId, 'product_id' => $id, 'current_quantity' => 30 + $index * 8,
                'warehouse' => 'Главный склад', 'as_of_date' => today()->toDateString(), 'reserved_quantity' => 0,
            ]);
        }
    }
}
