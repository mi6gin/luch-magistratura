<?php

namespace App\Http\Middleware;

use App\Services\BranchContext;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class EnsureBranchAccess
{
    public function __construct(private readonly BranchContext $branches) {}

    public function handle(Request $request, Closure $next): Response
    {
        $user = $request->user();
        abort_unless($user && $user->canUseBranch($this->branches->id()), 403, 'Нет доступа к выбранному филиалу.');
        if (! in_array($request->method(), ['GET', 'HEAD', 'OPTIONS'], true)) {
            $role = $user->roleForBranch($this->branches->id());
            $purchaserAction = $request->is('api/purchase-plan/export');
            $personalAction = $request->is('api/account/password');
            abort_if(! $personalAction && ($role === 'viewer' || ($role === 'purchaser' && ! $purchaserAction)), 403, 'Недостаточно прав для изменения данных.');
        }

        return $next($request);
    }
}
