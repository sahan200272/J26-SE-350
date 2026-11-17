# Windows wrapper for the nightly compaction job (RP-18, section 4). Development only.
# Task Scheduler starts this at 20:00. It holds NO logic: it only finds the repo,
# uses the repo's .venv Python, and runs the Python entry point.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\scheduler\run_compaction.ps1 -Vault "D:\path\to\vault"
#
# Exit code = the job's exit code (0 ok, 1 a write failed, 2 bad input).

param(
    [Parameter(Mandatory = $true)][string]$Vault
)

$ErrorActionPreference = "Stop"
$Repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$LogDir = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "compaction.log"

Set-Location $Repo
& $Python -m agentic_core.compaction.run --vault $Vault --log-file $Log
exit $LASTEXITCODE
