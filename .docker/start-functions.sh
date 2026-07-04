#!/bin/sh
set -eu

# AIA-394: apply database migrations before the Functions host starts.
# Enabled per-environment by the CD pipeline (deploy_container_app --run-migrations).
# The runner holds a SQL Server app lock, so concurrent replicas serialize; a
# migration failure aborts startup, the startup probe fails, and the deploy
# script reports the revision as failed instead of routing traffic to it.
if [ "${RUN_DB_MIGRATIONS_ON_STARTUP:-false}" = "true" ]; then
  echo "[startup] RUN_DB_MIGRATIONS_ON_STARTUP=true — running alembic upgrade head"
  uv run --no-dev python -m src.infrastructure.sqlserver.run_migrations
fi

exec uv run --no-dev /opt/startup/start_nonappservice.sh
