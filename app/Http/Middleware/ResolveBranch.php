<?php

namespace App\Http\Middleware;

use App\Services\BranchContext;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class ResolveBranch
{
    public function __construct(private readonly BranchContext $context) {}

    public function handle(Request $request, Closure $next): Response
    {
        $value = $request->header('X-Branch-ID', $request->query('branch_id'));
        $id = filter_var($value, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        abort_if($value !== null && $id === false, 422, 'Некорректный идентификатор филиала.');
        $this->context->resolve($id === false ? null : $id);

        return $next($request);
    }
}
