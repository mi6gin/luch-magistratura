<?php

namespace App\Http\Controllers;

use App\Models\Branch;
use App\Models\Product;
use App\Models\User;
use App\Models\WarehouseStock;
use App\Services\BranchContext;
use App\Services\DatasetAnalysisService;
use App\Services\InventoryExcelService;
use App\Services\LocalModelPipelineService;
use App\Services\LocalTrainingService;
use App\Services\MlBridge;
use App\Services\ModelHealthService;
use App\Services\ModelRegistryService;
use App\Services\ResearchExperimentService;
use App\Services\ResearchReportService;
use App\Services\ResearchTuningService;
use App\Services\ScenarioBenchmarkService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rules\Password;
use InvalidArgumentException;
use Symfony\Component\HttpFoundation\BinaryFileResponse;

class ApiController extends Controller
{
    public function __construct(
        private readonly MlBridge $ml,
        private readonly InventoryExcelService $excel,
        private readonly ModelHealthService $modelHealth,
        private readonly ResearchExperimentService $experiments,
        private readonly ModelRegistryService $models,
        private readonly LocalTrainingService $localTraining,
        private readonly LocalModelPipelineService $localPipeline,
        private readonly DatasetAnalysisService $datasetAnalysis,
        private readonly ResearchTuningService $tuning,
        private readonly ScenarioBenchmarkService $scenarios,
        private readonly ResearchReportService $researchReport,
        private readonly BranchContext $branches,
    ) {}

    public function branches(): JsonResponse
    {
        $query = Branch::query()->where('active', true)->orderBy('name');
        if (! request()->user()?->is_admin) {
            $query->whereIn('id', request()->user()->branches()->pluck('branches.id'));
        }

        return response()->json([
            'active_branch_id' => $this->branches->id(),
            'branches' => $query->get(['id', 'organization_id', 'name', 'code']),
        ]);
    }

    public function createBranch(Request $request): JsonResponse
    {
        abort_unless($request->user()?->is_admin, 403, 'Только администратор может создавать филиалы.');
        $data = $request->validate([
            'name' => ['required', 'string', 'max:120'],
            'code' => ['nullable', 'string', 'max:40', 'regex:/^[a-z0-9-]+$/', 'unique:branches,code'],
        ]);
        $code = $data['code'] ?? str()->slug($data['name']);
        abort_if($code === '', 422, 'Не удалось сформировать код филиала.');
        abort_if(Branch::where('organization_id', $this->branches->resolve()->organization_id)->where('code', $code)->exists(), 422, 'Филиал с таким кодом уже существует.');
        $branch = Branch::create([
            'organization_id' => $this->branches->resolve()->organization_id,
            'name' => $data['name'], 'code' => $code, 'active' => true,
        ]);
        $request->user()->branches()->syncWithoutDetaching([$branch->id => ['role' => 'admin']]);

        return response()->json(['success' => true, 'branch' => $branch], 201);
    }

    public function branchesSummary(Request $request): JsonResponse
    {
        abort_unless($request->user()?->is_admin, 403);
        $summary = Branch::query()->where('active', true)->orderBy('name')->get()->map(function (Branch $branch): array {
            return [
                'id' => $branch->id, 'name' => $branch->name,
                'products' => DB::table('branch_products')->where('branch_id', $branch->id)->count(),
                'sales_rows' => DB::table('sales_history')->where('branch_id', $branch->id)->count(),
                'stock_units' => (int) DB::table('warehouse_stock')->where('branch_id', $branch->id)->sum('current_quantity'),
            ];
        });

        return response()->json(['branches' => $summary]);
    }

    public function users(Request $request): JsonResponse
    {
        abort_unless($request->user()?->is_admin, 403);

        return response()->json(['users' => User::with('branches:id,name')->orderBy('name')->get()]);
    }

    public function createUser(Request $request): JsonResponse
    {
        abort_unless($request->user()?->is_admin, 403);
        $data = $request->validate([
            'name' => ['required', 'string', 'max:120'],
            'email' => ['required', 'email', 'max:255', 'unique:users,email'],
            'password' => ['required', 'string', 'max:128', Password::min(12)->mixedCase()->letters()->numbers()->symbols()],
            'memberships' => ['required', 'array', 'min:1'],
            'memberships.*.branch_id' => ['required', 'integer', 'distinct', 'exists:branches,id'],
            'memberships.*.role' => ['required', 'in:admin,analyst,purchaser,viewer'],
        ]);
        $user = User::create(['name' => $data['name'], 'email' => mb_strtolower($data['email']), 'password' => $data['password']]);
        $memberships = collect($data['memberships'])->mapWithKeys(fn (array $membership): array => [
            $membership['branch_id'] => ['role' => $membership['role']],
        ])->all();
        $user->branches()->sync($memberships);

        return response()->json(['success' => true, 'user' => $user->load('branches:id,name')], 201);
    }

    public function changePassword(Request $request): JsonResponse
    {
        $data = $request->validate([
            'current_password' => ['required', 'current_password'],
            'password' => ['required', 'string', 'max:128', 'confirmed', Password::min(12)->mixedCase()->letters()->numbers()->symbols()],
        ]);
        $request->user()->update(['password' => $data['password']]);
        Auth::logoutOtherDevices($data['current_password']);
        $request->session()->regenerate();
        $request->session()->regenerateToken();

        return response()->json(['success' => true]);
    }

    public function inventoryTemplate(Request $request): BinaryFileResponse
    {
        $path = tempnam(sys_get_temp_dir(), 'rayventory-template-');
        abort_unless($path !== false, 500, 'Не удалось создать временный файл шаблона.');
        $xlsxPath = $path.'.xlsx';
        @unlink($path);
        $withExample = $request->boolean('example');
        $this->excel->createTemplate($xlsxPath, $withExample);

        return response()->download(
            $xlsxPath,
            $withExample ? 'rayventory_filled_example.xlsx' : 'rayventory_blank_template.xlsx',
            ['Content-Type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
        )->deleteFileAfterSend(true);
    }

    public function previewInventoryImport(Request $request): JsonResponse
    {
        $request->validate([
            'file' => ['required', 'file', 'mimes:xlsx', 'max:20480'],
        ]);

        try {
            $preview = $this->excel->preview($request->file('file'), $this->branches->id());
        } catch (InvalidArgumentException $exception) {
            return response()->json(['error' => $exception->getMessage()], 422);
        }

        return response()->json([
            'success' => true,
            'message' => 'Файл проверен. Подтвердите импорт после просмотра сводки.',
            'preview' => $preview,
        ]);
    }

    public function confirmInventoryImport(Request $request): JsonResponse
    {
        $data = $request->validate([
            'token' => ['required', 'string', 'size:32'],
            'file_name' => ['required', 'string', 'max:255'],
        ]);

        try {
            $counts = $this->excel->commit($data['token'], $data['file_name'], $this->branches->id());
        } catch (InvalidArgumentException $exception) {
            return response()->json(['error' => $exception->getMessage()], 422);
        }

        $adaptation = null;
        $adaptationWarning = null;
        $plan = $this->ml->planning();
        if (($plan['success'] ?? true) !== false && ! isset($plan['error'])) {
            $adaptation = $this->modelHealth->record($plan, 'excel_import', $data['file_name']);
        } else {
            $adaptationWarning = 'Данные импортированы, но автоматическая оценка модели не завершилась. Запустите её на экране здоровья модели.';
        }
        $training = $this->localPipeline->schedule('excel_import');

        return response()->json([
            'success' => true,
            'message' => 'Импорт подтверждён и завершён. Резервная копия предыдущих данных сохранена.',
            'counts' => $counts,
            'adaptation' => $adaptation,
            'warning' => $adaptationWarning,
            'training' => $training,
        ]);
    }

    public function modelHealth(Request $request): JsonResponse
    {
        $latest = $this->modelHealth->latest();
        if ($request->boolean('refresh') || $latest === null) {
            $plan = $this->ml->planning();
            if (($plan['success'] ?? true) === false || isset($plan['error'])) {
                return $this->mlResponse($plan);
            }
            $latest = $this->modelHealth->record($plan, 'manual');
        }

        return response()->json(['latest' => $latest, 'history' => $this->modelHealth->history()]);
    }

    public function experiments(): JsonResponse
    {
        return response()->json(['experiments' => $this->experiments->list()]);
    }

    public function experiment(string $id): JsonResponse
    {
        $experiment = $this->experiments->find($id);
        abort_if($experiment === null, 404);

        return response()->json($experiment);
    }

    public function models(): JsonResponse
    {
        return response()->json($this->models->state());
    }

    public function trainingReadiness(): JsonResponse
    {
        return response()->json($this->localTraining->readiness());
    }

    public function trainingPipeline(): JsonResponse
    {
        return response()->json(['latest' => $this->localPipeline->latest()]);
    }

    public function datasetAnalysis(): JsonResponse
    {
        return response()->json(['analysis' => $this->datasetAnalysis->latest()]);
    }

    public function tuning(): JsonResponse
    {
        return response()->json(['tuning' => $this->tuning->latest()]);
    }

    public function scenarios(): JsonResponse
    {
        return response()->json(['benchmark' => $this->scenarios->latest()]);
    }

    public function researchReport(): JsonResponse
    {
        return response()->json(['report' => $this->researchReport->latest()]);
    }

    public function researchChart(string $model): Response
    {
        $chart = $this->researchReport->chart($model);
        abort_if($chart === null, 404);

        return response($chart, 200, ['Content-Type' => 'image/svg+xml; charset=UTF-8']);
    }

    public function startTrainingPipeline(): JsonResponse
    {
        $status = $this->localPipeline->schedule('manual');

        return response()->json(['success' => true, 'pipeline' => $status], $status['status'] === 'queued' ? 202 : 200);
    }

    public function registerModelCandidate(Request $request): JsonResponse
    {
        $data = $request->validate([
            'experiment_id' => ['required', 'string', 'regex:/^EXP-[A-Z0-9-]+$/'],
            'model' => ['required', 'string', 'max:100'],
        ]);
        try {
            $candidate = $this->models->registerCandidate($data['experiment_id'], $data['model']);
        } catch (InvalidArgumentException $exception) {
            return response()->json(['error' => $exception->getMessage()], 422);
        }

        return response()->json(['success' => true, 'candidate' => $candidate], 201);
    }

    public function promoteModel(Request $request, string $id): JsonResponse
    {
        $request->validate(['confirmation' => ['required', 'in:PROMOTE']]);
        try {
            return response()->json(['success' => true, 'model' => $this->models->promote($id)]);
        } catch (InvalidArgumentException $exception) {
            return response()->json(['error' => $exception->getMessage()], 422);
        }
    }

    public function aiBriefing(): JsonResponse
    {
        $critical = WarehouseStock::where('branch_id', $this->branches->id())->where('current_quantity', '<', 50)->count();
        $message = "Контур SAFE активен. {$critical} товаров в зоне риска. ";
        $message .= now()->month === 3
            ? 'Отмечен сезонный календарный фактор: проверьте диапазон q10-q90.'
            : 'Оценка основана на доступной истории и текущих остатках.';

        return response()->json(['briefing' => $message]);
    }

    public function purchasePlan(): JsonResponse
    {
        return $this->mlResponse($this->enrichedPurchasePlan());
    }

    public function exportPurchasePlan(Request $request): BinaryFileResponse
    {
        $data = $request->validate([
            'budget' => ['nullable', 'numeric', 'min:0'],
            'items' => ['required', 'array', 'list', 'min:1'],
            'items.*.product_id' => ['required', 'integer', 'distinct'],
            'items.*.quantity' => ['required', 'integer', 'min:1'],
        ]);
        $plan = $this->enrichedPurchasePlan();
        abort_if(isset($plan['error']) || ($plan['success'] ?? true) === false, 502, 'Не удалось пересчитать план закупок.');
        $actions = collect($plan['actions'] ?? [])->keyBy('product_id');
        $items = [];
        foreach ($data['items'] as $requested) {
            $action = $actions->get((int) $requested['product_id']);
            abort_unless($action, 422, 'В плане найден неизвестный товар. Обновите страницу.');
            $quantity = min((int) $requested['quantity'], (int) $action['order_quantity']);
            if ($quantity < 1) {
                continue;
            }
            $items[] = [
                ...$action,
                'quantity' => $quantity,
                'recommended_quantity' => (int) $action['order_quantity'],
            ];
        }
        abort_if($items === [], 422, 'В корзине нет позиций для выгрузки.');

        $temporary = tempnam(sys_get_temp_dir(), 'rayventory-order-');
        abort_unless($temporary !== false, 500, 'Не удалось создать файл заказа.');
        $path = $temporary.'.xlsx';
        @unlink($temporary);
        $this->excel->createPurchasePlanExport($path, $items, isset($data['budget']) ? (float) $data['budget'] : null);

        return response()->download(
            $path,
            'rayventory_purchase_plan_'.now()->format('Y-m-d').'.xlsx',
            ['Content-Type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
        )->deleteFileAfterSend(true);
    }

    public function dashboardStats(): JsonResponse
    {
        $products = $this->branchProducts();
        $total = 0.0;
        $critical = 0;
        $categories = [];

        foreach ($products as $product) {
            $quantity = (float) ($product->current_quantity ?? 0);
            $value = $quantity * (float) $product->branch_unit_price;
            $total += $value;
            $critical += $quantity < 50 ? 1 : 0;
            $category = $product->category ?: 'Общее';
            $categories[$category] = ($categories[$category] ?? 0) + $value;
        }

        return response()->json([
            'total_value' => round($total, 2),
            'critical_count' => $critical,
            'model_status' => 'SAFE',
            'categories' => collect($categories)->map(fn ($value, $category) => [
                'category' => $category,
                'val' => round($value, 2),
            ])->values(),
        ]);
    }

    public function stock(): JsonResponse
    {
        return response()->json($this->branchProducts()->map(fn ($product) => [
            'id' => (int) $product->id,
            'sku' => $product->sku ?? null,
            'name' => $product->name,
            'category' => $product->category,
            'current_quantity' => (int) ($product->current_quantity ?? 0),
            'unit_price' => (float) $product->branch_unit_price,
            'lead_time' => (int) $product->branch_lead_time,
        ]));
    }

    public function updateStock(Request $request): JsonResponse
    {
        $data = $request->validate([
            'product_id' => ['required', 'integer'],
            'quantity' => ['required', 'integer', 'min:0'],
        ]);
        abort_unless(DB::table('branch_products')->where('branch_id', $this->branches->id())->where('product_id', $data['product_id'])->exists(), 422, 'Товар не принадлежит выбранному филиалу.');
        WarehouseStock::updateOrCreate(
            ['branch_id' => $this->branches->id(), 'product_id' => $data['product_id']],
            ['current_quantity' => $data['quantity']],
        );

        return response()->json(['success' => true]);
    }

    public function simulate(Request $request): JsonResponse
    {
        $data = $request->validate([
            'product_id' => ['required', 'integer'],
            'overrides' => ['sometimes', 'array:is_promo,price_change'],
            'overrides.is_promo' => ['sometimes', 'boolean'],
            'overrides.price_change' => ['sometimes', 'numeric', 'between:-0.5,0.5'],
        ]);

        abort_unless(DB::table('branch_products')->where('branch_id', $this->branches->id())->where('product_id', $data['product_id'])->exists(), 422, 'Товар не принадлежит выбранному филиалу.');

        return $this->mlResponse($this->ml->simulate($data['product_id'], $data['overrides'] ?? []));
    }

    public function generateReport(Request $request): JsonResponse
    {
        $data = $request->validate([
            'type' => ['sometimes', 'string', 'in:standard,risk,optimization,trend,promo'],
            'formats' => ['sometimes', 'array', 'list', 'min:1', 'max:2'],
            'formats.*' => ['required', 'string', 'distinct', 'in:pdf,pptx'],
        ]);

        return $this->mlResponse($this->ml->generateReport(
            $data['type'] ?? 'standard',
            array_values($data['formats'] ?? ['pdf', 'pptx']),
        ));
    }

    public function downloadReport(string $filename): BinaryFileResponse
    {
        abort_unless(
            $filename === basename($filename)
            && ! str_contains($filename, '/')
            && ! str_contains($filename, '\\'),
            404,
        );

        $mimeTypes = [
            'pdf' => 'application/pdf',
            'pptx' => 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        ];
        $extension = strtolower(pathinfo($filename, PATHINFO_EXTENSION));
        abort_unless(isset($mimeTypes[$extension]), 404);

        $reportsDirectory = realpath($this->branches->scopedPath((string) config('rayventory.reports_path')));
        abort_unless($reportsDirectory !== false && is_dir($reportsDirectory), 404);

        $path = realpath($reportsDirectory.DIRECTORY_SEPARATOR.$filename);
        $directoryPrefix = rtrim($reportsDirectory, DIRECTORY_SEPARATOR).DIRECTORY_SEPARATOR;
        $comparisonPath = PHP_OS_FAMILY === 'Windows' ? strtolower((string) $path) : (string) $path;
        $comparisonPrefix = PHP_OS_FAMILY === 'Windows' ? strtolower($directoryPrefix) : $directoryPrefix;
        abort_unless(
            $path !== false
            && is_file($path)
            && str_starts_with($comparisonPath, $comparisonPrefix),
            404,
        );

        return response()->download($path, basename($path), ['Content-Type' => $mimeTypes[$extension]]);
    }

    private function mlResponse(array $result): JsonResponse
    {
        $failed = array_key_exists('error', $result) || ($result['success'] ?? true) === false;

        return response()->json($result, $failed ? 502 : 200);
    }

    private function enrichedPurchasePlan(): array
    {
        $plan = $this->ml->planning();
        if (! isset($plan['actions']) || ! is_array($plan['actions'])) {
            return $plan;
        }
        $suppliers = DB::table('product_planning_settings as settings')
            ->leftJoin('suppliers', 'suppliers.id', '=', 'settings.supplier_id')
            ->where('settings.branch_id', $this->branches->id())
            ->pluck('suppliers.name', 'settings.product_id');
        $plan['actions'] = array_map(function (array $action) use ($suppliers): array {
            $action['supplier'] = $suppliers[(int) $action['product_id']] ?? null;

            return $action;
        }, $plan['actions']);

        return $plan;
    }

    private function branchProducts(): Collection
    {
        return Product::query()
            ->join('branch_products as bp', 'bp.product_id', '=', 'products.id')
            ->leftJoin('warehouse_stock as ws', function ($join): void {
                $join->on('ws.product_id', '=', 'products.id')->where('ws.branch_id', $this->branches->id());
            })
            ->where('bp.branch_id', $this->branches->id())
            ->where('bp.active', true)
            ->select('products.*', 'bp.unit_price as branch_unit_price', 'bp.lead_time as branch_lead_time', DB::raw('COALESCE(SUM(ws.current_quantity), 0) as current_quantity'))
            ->groupBy('products.id', 'products.sku', 'products.name', 'products.category', 'products.lead_time', 'products.unit_price', 'bp.unit_price', 'bp.lead_time')
            ->get();
    }
}
