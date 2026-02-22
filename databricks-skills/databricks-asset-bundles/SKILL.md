-----

## name: databricks-asset-bundles
description: “Create and configure Databricks Asset Bundles (DABs) with best practices for multi-environment deployments. Use when working with: (1) Creating new DAB projects, (2) Adding resources (dashboards, pipelines, jobs, alerts), (3) Configuring multi-environment deployments, (4) Setting up permissions, (5) Deploying or running bundle resources, (6) Creating GitHub Actions CI/CD pipelines for DAB deployment, (7) Setting up OIDC authentication with GitHub Environments, (8) Automating bundle validate and deploy across dev/staging/prod”

# Databricks Asset Bundle (DABs) Writer

## Overview

Create DABs for multi-environment deployment (dev/staging/prod).

## Reference Files

- **<SDP_guidance.md>** - Spark Declarative Pipeline configurations
- **<alerts_guidance.md>** - SQL Alert schemas (critical - API differs)
- **<cicd_workflows.md>** - GitHub Actions workflow examples (2-env, 3-env, PR validate)
- **<cicd_variables.md>** - databricks.yml variables pattern for CI/CD

## Bundle Structure

```
project/
├── databricks.yml           # Main config + targets
├── resources/*.yml          # Resource definitions
└── src/                     # Code/dashboard files
```

### Main Configuration (databricks.yml)

```yaml
bundle:
  name: project-name

include:
  - resources/*.yml

variables:
  catalog:
    default: "default_catalog"
  schema:
    default: "default_schema"
  warehouse_id:
    lookup:
      warehouse: "Shared SQL Warehouse"

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: dev-profile
    variables:
      catalog: "dev_catalog"
      schema: "dev_schema"

  prod:
    mode: production
    workspace:
      profile: prod-profile
    variables:
      catalog: "prod_catalog"
      schema: "prod_schema"
```

### Dashboard Resources

**Support for dataset_catalog and dataset_schema parameters added in Databricks CLI 0.281.0  (January 2026)**

```yaml
resources:
  dashboards:
    dashboard_name:
      display_name: "[${bundle.target}] Dashboard Title"
      file_path: ../src/dashboards/dashboard.lvdash.json  # Relative to resources/
      warehouse_id: ${var.warehouse_id}
      dataset_catalog: ${var.catalog} # Default catalog used by all datasets in the dashboard if not otherwise specified in the query
      dataset_schema: ${var.schema} # Default schema used by all datasets in the dashboard if not otherwise specified in the query
      permissions:
        - level: CAN_RUN
          group_name: "users"
```

**Permission levels**: `CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE`

### Pipelines

**See <SDP_guidance.md>** for pipeline configuration

### SQL Alerts

**See <alerts_guidance.md>** - Alert schema differs significantly from other resources

### Jobs Resources

```yaml
resources:
  jobs:
    job_name:
      name: "[${bundle.target}] Job Name"
      tasks:
        - task_key: "main_task"
          notebook_task:
            notebook_path: ../src/notebooks/main.py  # Relative to resources/
          new_cluster:
            spark_version: "13.3.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2
      schedule:
        quartz_cron_expression: "0 0 9 * * ?"
        timezone_id: "America/Los_Angeles"
      permissions:
        - level: CAN_VIEW
          group_name: "users"
```

**Permission levels**: `CAN_VIEW`, `CAN_MANAGE_RUN`, `CAN_MANAGE`

⚠️ **Cannot modify “admins” group permissions** on jobs - verify custom groups exist before use

### Path Resolution

⚠️ **Critical**: Paths depend on file location:

|File Location           |Path Format |Example                      |
|------------------------|------------|-----------------------------|
|`resources/*.yml`       |`../src/...`|`../src/dashboards/file.json`|
|`databricks.yml` targets|`./src/...` |`./src/dashboards/file.json` |

**Why**: `resources/` files are one level deep, so use `../` to reach bundle root. `databricks.yml` is at root, so use `./`

### Volume Resources

```yaml
resources:
  volumes:
    my_volume:
      catalog_name: ${var.catalog}
      schema_name: ${var.schema}
      name: "volume_name"
      volume_type: "MANAGED"
```

⚠️ **Volumes use `grants` not `permissions`** - different format from other resources

### Apps Resources

**Apps resource support added in Databricks CLI 0.239.0 (January 2025)**

Apps in DABs have a minimal configuration - environment variables are defined in `app.yaml` in the source directory, NOT in databricks.yml.

#### Generate from Existing App (Recommended)

```bash
# Generate bundle config from existing CLI-deployed app
databricks bundle generate app --existing-app-name my-app --key my_app --profile DEFAULT

# This creates:
# - resources/my_app.app.yml (minimal resource definition)
# - src/app/ (downloaded source files including app.yaml)
```

#### Manual Configuration

**resources/my_app.app.yml:**

```yaml
resources:
  apps:
    my_app:
      name: my-app-${bundle.target}        # Environment-specific naming
      description: "My application"
      source_code_path: ../src/app         # Relative to resources/ dir
```

**src/app/app.yaml:** (Environment variables go here)

```yaml
command:
  - "python"
  - "dash_app.py"

env:
  - name: USE_MOCK_BACKEND
    value: "false"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: DATABRICKS_CATALOG
    value: "main"
  - name: DATABRICKS_SCHEMA
    value: "my_schema"
```

**databricks.yml:**

```yaml
bundle:
  name: my-bundle

include:
  - resources/*.yml

variables:
  warehouse_id:
    default: "default-warehouse-id"

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: dev-profile
    variables:
      warehouse_id: "dev-warehouse-id"
```

#### Key Differences from Other Resources

|Aspect              |Apps                             |Other Resources                   |
|--------------------|---------------------------------|----------------------------------|
|**Environment vars**|In `app.yaml` (source dir)       |In databricks.yml or resource file|
|**Configuration**   |Minimal (name, description, path)|Extensive (tasks, clusters, etc.) |
|**Source path**     |Points to app directory          |Points to specific files          |

⚠️ **Important**: When source code is in project root (not src/app), use `source_code_path: ..` in the resource file

### Other Resources

DABs supports schemas, models, experiments, clusters, warehouses, etc. Use `databricks bundle schema` to inspect schemas.

**Reference**: [DABs Resource Types](https://docs.databricks.com/dev-tools/bundles/resources)

## Common Commands

### Validation

```bash
databricks bundle validate                    # Validate default target
databricks bundle validate -t prod           # Validate specific target
```

### Deployment

```bash
databricks bundle deploy                      # Deploy to default target
databricks bundle deploy -t prod             # Deploy to specific target
databricks bundle deploy --auto-approve      # Skip confirmation prompts
databricks bundle deploy --force             # Force overwrite remote changes
```

### Running Resources

```bash
databricks bundle run resource_name          # Run a pipeline or job
databricks bundle run pipeline_name -t prod  # Run in specific environment

# Apps require bundle run to start after deployment
databricks bundle run app_resource_key -t dev    # Start/deploy the app
```

### Monitoring & Logs

**View application logs (for Apps resources):**

```bash
# View logs for deployed apps
databricks apps logs <app-name> --profile <profile-name>

# Examples:
databricks apps logs my-dash-app-dev -p DEFAULT
databricks apps logs my-streamlit-app-prod -p DEFAULT
```

**What logs show:**

- `[SYSTEM]` - Deployment progress, file updates, dependency installation
- `[APP]` - Application output (print statements, errors)
- Backend connection status
- Deployment IDs and timestamps
- Stack traces for errors

**Key log patterns to look for:**

- ✅ `Deployment successful` - Confirms deployment completed
- ✅ `App started successfully` - App is running
- ✅ `Initialized real backend` - Backend connected to Unity Catalog
- ❌ `Error:` - Look for error messages and stack traces
- 📝 `Requirements installed` - Dependencies loaded correctly

### Cleanup

```bash
databricks bundle destroy -t dev
databricks bundle destroy -t prod --auto-approve
```

-----

## CI/CD with GitHub Actions

For complete workflow examples see **<cicd_workflows.md>** and for variables management see **<cicd_variables.md>**.

### Prerequisites (BLOCKING — verify before generating pipelines)

**1. Databricks Service Principal with OIDC federation**

Create the SP in the **Databricks Account Console** (not workspace-level), then add a federated credential for each GitHub environment:

- Azure: `accounts.azuredatabricks.com` → Service Principals
- AWS/GCP: `accounts.cloud.databricks.com` → Service Principals

Subject format per environment: `repo:<owner>/<repo>:environment:<EnvName>`

**2. GitHub Environments**

Per environment (e.g. `dev`, `prod`), configure:

|Name                  |Type                 |Value                                    |
|----------------------|---------------------|-----------------------------------------|
|`DATABRICKS_HOST`     |Variable (not secret)|`https://<workspace>.azuredatabricks.net`|
|`DATABRICKS_CLIENT_ID`|Secret               |SP Application (Client) ID               |

If either prerequisite is missing, stop and guide the user to complete it before generating any files.

### Gather Context (ask all at once)

Before generating workflow files, collect:

1. How many environments and their names? (e.g. dev/staging/prod)
1. Which branch triggers deployment to which environment?
1. Where is the bundle folder? (repo root or subfolder)
1. Does `databricks.yml` already exist? (inspect for hardcoded values)
1. Is there a Python wheel artifact to build?
1. Is there a Databricks Git Folders/Repos sync step?
1. Validate before deploy, or deploy only?

### databricks.yml for CI/CD

⚠️ **Never hardcode `workspace.host`** — it must come from the `DATABRICKS_HOST` GitHub Environment variable. Remove it from `databricks.yml` entirely.

```yaml
bundle:
  name: my-bundle

include:
  - resources/*.yml

variables:
  service_principal_id:
    description: "SP UUID — passed via --var flag in CI"
  catalog:
    default: "dev_catalog"
  schema:
    default: "dev_schema"

targets:
  dev:
    default: true
    mode: development
    variables:
      catalog: "dev_catalog"
      schema: "dev_schema"

  prod:
    mode: production
    run_as:
      service_principal_name: ${var.service_principal_id}
    variables:
      catalog: "prod_catalog"
      schema: "prod_schema"
```

See **<cicd_variables.md>** for full variable management patterns.

### Workflow File Naming

|Validate step?|Filename                          |`name:` field in workflow     |
|--------------|----------------------------------|------------------------------|
|Yes           |`validate_and_deploy_to_<env>.yml`|`validate_and_deploy_to_<env>`|
|No            |`deploy_to_<env>.yml`             |`deploy_to_<env>`             |

Generate one file per environment.

### Workflow Template

```yaml
name: validate_and_deploy_to_prod

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: prod
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: databricks/setup-cli@main

      - name: Authenticate via OIDC
        uses: databricks/auth-actions@main
        with:
          auth-type: github-oidc
          client-id: ${{ secrets.DATABRICKS_CLIENT_ID }}
          host: ${{ vars.DATABRICKS_HOST }}

      - name: Validate bundle         # omit this step if deploy-only
        run: databricks bundle validate -t prod

      - name: Plan bundle             # omit this step if deploy-only
        run: |
          databricks bundle plan -t prod \
            --var="service_principal_id=${{ secrets.DATABRICKS_CLIENT_ID }}"

      - name: Deploy bundle
        run: |
          databricks bundle deploy -t prod \
            --var="service_principal_id=${{ secrets.DATABRICKS_CLIENT_ID }}"
```

### Variable Storage Reference

|Value                 |Store as          |Location                                   |
|----------------------|------------------|-------------------------------------------|
|Workspace URL         |Variable          |GitHub Environment → `DATABRICKS_HOST`     |
|SP Client ID          |Secret            |GitHub Environment → `DATABRICKS_CLIENT_ID`|
|Catalog / schema names|Default values    |`databricks.yml` variables block           |
|SP UUID (`run_as`)    |Passed via `--var`|CI step using `DATABRICKS_CLIENT_ID` value |

-----

## Common Issues

|Issue                                  |Solution                                                                                              |
|---------------------------------------|------------------------------------------------------------------------------------------------------|
|**App deployment fails**               |Check logs: `databricks apps logs <app-name>` for error details                                       |
|**App not connecting to Unity Catalog**|Check logs for backend connection errors; verify warehouse ID and permissions                         |
|**Wrong permission level**             |Dashboards: CAN_READ/RUN/EDIT/MANAGE; Jobs: CAN_VIEW/MANAGE_RUN/MANAGE                                |
|**Path resolution fails**              |Use `../src/` in resources/*.yml, `./src/` in databricks.yml                                          |
|**Catalog doesn’t exist**              |Create catalog first or update variable                                                               |
|**“admins” group error on jobs**       |Cannot modify admins permissions on jobs                                                              |
|**Volume permissions**                 |Use `grants` not `permissions` for volumes                                                            |
|**Hardcoded catalog in dashboard**     |Use dataset_catalog parameter (CLI v0.281.0+), create environment-specific files, or parameterize JSON|
|**App not starting after deploy**      |Apps require `databricks bundle run <resource_key>` to start                                          |
|**App env vars not working**           |Environment variables go in `app.yaml` (source dir), not databricks.yml                               |
|**Wrong app source path**              |Use `../` from resources/ dir if source is in project root                                            |
|**Debugging any app issue**            |First step: `databricks apps logs <app-name>` to see what went wrong                                  |
|**CI: workspace.host not found**       |Remove `workspace.host` from databricks.yml; set `DATABRICKS_HOST` as GitHub Environment variable     |
|**CI: validate fails**                 |`DATABRICKS_HOST` must be set before validate step runs                                               |
|**CI: service_principal_name error**   |Pass `--var="service_principal_id=<uuid>"` in deploy step                                             |
|**CI: OIDC auth fails**                |Verify federated credential subject matches `repo:<owner>/<repo>:environment:<EnvName>` exactly       |

## Key Principles

1. **Path resolution**: `../src/` in resources/*.yml, `./src/` in databricks.yml
1. **Variables**: Parameterize catalog, schema, warehouse
1. **Mode**: `development` for dev/staging, `production` for prod
1. **Groups**: Use `"users"` for all workspace users
1. **Job permissions**: Verify custom groups exist; can’t modify “admins”
1. **CI/CD**: Never hardcode `workspace.host`; use GitHub Environment variables + OIDC auth

## Related Skills

- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - pipeline definitions referenced by DABs
- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - app deployment via DABs
- **[databricks-app-python](../databricks-app-python/SKILL.md)** - Python app deployment via DABs
- **[databricks-config](../databricks-config/SKILL.md)** - profile and authentication setup for CLI/SDK
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - job orchestration managed through bundles

## Resources

- [Databricks Asset Bundles Documentation](https://docs.databricks.com/dev-tools/bundles/)
- [Bundle Resources Reference](https://docs.databricks.com/dev-tools/bundles/resources)
- [Bundle Configuration Reference](https://docs.databricks.com/dev-tools/bundles/settings)
- [Supported Resource Types](https://docs.databricks.com/aws/en/dev-tools/bundles/resources#resource-types)
- [Examples Repository 1](https://github.com/databricks-solutions/databricks-dab-examples)
- [Example Repository 2](https://github.com/databricks/bundle-examples)