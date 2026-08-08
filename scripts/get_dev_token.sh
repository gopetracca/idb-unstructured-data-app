#!/usr/bin/env bash
# Mint a bearer token for the Unstructured Data API (client-credentials flow).
#
# Returns an app-only token carrying the `roles` claim — whatever App Roles the
# service principal is *assigned*. It cannot produce `scp`: delegated scopes are
# only issued when a user is in the flow.
#
# For a token carrying all four delegated scopes, use the PowerShell script,
# which runs the interactive authorization-code flow:
#
#     ./scripts/get_dev_token.ps1 -Decode
#
# Usage:
#     export AIMVP_API_CLIENT_SECRET=$(az keyvault secret show --vault-name <kv> \
#         --name sec-aimvp-a-api-unstructdata --query value -o tsv)
#     TOKEN=$(./scripts/get_dev_token.sh)
#     curl -H "Authorization: Bearer $TOKEN" "$API/api/v1/capabilities"
#
#     ./scripts/get_dev_token.sh --decode     # print claims instead

set -euo pipefail

CLIENT_ID="${AIMVP_API_CLIENT_ID:-bd03bba6-51e7-4316-84d6-634e182decb2}"
TENANT_ID="${AIMVP_API_TENANT_ID:-9dfb1a05-5f1d-449a-8960-62abcb479e7d}"
SECRET="${AIMVP_API_CLIENT_SECRET:-}"
DECODE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --decode)     DECODE=true; shift ;;
    --client-id)  CLIENT_ID="$2"; shift 2 ;;
    --tenant-id)  TENANT_ID="$2"; shift 2 ;;
    -h|--help)    sed -n '2,22p' "$0"; exit 0 ;;
    *)            echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SECRET" ]; then
  cat >&2 <<'EOF'
No client secret. Set it from Key Vault first:

  export AIMVP_API_CLIENT_SECRET=$(az keyvault secret show --vault-name <kv> \
      --name sec-aimvp-a-api-unstructdata --query value -o tsv)
EOF
  exit 1
fi

response=$(curl -sS -X POST \
  "https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${SECRET}" \
  -d "scope=api://${CLIENT_ID}/.default")

token=$(printf '%s' "$response" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

if [ -z "$token" ]; then
  echo "Token request failed:" >&2
  printf '%s\n' "$response" >&2
  exit 1
fi

if [ "$DECODE" = true ]; then
  payload=$(printf '%s' "$token" | cut -d. -f2 | tr '_-' '/+')
  case $(( ${#payload} % 4 )) in
    2) payload="${payload}==" ;;
    3) payload="${payload}=" ;;
  esac
  printf '%s' "$payload" | base64 -d 2>/dev/null | tr ',' '\n' \
    | grep -E '"(aud|iss|ver|azp|appid|roles|scp|oid|tid)"' || true
  echo
fi

printf '%s\n' "$token"
