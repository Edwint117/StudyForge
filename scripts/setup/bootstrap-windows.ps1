param([switch]$SkipCloud)
$ErrorActionPreference = 'Stop'
$sfRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$sfTools = Join-Path $sfRoot '.tools'
New-Item -ItemType Directory -Force -Path $sfTools | Out-Null

function Install-VerifiedArchive([string]$Url, [string]$Hash, [string]$Name, [string]$Destination) {
    $sfArchive = Join-Path $sfTools $Name
    if (-not (Test-Path -LiteralPath $sfArchive)) { Invoke-WebRequest -Uri $Url -OutFile $sfArchive }
    if ((Get-FileHash -LiteralPath $sfArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash.ToLowerInvariant()) {
        throw 'Tool archive checksum mismatch. No executable was run.'
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Expand-Archive -LiteralPath $sfArchive -DestinationPath $Destination -Force
}

$sfUvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $sfUvCommand -and -not (Test-Path -LiteralPath (Join-Path $sfTools 'uv/uv.exe'))) {
    $sfUvUrl = 'https://github.com/astral-sh/uv/releases/download/0.12.19/uv-x86_64-pc-windows-msvc.zip'
    $sfUvChecksum = [string](Invoke-RestMethod -Uri "$sfUvUrl.sha256")
    $sfUvHash = ($sfUvChecksum.Trim() -split '\s+')[0]
    if ($sfUvHash -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid uv checksum manifest' }
    Install-VerifiedArchive $sfUvUrl $sfUvHash 'uv-0.12.19.zip' (Join-Path $sfTools 'uv')
}
$sfUv = if ($sfUvCommand) { $sfUvCommand.Source } else { Join-Path $sfTools 'uv/uv.exe' }
if (-not $env:UV_PYTHON_INSTALL_DIR) {
    $env:UV_PYTHON_INSTALL_DIR = [Environment]::GetEnvironmentVariable('UV_PYTHON_INSTALL_DIR', 'User')
    if (-not $env:UV_PYTHON_INSTALL_DIR) { $env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv/python' }
}
& $sfUv --version
& $sfUv python install 3.12 --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }

if (-not (Test-Path -LiteralPath (Join-Path $sfTools 'gitleaks/gitleaks.exe'))) {
    $sfLeakBase = 'https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/'
    $sfLeakChecksum = [string](Invoke-RestMethod -Uri ($sfLeakBase + 'gitleaks_8.30.1_checksums.txt'))
    $sfLeakLine = ($sfLeakChecksum -split "`n" | Where-Object { $_ -match ' gitleaks_8.30.1_windows_x64.zip$' })
    $sfLeakHash = ($sfLeakLine.Trim() -split '\s+')[0]
    if ($sfLeakHash -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid gitleaks checksum manifest' }
    Install-VerifiedArchive ($sfLeakBase + 'gitleaks_8.30.1_windows_x64.zip') $sfLeakHash 'gitleaks-8.30.1.zip' (Join-Path $sfTools 'gitleaks')
}
& (Join-Path $sfTools 'gitleaks/gitleaks.exe') version

if (-not $SkipCloud) {
    $sfCloudCommand = Get-Command gcloud -ErrorAction SilentlyContinue
    if (-not $sfCloudCommand -and -not (Test-Path -LiteralPath (Join-Path $sfTools 'google-cloud-sdk/bin/gcloud.cmd'))) {
        Install-VerifiedArchive 'https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-586.0.0-windows-x86_64-bundled-python.zip' '5fecb9af0f178331b2333c167e57a2676ac286029fb16e328aef911f9d2df2a8' 'gcloud-586.0.0.zip' $sfTools
    }
    $sfCloud = if ($sfCloudCommand) { $sfCloudCommand.Source } else { Join-Path $sfTools 'google-cloud-sdk/bin/gcloud.cmd' }
    & $sfCloud version
    if ($LASTEXITCODE -ne 0) { throw 'Google Cloud CLI validation failed' }
}
