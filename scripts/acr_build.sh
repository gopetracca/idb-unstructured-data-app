#!/usr/bin/env bash
# Builds and pushes the container image to ACR using a server-side build.
#
# Linux equivalent of scripts/acr_build.ps1.
# Uses 'az acr build' — no local Docker daemon or docker push needed.
# Relies on .acrignore at repo root to keep the build context small.
#
# Prerequisites:
#   - az CLI installed and logged in ('az login' or OIDC in CI)
#   - Contributor or AcrPush role on the ACR
#   - uv.lock present in repo root (run 'uv lock' if missing)
#
# Usage:
#   ./scripts/acr_build.sh [OPTIONS]
#
# Options:
#   --registry <name>        ACR name            (default: acrnpdaimvpshared)
#   --image    <name>        Image name           (default: aimvp-unnstructured-data-app)
#   --target   <stage>       Dockerfile stage     (default: runtime)
#   --tags     <t1,t2,...>   Comma-separated tags (default: latest)
#
# Examples:
#   ./scripts/acr_build.sh
#   ./scripts/acr_build.sh --tags sha-7685b57
#   ./scripts/acr_build.sh --tags sha-abc1234,v1.2.3,latest

set -euo pipefail

# ---------------------------------------------------------------------------
# Git SHA tag (short commit, falls back to 'unknown' in detached/no-git envs)
# ---------------------------------------------------------------------------
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
ACR_NAME="acrnpdaimvpshared"
IMAGE_NAME="aimvp-unnstructured-data-app"
TARGET="runtime"
TAGS="sha-${GIT_SHA},latest"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --registry) ACR_NAME="$2";  shift 2 ;;
    --image)    IMAGE_NAME="$2"; shift 2 ;;
    --target)   TARGET="$2";    shift 2 ;;
    --tags)     TAGS="$2";      shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve repo root (script lives in scripts/)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "ACR server-side build"
echo "  Registry : $ACR_NAME"
echo "  Image    : $IMAGE_NAME"
echo "  Tags     : $TAGS"
echo "  Stage    : $TARGET"
echo "  Context  : $REPO_ROOT"
echo ""

# ---------------------------------------------------------------------------
# Build --image flags from comma-separated tags
# ---------------------------------------------------------------------------
IMAGE_FLAGS=()
IFS=',' read -ra TAG_LIST <<< "$TAGS"
for TAG in "${TAG_LIST[@]}"; do
  TAG="${TAG// /}"  # strip whitespace
  [[ -z "$TAG" ]] && continue
  IMAGE_FLAGS+=(--image "${IMAGE_NAME}:${TAG}")
done

if [[ ${#IMAGE_FLAGS[@]} -eq 0 ]]; then
  echo "Error: no tags resolved from: $TAGS" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Run az acr build from repo root (.acrignore handles upload exclusions)
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"

az acr build \
  --registry  "$ACR_NAME" \
  "${IMAGE_FLAGS[@]}" \
  --target    "$TARGET" \
  --build-arg INSTALL_IADB_CA=false \
  --build-arg IADB_ROOT_CA_FILE=.docker/empty-iadb-root-ca.crt \
  .

echo ""
echo "Build complete:"
for TAG in "${TAG_LIST[@]}"; do
  TAG="${TAG// /}"
  [[ -z "$TAG" ]] && continue
  echo "  ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${TAG}"
done
