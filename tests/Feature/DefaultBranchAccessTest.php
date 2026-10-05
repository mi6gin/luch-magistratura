<?php

namespace Tests\Feature;

use App\Models\Branch;
use App\Models\User;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class DefaultBranchAccessTest extends TestCase
{
    public function test_limited_user_can_login_and_use_their_branch_without_an_explicit_selection(): void
    {
        $branch = $this->createBranch('second');
        $limited = User::create(['name' => 'Limited', 'email' => 'limited-default@example.test', 'password' => 'password']);
        $limited->branches()->attach($branch->id, ['role' => 'viewer']);
        DB::table('products')->insert(['id' => 1, 'sku' => 'FOREIGN', 'name' => 'Foreign product', 'category' => 'Demo', 'lead_time' => 3, 'unit_price' => 100]);
        DB::table('branch_products')->insert(['branch_id' => 1, 'product_id' => 1, 'lead_time' => 3, 'unit_price' => 100, 'active' => true, 'created_at' => now(), 'updated_at' => now()]);

        auth()->logout();
        $this->post('/login', ['email' => $limited->email, 'password' => 'password'])->assertRedirect('/');
        $this->assertAuthenticatedAs($limited);
        $this->get('/')->assertOk();
        $this->getJson('/api/branches')->assertOk()
            ->assertJsonPath('active_branch_id', $branch->id)
            ->assertJsonCount(1, 'branches')
            ->assertJsonPath('branches.0.id', $branch->id);
        $this->getJson('/api/stock')->assertOk()->assertExactJson([]);
        $this->getJson('/api/stock?branch_id=1')->assertForbidden();
        $this->getJson('/api/stock', ['X-Branch-ID' => '1'])->assertForbidden();
        $this->getJson('/api/stock')->assertOk()->assertExactJson([]);
        $this->postJson('/api/stock/update', ['product_id' => 1, 'quantity' => 10])->assertForbidden();
    }

    public function test_default_branch_skips_inactive_memberships_and_is_deterministic(): void
    {
        $inactive = $this->createBranch('inactive', false);
        $firstActive = $this->createBranch('active-first');
        $lastActive = $this->createBranch('active-last');
        $limited = User::create(['name' => 'Limited', 'email' => 'active-default@example.test', 'password' => 'password']);
        $limited->branches()->attach([
            $lastActive->id => ['role' => 'viewer'],
            $inactive->id => ['role' => 'viewer'],
            $firstActive->id => ['role' => 'viewer'],
        ]);

        $this->actingAs($limited)->getJson('/api/branches')->assertOk()
            ->assertJsonPath('active_branch_id', $firstActive->id)
            ->assertJsonCount(2, 'branches');
        $this->getJson('/api/branches', ['X-Branch-ID' => (string) $lastActive->id])->assertOk()
            ->assertJsonPath('active_branch_id', $lastActive->id);
    }

    public function test_user_without_active_membership_receives_a_clear_forbidden_response(): void
    {
        $inactive = $this->createBranch('inactive', false);
        $limited = User::create(['name' => 'Inactive', 'email' => 'inactive-default@example.test', 'password' => 'password']);
        $limited->branches()->attach($inactive->id, ['role' => 'viewer']);

        $this->actingAs($limited)->get('/')->assertForbidden();
        $this->getJson('/api/stock')->assertForbidden()->assertJsonPath('message', 'Нет доступных активных филиалов.');
    }

    public function test_administrator_keeps_the_existing_default_branch(): void
    {
        $this->createBranch('second');
        $this->getJson('/api/branches')->assertOk()->assertJsonPath('active_branch_id', 1);
    }

    private function createBranch(string $code, bool $active = true): Branch
    {
        return Branch::create(['organization_id' => 1, 'name' => $code, 'code' => $code, 'active' => $active]);
    }
}
