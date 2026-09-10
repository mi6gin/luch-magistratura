<?php

namespace App\Services;

use App\Models\Branch;
use Illuminate\Support\Facades\Schema;

class BranchContext
{
    private ?Branch $branch = null;

    public function resolve(?int $requestedId = null): Branch
    {
        if ($this->branch !== null && ($requestedId === null || $this->branch->id === $requestedId)) {
            return $this->branch;
        }
        abort_unless(Schema::hasTable('branches'), 503, 'Филиальная схема базы ещё не установлена. Выполните миграции.');
        $query = Branch::query()->where('active', true);
        $this->branch = $requestedId === null ? $query->orderBy('id')->first() : $query->find($requestedId);
        abort_if($this->branch === null, 404, 'Филиал не найден или отключён.');

        return $this->branch;
    }

    public function id(): int
    {
        return (int) $this->resolve()->id;
    }

    public function set(Branch $branch): void
    {
        $this->branch = $branch;
    }

    public function scopedPath(string $root): string
    {
        return rtrim($root, DIRECTORY_SEPARATOR).DIRECTORY_SEPARATOR.'branches'.DIRECTORY_SEPARATOR.$this->id();
    }
}
