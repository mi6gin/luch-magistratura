<?php

namespace App\Http\Middleware;

use App\Services\BranchContext;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Symfony\Component\HttpFoundation\Response;

class AuditMutations
{
    public function __construct(private readonly BranchContext $branches) {}

    public function handle(Request $request, Closure $next): Response
    {
        $response = $next($request);
        if (! in_array($request->method(), ['GET', 'HEAD', 'OPTIONS'], true)) {
            DB::table('audit_logs')->insert([
                'branch_id' => $this->branches->id(), 'user_id' => $request->user()?->id,
                'method' => $request->method(), 'path' => $request->path(),
                'status' => $response->getStatusCode(), 'ip' => $request->ip(), 'created_at' => now(),
            ]);
        }

        return $response;
    }
}
