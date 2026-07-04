# AIA-394 — Database Migrations in the CD Pipeline

Alembic migrations run **once per deploy, as a step of the CD pipeline** — not
at container startup. The workflow pulls the exact image about to be deployed
and runs its migration runner in a one-shot container on the GitHub Actions
runner (which has network access to SQL Server). The app revision is only
rolled out after the migration container exits successfully.

```
CI (tests) ──► build & push image ──► Run database migrations ──► Deploy Container App revision
                                        │ non-zero exit
                                        └────────► pipeline stops, old revision keeps serving
```

Design notes:

- **Same image as the deploy**: migration code, ODBC Driver 18 and
  dependencies are exactly what ships — no separate environment to drift.
  This mirrors the manual flow used until now (`docker-compose.dev.yml`,
  service `sqlserver-migrate`).
- **Not at container startup**: with multiple replicas every start (including
  scale-out) would re-run the runner and couple app boot to DDL permissions.
- **Concurrency guard**: the runner
  (`src/infrastructure/sqlserver/run_migrations.py`) takes a `sp_getapplock`
  application lock, so a pipeline run racing a manual run serializes instead
  of migrating concurrently.
- **Separate credentials**: the step uses
  `SQL_SERVER_DATABASE_URL_MIGRATIONS` (a DDL-capable login, e.g.
  `oper_ai_deployer`); the app runtime keeps its own least-privilege URL.
- An alternative implementation that runs migrations as an Azure Container
  Apps Job inside the environment network (for infra where the runner cannot
  reach SQL Server) is preserved on branch
  `feature/AIA-394-aca-job-migrations`.

---

## 1. Setup (once per environment)

Add the secret `SQL_SERVER_DATABASE_URL_MIGRATIONS` to the matching GitHub
Environment (development / staging / production): the SQLAlchemy async URL
(`mssql+aioodbc://...`) of a login with DDL rights on the target database.

While the secret is unset, the pipeline skips the migration step, so
environments can be onboarded one at a time.

## 2. What the pipeline does per deploy

`scripts/run_migrations_container.sh` (called by
`.github/workflows/continuous-deployment-container-apps.yml` before the deploy
step):

1. `az acr login` + `docker pull` of the image tag being deployed.
2. `docker run --rm -e SQL_SERVER_ENABLED=true -e SQL_SERVER_DATABASE_URL_MIGRATIONS
   --entrypoint /opt/python/3/bin/python <image> -m src.infrastructure.sqlserver.run_migrations`
   — the secret is forwarded via the environment, never as an argument.
3. A non-zero container exit fails the workflow; the deploy step never runs.

Migration logs stream inline in the Actions job output.

## 3. Running manually

Same as before via docker compose (uses `.env.dev`):

```bash
docker compose -f docker-compose.dev.yml up sqlserver-migrate
```

Or with the pipeline script from a workstation that has `az` + `docker`:

```bash
export SQL_SERVER_DATABASE_URL_MIGRATIONS='mssql+aioodbc://...'
scripts/run_migrations_container.sh \
  --acr acrnpdaimvpshared \
  --image aimvp-unstructured-data-app \
  --tag <tag>
```

Local development keeps using alembic directly:

```bash
uv run alembic upgrade head
```

## 4. Rollback

Migrations are expected to be backward-compatible (expand/contract). To roll
back a bad migration, run `alembic downgrade <revision>` manually against the
migrations URL — the pipeline never downgrades automatically.
