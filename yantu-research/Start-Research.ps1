param([switch]$NoBuild)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$dockerPath = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe' }
if (-not (Test-Path -LiteralPath $dockerPath)) { throw 'Docker Desktop is not installed. Start Docker Desktop, then retry.' }
& $dockerPath info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop (Linux containers) before continuing.' }
$configPath = Join-Path $PSScriptRoot '.env.research'
if (-not (Test-Path -LiteralPath $configPath)) {
    $randomBytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($randomBytes)
    $rng.Dispose()
    $databasePassword = -join ($randomBytes | ForEach-Object { $_.ToString('x2') })
    $configuration = @(
        'RESEARCH_PORT=8089'
        'RESEARCH_BIND=127.0.0.1'
        "RESEARCH_DB_PASSWORD=$databasePassword"
    ) -join "`n"
    [IO.File]::WriteAllText($configPath, $configuration + "`n", (New-Object Text.UTF8Encoding $false))
}
$composeArguments = @('compose','--env-file',$configPath,'-f','compose.local.yaml','up','-d','--wait','--wait-timeout','180')
if (-not $NoBuild) { $composeArguments += '--build' }
& $dockerPath @composeArguments
if ($LASTEXITCODE -ne 0) { throw 'Laboratory service did not start. See the Docker output above.' }
$portLine = Get-Content -LiteralPath $configPath | Where-Object { $_ -match '^RESEARCH_PORT=' } | Select-Object -First 1
$port = if ($portLine) { $portLine.Substring(14) } else { '8089' }
Write-Host "Research: http://localhost:$port" -ForegroundColor Green
Write-Host 'Open the URL and register your new laboratory account.'
