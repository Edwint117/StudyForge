param([ValidateSet('setup','dev')][string]$Mode = 'setup')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $repoRoot
function Assert-LastExit { if ($LASTEXITCODE -ne 0) { throw 'Workspace command failed; inspect preceding non-secret diagnostics.' } }
if ($Mode -eq 'setup') {
  pnpm install --frozen-lockfile
  Assert-LastExit
  & (Join-Path $repoRoot '.tools/uv/uv.exe') sync --frozen --project services/engine
  Assert-LastExit
  pnpm supabase:start
  Assert-LastExit
  pnpm env:sync-local
  Assert-LastExit
  pnpm deploy:local
  Assert-LastExit
  pnpm env:container-local
  Assert-LastExit
  docker compose build engine
  Assert-LastExit
  Write-Output 'Web and engine dependencies are ready. Sandbox remains blocked on ADR-0020.'
} else {
  pnpm env:container-local
  Assert-LastExit
  docker compose up -d engine
  Assert-LastExit
  try { pnpm dev:web; Assert-LastExit }
  finally { docker compose stop engine }
}
