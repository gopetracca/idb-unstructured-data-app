#!/usr/bin/env bash
# Applies database migrations from the CD runner: pulls the image being
# deployed and runs its migration runner (alembic upgrade head) in a one-shot
# container. The runner has network access to SQL Server, so a failed
# migration fails this script and the pipeline never rolls out the revision.
#
# Mirrors the manual flow in docker-compose.dev.yml (sqlserver-migrate), using
# the connection string from SQL_SERVER_DATABASE_URL_MIGRATIONS.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  SQL_SERVER_DATABASE_URL_MIGRATIONS=<url> scripts/run_migrations_container.sh --acr <name> --image <name> --tag <tag>

Required:
  --acr <name>             Azure Container Registry name, without azurecr.io.
  --image <name>           Image repository name, without registry prefix.
  --tag <tag>              Immutable image tag to run, for example sha-7685b57.

Environment:
  SQL_SERVER_DATABASE_URL_MIGRATIONS
                           SQLAlchemy async URL (mssql+aioodbc://...) with DDL
                           rights. Forwarded to the container, never passed as
                           an argument.

Example:
  scripts/run_migrations_container.sh \
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

ACR_NAME=""
IMAGE_NAME=""
IMAGE_TAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_value "--acr" "$ACR_NAME"
require_value "--image" "$IMAGE_NAME"
require_value "--tag" "$IMAGE_TAG"

if [[ "$(printf '%s' "$IMAGE_TAG" | tr '[:upper:]' '[:lower:]')" == "latest" ]]; then
  die "refusing to run migrations from mutable tag 'latest'"
fi

[[ -n "${SQL_SERVER_DATABASE_URL_MIGRATIONS:-}" ]] \
  || die "SQL_SERVER_DATABASE_URL_MIGRATIONS must be set in the environment"

command -v az >/dev/null 2>&1 || die "Azure CLI 'az' was not found on PATH"
command -v docker >/dev/null 2>&1 || die "docker was not found on PATH"

FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

echo ""
echo "Database migrations (one-shot container on this runner)"
echo "  Image : $FULL_IMAGE"
echo ""

az acr login --name "$ACR_NAME" --output none
docker pull --quiet "$FULL_IMAGE"

# -e without a value forwards the secret from this environment; --entrypoint
# skips datadog-init/Functions host. /opt/python/3 is the image's uv-synced
# venv and the WORKDIR holds alembic.ini + src/ (see Dockerfile).
docker run --rm \
  -e SQL_SERVER_ENABLED=true \
  -e SQL_SERVER_DATABASE_URL_MIGRATIONS \
  --entrypoint /opt/python/3/bin/python \
  "$FULL_IMAGE" \
  -m src.infrastructure.sqlserver.run_migrations

echo ""
echo "Database migrations applied successfully"
