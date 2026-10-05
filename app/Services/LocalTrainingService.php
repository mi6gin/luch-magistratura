<?php

namespace App\Services;

use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

class LocalTrainingService
{
    public function __construct(private readonly BranchContext $branches) {}

    // Three 28-day rolling folds reserve 56 validation + 28 test days,
    // then shift the earliest origin by 56 days. Its train_end must be
    // strictly after date_start + 120 days: 122 + 56 + 28 + 56 = 262.
    private const MINIMUM_DAYS = 262;

    private const RECOMMENDED_DAYS = 365;

    public function readiness(): array
    {
        $series = DB::table('sales_history')
            ->where('branch_id', $this->branches->id())
            ->selectRaw('product_id, MIN(sale_date) AS date_start, MAX(sale_date) AS date_end, COUNT(DISTINCT sale_date) AS observations')
            ->groupBy('product_id')
            ->get()
            ->map(function (object $row): array {
                $start = CarbonImmutable::parse($row->date_start);
                $end = CarbonImmutable::parse($row->date_end);
                $span = $start->diffInDays($end) + 1;

                return [
                    'product_id' => (int) $row->product_id,
                    'date_start' => $start->toDateString(),
                    'date_end' => $end->toDateString(),
                    'span_days' => $span,
                    'observations' => (int) $row->observations,
                    'eligible' => $span >= self::MINIMUM_DAYS && (int) $row->observations >= self::MINIMUM_DAYS,
                ];
            });
        $eligibleSeries = $series->where('eligible', true);
        $eligible = $eligibleSeries->count();
        $minimumSpan = (int) ($series->min('span_days') ?? 0);
        $foldChecks = $this->testFoldChecks($eligibleSeries->pluck('product_id')->all(), $series->max('date_end'));
        $testFoldsAvailable = count(array_filter($foldChecks, fn (array $fold): bool => $fold['series_uncensored'] > 0));
        $ready = $eligible > 0 && $testFoldsAvailable === 3;

        return [
            'ready' => $ready,
            'privacy' => 'Данные читаются локально из SQLite и не отправляются во внешние сервисы.',
            'minimum_days' => self::MINIMUM_DAYS,
            'minimum_observations' => self::MINIMUM_DAYS,
            'rolling_folds' => 3,
            'precheck_scope' => 'minimum-history-and-stockout-free-test-folds',
            'test_folds_available' => $testFoldsAvailable,
            'test_fold_checks' => $foldChecks,
            'recommended_days' => self::RECOMMENDED_DAYS,
            'series_total' => $series->count(),
            'series_eligible' => $eligible,
            'minimum_series_span_days' => $minimumSpan,
            'date_start' => $series->min('date_start'),
            'date_end' => $series->max('date_end'),
            'message' => $ready
                ? "Минимальные требования локального эксперимента выполнены для SKU: {$eligible}."
                : ($eligible > 0
                    ? 'В одном из трёх тестовых окон все подходящие SKU имеют подтверждённый дефицит. Нужен хотя бы один SKU без дефицита в каждом тестовом окне.'
                    : 'Для трёх rolling-окон загрузите минимум '.self::MINIMUM_DAYS.' дней истории и '.self::MINIMUM_DAYS.' ежедневных наблюдений хотя бы для одного SKU; рекомендуется полный год.'),
            'command' => '.venv-ml/bin/python ml/research_cli.py prepare-local',
        ];
    }

    private function testFoldChecks(array $productIds, ?string $testEnd): array
    {
        if ($productIds === [] || $testEnd === null) {
            return [];
        }

        // Each rolling test period is exactly one 28-day forecast window.
        // A known stockout anywhere in it censors that SKU's entire target.
        // Training and validation window eligibility remains a CLI check.
        $checks = [];
        $lastDate = CarbonImmutable::parse($testEnd);
        for ($fold = 0; $fold < 3; $fold++) {
            $end = $lastDate->subDays((2 - $fold) * 28);
            $start = $end->subDays(27);
            $censored = DB::table('sales_history')
                ->where('branch_id', $this->branches->id())
                ->whereIn('product_id', $productIds)
                ->whereBetween('sale_date', [$start->toDateString(), $end->toDateString()])
                ->where('in_stock', 0)
                ->distinct()->count('product_id');
            $checks[] = [
                'fold' => $fold + 1,
                'date_start' => $start->toDateString(),
                'date_end' => $end->toDateString(),
                'series_uncensored' => count($productIds) - $censored,
            ];
        }

        return $checks;
    }
}
