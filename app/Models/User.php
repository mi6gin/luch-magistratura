<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Foundation\Auth\User as Authenticatable;

class User extends Authenticatable
{
    protected $fillable = ['name', 'email', 'password', 'is_admin'];

    protected $hidden = ['password', 'remember_token'];

    protected function casts(): array
    {
        return ['password' => 'hashed', 'is_admin' => 'boolean'];
    }

    public function branches(): BelongsToMany
    {
        return $this->belongsToMany(Branch::class)->withPivot('role');
    }

    public function canUseBranch(int $branchId): bool
    {
        return $this->is_admin || $this->branches()->whereKey($branchId)->exists();
    }

    public function roleForBranch(int $branchId): ?string
    {
        return $this->is_admin ? 'admin' : $this->branches()->whereKey($branchId)->first()?->pivot?->role;
    }
}
