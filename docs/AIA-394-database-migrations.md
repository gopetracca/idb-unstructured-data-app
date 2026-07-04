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

## 1. Provisioning (Terraform, infra repository)

The Container Apps Job is an Azure resource and is **provisioned by Terraform
in the infrastructure repository**, one job per environment, alongside the
Container App. The pipeline never creates it — `scripts/run_migrations_job.sh`
fails fast with *"migrations job not found"* if it is missing, and the whole
migration step is skipped while the GitHub environment variable
`MIGRATIONS_JOB_NAME` is unset. That makes the rollout order safe:

1. Terraform creates the job in the target environment.
2. Set the GitHub **environment variable** `MIGRATIONS_JOB_NAME` (e.g.
   `caj-np-d-aimvp-migrations`) on the matching GitHub Environment
   (development / staging / production).
3. The next deploy runs migrations automatically. Environments can be
   onboarded one at a time; until then migrations stay manual
   (see `docs/AIA-424-deployment-steps.md`).

### Terraform handoff spec

What Terraform must produce (adapt naming/modules to the infra repo's
conventions — this is a spec, not a drop-in):

```hcl
resource "azurerm_container_app_job" "migrations" {
  name                         = "caj-np-d-aimvp-migrations"   # per environment
  resource_group_name          = "rg-np-d-aimvp"
  location                     = var.location
  container_app_environment_id = azurerm_container_app_environment.main.id # same env as the app

  replica_timeout_in_seconds = 1800
  replica_retry_limit        = 0

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type = "SystemAssigned"   # or the user-assigned identity used for ACR pulls
  }

  registry {
    server   = "acrnpdaimvpshared.azurecr.io"
    identity = "System"       # match how the app's registry access is wired
  }

  # DDL-rights connection string, sourced from Key Vault — do not inline.
  secret {
    name  = "sql-migrations-url"
    value = data.azurerm_key_vault_secret.sql_migrations_url.value
  }

  template {
    container {
      name   = "migrations"
      image  = "acrnpdaimvpshared.azurecr.io/aimvp-unstructured-data-app:<bootstrap-tag>"
      cpu    = 0.5
      memory = "1Gi"

      # Override the image entrypoint: datadog-init + the Functions host are
      # not needed for a migration run. WORKDIR is /home/site/wwwroot, where
      # alembic.ini and src/ live.
      command = ["/opt/python/3/bin/python"]
      args    = ["-m", "src.infrastructure.sqlserver.run_migrations"]

      env {
        name  = "SQL_SERVER_ENABLED"
        value = "true"
      }
      env {
        name        = "SQL_SERVER_DATABASE_URL_MIGRATIONS"
        secret_name = "sql-migrations-url"
      }
    }
  }

  # The CD pipeline retargets the image on every deploy
  # (az containerapp job update --image); Terraform must not fight it.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}
```

Notes:

- The migrations URL should use a login with DDL rights; the app's runtime
  connection string then no longer needs them.
- The RBAC role `AcrPull` on the registry is required for the job's identity
  (mirror whatever the Container App uses today).
- `<bootstrap-tag>` only matters until the first pipeline run; after that the
  pipeline keeps the image current and Terraform ignores it.

For reference, the equivalent one-shot `az` command (what the Terraform above
encodes) is:

```bash
az containerapp job create \
  --name caj-np-d-aimvp-migrations \
  --resource-group rg-np-d-aimvp \
  --environment <container-apps-environment-name> \
  --trigger-type Manual \
  --replica-timeout 1800 \
  --replica-retry-limit 0 \
  --parallelism 1 \
  --replica-completion-count 1 \
  --cpu 0.5 --memory 1.0Gi \
  --image acrnpdaimvpshared.azurecr.io/aimvp-unstructured-data-app:<tag> \
  --command "/opt/python/3/bin/python" \
  --args "-m" "src.infrastructure.sqlserver.run_migrations" \
  --registry-server acrnpdaimvpshared.azurecr.io \
  --registry-identity system \
  --secrets "sql-migrations-url=<mssql+aioodbc:// url with DDL rights>" \
  --env-vars \
      "SQL_SERVER_ENABLED=true" \
      "SQL_SERVER_DATABASE_URL_MIGRATIONS=secretref:sql-migrations-url"
```

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
