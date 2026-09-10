<?php

namespace App\Services;

use App\Jobs\RunLocalTrainingPipeline;
use Illuminate\Support\Facades\File;
use RuntimeException;
use Symfony\Component\Process\Process;
use Throwable;

class LocalModelPipelineService
{
    public function __construct(
        private readonly LocalTrainingService $training,
        private readonly ModelRegistryService $registry,
        private readonly BranchContext $branches,
    ) {}

    public function schedule(string $trigger = 'manual'): array
    {
        $latest = $this->latest();
        if (in_array($latest['status'] ?? null, ['queued', 'preparing', 'analyzing', 'evaluating'], true)) {
            return $latest;
        }
        $readiness = $this->training->readiness();
        $id = 'TRAIN-'.now()->utc()->format('Ymd\THis\Z').'-'.strtoupper(bin2hex(random_bytes(3)));
        $status = [
            'id' => $id,
            'status' => $readiness['ready'] ? 'queued' : 'skipped',
            'trigger' => $trigger,
            'created_at' => now()->toIso8601String(),
            'updated_at' => now()->toIso8601String(),
            'message' => $readiness['ready'] ? 'Локальный эксперимент поставлен в очередь.' : $readiness['message'],
            'experiment_id' => null,
            'candidate_id' => null,
            'branch_id' => $this->branches->id(),
        ];
        $this->save($status);
        if ($readiness['ready']) {
            RunLocalTrainingPipeline::dispatchAfterResponse($id, $this->branches->id());
        }

        return $status;
    }

    public function execute(string $id): void
    {
        $status = $this->find($id);
        if ($status === null) {
            throw new RuntimeException('Статус локального обучения не найден.');
        }
        try {
            $status = $this->update($status, 'preparing', 'Подготавливаем приватный набор из SQLite.');
            $dataDirectory = $this->branches->scopedPath((string) config('rayventory.local_training_data_path', base_path('data/processed/local-inventory')));
            $this->run([
                'prepare-local', '--database', (string) config('rayventory.database_path'),
                '--output-dir', $dataDirectory, '--branch-id', (string) $this->branches->id(),
            ]);
            $status = $this->update($status, 'analyzing', 'Анализируем спрос, сезонность и внешние факторы.');
            $this->run([
                'analyze', '--data', $dataDirectory.'/local_inventory.csv.gz',
                '--manifest', $dataDirectory.'/manifest.json',
                '--output', $this->branches->scopedPath(dirname((string) config('rayventory.dataset_analysis_path'))).'/latest.json',
            ]);
            $status = $this->update($status, 'evaluating', 'Сравниваем безопасные методы на rolling-окнах.');
            $result = $this->run([
                'train', '--data', $dataDirectory.'/local_inventory.csv.gz',
                '--manifest', $dataDirectory.'/manifest.json',
                '--output', $this->branches->scopedPath((string) config('rayventory.experiments_path')),
                '--models', '--folds', '3', '--summary',
            ]);
            $candidate = $this->registry->registerCandidate($result['experiment_id'], 'risk_calibrated_router');
            $status['experiment_id'] = $result['experiment_id'];
            $status['candidate_id'] = $candidate['id'];
            $this->update($status, $candidate['eligible'] ? 'review_required' : 'blocked', $candidate['eligible']
                ? 'Кандидат готов. Проверьте метрики и подтвердите публикацию вручную.'
                : 'Эксперимент завершён, но кандидат не прошёл проверки публикации.');
        } catch (Throwable $exception) {
            report($exception);
            $this->update($status, 'failed', $exception->getMessage() ?: 'Локальный ML-конвейер завершился ошибкой.');
        }
    }

    public function latest(): ?array
    {
        $files = $this->files();

        return $files === [] ? null : $this->read($files[0]);
    }

    public function find(string $id): ?array
    {
        if (preg_match('/^TRAIN-[A-Z0-9-]+$/', $id) !== 1) {
            return null;
        }
        $path = $this->directory().'/'.$id.'.json';

        return File::isFile($path) ? $this->read($path) : null;
    }

    private function run(array $arguments): array
    {
        $process = new Process([
            (string) config('rayventory.research_python', 'py'),
            base_path('ml/research_cli.py'),
            ...$arguments,
        ], base_path());
        $process->setTimeout((float) config('rayventory.training_timeout', 3600));
        $process->run();
        $result = json_decode(trim($process->getOutput()), true);
        if (! $process->isSuccessful() || ! is_array($result) || ($result['success'] ?? true) === false) {
            $message = is_array($result) ? ($result['error'] ?? null) : null;
            $message = $message ?: trim($process->getErrorOutput());
            throw new RuntimeException($message ?: 'Исследовательский CLI вернул некорректный результат.');
        }

        return $result;
    }

    private function update(array $status, string $state, string $message): array
    {
        $status['status'] = $state;
        $status['message'] = $message;
        $status['updated_at'] = now()->toIso8601String();
        $this->save($status);

        return $status;
    }

    private function save(array $status): void
    {
        File::ensureDirectoryExists($this->directory());
        File::put($this->directory().'/'.$status['id'].'.json', json_encode($status, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR), true);
    }

    private function files(): array
    {
        if (! File::isDirectory($this->directory())) {
            return [];
        }

        return collect(File::files($this->directory()))->sortByDesc->getMTime()->map->getPathname()->values()->all();
    }

    private function read(string $path): array
    {
        return json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR);
    }

    private function directory(): string
    {
        return $this->branches->scopedPath((string) config('rayventory.training_jobs_path', storage_path('app/training-jobs')));
    }
}
