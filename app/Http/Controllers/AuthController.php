<?php

namespace App\Http\Controllers;

use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Str;
use Illuminate\View\View;

class AuthController extends Controller
{
    public function form(): View
    {
        return view('auth.login');
    }

    public function login(Request $request): RedirectResponse
    {
        $credentials = $request->validate(['email' => ['required', 'email'], 'password' => ['required', 'string']]);
        $credentials['email'] = Str::lower($credentials['email']);
        $key = hash('sha256', $credentials['email'].'|'.$request->ip());
        if (RateLimiter::tooManyAttempts($key, 5)) {
            return back()->withErrors([
                'email' => 'Слишком много попыток входа. Повторите через '.RateLimiter::availableIn($key).' сек.',
            ])->onlyInput('email');
        }
        if (! Auth::attempt($credentials, false)) {
            RateLimiter::hit($key, 60);
            Log::warning('Authentication failed', ['identity_hash' => hash('sha256', $credentials['email']), 'ip' => $request->ip()]);

            return back()->withErrors(['email' => 'Неверный email или пароль.'])->onlyInput('email');
        }
        RateLimiter::clear($key);
        $request->session()->regenerate();
        Log::info('Authentication succeeded', ['user_id' => Auth::id(), 'ip' => $request->ip()]);

        return redirect()->intended(route('dashboard'));
    }

    public function logout(Request $request): RedirectResponse
    {
        Auth::logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect()->route('login');
    }

    public function settings(Request $request): View
    {
        return view('pages.settings', ['page' => 'settings', 'section' => 'ACCOUNT', 'heading' => 'Настройки и доступ']);
    }
}
