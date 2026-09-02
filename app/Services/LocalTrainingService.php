<?php

namespace App\Services;

use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

class LocalTrainingService
{
    private const MINIMUM_DAYS = 175;

    private const RECOMMENDED_DAYS = 365;

    public function readiness(): array
    {
        $series = DB::table('sales_history')
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
                    'eligible' => $span >= self::MINIMUM_DAYS,
                ];
            });
        $eligible = $series->where('eligible', true)->count();
        $minimumSpan = (int) ($series->min('span_days') ?? 0);
        $ready = $eligible > 0;

        return [
            'ready' => $ready,
            'privacy' => 'Данные читаются локально из SQLite и не отправляются во внешние сервисы.',
            'minimum_days' => self::MINIMUM_DAYS,
            'recommended_days' => self::RECOMMENDED_DAYS,
            'series_total' => $series->count(),
            'series_eligible' => $eligible,
            'minimum_series_span_days' => $minimumSpan,
            'date_start' => $series->min('date_start'),
            'date_end' => $series->max('date_end'),
            'message' => $ready
                ? "К локальному эксперименту готово SKU: {$eligible}."
                : 'Недостаточно истории: загрузите минимум '.self::MINIMUM_DAYS.' дней хотя бы для одного SKU; рекомендуется полный год.',
            'command' => '.venv-ml/bin/python ml/research_cli.py prepare-local',
        ];
    }
}
