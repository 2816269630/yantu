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
        'RESEARCH_PORT=8088'
        'RESEARCH_BIND=127.0.0.1'
        "RESEARCH_DB_PASSWORD=$databasePassword"
        'PLANE_BASE_URL=http://host.docker.internal'
        'PLANE_API_KEY='
        'PLANE_ALLOWED_PROJECTS='
        'AI_BASE_URL='
        'AI_MODEL='
    ) -join "`n"
    [IO.File]::WriteAllText($configPath, $configuration + "`n", (New-Object Text.UTF8Encoding $false))
}
$composeArguments = @('compose','--env-file',$configPath,'-f','compose.local.yaml','up','-d','--wait','--wait-timeout','180')
if (-not $NoBuild) { $composeArguments += '--build' }
& $dockerPath @composeArguments
if ($LASTEXITCODE -ne 0) { throw 'Research service did not start. See the Docker output above. Existing Plane data has not been changed.' }
$portLine = Get-Content -LiteralPath $configPath | Where-Object { $_ -match '^RESEARCH_PORT=' } | Select-Object -First 1
$port = if ($portLine) { $portLine.Substring(14) } else { '8088' }
Write-Host "Research: http://localhost:$port" -ForegroundColor Green
Write-Host 'Open the research URL to enter the standalone research system.'
