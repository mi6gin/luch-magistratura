<?php

namespace App\Services;

use JsonException;
use RuntimeException;
use Symfony\Component\Process\Exception\ProcessTimedOutException;
use Symfony\Component\Process\Process;
use Throwable;

class MlBridge
{
    public function simulate(int $productId = 1, array $overrides = []): array
    {
        return $this->run('simulate', [
            'product_id' => $productId,
            'overrides' => $overrides,
        ]);
    }

    public function generateReport(string $type = 'standard', array $formats = ['pdf', 'pptx']): array
    {
        return $this->run('report', [
            'type' => $type,
            'formats' => $formats,
        ]);
    }

    public function planning(): array
    {
        return $this->run('planning', ['scope' => 'portfolio']);
    }

    private function run(string $action, array $payload): array
    {
        $arguments = [
            (string) config('rayventory.python', 'py'),
            (string) config('rayventory.engine_path'),
            $action,
            '--payload-b64',
            base64_encode(json_encode($payload, JSON_THROW_ON_ERROR)),
        ];

        $process = new Process($arguments, base_path(), [
            'ML_DB_PATH' => (string) config('rayventory.database_path'),
            'ML_REPORTS_PATH' => (string) config('rayventory.reports_path'),
            'ML_MODEL_REGISTRY_PATH' => (string) config('rayventory.model_registry_path'),
            'ML_MODELS_PATH' => (string) config('rayventory.models_path'),
        ]);
        $process->setTimeout((float) config('rayventory.timeout', 120));
        try {
            $process->run();
        } catch (ProcessTimedOutException $exception) {
            report($exception);

            return ['error' => 'ML engine timed out'];
        } catch (Throwable $exception) {
            report($exception);

            return ['error' => 'ML engine failed'];
        }

        $result = $this->lastJsonLine($process->getOutput())
            ?? $this->lastJsonLine($process->getErrorOutput());
        if (! $process->isSuccessful()) {
            report(new RuntimeException('ML engine exited with code '.($process->getExitCode() ?? 'unknown')));

            return [
                'error' => is_string($result['error'] ?? null) && $result['error'] !== ''
                    ? $result['error']
                    : 'ML engine failed',
            ];
        }

        if ($result === null) {
            report(new RuntimeException('ML engine returned invalid output'));

            return ['error' => 'Invalid output format from ML engine'];
        }

        return $result;
    }

    private function lastJsonLine(string $output): ?array
    {
        // Split only on ASCII newlines so PCRE cannot cut through UTF-8 Cyrillic bytes.
        $lines = array_reverse(preg_split('/\r\n|\r|\n/', trim($output)) ?: []);
        foreach ($lines as $line) {
            try {
                $decoded = json_decode(trim($line), true, 512, JSON_THROW_ON_ERROR);
                if (is_array($decoded)) {
                    return $decoded;
                }
            } catch (JsonException) {
                continue;
            }
        }

        return null;
    }
}
