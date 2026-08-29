<?php

namespace App\Services;


class MlBridge
{
    public function startSimulation(int $productId, array $overrides = []): array
    {
        return $this->startJob('simulate', [
            'product_id' => $productId,
            'overrides' => $overrides,
        ]);
    }

    public function job(string $jobId): array
    {
        $directory = storage_path('app/ml-jobs');
        $statePath = $directory.DIRECTORY_SEPARATOR.$jobId.'.json';
        if (!is_file($statePath)) {
            return ['status' => 'not_found'];
        }

        $state = json_decode((string) file_get_contents($statePath), true) ?: [];
        if (($state['status'] ?? null) !== 'processing' || !is_file($state['done'])) {
            return $state;
        }

        $output = is_file($state['output']) ? (string) file_get_contents($state['output']) : '';
        $lines = array_reverse(preg_split('/\R/', trim($output)) ?: []);
        foreach ($lines as $line) {
            $line = trim($line);
            if (str_starts_with($line, '{')) {
                $result = json_decode($line, true);
                $state['status'] = isset($result['error']) ? 'failed' : 'completed';
                $state['result'] = $result;
                file_put_contents($statePath, json_encode($state, JSON_UNESCAPED_UNICODE));
                return $state;
            }
        }

        $state['status'] = 'failed';
        $state['result'] = ['error' => 'Invalid output format from ML engine'];
        file_put_contents($statePath, json_encode($state, JSON_UNESCAPED_UNICODE));
        return $state;
    }

    public function simulate(int $productId = 1, array $overrides = []): array
    {
        return $this->run('simulate', [
            'product_id' => $productId,
            'overrides' => $overrides,
        ]);
    }

    public function generateReport(string $type = 'standard'): array
    {
        return $this->run('report', ['type' => $type]);
    }

    private function startJob(string $action, array $payload): array
    {
        $directory = storage_path('app/ml-jobs');
        if (!is_dir($directory)) {
            mkdir($directory, 0775, true);
        }

        $jobId = bin2hex(random_bytes(12));
        $output = $directory.DIRECTORY_SEPARATOR.$jobId.'.out';
        $done = $directory.DIRECTORY_SEPARATOR.$jobId.'.done';
        $statePath = $directory.DIRECTORY_SEPARATOR.$jobId.'.json';
        $python = (string) config('rayventory.python', 'py');
        $script = (string) config('rayventory.engine_path');
        $json = json_encode($payload, JSON_THROW_ON_ERROR);
        $command = implode(' ', array_map('escapeshellarg', [$python, $script, $action, '--payload', $json]));

        $state = ['status' => 'processing', 'output' => $output, 'done' => $done];
        file_put_contents($statePath, json_encode($state, JSON_UNESCAPED_UNICODE));

        if (PHP_OS_FAMILY === 'Windows') {
            $batch = $directory.DIRECTORY_SEPARATOR.$jobId.'.bat';
            $batchBody = '@echo off'.PHP_EOL.$command.' > "'.$output.'" 2>&1'.PHP_EOL.'echo done>"'.$done.'"';
            file_put_contents($batch, $batchBody);
            pclose(popen('start "" /B cmd /D /C "'.$batch.'"', 'r'));
        } else {
            $process = new \Symfony\Component\Process\Process($command, base_path(), null, null, null);
            $process->start(function ($type, $buffer) use ($output, $done): void {
                file_put_contents($output, $buffer, FILE_APPEND);
                if ($type === \Symfony\Component\Process\Process::ERR) {
                    file_put_contents($done, 'done');
                }
            });
        }

        return ['job_id' => $jobId, 'status' => 'processing'];
    }

    private function run(string $action, array $payload): array
    {
        $arguments = [
            (string) config('rayventory.python', 'py'),
            (string) config('rayventory.engine_path'),
            $action,
            '--payload',
            json_encode($payload, JSON_THROW_ON_ERROR),
        ];
        $command = implode(' ', array_map('escapeshellarg', $arguments));

        $output = shell_exec($command.' 2>&1');
        if (!$output) {
            report(new \RuntimeException('ML engine returned no output'));
            return ['error' => 'ML engine failed'];
        }

        $lines = array_reverse(preg_split('/\R/', trim($output)) ?: []);
        foreach ($lines as $line) {
            $line = trim($line);
            if (str_starts_with($line, '{')) {
                return json_decode($line, true, 512, JSON_THROW_ON_ERROR);
            }
        }

        return ['error' => 'Invalid output format from ML engine'];
    }
}
