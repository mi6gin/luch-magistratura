param(
    [ValidateSet('web', 'worker', 'verify')]
    [string]$Mode = 'web',
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$portablePhp = Join-Path $projectRoot '.tools/php/php.exe'
$pythonPath = Join-Path $projectRoot '.venv-ml/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv or .venv-ml and install the project requirements first.'
}
if (Test-Path -LiteralPath $portablePhp) {
    $phpPath = $portablePhp
} else {
    $phpPath = (Get-Command php -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'vendor/autoload.php'))) {
    throw 'Install Composer dependencies first.'
}
if ($Mode -ne 'verify' -and -not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    throw 'Copy .env.example to .env, set the administrator password, generate APP_KEY and run rayventory:setup first.'
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable"
    }
}

$env:PATH = "$(Split-Path -Parent $phpPath);$env:PATH"
$env:ML_PYTHON = $pythonPath
$env:ML_RESEARCH_PYTHON = $pythonPath
$env:PYTHONUTF8 = '1'
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
$runtimeTemp = Join-Path $projectRoot 'storage/framework/cache/data/runtime-temp'
New-Item -ItemType Directory -Force -Path $runtimeTemp | Out-Null
$env:TEMP = $runtimeTemp
$env:TMP = $runtimeTemp
Push-Location -LiteralPath $projectRoot
try {
    switch ($Mode) {
        'web' {
            $publicPath = Join-Path $projectRoot 'public'
            $routerPath = Join-Path $projectRoot 'vendor/laravel/framework/src/Illuminate/Foundation/resources/server.php'
            Push-Location -LiteralPath $publicPath
            try {
                Invoke-Checked $phpPath @('-S', "127.0.0.1:$Port", '-t', $publicPath, $routerPath)
            } finally {
                Pop-Location
            }
        }
        'worker' {
            Invoke-Checked $phpPath @('artisan', 'queue:work', '--sleep=2', '--tries=1', '--timeout=3600')
        }
        'verify' {
            Invoke-Checked $phpPath @('vendor/phpunit/phpunit/phpunit', '--colors=never')
            Invoke-Checked $phpPath @('vendor/laravel/pint/builds/pint', '--test')
            Invoke-Checked $pythonPath @('-m', 'compileall', '-q', 'ml')
            Invoke-Checked $pythonPath @('-m', 'unittest', 'discover', '-s', 'ml/tests', '-p', 'test_*.py')
            Invoke-Checked $pythonPath @('ml/research_cli.py', '--help')
        }
    }
} finally {
    Pop-Location
}
