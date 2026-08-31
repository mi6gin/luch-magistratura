<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class SalesHistory extends Model
{
    protected $table = 'sales_history';

    public $timestamps = false;

    protected $guarded = [];
}
