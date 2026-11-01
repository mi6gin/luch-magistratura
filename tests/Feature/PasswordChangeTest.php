<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Hash;
use Tests\TestCase;

class PasswordChangeTest extends TestCase
{
    public function test_read_only_and_purchasing_users_can_log_out(): void
    {
        foreach (['viewer', 'purchaser'] as $role) {
            $this->user->update(['is_admin' => false]);
            $this->user->branches()->updateExistingPivot($this->branchId, ['role' => $role]);
            $this->user->unsetRelation('branches');
            $this->actingAs($this->user)->post('/logout')->assertRedirect('/login');
            $this->assertGuest();
        }
    }

    public function test_password_change_succeeds_and_returns_the_rotated_csrf_token(): void
    {
        $oldToken = str_repeat('a', 40);
        $response = $this->actingAs($this->user)->withSession(['_token' => $oldToken])
            ->postJson('/api/account/password', [
                'current_password' => 'password',
                'password' => 'Changed#Password2026',
                'password_confirmation' => 'Changed#Password2026',
            ])->assertOk()->assertJson(['success' => true]);

        $this->assertTrue(Hash::check('Changed#Password2026', $this->user->fresh()->password));
        $this->assertFalse(Hash::check('password', $this->user->fresh()->password));
        $this->assertNotSame($oldToken, $response->json('csrf_token'));
        $this->assertSame(session()->token(), $response->json('csrf_token'));
        $this->getJson('/api/stock')->assertOk();
    }

    public function test_wrong_current_password_does_not_change_the_password(): void
    {
        $originalHash = $this->user->password;
        $this->actingAs($this->user)->postJson('/api/account/password', [
            'current_password' => 'wrong-password',
            'password' => 'Changed#Password2026',
            'password_confirmation' => 'Changed#Password2026',
        ])->assertUnprocessable()->assertJsonValidationErrors('current_password');

        $this->assertSame($originalHash, $this->user->fresh()->password);
    }
}
