param(
  [Parameter(Position = 0)]
  [ValidateSet('help','setup','setup-full','offline','dense','enrich','neo4j','load-neo4j','online','online-check','online-ollama','frontend','test','validate','kaggle')]
  [string]$Task = 'help',
  [string]$Config,
  [string]$HostAddress = '127.0.0.1',
  [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Import-ProjectEnvironment {
  $environmentFile = Join-Path $ProjectRoot '.env'
  if (-not (Test-Path -LiteralPath $environmentFile)) { return }
  foreach ($line in Get-Content -LiteralPath $environmentFile -Encoding UTF8) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
    $name, $value = $trimmed.Split('=', 2)
    if (-not [Environment]::GetEnvironmentVariable($name.Trim(), 'Process')) {
      [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim().Trim('"').Trim("'"), 'Process')
    }
  }
}

function Get-ProjectPython {
  if ($env:VN_LABOR_PYTHON) {
    $candidate = $env:VN_LABOR_PYTHON
  } else {
    $candidate = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
  }
  if (-not (Test-Path -LiteralPath $candidate)) {
    throw 'Chưa có môi trường Python. Chạy: run.bat setup-full'
  }
  return (Resolve-Path -LiteralPath $candidate).Path
}

function Assert-ExitCode([string]$Action) {
  if ($LASTEXITCODE -ne 0) { throw "$Action failed with exit code $LASTEXITCODE" }
}

function Initialize-Python([bool]$Full) {
  $venv = Join-Path $ProjectRoot '.venv'
  if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
    $portable = Join-Path $ProjectRoot '.python312\python.exe'
    if (Test-Path -LiteralPath $portable) {
      & $portable -m venv $venv
    } else {
      & py -3.12 -m venv $venv
    }
    Assert-ExitCode 'Python environment creation'
  }
  $python = Join-Path $venv 'Scripts\python.exe'
  & $python -m pip install --upgrade pip
  Assert-ExitCode 'pip upgrade'
  $target = if ($Full) { "${ProjectRoot}[full]" } else { $ProjectRoot }
  & $python -m pip install -e $target
  Assert-ExitCode 'project installation'
}

function Show-Help {
  @'
VN Labor Legal GraphRAG

  run.bat setup             Install core Python dependencies
  run.bat setup-full        Install all OFFLINE/ONLINE dependencies
  run.bat offline           Run the complete OFFLINE pipeline
  run.bat dense             Rebuild only the Dense index
  run.bat enrich            Enrich diagnostic checklists with Ollama
  run.bat neo4j             Start local Neo4j
  run.bat load-neo4j        Load the current graph into Neo4j
  run.bat online            Start deterministic ONLINE API
  run.bat online-check      Verify the pinned OFFLINE release for ONLINE
  run.bat online-ollama     Start ONLINE API with Ollama adjudication
  run.bat frontend          Start the React/Vite frontend
  run.bat test              Compile and run the repository test suite
  run.bat validate          Validate OFFLINE artifacts
  run.bat kaggle            Build the private Kaggle upload package
'@ | Write-Host
}

Import-ProjectEnvironment
Push-Location $ProjectRoot
try {
  switch ($Task) {
    'help' { Show-Help }
    'setup' { Initialize-Python $false }
    'setup-full' { Initialize-Python $true }
    'offline' {
      $python = Get-ProjectPython
      $env:PYTHONUTF8 = '1'; if (-not $env:HF_HOME) { $env:HF_HOME = Join-Path $ProjectRoot '.cache\huggingface' }
      if (-not $env:EASYOCR_MODULE_PATH) { $env:EASYOCR_MODULE_PATH = Join-Path $ProjectRoot '.cache\easyocr' }
      $selected = if ($Config) { $Config } else { 'config/pipeline.yaml' }
      & $python -m vn_labor_offline.cli all --config $selected
      Assert-ExitCode 'OFFLINE pipeline'
    }
    'dense' {
      $python = Get-ProjectPython
      $env:PYTHONUTF8 = '1'; $env:PYTHONUNBUFFERED = '1'; $env:HF_HUB_DISABLE_XET = '1'
      if (-not $env:HF_HOME) { $env:HF_HOME = Join-Path $ProjectRoot '.cache\huggingface' }
      & $python scripts/prepare_dense_model.py
      Assert-ExitCode 'Dense model preparation'
      $env:HF_HUB_OFFLINE = '1'
      $selected = if ($Config) { $Config } else { 'config/pipeline.yaml' }
      & $python -m vn_labor_offline.cli dense --config $selected
      Assert-ExitCode 'Dense rebuild'
    }
    'enrich' {
      $python = Get-ProjectPython
      & ollama pull qwen3:4b
      Assert-ExitCode 'Ollama model download'
      $selected = if ($Config) { $Config } else { 'config/pipeline.yaml' }
      & $python -m vn_labor_offline.cli enrich --config $selected --mode ollama
      Assert-ExitCode 'Ollama enrichment'
    }
    'neo4j' {
      & docker compose -f docker-compose.yml up -d neo4j
      Assert-ExitCode 'Neo4j startup'
    }
    'load-neo4j' {
      $python = Get-ProjectPython
      $selected = if ($Config) { $Config } else { 'config/pipeline.yaml' }
      & $python -m vn_labor_offline.cli load-neo4j --config $selected
      Assert-ExitCode 'Neo4j load'
    }
    'online' {
      $python = Get-ProjectPython
      $selected = if ($Config) { $Config } else { 'config/online.yaml' }
      & $python scripts/serve_online.py --config $selected --host $HostAddress --port $Port
      Assert-ExitCode 'ONLINE API'
    }
    'online-check' {
      $python = Get-ProjectPython
      $selected = if ($Config) { $Config } else { 'config/online.yaml' }
      & $python -m vn_labor_online.cli --config $selected check
      Assert-ExitCode 'ONLINE artifact compatibility check'
    }
    'online-ollama' {
      $python = Get-ProjectPython
      $selected = if ($Config) { $Config } else { 'config/online_ollama.yaml' }
      & $python scripts/serve_online.py --config $selected --host $HostAddress --port $Port
      Assert-ExitCode 'ONLINE Ollama API'
    }
    'frontend' {
      Push-Location (Join-Path $ProjectRoot 'frontend')
      try {
        if (-not (Test-Path -LiteralPath 'node_modules')) {
          & npm.cmd ci
          Assert-ExitCode 'frontend dependency installation'
        }
        & npm.cmd run dev
        Assert-ExitCode 'frontend development server'
      } finally { Pop-Location }
    }
    'test' {
      $python = Get-ProjectPython
      & $python -m compileall -q src scripts tests
      Assert-ExitCode 'Python compile check'
      & $python -m unittest discover -s tests -p 'test_*.py'
      Assert-ExitCode 'test suite'
    }
    'validate' {
      $python = Get-ProjectPython
      & $python scripts/validate_outputs.py
      Assert-ExitCode 'OFFLINE validation'
    }
    'kaggle' {
      $python = Get-ProjectPython
      & $python scripts/package_kaggle.py
      Assert-ExitCode 'Kaggle packaging'
    }
  }
} finally {
  Pop-Location
}
