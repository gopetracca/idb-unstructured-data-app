#!/usr/bin/env bash
# Deploys an already-built ACR image to Azure Container Apps and verifies that
# Azure creates and provisions a new revision.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/deploy_container_app.sh --app <name> --resource-group <name> --acr <name> --image <name> --tag <tag> [options]

Required:
  --app <name>             Azure Container App name.
  --resource-group <name>  Azure resource group.
  --acr <name>             Azure Container Registry name, without azurecr.io.
  --image <name>           Image repository name, without registry prefix.
  --tag <tag>              Immutable image tag to deploy, for example sha-7685b57 or v1.2.3.

Options:
  --timeout <seconds>          Provisioning timeout. Default: 600.
  --poll-interval <seconds>    Revision polling interval. Default: 10.
  --revision-suffix <suffix>   Override the generated revision suffix.
  --allow-latest               Allow deploying the latest tag. Disabled by default.
  -h, --help                   Show this help.

Examples:
  scripts/deploy_container_app.sh \
    --app ca-np-d-aimvp-unstructdata \
    --resource-group rg-np-d-aimvp \
    --acr acrnpdaimvpshared \
    --image aimvp-unnstructured-data-app \
    --tag sha-7685b57
USAGE
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_value() {
  local option_name="$1"
  local option_value="$2"

  if [[ -z "$option_value" ]]; then
    die "$option_name is required"
  fi
}

sanitize_revision_suffix() {
  local raw_suffix="$1"
  local app_name="$2"
  local suffix
  local max_suffix_length

  suffix="$(printf '%s' "$raw_suffix" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9-]+/-/g; s/-+/-/g; s/^-+//; s/-+$//')"

  if [[ -z "$suffix" ]]; then
    suffix="revision"
  fi

  if [[ ! "$suffix" =~ ^[a-z] ]]; then
    suffix="r-$suffix"
  fi

  # Azure revision names are derived as <container-app-name>--<suffix>.
  max_suffix_length=$((63 - ${#app_name} - 2))
  if (( max_suffix_length < 1 )); then
    die "container app name is too long to generate a revision suffix safely"
  fi

  if (( ${#suffix} > max_suffix_length )); then
    suffix="${suffix:0:max_suffix_length}"
    suffix="$(printf '%s' "$suffix" | sed -E 's/-+$//')"
  fi

  suffix="$(printf '%s' "$suffix" | sed -E 's/[^a-z0-9]+$//')"
  if [[ -z "$suffix" || ! "$suffix" =~ ^[a-z] ]]; then
    suffix="r"
  fi

  printf '%s' "$suffix"
}

CONTAINER_APP_NAME=""
RESOURCE_GROUP=""
ACR_NAME=""
IMAGE_NAME=""
IMAGE_TAG=""
REVISION_SUFFIX=""
TIMEOUT_SECONDS=600
POLL_INTERVAL_SECONDS=10
ALLOW_LATEST=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      [[ $# -ge 2 ]] || die "--app requires a value"
      CONTAINER_APP_NAME="$2"
      shift 2
      ;;
    --resource-group)
      [[ $# -ge 2 ]] || die "--resource-group requires a value"
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --acr)
      [[ $# -ge 2 ]] || die "--acr requires a value"
      ACR_NAME="$2"
      shift 2
      ;;
    --image)
      [[ $# -ge 2 ]] || die "--image requires a value"
      IMAGE_NAME="$2"
      shift 2
      ;;
    --tag)
      [[ $# -ge 2 ]] || die "--tag requires a value"
      IMAGE_TAG="$2"
      shift 2
      ;;
    --timeout)
      [[ $# -ge 2 ]] || die "--timeout requires a value"
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --poll-interval)
      [[ $# -ge 2 ]] || die "--poll-interval requires a value"
      POLL_INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --revision-suffix)
      [[ $# -ge 2 ]] || die "--revision-suffix requires a value"
      REVISION_SUFFIX="$2"
      shift 2
      ;;
    --allow-latest)
      ALLOW_LATEST=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_value "--app" "$CONTAINER_APP_NAME"
require_value "--resource-group" "$RESOURCE_GROUP"
require_value "--acr" "$ACR_NAME"
require_value "--image" "$IMAGE_NAME"
require_value "--tag" "$IMAGE_TAG"

[[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || die "--timeout must be a positive integer"
[[ "$POLL_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || die "--poll-interval must be a positive integer"
(( TIMEOUT_SECONDS > 0 )) || die "--timeout must be greater than zero"
(( POLL_INTERVAL_SECONDS > 0 )) || die "--poll-interval must be greater than zero"

if [[ "${IMAGE_TAG,,}" == "latest" && "$ALLOW_LATEST" != true ]]; then
  die "refusing to deploy mutable tag 'latest'; pass --allow-latest to override"
fi

command -v az >/dev/null 2>&1 || die "Azure CLI 'az' was not found on PATH"

if [[ -z "$REVISION_SUFFIX" ]]; then
  REVISION_SUFFIX="$(sanitize_revision_suffix "$IMAGE_TAG" "$CONTAINER_APP_NAME")"
else
  REVISION_SUFFIX="$(sanitize_revision_suffix "$REVISION_SUFFIX" "$CONTAINER_APP_NAME")"
fi

FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

echo ""
echo "Container App deployment"
echo "  App             : $CONTAINER_APP_NAME"
echo "  Resource group  : $RESOURCE_GROUP"
echo "  Image           : $FULL_IMAGE"
echo "  Revision suffix : $REVISION_SUFFIX"
echo "  Timeout         : ${TIMEOUT_SECONDS}s"
echo ""

OLD_IMAGE="$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'properties.template.containers[0].image' \
  -o tsv)"

OLD_REVISION="$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'properties.latestRevisionName' \
  -o tsv)"

ACTIVE_REVISIONS_MODE="$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'properties.configuration.activeRevisionsMode' \
  -o tsv)"

echo "Previous image    : ${OLD_IMAGE:-<none>}"
echo "Previous revision : ${OLD_REVISION:-<none>}"
echo "Traffic mode      : ${ACTIVE_REVISIONS_MODE:-<unknown>}"
echo ""

az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$FULL_IMAGE" \
  --revision-suffix "$REVISION_SUFFIX" \
  --set-env-vars "DD_VERSION=$IMAGE_TAG" \
  --output none

LATEST_REVISION="$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'properties.latestRevisionName' \
  -o tsv)"

require_value "latest revision name returned by Azure" "$LATEST_REVISION"

if [[ -n "$OLD_REVISION" && "$LATEST_REVISION" == "$OLD_REVISION" ]]; then
  die "Container App latest revision did not change after update; refusing to report success for a no-op deploy"
fi

echo "Latest revision   : $LATEST_REVISION"
echo ""

deadline=$((SECONDS + TIMEOUT_SECONDS))
PROVISIONING_STATE=""

while (( SECONDS < deadline )); do
  PROVISIONING_STATE="$(az containerapp revision show \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --revision "$LATEST_REVISION" \
    --query 'properties.provisioningState' \
    -o tsv 2>/dev/null || true)"

  if [[ -z "$PROVISIONING_STATE" ]]; then
    PROVISIONING_STATE="Unknown"
  fi

  echo "Revision $LATEST_REVISION provisioning state: $PROVISIONING_STATE"

  case "$PROVISIONING_STATE" in
    Provisioned)
      break
      ;;
    Failed)
      die "revision $LATEST_REVISION provisioning failed"
      ;;
  esac

  sleep "$POLL_INTERVAL_SECONDS"
done

if [[ "$PROVISIONING_STATE" != "Provisioned" ]]; then
  die "timed out after ${TIMEOUT_SECONDS}s waiting for revision $LATEST_REVISION to provision"
fi

NEW_IMAGE="$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'properties.template.containers[0].image' \
  -o tsv)"

TRAFFIC_WEIGHTS="$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'properties.configuration.ingress.traffic' \
  -o json)"

echo ""
echo "Deployment verified"
echo "  Old image          : ${OLD_IMAGE:-<none>}"
echo "  New image          : ${NEW_IMAGE:-<none>}"
echo "  Latest revision    : $LATEST_REVISION"
echo "  Provisioning state : $PROVISIONING_STATE"
echo "  Traffic mode       : ${ACTIVE_REVISIONS_MODE:-<unknown>}"
echo "  Traffic weights    : ${TRAFFIC_WEIGHTS:-[]}"
