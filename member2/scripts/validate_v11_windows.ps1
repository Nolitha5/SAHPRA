# Member 2 native validation on a model-enabled Windows workstation.
# Run from the project root. Regulator/source approval is NOT implied by success.
param(
  [string]$Model = 'BAAI/bge-large-en-v1.5',
  [int]$WindowTokens = 384,
  [int]$OverlapTokens = 64,
  [switch]$InstallDependencies,
  [switch]$OfflineModels
)
$ErrorActionPreference = 'Stop'
if ($InstallDependencies) {
  python -m pip install -e '.[vector,models,dev,experiment]'
  if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
python scripts/audit_regulatory_page_citations.py --root .
if ($LASTEXITCODE -ne 0) { throw 'Original PDF passage-anchor audit failed' }
$runArgs = @('scripts/run_native_bge_chroma_validation.py', '--root', '.', '--model', $Model,
  '--window-tokens', $WindowTokens.ToString(), '--overlap-tokens', $OverlapTokens.ToString(),
  '--out', 'validation/v1.1_NATIVE_CHROMA_BGE_RESULTS.json')
if ($OfflineModels) { $runArgs += '--offline' }
python @runArgs
if ($LASTEXITCODE -ne 0) { throw 'Native ChromaDB/BGE still BLOCKED or failed; inspect validation/v1.1_NATIVE_CHROMA_BGE_RESULTS.json' }
Write-Host 'Native technical indexing and persistence PASS. Regulatory approval/expert evaluation NOT claimed.'
