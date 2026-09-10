<?php

namespace Tests;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    use RefreshDatabase;

    protected User $user;

    protected int $branchId = 1;

    protected function setUp(): void
    {
        parent::setUp();
        $this->user = User::create([
            'name' => 'Test Admin', 'email' => 'admin@example.test',
            'password' => 'password', 'is_admin' => true,
        ]);
        $this->user->branches()->attach($this->branchId, ['role' => 'admin']);
        $this->actingAs($this->user);
    }

    protected function branchHeaders(?int $branchId = null): array
    {
        return ['X-Branch-ID' => (string) ($branchId ?? $this->branchId)];
    }
}
