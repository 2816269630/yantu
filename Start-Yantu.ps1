param([switch]$NoBuild)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'yantu-research\Start-Research.ps1') -NoBuild:$NoBuild
