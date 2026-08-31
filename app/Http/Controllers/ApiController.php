<?php

namespace App\Http\Controllers;

use App\Models\Product;
use App\Models\WarehouseStock;
use App\Services\MlBridge;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\BinaryFileResponse;

class ApiController extends Controller
{
    public function __construct(private readonly MlBridge $ml) {}

    public function aiBriefing(): JsonResponse
    {
        $critical = WarehouseStock::where('current_quantity', '<', 50)->count();
        $message = "Контур SAFE активен. {$critical} товаров в зоне риска. ";
        $message .= now()->month === 3
            ? 'Отмечен сезонный календарный фактор: проверьте диапазон q10-q90.'
            : 'Оценка основана на доступной истории и текущих остатках.';

        return response()->json(['briefing' => $message]);
    }

    public function dashboardStats(): JsonResponse
    {
        $products = Product::with('warehouseStock')->get();
        $total = 0.0;
        $critical = 0;
        $categories = [];

        foreach ($products as $product) {
            $quantity = (float) ($product->warehouseStock?->current_quantity ?? 0);
            $value = $quantity * (float) $product->unit_price;
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
        return response()->json(Product::with('warehouseStock')->get()->map(fn ($product) => [
            'id' => (int) $product->id,
            'name' => $product->name,
            'category' => $product->category,
            'current_quantity' => (int) ($product->warehouseStock?->current_quantity ?? 0),
            'unit_price' => (float) $product->unit_price,
            'lead_time' => (int) $product->lead_time,
        ]));
    }

    public function updateStock(Request $request): JsonResponse
    {
        $data = $request->validate([
            'product_id' => ['required', 'integer', 'exists:products,id'],
            'quantity' => ['required', 'integer', 'min:0'],
        ]);
        WarehouseStock::updateOrCreate(
            ['product_id' => $data['product_id']],
            ['current_quantity' => $data['quantity']],
        );

        return response()->json(['success' => true]);
    }

    public function simulate(Request $request): JsonResponse
    {
        $data = $request->validate([
            'product_id' => ['required', 'integer', 'exists:products,id'],
            'overrides' => ['sometimes', 'array:is_promo,price_change'],
            'overrides.is_promo' => ['sometimes', 'boolean'],
            'overrides.price_change' => ['sometimes', 'numeric', 'between:-0.5,0.5'],
        ]);

        return $this->mlResponse($this->ml->simulate($data['product_id'], $data['overrides'] ?? []));
    }

    public function startSimulation(Request $request): JsonResponse
    {
        $data = $request->validate([
            'product_id' => ['required', 'integer', 'exists:products,id'],
            'overrides' => ['sometimes', 'array:is_promo,price_change'],
            'overrides.is_promo' => ['sometimes', 'boolean'],
            'overrides.price_change' => ['sometimes', 'numeric', 'between:-0.5,0.5'],
        ]);

        return response()->json($this->ml->startSimulation($data['product_id'], $data['overrides'] ?? []));
    }

    public function job(string $jobId): JsonResponse
    {
        abort_unless(preg_match('/^[a-f0-9]{24}$/', $jobId) === 1, 404);
        $job = $this->ml->job($jobId);

        return response()->json($job, $job['status'] === 'not_found' ? 404 : 200);
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

        $reportsDirectory = realpath((string) config('rayventory.reports_path'));
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
}
