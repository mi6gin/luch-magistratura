<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Product extends Model
{
    protected $table = 'products';

    public $timestamps = false;

    protected $guarded = [];

    public function warehouseStock(): HasOne
    {
        return $this->hasOne(WarehouseStock::class, 'product_id');
    }

    public function branchProducts(): HasMany
    {
        return $this->hasMany(BranchProduct::class, 'product_id');
    }

    public function warehouseInTransit(): HasOne
    {
        return $this->hasOne(WarehouseInTransit::class, 'product_id');
    }

    public function salesHistory(): HasMany
    {
        return $this->hasMany(SalesHistory::class, 'product_id');
    }
}
