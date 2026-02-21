# `databricks.yml` Variables and Multi-Target Configuration

How to structure `databricks.yml` to avoid hardcoded values and support multiple deployment environments, each pointing to a different workspace.

---

## Core Principle: Declare Variables, Override in Targets

```
variables:              ← Declare all variables here with descriptions and optional defaults
  catalog:
    description: ...
    default: my_catalog  ← Used by dev target automatically if not overridden

targets:
  dev:
    variables:           ← Override variable values for this specific target
      catalog: dev_catalog
  prod:
    variables:
      catalog: prod_catalog
```

Variables can be passed at deploy time via `--var` on the CLI (useful for secrets or CI-injected values), or set as defaults in the target definition.

---

## Complete `databricks.yml` Template

```yaml
# databricks.yml
bundle:
  name: <your_bundle_name>
  uuid: <generated-uuid>   # Generate with: python -c "import uuid; print(uuid.uuid4())"

include:
  - resources/*.yml
  - resources/*/*.yml

# If your bundle builds a Python wheel:
artifacts:
  python_artifact:
    type: whl
    build: uv build --wheel

# ============================================================
# VARIABLE DECLARATIONS
# All environment-specific values live here, not hardcoded.
# ============================================================
variables:
  catalog:
    description: Unity Catalog catalog name for this deployment
    default: my_catalog          # Used when not overridden in target

  schema:
    description: Schema name within the catalog
    default: default

  service_principal_id:
    description: Application (Client) UUID of the service principal (passed from CI via --var)
    # No default — must be provided at deploy time

  admin_user_email:
    description: Email of the admin user for CAN_MANAGE permissions in prod
    # No default — must be provided at deploy time for prod

# ============================================================
# TARGETS
# One target per deployment environment.
# workspace.host is intentionally NOT set here — it is provided
# via DATABRICKS_HOST environment variable in the CI pipeline,
# so different GitHub environments point to different workspaces.
# ============================================================
targets:

  dev:
    mode: development
    default: true               # Used when no --target is specified locally

    run_as:
      service_principal_name: ${var.service_principal_id}

    presets:
      name_prefix: "${workspace.current_user.short_name}_"
      pipelines_development: true
      trigger_pause_status: PAUSED
      jobs_max_concurrent_runs: 10
      tags:
        env: dev
        team: data-engineering

    workspace:
      # host is NOT set here — comes from DATABRICKS_HOST env var in GitHub Actions
      root_path: ~/Shared/.bundle/${bundle.name}/${bundle.target}

    variables:
      catalog: my_catalog_dev
      schema: dev

    resources:
      schemas:
        dev_schema:
          name: ${var.schema}
          catalog_name: ${var.catalog}
          comment: "Schema for development environment"

  staging:
    mode: production            # Use production mode even for staging (no dev prefixes)

    run_as:
      service_principal_name: ${var.service_principal_id}

    presets:
      name_prefix: "staging_"
      pipelines_development: false
      trigger_pause_status: PAUSED  # Keep paused in staging unless explicitly unpaused
      tags:
        env: staging
        team: data-engineering

    workspace:
      root_path: ~/Shared/.bundle/${bundle.name}/${bundle.target}

    variables:
      catalog: my_catalog
      schema: staging

    resources:
      schemas:
        staging_schema:
          name: ${var.schema}
          catalog_name: ${var.catalog}
          comment: "Schema for staging environment"

  prod:
    mode: production

    run_as:
      service_principal_name: ${var.service_principal_id}

    presets:
      name_prefix: "prod_"
      pipelines_development: false
      trigger_pause_status: UNPAUSED  # Schedules are active in prod
      jobs_max_concurrent_runs: 1
      tags:
        env: prod
        team: data-engineering

    workspace:
      root_path: ~/Shared/.bundle/${bundle.name}/${bundle.target}

    variables:
      catalog: my_catalog
      schema: prod

    resources:
      schemas:
        prod_schema:
          name: ${var.schema}
          catalog_name: ${var.catalog}
          comment: "Schema for production environment"

    permissions:
      - user_name: ${var.admin_user_email}
        level: CAN_MANAGE
```

---

## How `workspace.host` Works Without Hardcoding

The Databricks CLI resolves the workspace in this order:

1. `workspace.host` in `databricks.yml` (hardcoded — avoid this for multi-env)
2. `DATABRICKS_HOST` environment variable ← **Use this in GitHub Actions**
3. Default profile in `~/.databrickscfg`

By **not** setting `workspace.host` in `databricks.yml` and **setting** `DATABRICKS_HOST` in each GitHub environment, you get:

- Dev workflow runs → `DATABRICKS_HOST=https://dev.azuredatabricks.net` → deploys to dev workspace
- Prod workflow runs → `DATABRICKS_HOST=https://prod.azuredatabricks.net` → deploys to prod workspace
- Same `databricks.yml`, different workspaces, zero hardcoded URLs

---

## Passing Variables: Three Methods

### Method 1: Default values in `databricks.yml` (for non-sensitive, stable config)

```yaml
variables:
  catalog:
    default: my_catalog   # Applied automatically unless overridden
```

### Method 2: Target-level overrides in `databricks.yml` (for per-environment config)

```yaml
targets:
  prod:
    variables:
      catalog: my_catalog_prod
      schema: prod
```

### Method 3: `--var` flag at deploy time (for CI-injected secrets/dynamic values)

```bash
# In GitHub Actions workflow:
databricks bundle deploy --target prod \
  --var="service_principal_id=${{ secrets.DATABRICKS_CLIENT_ID }}" \
  --var="admin_user_email=${{ vars.ADMIN_USER_EMAIL }}"
```

**When to use each method:**

| Value type | Recommended method |
|------------|-------------------|
| Stable, non-sensitive (catalog name, schema) | Target-level override in `databricks.yml` |
| Sensitive (SP ID, token) | `--var` from CI secrets |
| Dynamic (workspace host) | `DATABRICKS_HOST` env var (not `--var`) |
| Shared across all targets | Variable default in `variables:` section |

---

## Variable Reference Syntax

Inside `databricks.yml` resources and settings:

```yaml
# Reference a declared variable
name: ${var.catalog}

# Reference workspace context (built-in, not declared as variables)
name_prefix: "${workspace.current_user.short_name}_"
root_path: ~/Shared/.bundle/${bundle.name}/${bundle.target}

# Reference bundle metadata
name: "${bundle.name}-${bundle.target}-job"
```

---

## Example: Job Resource Using Variables

```yaml
# resources/jobs/my_job.yml
resources:
  jobs:
    my_etl_job:
      name: "${bundle.name}-etl-${bundle.target}"
      
      tasks:
        - task_key: main_task
          notebook_task:
            notebook_path: ../src/notebooks/etl_main
            base_parameters:
              catalog: ${var.catalog}
              schema: ${var.schema}
          
          job_cluster_key: main_cluster

      job_clusters:
        - job_cluster_key: main_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: Standard_DS3_v2
            num_workers: 2
            spark_conf:
              spark.databricks.delta.preview.enabled: "true"
```

---

## Adding a New Environment: Checklist

When adding a new environment (e.g., `staging`):

**In `databricks.yml`:**
- [ ] Add a new `targets.staging:` block with `mode`, `run_as`, `presets`, `variables`
- [ ] Set environment-specific variable overrides (catalog, schema)
- [ ] Do NOT set `workspace.host` — let it come from env var

**In GitHub:**
- [ ] Create a new GitHub Environment named `Staging` (Settings > Environments)
- [ ] Add `DATABRICKS_HOST` variable pointing to the staging workspace URL
- [ ] Add `DATABRICKS_CLIENT_ID` secret with the staging SP UUID

**In `.github/workflows/`:**
- [ ] Create `deploy_staging.yml`
- [ ] Set `on.push.branches: [staging]`
- [ ] Set `environment: Staging`
- [ ] Add validate step before deploy
- [ ] Pass any required `--var` values
