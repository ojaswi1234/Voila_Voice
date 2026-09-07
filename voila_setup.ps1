<#
.SYNOPSIS
    Voila_Voice setup automation.
.DESCRIPTION
    1. Replaces stale hardcoded paths (old project folder) with the current one.
    2. Rebuilds voila.exe from local-agent (Go).
    3. Optionally launches the agent.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\voila_setup.ps1
.EXAMPLE
    .\voila_setup.ps1 -WhatIfOnly     # preview path fixes, change nothing
.EXAMPLE
    .\voila_setup.ps1 -Run            # fix + build + launch the agent
#>
[CmdletBinding()]
param(
    [string]$OldPath = 'C:\Users\ojasw\Desktop\voice-cli-system',
    [string]$NewPath = $PSScriptRoot,   # repo folder = wherever the script sits
    [switch]$Run,                      # launch the agent when done
    [switch]$WhatIfOnly                # preview only, change nothing
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrEmpty($NewPath)) { $NewPath = (Get-Location).Path }

$goDir   = Join-Path $NewPath 'local-agent'
$exePath = Join-Path $goDir 'voila.exe'

Write-Host "== Voila setup ==" -ForegroundColor Cyan
Write-Host "Repo : $NewPath"

# --- sanity check ----------------------------------------------------------
if (-not (Test-Path $goDir)) { throw "local-agent folder not found under $NewPath - run this from the repo root." }

# --- 1. fix stale paths -----------------------------------------------------
Write-Host "`n[1/3] Scanning for stale path: $OldPath" -ForegroundColor Yellow

$hits = git -C $NewPath grep -l -F -I -- $OldPath
if (-not $hits) {
    Write-Host "  Nothing to fix."
} else {
    foreach ($f in $hits) {
        $full = Join-Path $NewPath $f
        $raw  = Get-Content $full -Raw
        $new  = $raw.Replace($OldPath, $NewPath)
        if ($WhatIfOnly) {
            Write-Host "  WOULD update: $f" -ForegroundColor DarkGray
        } else {
            Set-Content $full $new -NoNewline -Encoding UTF8
            Write-Host "  updated: $f" -ForegroundColor Green
        }
    }
}

# --- 2. build voila.exe ------------------------------------------------------
Write-Host "`n[2/3] Building voila.exe" -ForegroundColor Yellow
if (-not (Get-Command go -ErrorAction SilentlyContinue)) { throw "Go toolchain not found in PATH." }

Push-Location $goDir
try {
    go mod download
    go build -o voila.exe .
    if (-not (Test-Path $exePath)) { throw "Build finished but voila.exe is missing." }
    Write-Host "  built: $exePath" -ForegroundColor Green
} finally {
    Pop-Location
}

# --- 3. launch ----------------------------------------------------------------
if ($Run) {
    Write-Host "`n[3/3] Starting Voila agent" -ForegroundColor Yellow
    $pyw = Join-Path $goDir 'run_hidden_agent.pyw'
    if (Test-Path $pyw) {
        Start-Process python -ArgumentList "`"$pyw`"" -WorkingDirectory $goDir
        Write-Host "  launched run_hidden_agent.pyw" -ForegroundColor Green
    } else {
        Write-Host "  run_hidden_agent.pyw not found - skipping launch." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "`n[3/3] Skipped launch (pass -Run to start the agent)." -ForegroundColor DarkGray
}

Write-Host "`nDone." -ForegroundColor Cyan
