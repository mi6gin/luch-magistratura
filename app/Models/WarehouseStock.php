<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class WarehouseStock extends Model
{
    protected $table = 'warehouse_stock';
    protected $primaryKey = 'product_id';
    public $incrementing = false;
    public $timestamps = false;
    protected $guarded = [];

    public function product(): BelongsTo
    {
        return $this->belongsTo(Product::class, 'product_id');
    }
}
