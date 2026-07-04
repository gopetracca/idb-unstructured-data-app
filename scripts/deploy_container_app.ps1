#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Deploys an already-built ACR image to Azure Container Apps.

.DESCRIPTION
    Updates a Container App to a specific image tag, sets DD_VERSION to that tag,
    verifies that Azure created a new latest revision, and waits until the
    revision reaches the Provisioned state.

.PARAMETER App
    Azure Container App name.

.PARAMETER ResourceGroup
    Azure resource group.

.PARAMETER Acr
    Azure Container Registry name, without azurecr.io.

.PARAMETER Image
    Image repository name, without registry prefix.

.PARAMETER Tag
    Immutable image tag to deploy, for example sha-7685b57 or v1.2.3.

.PARAMETER TimeoutSeconds
    Provisioning timeout in seconds. Defaults to 600.

.PARAMETER PollIntervalSeconds
    Revision polling interval in seconds. Defaults to 10.

.PARAMETER RevisionSuffix
    Override the generated revision suffix.

.PARAMETER AllowLatest
    Allow deploying the mutable latest tag. Disabled by default.

.PARAMETER ConfigureProbes
    Also set liveness/readiness/startup probes (/health/live, /health/ready)
    on the revision. Requires python3 (or python) on PATH.

.PARAMETER RunMigrations
    Set RUN_DB_MIGRATIONS_ON_STARTUP=true so the new revision applies alembic
    migrations at startup.

.EXAMPLE
    .\scripts\deploy_container_app.ps1 `
        -App ca-np-d-aimvp-unstructdata `
        -ResourceGroup rg-np-d-aimvp `
        -Acr acrnpdaimvpshared `
        -Image aimvp-unnstructured-data-app `
        -Tag sha-7685b57
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$App,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$Acr,

    [Parameter(Mandatory = $true)]
    [string]$Image,

    [Parameter(Mandatory = $true)]
    [string]$Tag,

    [int]$TimeoutSeconds = 600,

    [int]$PollIntervalSeconds = 10,

    [string]$RevisionSuffix,

    [switch]$AllowLatest,

    [switch]$ConfigureProbes,

    [switch]$RunMigrations
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-Deploy {
    param([Parameter(Mandatory = $true)][string]$Message)

    [Console]::Error.WriteLine("Error: $Message")
    exit 1
}

function Invoke-AzValue {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [switch]$AllowFailure
    )

    # Local override prevents stderr ErrorRecord objects (merged via 2>&1) from
    # triggering the script-level $ErrorActionPreference = "Stop".
    $local:ErrorActionPreference = "Continue"
    $output = & az @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        if ($AllowFailure) {
            return $null
        }

        $message = ($output | Out-String).Trim()
        throw "az $($Arguments -join ' ') failed with exit code $exitCode`n$message"
    }

    return ($output | Out-String).Trim()
}

function Invoke-AzCommand {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    # Local override prevents stderr ErrorRecord objects (merged via 2>&1) from
    # triggering the script-level $ErrorActionPreference = "Stop".
    $local:ErrorActionPreference = "Continue"
    $output = & az @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        $message = ($output | Out-String).Trim()
        throw "az $($Arguments -join ' ') failed with exit code $exitCode`n$message"
    }
}

function Get-RevisionSuffix {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RawSuffix,

        [Parameter(Mandatory = $true)]
        [string]$AppName
    )

    $suffix = $RawSuffix.ToLowerInvariant()
    $suffix = $suffix -replace '[^a-z0-9-]+', '-'
    $suffix = $suffix -replace '-+', '-'
    $suffix = $suffix.Trim('-')

    if ([string]::IsNullOrWhiteSpace($suffix)) {
        $suffix = "revision"
    }

    if ($suffix -notmatch '^[a-z]') {
        $suffix = "r-$suffix"
    }

    # Azure revision names are derived as <container-app-name>--<suffix>.
    $maxSuffixLength = 63 - $AppName.Length - 2
    if ($maxSuffixLength -lt 1) {
        Stop-Deploy "container app name is too long to generate a revision suffix safely"
    }

    if ($suffix.Length -gt $maxSuffixLength) {
        $suffix = $suffix.Substring(0, $maxSuffixLength).TrimEnd('-')
    }

    $suffix = $suffix -replace '[^a-z0-9]+$', ''
    if ([string]::IsNullOrWhiteSpace($suffix) -or $suffix -notmatch '^[a-z]') {
        $suffix = "r"
    }

    return $suffix
}

try {
    if ($TimeoutSeconds -le 0) {
        Stop-Deploy "-TimeoutSeconds must be greater than zero"
    }

    if ($PollIntervalSeconds -le 0) {
        Stop-Deploy "-PollIntervalSeconds must be greater than zero"
    }

    if ($Tag.Equals("latest", [StringComparison]::OrdinalIgnoreCase) -and -not $AllowLatest.IsPresent) {
        Stop-Deploy "refusing to deploy mutable tag 'latest'; pass -AllowLatest to override"
    }

    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        Stop-Deploy "Azure CLI 'az' was not found on PATH"
    }

    if ([string]::IsNullOrWhiteSpace($RevisionSuffix)) {
        $RevisionSuffix = Get-RevisionSuffix -RawSuffix $Tag -AppName $App
    } else {
        $RevisionSuffix = Get-RevisionSuffix -RawSuffix $RevisionSuffix -AppName $App
    }

    $fullImage = "{0}.azurecr.io/{1}:{2}" -f $Acr, $Image, $Tag

    Write-Host ""
    Write-Host "Container App deployment"
    Write-Host "  App             : $App"
    Write-Host "  Resource group  : $ResourceGroup"
    Write-Host "  Image           : $fullImage"
    Write-Host "  Revision suffix : $RevisionSuffix"
    Write-Host "  Timeout         : ${TimeoutSeconds}s"
    Write-Host ""

    $oldImage = Invoke-AzValue -Arguments @(
        "containerapp", "show",
        "--name", $App,
        "--resource-group", $ResourceGroup,
        "--query", "properties.template.containers[0].image",
        "-o", "tsv"
    )

    $oldRevision = Invoke-AzValue -Arguments @(
        "containerapp", "show",
        "--name", $App,
        "--resource-group", $ResourceGroup,
        "--query", "properties.latestRevisionName",
        "-o", "tsv"
    )

    $activeRevisionsMode = Invoke-AzValue -Arguments @(
        "containerapp", "show",
        "--name", $App,
        "--resource-group", $ResourceGroup,
        "--query", "properties.configuration.activeRevisionsMode",
        "-o", "tsv"
    )

    Write-Host "Previous image    : $(if ($oldImage) { $oldImage } else { '<none>' })"
    Write-Host "Previous revision : $(if ($oldRevision) { $oldRevision } else { '<none>' })"
    Write-Host "Traffic mode      : $(if ($activeRevisionsMode) { $activeRevisionsMode } else { '<unknown>' })"
    Write-Host ""

    $envVars = @("DD_VERSION=$Tag")
    if ($RunMigrations.IsPresent) {
        $envVars += "RUN_DB_MIGRATIONS_ON_STARTUP=true"
    }

    if ($ConfigureProbes.IsPresent) {
        # Image + env vars + probes in a single template update (one revision).
        $python = (Get-Command python3 -ErrorAction SilentlyContinue) ?? (Get-Command python -ErrorAction SilentlyContinue)
        if (-not $python) {
            Stop-Deploy "python3 (or python) is required for -ConfigureProbes"
        }

        $probesScript = Join-Path $PSScriptRoot "containerapp_probes.py"
        $payloadFile = New-TemporaryFile

        $probeArgs = @(
            $probesScript,
            "--image", $fullImage,
            "--dd-version", $Tag,
            "--revision-suffix", $RevisionSuffix
        )
        if ($RunMigrations.IsPresent) {
            $probeArgs += @("--set-env", "RUN_DB_MIGRATIONS_ON_STARTUP=true")
        }

        try {
            $appJson = Invoke-AzValue -Arguments @(
                "containerapp", "show",
                "--name", $App,
                "--resource-group", $ResourceGroup,
                "-o", "json"
            )

            $appJson | & $python.Source @probeArgs | Set-Content -Path $payloadFile -Encoding utf8

            if ($LASTEXITCODE -ne 0) {
                Stop-Deploy "containerapp_probes.py failed with exit code $LASTEXITCODE"
            }

            Invoke-AzCommand -Arguments @(
                "containerapp", "update",
                "--name", $App,
                "--resource-group", $ResourceGroup,
                "--yaml", $payloadFile.FullName,
                "--output", "none"
            )
        } finally {
            Remove-Item -Path $payloadFile -ErrorAction SilentlyContinue
        }
    } else {
        Invoke-AzCommand -Arguments (@(
            "containerapp", "update",
            "--name", $App,
            "--resource-group", $ResourceGroup,
            "--image", $fullImage,
            "--revision-suffix", $RevisionSuffix,
            "--set-env-vars"
        ) + $envVars + @("--output", "none"))
    }

    $latestRevision = Invoke-AzValue -Arguments @(
        "containerapp", "show",
        "--name", $App,
        "--resource-group", $ResourceGroup,
        "--query", "properties.latestRevisionName",
        "-o", "tsv"
    )

    if ([string]::IsNullOrWhiteSpace($latestRevision)) {
        Stop-Deploy "latest revision name returned by Azure is empty"
    }

    if (-not [string]::IsNullOrWhiteSpace($oldRevision) -and $latestRevision -eq $oldRevision) {
        Stop-Deploy "Container App latest revision did not change after update; refusing to report success for a no-op deploy"
    }

    Write-Host "Latest revision   : $latestRevision"
    Write-Host ""

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $provisioningState = ""

    while ((Get-Date) -lt $deadline) {
        $provisioningState = Invoke-AzValue -Arguments @(
            "containerapp", "revision", "show",
            "--name", $App,
            "--resource-group", $ResourceGroup,
            "--revision", $latestRevision,
            "--query", "properties.provisioningState",
            "-o", "tsv"
        ) -AllowFailure

        if ([string]::IsNullOrWhiteSpace($provisioningState)) {
            $provisioningState = "Unknown"
        }

        Write-Host "Revision $latestRevision provisioning state: $provisioningState"

        if ($provisioningState -eq "Provisioned") {
            break
        }

        if ($provisioningState -eq "Failed") {
            Stop-Deploy "revision $latestRevision provisioning failed"
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }

    if ($provisioningState -ne "Provisioned") {
        Stop-Deploy "timed out after ${TimeoutSeconds}s waiting for revision $latestRevision to provision"
    }

    $newImage = Invoke-AzValue -Arguments @(
        "containerapp", "show",
        "--name", $App,
        "--resource-group", $ResourceGroup,
        "--query", "properties.template.containers[0].image",
        "-o", "tsv"
    )

    $trafficWeights = Invoke-AzValue -Arguments @(
        "containerapp", "show",
        "--name", $App,
        "--resource-group", $ResourceGroup,
        "--query", "properties.configuration.ingress.traffic",
        "-o", "json"
    ) -AllowFailure

    if ([string]::IsNullOrWhiteSpace($trafficWeights)) {
        $trafficWeights = "[]"
    }

    Write-Host ""
    Write-Host "Deployment verified"
    Write-Host "  Old image          : $(if ($oldImage) { $oldImage } else { '<none>' })"
    Write-Host "  New image          : $(if ($newImage) { $newImage } else { '<none>' })"
    Write-Host "  Latest revision    : $latestRevision"
    Write-Host "  Provisioning state : $provisioningState"
    Write-Host "  Traffic mode       : $(if ($activeRevisionsMode) { $activeRevisionsMode } else { '<unknown>' })"
    Write-Host "  Traffic weights    : $trafficWeights"
} catch {
    $errMsg = if ($_.Exception -and $_.Exception.Message) { $_.Exception.Message } else { $_.ToString() }
    [Console]::Error.WriteLine("Error: $errMsg")
    exit 1
}
