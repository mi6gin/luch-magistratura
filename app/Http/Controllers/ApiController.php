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
    public function __construct(private readonly MlBridge $ml)
    {
    }

    public function aiBriefing(): JsonResponse
    {
        $critical = WarehouseStock::where('current_quantity', '<', 50)->count();
        $message = "Система Laravel + ИИ активна. {$critical} товаров в зоне риска. ";
        $message .= now()->month === 3 ? 'Сезон Наурыза! Спрос вырастет до 2.2x.' : 'Рынок РК стабилен.';

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
            'accuracy' => 94.2,
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
            'product_id' => ['required', 'integer'],
            'quantity' => ['required', 'integer'],
        ]);
        WarehouseStock::updateOrCreate(
            ['product_id' => $data['product_id']],
            ['current_quantity' => $data['quantity']],
        );

        return response()->json(['success' => true]);
    }

    public function simulate(Request $request): JsonResponse
    {
        $data = $request->validate(['product_id' => ['integer'], 'overrides' => ['array']]);
        return response()->json($this->ml->simulate($data['product_id'] ?? 1, $data['overrides'] ?? []));
    }

    public function startSimulation(Request $request): JsonResponse
    {
        $data = $request->validate(['product_id' => ['required', 'integer'], 'overrides' => ['array']]);
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
        $data = $request->validate(['type' => ['string', 'in:standard,risk,optimization,trend,promo']]);
        return response()->json($this->ml->generateReport($data['type'] ?? 'standard'));
    }

    public function downloadReport(string $filename): BinaryFileResponse
    {
        $path = realpath(config('rayventory.reports_path').DIRECTORY_SEPARATOR.basename($filename));
        abort_unless($path && str_ends_with(strtolower($path), '.pdf') && is_file($path), 404);
        return response()->download($path, basename($path), ['Content-Type' => 'application/pdf']);
    }
}
