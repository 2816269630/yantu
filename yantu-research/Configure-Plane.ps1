$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$configPath = Join-Path $PSScriptRoot '.env.research'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Run Start-Research.ps1 once before configuring Plane.' }
Write-Host 'In Plane: Profile > Settings > Personal access tokens, create a token for your project.'
$projectLink = Read-Host 'Paste the Plane project URL (http://localhost/workspace/projects/UUID/...)'
$projectUri = $null
if (-not [Uri]::TryCreate($projectLink, [UriKind]::Absolute, [ref]$projectUri)) { throw 'Invalid project URL.' }
$match = [regex]::Match($projectUri.AbsolutePath, '^/([^/]+)/projects/([0-9a-fA-F-]{36})(?:/|$)')
if (-not $match.Success) { throw 'Open your Plane project and copy its full browser URL.' }
if ($projectUri.Host -notin @('localhost','127.0.0.1')) { throw 'This local setup expects a localhost Plane URL.' }
$apiKeySecure = Read-Host 'Paste the Plane API key (hidden)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiKeySecure)
try { $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
if ($apiKey -notmatch '^[A-Za-z0-9._-]{10,512}$') { throw 'API key format was not recognized.' }
$projectEntry = $match.Groups[1].Value + ':' + $match.Groups[2].Value
$lines = @(Get-Content -LiteralPath $configPath)
$oldAllowlist = ($lines | Where-Object { $_ -match '^PLANE_ALLOWED_PROJECTS=' } | Select-Object -First 1) -replace '^PLANE_ALLOWED_PROJECTS=', ''
$allowlist = (@(($oldAllowlist -split ',') | Where-Object { $_ }) + $projectEntry | Select-Object -Unique) -join ','
$values = @{
    'PLANE_API_KEY' = $apiKey
    'PLANE_ALLOWED_PROJECTS' = $allowlist
    'PLANE_BASE_URL' = $projectUri.Scheme + '://host.docker.internal:' + $projectUri.Port
}
foreach ($key in $values.Keys) {
    $lines = @($lines | Where-Object { -not $_.StartsWith($key + '=') })
    $lines += $key + '=' + $values[$key]
}
[IO.File]::WriteAllText($configPath, ($lines -join "`n") + "`n", (New-Object Text.UTF8Encoding $false))
$apiKey = $null
Write-Host 'Saved locally. Refresh Research > Space settings and select your Plane project.' -ForegroundColor Green
& (Join-Path $PSScriptRoot 'Start-Research.ps1') -NoBuild
