<#
.SYNOPSIS
    Mint a bearer token for the Unstructured Data API.

.DESCRIPTION
    Two flows, because Entra puts authorization in a different claim depending on
    how the token was obtained — and the API accepts both (see
    src/presentation/http/auth/dependencies.py::granted_scopes).

      Authorization code (default)
          client id + secret + your interactive sign-in.
          Returns scp = "Search documents.read documents.write admin".
          The delegated scopes are type:User, so you consent to them yourself —
          no Application Administrator, and no App Role on your account.

      Client credentials (-AppOnly)
          client id + secret only, no user.
          Returns roles = whatever App Roles the service principal is *assigned*.
          Assignments require an Application Administrator; an app registration
          owner cannot self-assign. See "Granting App Roles" below.

    The asymmetry worth remembering: delegated scopes are granted by CONSENT,
    which a user can give. App Roles are granted by ASSIGNMENT, which needs an
    admin.

.PARAMETER AppOnly
    Use the client-credentials flow instead of authorization code.

.PARAMETER Decode
    Print the token's claims instead of only returning the token.

.EXAMPLE
    $env:AIMVP_API_CLIENT_SECRET = az keyvault secret show --vault-name <kv> `
        --name sec-aimvp-a-api-unstructdata --query value -o tsv
    $tok = .\scripts\get_dev_token.ps1 -Decode

.EXAMPLE
    $tok = .\scripts\get_dev_token.ps1 -AppOnly
    curl.exe -H "Authorization: Bearer $tok" $api/api/v1/capabilities

.NOTES
    Never pass the secret as a literal argument — it lands in your shell history.
    Use the AIMVP_API_CLIENT_SECRET environment variable.
#>

[CmdletBinding()]
param(
    # Dev app registration: aimvp-a-np-d-api-unstructdata
    [string]$ClientId = 'bd03bba6-51e7-4316-84d6-634e182decb2',
    [string]$TenantId = '9dfb1a05-5f1d-449a-8960-62abcb479e7d',
    [string]$Secret   = $env:AIMVP_API_CLIENT_SECRET,
    # Must exactly match a redirect URI registered on the app.
    [string]$Redirect = 'http://localhost:8000',
    [switch]$AppOnly,
    [switch]$Decode
)

$ErrorActionPreference = 'Stop'

if (-not $Secret) {
    Write-Error @'
No client secret. Set it from Key Vault first:

  $env:AIMVP_API_CLIENT_SECRET = az keyvault secret show --vault-name <kv> `
      --name sec-aimvp-a-api-unstructdata --query value -o tsv
'@
    exit 1
}

$authority = "https://login.microsoftonline.com/$TenantId/oauth2/v2.0"

function Write-Claims {
    param([string]$Token)

    $payload = $Token.Split('.')[1].Replace('-', '+').Replace('_', '/')
    while ($payload.Length % 4) { $payload += '=' }
    $claims = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json

    Write-Host ''
    Write-Host '--- token claims ---' -ForegroundColor Cyan
    foreach ($name in 'aud', 'iss', 'ver', 'azp', 'appid', 'roles', 'scp', 'oid', 'tid', 'preferred_username') {
        if ($claims.PSObject.Properties.Name -contains $name) {
            Write-Host ('  {0,-20} {1}' -f $name, ($claims.$name -join ' '))
        }
    }
    Write-Host '--------------------' -ForegroundColor Cyan
    Write-Host ''
}

# ---------------------------------------------------------------- app-only --

if ($AppOnly) {
    $response = Invoke-RestMethod -Method Post -Uri "$authority/token" -Body @{
        grant_type    = 'client_credentials'
        client_id     = $ClientId
        client_secret = $Secret
        # .default asks for every App Role the SP is assigned — it cannot
        # produce scp, because there is no user in this flow.
        scope         = "api://$ClientId/.default"
    }

    if ($Decode) { Write-Claims $response.access_token }
    return $response.access_token
}

# ------------------------------------------------------- authorization code --

$scopes = @(
    "api://$ClientId/Search"
    "api://$ClientId/documents.read"
    "api://$ClientId/documents.write"
    "api://$ClientId/admin"
) -join ' '

$state = [guid]::NewGuid().ToString('N')
$authUrl = "$authority/authorize?" + (@(
    "client_id=$ClientId"
    'response_type=code'
    "redirect_uri=$([uri]::EscapeDataString($Redirect))"
    'response_mode=query'
    "scope=$([uri]::EscapeDataString($scopes))"
    "state=$state"
    'prompt=consent'    # surface the consent screen on first run
) -join '&')

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("$Redirect/")
try {
    $listener.Start()
} catch {
    Write-Error "Cannot listen on $Redirect - is the port already in use? (The local API dev server also defaults to 8000.)"
    exit 1
}

Write-Host 'Opening a browser to sign in and consent...' -ForegroundColor Cyan
Write-Host "If it does not open, paste this URL:`n$authUrl`n"
Start-Process $authUrl

try {
    $context   = $listener.GetContext()   # blocks until Entra redirects back
    $code      = $context.Request.QueryString['code']
    $err       = $context.Request.QueryString['error']
    $errDesc   = $context.Request.QueryString['error_description']
    $gotState  = $context.Request.QueryString['state']

    $message = if ($code) {
        '<h2>Signed in.</h2><p>Close this tab and return to the terminal.</p>'
    } else {
        "<h2>Sign-in failed.</h2><pre>$err`n$errDesc</pre>"
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(
        "<!doctype html><meta charset=""utf-8""><body style=""font-family:system-ui;padding:3rem"">$message")
    $context.Response.ContentType = 'text/html; charset=utf-8'
    $context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $context.Response.Close()
} finally {
    $listener.Stop()
}

if (-not $code)             { Write-Error "Authorization failed: $err - $errDesc"; exit 1 }
if ($gotState -ne $state)   { Write-Error 'State mismatch - possible CSRF, aborting.'; exit 1 }

$response = Invoke-RestMethod -Method Post -Uri "$authority/token" -Body @{
    grant_type    = 'authorization_code'
    client_id     = $ClientId
    client_secret = $Secret
    code          = $code
    redirect_uri  = $Redirect
    scope         = $scopes
}

if ($Decode) { Write-Claims $response.access_token }
$response.access_token

<#
--------------------------------------------------------------------------------
Granting App Roles (so -AppOnly returns all four)

Requires Application Administrator, Cloud Application Administrator, or
Privileged Role Administrator. The "IADB Application Developer" custom role can
edit the app registration but cannot create appRoleAssignments.

    $sp  = '7511d6e0-0636-41b6-a772-73ce855b2415'   # SP: aimvp-a-np-d-api-unstructdata
    $app = 'd4296150-90e1-421e-89a0-6828b4101125'   # its application object

    $roles = (az ad app show --id $app -o json | ConvertFrom-Json).appRoles
    foreach ($role in $roles | Where-Object { $_.value -like '*.All' }) {
        $body = @{ principalId = $sp; resourceId = $sp; appRoleId = $role.id } |
            ConvertTo-Json -Compress
        $body | Set-Content "$env:TEMP\ara.json" -Encoding utf8
        az rest --method POST `
            --url "https://graph.microsoft.com/v1.0/servicePrincipals/$sp/appRoleAssignedTo" `
            --headers 'Content-Type=application/json' --body "@$env:TEMP\ara.json"
    }
--------------------------------------------------------------------------------
#>
