$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.venv')) { py -3.11 -m venv .venv }
& '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]'
& '.\.venv\Scripts\python.exe' scripts/validate_local_release.py
Write-Host 'Optional native ChromaDB (requires internet and approved Python wheel):'
Write-Host '  .\.venv\Scripts\python.exe -m pip install -e ".[vector,models,dev]"'
Write-Host '  .\.venv\Scripts\python.exe -m m2.chroma_validation'
Write-Host 'Review validation/ADVANCED_VALIDATION_REPORT.json; NOT pilot sign-off.'
