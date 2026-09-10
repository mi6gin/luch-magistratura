<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class WarehouseInTransit extends Model
{
    protected $table = 'warehouse_in_transit';

    public $timestamps = false;

    protected $guarded = [];
}
