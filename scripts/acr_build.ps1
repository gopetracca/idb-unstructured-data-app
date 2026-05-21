#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Builds and pushes the container image to ACR using a server-side build.

.DESCRIPTION
    Uses 'az acr build' to send the build context to Azure Container Registry
    and build the image in the cloud — no local Docker daemon or docker push needed.

    Prerequisites:
        - az cli installed and logged in ('az login')
        - Contributor or AcrPush role on the ACR

.PARAMETER Tag
    Image tag to apply. Defaults to 'latest'.

.PARAMETER Target
    Dockerfile build target stage. Use 'runtime' for production, 'dev' for dev image.
    Defaults to 'runtime'.

.EXAMPLE
    # Build production image with 'latest' tag
    .\scripts\acr_build.ps1

    # Build with a specific tag
    .\scripts\acr_build.ps1 -Tag "1.2.3"

    # Build the dev stage
    .\scripts\acr_build.ps1 -Target dev -Tag dev
#>

param(
    [string]$Tags   = "",
    [string]$Target = "runtime"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Git SHA tag (short commit, falls back to 'unknown' if not in a git repo)
# ---------------------------------------------------------------------------
$GitSha = (git rev-parse --short HEAD 2>$null)
if (-not $GitSha) { $GitSha = "unknown" } else { $GitSha = $GitSha.Trim() }

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
$ACR_NAME   = "acrnpdaimvpshared"
$IMAGE_NAME = "aimvp-unnstructured-data-app"

# Default tags include git SHA + latest; caller can override with -Tags "sha-abc,v1.2.3"
if (-not $Tags) { $Tags = "sha-${GitSha},latest" }

$TagList = $Tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
$FULL_IMAGE = "${ACR_NAME}.azurecr.io/${IMAGE_NAME}:$($TagList[0])"

# ---------------------------------------------------------------------------
# Resolve repo root (script lives in scripts/)
# ---------------------------------------------------------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "ACR server-side build"
Write-Host "  Registry : $ACR_NAME"
Write-Host "  Image    : $IMAGE_NAME"
Write-Host "  Tags     : $($TagList -join ', ')"
Write-Host "  Stage    : $Target"
Write-Host "  Context  : $RepoRoot"
Write-Host ""

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
# az acr build requires a directory (not a tarball) as source.
# We copy only the runtime-relevant files to a temp directory to avoid:
#   - Windows MAX_PATH errors deep inside .venv
#   - uploading tests/, docs/, scripts/, htmlcov/, etc.
$TempContext = Join-Path $env:TEMP "acr-context-$(New-Guid)"
try {
    Write-Host "Creating minimal build context in $TempContext ..."
    New-Item -ItemType Directory -Path $TempContext -Force | Out-Null

    # Individual files needed by the Dockerfile / runtime
    @("Dockerfile", "function_app.py", "host.json", "pyproject.toml", "uv.lock", "requirements.txt") | ForEach-Object {
        $src = Join-Path $RepoRoot $_
        if (Test-Path $src) { Copy-Item $src $TempContext }
    }

    # Placeholder certificate input required by the Dockerfile's optional CA step.
    # ACR/cloud builds keep INSTALL_IADB_CA=false, so the placeholder is not installed.
    $dockerDir = Join-Path $TempContext ".docker"
    New-Item -ItemType Directory -Path $dockerDir -Force | Out-Null
    @("empty-iadb-root-ca.crt", "start-functions.sh") | ForEach-Object {
        Copy-Item `
            (Join-Path $RepoRoot ".docker\$_") `
            (Join-Path $dockerDir $_)
    }

    # Directories needed at runtime
    @("src") | ForEach-Object {
        $src = Join-Path $RepoRoot $_
        if (Test-Path $src) { Copy-Item $src (Join-Path $TempContext $_) -Recurse }
    }

    Write-Host "Sending context to ACR..."
    $ImageArgs = @()
    foreach ($t in $TagList) { $ImageArgs += "--image"; $ImageArgs += "${IMAGE_NAME}:${t}" }

    az acr build `
        --registry   $ACR_NAME `
        @ImageArgs `
        --target     $Target `
        --build-arg  INSTALL_IADB_CA=false `
        --build-arg  IADB_ROOT_CA_FILE=.docker/empty-iadb-root-ca.crt `
        --file       "$TempContext\Dockerfile" `
        $TempContext

    if ($LASTEXITCODE -ne 0) {
        Write-Error "az acr build failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
} finally {
    if (Test-Path $TempContext) { Remove-Item $TempContext -Recurse -Force }
}

Write-Host ""
Write-Host "Build complete:"
foreach ($t in $TagList) {
    Write-Host "  ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${t}"
}
