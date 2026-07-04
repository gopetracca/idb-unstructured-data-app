#!/usr/bin/env bash
# Runs database migrations as a one-shot Azure Container Apps Job execution and
# waits for it to finish. The CD pipeline calls this before deploying the new
# app revision, with the same image tag, so a failed migration blocks the
# rollout. The job itself is provisioned once per environment — see
# docs/AIA-394-database-migrations.md.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/run_migrations_job.sh --job <name> --resource-group <name> --acr <name> --image <name> --tag <tag> [options]

Required:
  --job <name>             Container Apps Job name (migrations job).
  --resource-group <name>  Azure resource group.
  --acr <name>             Azure Container Registry name, without azurecr.io.
  --image <name>           Image repository name, without registry prefix.
  --tag <tag>              Immutable image tag to run, for example sha-7685b57.

Options:
  --timeout <seconds>        Execution timeout. Default: 900.
  --poll-interval <seconds>  Execution polling interval. Default: 10.
  -h, --help                 Show this help.

Example:
  scripts/run_migrations_job.sh \
    --job caj-np-d-aimvp-migrations \
    --resource-group rg-np-d-aimvp \
    --acr acrnpdaimvpshared \
    --image aimvp-unstructured-data-app \
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

JOB_NAME=""
RESOURCE_GROUP=""
ACR_NAME=""
IMAGE_NAME=""
IMAGE_TAG=""
TIMEOUT_SECONDS=900
POLL_INTERVAL_SECONDS=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job)
      [[ $# -ge 2 ]] || die "--job requires a value"
      JOB_NAME="$2"
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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_value "--job" "$JOB_NAME"
require_value "--resource-group" "$RESOURCE_GROUP"
require_value "--acr" "$ACR_NAME"
require_value "--image" "$IMAGE_NAME"
require_value "--tag" "$IMAGE_TAG"

[[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || die "--timeout must be a positive integer"
[[ "$POLL_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || die "--poll-interval must be a positive integer"
(( TIMEOUT_SECONDS > 0 )) || die "--timeout must be greater than zero"
(( POLL_INTERVAL_SECONDS > 0 )) || die "--poll-interval must be greater than zero"

if [[ "${IMAGE_TAG,,}" == "latest" ]]; then
  die "refusing to run migrations from mutable tag 'latest'"
fi

command -v az >/dev/null 2>&1 || die "Azure CLI 'az' was not found on PATH"

FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

echo ""
echo "Database migrations (Container Apps Job)"
echo "  Job             : $JOB_NAME"
echo "  Resource group  : $RESOURCE_GROUP"
echo "  Image           : $FULL_IMAGE"
echo "  Timeout         : ${TIMEOUT_SECONDS}s"
echo ""

az containerapp job show \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --output none \
  || die "migrations job '$JOB_NAME' not found in '$RESOURCE_GROUP' — provision it once per environment (see docs/AIA-394-database-migrations.md)"

# Point the job template at the image being deployed, then start one execution.
az containerapp job update \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$FULL_IMAGE" \
  --output none

EXECUTION_NAME="$(az containerapp job start \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'name' \
  -o tsv)"

require_value "execution name returned by 'az containerapp job start'" "$EXECUTION_NAME"

echo "Execution         : $EXECUTION_NAME"
echo ""

deadline=$((SECONDS + TIMEOUT_SECONDS))
STATUS=""

while (( SECONDS < deadline )); do
  STATUS="$(az containerapp job execution show \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --job-execution-name "$EXECUTION_NAME" \
    --query 'properties.status' \
    -o tsv 2>/dev/null || true)"

  if [[ -z "$STATUS" ]]; then
    STATUS="Unknown"
  fi

  echo "Execution $EXECUTION_NAME status: $STATUS"

  case "$STATUS" in
    Succeeded)
      break
      ;;
    Failed|Stopped|Degraded)
      echo "" >&2
      echo "Migration job execution ended with status '$STATUS'." >&2
      echo "Inspect logs with:" >&2
      echo "  az containerapp job logs show --name $JOB_NAME --resource-group $RESOURCE_GROUP --execution $EXECUTION_NAME --container $JOB_NAME" >&2
      die "database migrations failed — aborting deploy"
      ;;
  esac

  sleep "$POLL_INTERVAL_SECONDS"
done

if [[ "$STATUS" != "Succeeded" ]]; then
  die "timed out after ${TIMEOUT_SECONDS}s waiting for migration execution $EXECUTION_NAME"
fi

echo ""
echo "Database migrations applied successfully"
