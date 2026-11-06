# start_member2_explorer.ps1
# Launches the Member 2 Regulatory Knowledge Base & Evidence Explorer
# on localhost only (127.0.0.1:8501).
#
# Usage:
#   .\scripts\start_member2_explorer.ps1
#   .\scripts\start_member2_explorer.ps1 -Port 8502

param(
    [int]$Port = 8501
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$AppPath = Join-Path $ProjectRoot "tools\member2_explorer\app.py"

Write-Host ""
Write-Host "Member 2 - Regulatory Knowledge Base and Evidence Explorer"
Write-Host "==========================================================="
Write-Host "Project: $ProjectRoot"
Write-Host "App:     $AppPath"
Write-Host "Address: http://127.0.0.1:$Port"
Write-Host ""

if (-not (Test-Path $AppPath)) {
    Write-Error "App not found: $AppPath"
    exit 1
}

# Verify Python dependencies
$missing = @()
foreach ($pkg in @("streamlit", "chromadb", "sentence_transformers")) {
    $check = python -c "import $pkg" 2>&1
    if ($LASTEXITCODE -ne 0) { $missing += $pkg }
}
if ($missing.Count -gt 0) {
    Write-Warning "Missing packages: $($missing -join ', ')"
    Write-Host "Run: pip install $($missing -join ' ')"
    exit 1
}

Write-Host "Starting Streamlit - press Ctrl+C to stop"
Write-Host ""

Set-Location $ProjectRoot
python -m streamlit run $AppPath `
    --server.address 127.0.0.1 `
    --server.port $Port `
    --server.headless false `
    --browser.gatherUsageStats false `
    --server.enableCORS false
