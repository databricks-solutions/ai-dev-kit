# GitHub Actions Workflows for Databricks Asset Bundle CI/CD

Complete annotated examples for deploying Databricks Asset Bundles across multiple environments using GitHub Actions with OIDC authentication.

---

## Prerequisites

### 1. GitHub Environments Setup

In your GitHub repository go to **Settings > Environments** and create one environment per Databricks workspace:

| Environment | Variables | Secrets |
|-------------|-----------|---------|
| `Dev` | `DATABRICKS_HOST` = `https://dev-workspace.azuredatabricks.net` | `DATABRICKS_CLIENT_ID` = `<SP-UUID>` |
| `Staging` | `DATABRICKS_HOST` = `https://staging-workspace.azuredatabricks.net` | `DATABRICKS_CLIENT_ID` = `<SP-UUID>` |
| `Prod` | `DATABRICKS_HOST` = `https://prod-workspace.azuredatabricks.net`, `ADMIN_USER_EMAIL` = `admin@company.com` | `DATABRICKS_CLIENT_ID` = `<SP-UUID>` |

> **Variables** (`vars.*`) are non-sensitive config — visible in logs. Use for workspace URLs, user emails, catalog names.  
> **Secrets** (`secrets.*`) are encrypted — never visible in logs. Use for Client IDs, tokens, credentials.

### 2. OIDC Service Principal Setup

For each environment you need a Databricks Service Principal with:
- A **Federated credential** linked to your GitHub repo (`repo:<owner>/<repo>:environment:<EnvName>`)
- **CAN_MANAGE** or **IS_OWNER** permissions on the target workspace
- The SP's Application (Client) UUID stored as `DATABRICKS_CLIENT_ID` secret in the GitHub environment

---

## Pattern 1: Two Environments (Dev + Prod) — With Validate

The most common setup: `dev` branch → Dev workspace, `main` branch → Prod workspace.
Files: `validate_and_deploy_to_dev.yml` and `validate_and_deploy_to_prod.yml`.

### Dev Pipeline — `validate_and_deploy_to_dev.yml`

```yaml
name: Validate and Deploy to Dev

# Prevent parallel deploys to the same environment
concurrency: dev_environment

on:
  push:
    branches:
      - dev
    paths:
      # Only trigger when bundle files or workflow files change
      - '<bundle_folder>/**'
      - '.github/workflows/**'

permissions:
  # Required for OIDC token generation
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    name: 'Deploy to Dev'
    # This links the job to the GitHub "Dev" environment.
    # All vars.* and secrets.* in this job come from that environment.
    environment: Dev

    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}         # From Dev environment variables
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}  # From Dev environment secrets

    steps:
      - uses: actions/checkout@v3
        name: Check Out Branch

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      # uv is required if your bundle builds a Python wheel artifact
      - name: Install uv
        run: pip install uv

      - name: Install Databricks CLI
        uses: databricks/setup-cli@main

      # Sync the Databricks Git Folder (Repo) in the workspace to the dev branch.
      # This ensures workspace notebooks are in sync with the repo before the bundle deploys.
      - name: Sync Git Folder in Dev Workspace
        run: databricks repos update /Workspace/Shared/<your-repo-name> --branch dev

      # Validate catches YAML errors, missing resources, and permission issues
      # before any resources are modified in the workspace.
      - name: Validate bundle (dev)
        working-directory: ./<bundle_folder>
        run: databricks bundle validate --target dev

      # Deploy the bundle. Variables that are environment-specific and not set
      # as defaults in databricks.yml must be passed here via --var.
      - name: Deploy bundle to dev
        working-directory: ./<bundle_folder>
        run: |
          databricks bundle deploy --target dev \
            --var="service_principal_id=${{ secrets.DATABRICKS_CLIENT_ID }}"
```

### Prod Pipeline — `validate_and_deploy_to_prod.yml`

```yaml
name: Validate and Deploy to Prod

concurrency: prod_environment

on:
  push:
    branches:
      - main
    paths:
      - '<bundle_folder>/**'
      - '.github/workflows/**'

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    name: 'Deploy to Production'
    environment: Prod

    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
      ADMIN_USER_EMAIL: ${{ vars.ADMIN_USER_EMAIL }}

    steps:
      - uses: actions/checkout@v3
      - uses: databricks/setup-cli@main

      - name: Sync Git Folder in Prod Workspace
        run: databricks repos update /Workspace/Shared/<your-repo-name> --branch main

      - name: Validate bundle (prod)
        working-directory: ./<bundle_folder>
        run: databricks bundle validate --target prod

      - name: Deploy bundle to prod
        working-directory: ./<bundle_folder>
        run: |
          databricks bundle deploy --target prod \
            --var="databricks_host=${{ vars.DATABRICKS_HOST }}" \
            --var="admin_user_email=${{ vars.ADMIN_USER_EMAIL }}"
```

---

## Pattern 2: Three Environments (Dev + Staging + Prod) — With Validate

Add a staging environment that triggers on push to a `staging` branch.
Files: `validate_and_deploy_to_dev.yml`, `validate_and_deploy_to_staging.yml`, `validate_and_deploy_to_prod.yml`.

### Staging Pipeline — `validate_and_deploy_to_staging.yml`

```yaml
name: Validate and Deploy to Staging

concurrency: staging_environment

on:
  push:
    branches:
      - staging
    paths:
      - '<bundle_folder>/**'
      - '.github/workflows/**'

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    name: 'Deploy to Staging'
    environment: Staging  # GitHub environment "Staging" with its own DATABRICKS_HOST and CLIENT_ID

    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}

    steps:
      - uses: actions/checkout@v3
      - uses: databricks/setup-cli@main

      - name: Sync Git Folder in Staging Workspace
        run: databricks repos update /Workspace/Shared/<your-repo-name> --branch staging

      - name: Validate bundle (staging)
        working-directory: ./<bundle_folder>
        run: databricks bundle validate --target staging

      - name: Deploy bundle to staging
        working-directory: ./<bundle_folder>
        run: |
          databricks bundle deploy --target staging \
            --var="service_principal_id=${{ secrets.DATABRICKS_CLIENT_ID }}"
```

---

## Pattern 3: Validate Only on Pull Request (No Deploy)

Add a workflow that runs validate on every PR to catch errors before merge, without deploying.

```yaml
# .github/workflows/validate_pr.yml
name: Validate Bundle on PR

on:
  pull_request:
    branches:
      - dev
      - staging
      - main
    paths:
      - '<bundle_folder>/**'

permissions:
  id-token: write
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    name: 'Validate Bundle'
    # Use the environment matching the target branch
    environment: ${{ github.base_ref == 'main' && 'Prod' || github.base_ref == 'staging' && 'Staging' || 'Dev' }}

    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}

    steps:
      - uses: actions/checkout@v3
      - uses: databricks/setup-cli@main

      - name: Validate bundle
        working-directory: ./<bundle_folder>
        run: |
          TARGET=${{ github.base_ref == 'main' && 'prod' || github.base_ref == 'staging' && 'staging' || 'dev' }}
          databricks bundle validate --target $TARGET
```

---

## Common Mistakes and Fixes

### ❌ `DATABRICKS_HOST` not set → auth fails silently

The `workspace.host` in `databricks.yml` must either be set explicitly per target OR provided via the `DATABRICKS_HOST` environment variable. If you comment out `workspace.host` in `databricks.yml`, you **must** set `DATABRICKS_HOST` in the workflow env.

```yaml
# In workflow — this is what makes the CLI know which workspace to connect to
env:
  DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
```

### ❌ `service_principal_name` receives a UUID instead of a name

In `databricks.yml`, `run_as.service_principal_name` expects the Application (Client) UUID of the SP, not a human-readable name. This is consistent with how the Databricks CLI identifies SPs.

```yaml
# databricks.yml — correct usage
run_as:
  service_principal_name: ${var.service_principal_id}  # UUID, e.g. "a1b2c3d4-..."
```

### ❌ Missing `uv` when building Python wheel artifacts

If your bundle has a `whl` artifact with `build: uv build --wheel`, the runner must have `uv` installed. Add these steps before `databricks/setup-cli`:

```yaml
- uses: actions/setup-python@v4
  with:
    python-version: '3.10'
- run: pip install uv
```

### ❌ Two simultaneous deploys to same environment

Use `concurrency:` at the workflow level to serialize deploys:

```yaml
concurrency: prod_environment  # Only one deploy to prod at a time
```

### ❌ `bundle validate` fails for prod because `workspace.host` is not set

If you pass `workspace.host` only at deploy time (via env var or `--var`), validate also needs it. Set `DATABRICKS_HOST` in the workflow env before validate runs — it applies to both commands.
