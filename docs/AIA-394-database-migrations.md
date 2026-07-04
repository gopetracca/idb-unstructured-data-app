# AIA-394 — Database Migrations in the CD Pipeline

Alembic migrations run **once per deploy** as a step of the CD pipeline, not at
container startup. The pipeline triggers a one-shot **Azure Container Apps Job**
that runs `alembic upgrade head` with the exact image about to be deployed, and
the app revision is only rolled out after the job execution succeeds.

```
CI (tests) ──► build & push image ──► migrations job (this doc) ──► deploy revision
                                        │ Failed/timeout
                                        └────────► pipeline stops, old revision keeps running
```

Why a Container Apps Job instead of running alembic on the GitHub runner:

- The GitHub-hosted runner has no network path to SQL Server and the pipeline
  holds no database credentials — all data-plane config lives on Azure
  resources. The job runs inside the same Container Apps environment (same
  VNet/egress) with its own secrets.
- The job reuses the application image, so the migration code, ODBC driver and
  dependencies are exactly what is being deployed.

Why not at container startup: with multiple replicas every start (including
scale-out) would re-run the runner and couple app boot to DDL permissions.
The runner itself (`src/infrastructure/sqlserver/run_migrations.py`) still
takes a `sp_getapplock` application lock, so a pipeline run racing a manual
run serializes instead of migrating concurrently.

---

## 1. One-time provisioning (per environment)

Create the job next to the Container App (adjust names per environment):

```bash
ACR=acrnpdaimvpshared
RG=rg-np-d-aimvp
ACA_ENV=<container-apps-environment-name>   # same environment as the app
JOB=caj-np-d-aimvp-migrations
IMAGE=$ACR.azurecr.io/aimvp-unstructured-data-app:<current-tag>

az containerapp job create \
  --name "$JOB" \
  --resource-group "$RG" \
  --environment "$ACA_ENV" \
  --trigger-type Manual \
  --replica-timeout 1800 \
  --replica-retry-limit 0 \
  --parallelism 1 \
  --replica-completion-count 1 \
  --cpu 0.5 --memory 1.0Gi \
  --image "$IMAGE" \
  --command "/opt/python/3/bin/python" \
  --args "-m" "src.infrastructure.sqlserver.run_migrations" \
  --registry-server "$ACR.azurecr.io" \
  --registry-identity system \
  --secrets "sql-migrations-url=<mssql+aioodbc:// url with DDL rights>" \
  --env-vars \
      "SQL_SERVER_ENABLED=true" \
      "SQL_SERVER_DATABASE_URL_MIGRATIONS=secretref:sql-migrations-url"
```

Notes:

- `--command` overrides the image entrypoint (datadog-init + Functions host is
  not needed for a migration run); the image `WORKDIR` is `/home/site/wwwroot`,
  where `alembic.ini` and `src/` live.
- The migrations URL may use a login with DDL rights; the app's runtime
  connection string then no longer needs them.
- If the registry is attached with a user-assigned identity, replace
  `--registry-identity system` accordingly.

Then set the GitHub **environment variable** `MIGRATIONS_JOB_NAME` (e.g.
`caj-np-d-aimvp-migrations`) on the matching GitHub Environment (development /
staging / production). While the variable is unset the pipeline skips the
migration step, so environments can be onboarded one at a time.

## 2. What the pipeline does per deploy

`scripts/run_migrations_job.sh` (called by
`.github/workflows/continuous-deployment-container-apps.yml`):

1. `az containerapp job update --image <new tag>` — points the job at the
   image being deployed.
2. `az containerapp job start` — starts one execution.
3. Polls `az containerapp job execution show` until `Succeeded`
   (`Failed`/`Stopped`/timeout fails the pipeline and the deploy never runs).

## 3. Running manually

From a workstation with `az` access (e.g. hotfix or first-time backfill):

```bash
scripts/run_migrations_job.sh \
  --job caj-np-d-aimvp-migrations \
  --resource-group rg-np-d-aimvp \
  --acr acrnpdaimvpshared \
  --image aimvp-unstructured-data-app \
  --tag <tag>
```

Logs of a given execution:

```bash
az containerapp job logs show \
  --name caj-np-d-aimvp-migrations \
  --resource-group rg-np-d-aimvp \
  --execution <execution-name> \
  --container caj-np-d-aimvp-migrations
```

Local development keeps using alembic directly:

```bash
uv run alembic upgrade head
```

## 4. Rollback

Migrations are expected to be backward-compatible (expand/contract). To roll
back a bad migration, run `alembic downgrade <revision>` manually against the
migrations URL — the pipeline never downgrades automatically.
