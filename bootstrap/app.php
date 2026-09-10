<?php

use App\Http\Middleware\AuditMutations;
use App\Http\Middleware\EnsureBranchAccess;
use App\Http\Middleware\ResolveBranch;
use App\Http\Middleware\SecurityHeaders;
use App\Providers\AppServiceProvider;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withProviders([AppServiceProvider::class])
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        $middleware->append(SecurityHeaders::class);
        $middleware->append(ResolveBranch::class);
        $middleware->alias(['branch.access' => EnsureBranchAccess::class, 'audit' => AuditMutations::class]);
    })
    ->withExceptions(function (Exceptions $exceptions): void {})->create();
