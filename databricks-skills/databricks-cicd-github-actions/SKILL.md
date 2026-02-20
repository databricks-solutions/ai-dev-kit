---
name: "databricks-cicd-github-actions"
description: "CI/CD pipelines for Databricks Asset Bundles using GitHub Actions. Activate when the user wants to: create GitHub Actions workflows for DAB deployment, set up multi-environment pipelines (dev/staging/prod) pointing to different Databricks workspaces, configure variables and secrets in databricks.yml without hardcoding values, add bundle validate before deploy, or set up OIDC authentication with GitHub environments. Also activate when the user asks to 'create pipelines', 'set up CI/CD', 'deploy to multiple environments', or 'automate bundle deploy'."
---

# Databricks CI/CD with GitHub Actions

## Workflow: How to Use This Skill

**Step 0 — Verify prerequisites before doing anything else.**

Before asking any other question, confirm that the user has completed these two mandatory prerequisites. If either is missing, stop and guide them to complete it first — the pipelines will not work without both.

### Prerequisite 1 — Databricks Service Principal with Federation (Databricks Account Console)

The user must have created a Service Principal in the **Databricks Account Console** (not workspace-level) and configured federated credentials for each GitHub environment.

Ask the user:
> *"Have you already created a Databricks Service Principal in the Account Console and set up the GitHub OIDC federation for each environment?"*

If **no**, instruct them to:
1. Go to **accounts.azuredatabricks.com** (Azure) or **accounts.cloud.databricks.com** (AWS/GCP)
2. Navigate to **User Management → Service Principals → Add Service Principal**
3. For each SP (one per environment, or one shared across environments), open the SP → **Credentials tab → Add federated credential**:
   - **Issuer**: `https://token.actions.githubusercontent.com`
   - **Subject**: `repo:<github-owner>/<repo-name>:environment:<EnvironmentName>` (e.g. `repo:myorg/myrepo:environment:Dev`)
   - One federated credential per GitHub environment
4. Note the SP's **Application (Client) ID** (UUID) — this becomes `DATABRICKS_CLIENT_ID`
5. Assign the SP to the target Databricks workspace with at minimum **CAN_USE** + appropriate resource permissions

Do not proceed until the user confirms this is done.

### Prerequisite 2 — GitHub Environments with Variables and Secrets

The user must have created a GitHub Environment for each deployment target, each containing exactly these configuration values:

Ask the user:
> *"Have you created the GitHub Environments in your repo settings, with DATABRICKS_HOST as a variable and DATABRICKS_CLIENT_ID as a secret for each environment?"*

If **no**, instruct them to:
1. Go to the GitHub repository → **Settings → Environments → New environment**
2. Create one environment per deployment target (e.g. `Dev`, `Prod`)
3. For each environment, add:

| Type | Name | Value |
|------|------|-------|
| **Variable** | `DATABRICKS_HOST` | `https://<workspace>.azuredatabricks.net` |
| **Secret** | `DATABRICKS_CLIENT_ID` | `<SP Application/Client UUID>` |

> **Why variable vs secret?** `DATABRICKS_HOST` is a URL — not sensitive, useful to see in logs. `DATABRICKS_CLIENT_ID` is an identity credential — must be a secret, never visible in logs.

Additional values for Prod (if using permissions in the bundle):

| Type | Name | Value |
|------|------|-------|
| **Variable** | `ADMIN_USER_EMAIL` | `admin@yourcompany.com` |

Do not proceed until the user confirms both prerequisites are complete.

---

**Step 1 — Gather context before generating anything.**

Before writing any file, ask the user ALL of the following questions at once:

1. **How many environments do you need?** (e.g. 2: dev + prod, or 3: dev + staging + prod)
2. **What is the name and target branch for each environment?** (e.g. Dev → branch `dev`, Prod → branch `main`)
3. **Where is your bundle folder?** (the directory containing `databricks.yml`, e.g. `./my_bundle/`)
4. **Do you have an existing `databricks.yml`?** If yes, ask the user to share it or read it from the repo — then inspect it before generating anything (see Step 2).
5. **Does your bundle build a Python wheel artifact?** (`artifacts:` with `type: whl`) — determines whether to include `uv` and `setup-python` steps.
6. **Do you use Databricks Git Folders (Repos) in the workspace?** If yes, what is the workspace path? (e.g. `/Workspace/Shared/my-repo`)
7. **Do you want a `bundle validate` step before deploy?** Options:
   - **Sync Git Folder + Validate + Deploy** *(recommended — catches YAML and config errors before touching the workspace)*
   - **Sync Git Folder + Deploy only** *(simpler, skips pre-flight check)*

**Step 2 — Inspect the existing `databricks.yml` before generating pipelines.**

If the user has an existing `databricks.yml`, read it and check for issues to fix:
- Hardcoded `workspace.host` in any target → remove it; it must come from `DATABRICKS_HOST` env var in CI
- Hardcoded values in `targets:` (catalog names, schema names, user emails) → extract as `variables:`
- Missing `variables:` block → add declarations with descriptions
- `run_as.service_principal_name` set to a literal value → replace with `${var.service_principal_id}`
- `permissions` with hardcoded user emails → replace with `${var.admin_user_email}`

For bundle structure, resource definitions, and `databricks.yml` syntax details, load and reference the **databricks-asset-bundles** skill.

**Step 3 — Generate one pipeline file per environment + updated `databricks.yml`.**

Produce:
- One `.github/workflows/` file per environment, named following the standard convention (see **File Naming Convention** below)
- An updated `databricks.yml` with a clean `variables:` block and no hardcoded environment-specific values
- A GitHub Environments setup checklist (variables and secrets to configure per environment)

---

## File Naming Convention

Workflow files follow a fixed naming standard based on the pipeline mode chosen in Step 1 question 7:

**With validate (recommended):**
```
.github/workflows/validate_and_deploy_to_<env_name>.yml
```

**Without validate:**
```
.github/workflows/deploy_to_<env_name>.yml
```

The workflow `name:` field at the top of the YAML matches the filename convention:
```yaml
# With validate:
name: Validate and Deploy to Dev

# Without validate:
name: Deploy to Dev
```

Examples for a 3-environment setup with validate:
```
.github/workflows/
├── validate_and_deploy_to_dev.yml
├── validate_and_deploy_to_staging.yml
└── validate_and_deploy_to_prod.yml
```

Examples for a 2-environment setup without validate:
```
.github/workflows/
├── deploy_to_dev.yml
└── deploy_to_prod.yml
```

---

## What Gets Created Per Environment

For N environments, N workflow files are generated using the naming convention above. Example with validate enabled:

```
.github/workflows/
├── validate_and_deploy_to_dev.yml
├── validate_and_deploy_to_staging.yml    # only if staging requested
└── validate_and_deploy_to_prod.yml
```

Each workflow runs these steps in order:
1. Checkout repo (`actions/checkout@v3`)
2. Set up Python + install `uv` *(only if bundle has a whl artifact)*
3. Install Databricks CLI (`databricks/setup-cli@main`)
4. Sync Databricks Git Folder *(only if user uses Repos)*
5. `databricks bundle validate --target <env>` *(only if user chose validate+deploy)*
6. `databricks bundle deploy --target <env>` with env-specific `--var` flags

---

## Authentication: OIDC (Always Recommended Over PAT)

```yaml
permissions:
  id-token: write    # Required for OIDC token generation
  contents: read

jobs:
  deploy:
    environment: Dev   # Scopes vars.* and secrets.* to the GitHub "Dev" environment
    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
```

OIDC prerequisites (one SP per environment):
- Databricks Service Principal with a Federated Credential: `repo:<owner>/<repo>:environment:<EnvName>`
- SP Application (Client) UUID stored as `DATABRICKS_CLIENT_ID` secret in the GitHub environment
- `DATABRICKS_HOST` workspace URL stored as a variable in the GitHub environment

---

## workspace.host: Never Hardcode

Remove `workspace.host` from `databricks.yml` entirely. It must come from `DATABRICKS_HOST` in the CI env — this is what allows the same bundle to deploy to different workspaces per environment.

```yaml
# databricks.yml — CORRECT
targets:
  dev:
    workspace:
      root_path: ~/Shared/.bundle/${bundle.name}/${bundle.target}
      # No host here — provided by DATABRICKS_HOST in GitHub Actions

# databricks.yml — WRONG (hardcoded)
targets:
  dev:
    workspace:
      host: https://dev-workspace.azuredatabricks.net  # ❌ Remove this
```

---

## Variables: What Goes Where

| Value | Store in | Accessed as |
|-------|----------|-------------|
| Workspace URL | GitHub Environment Variable | `${{ vars.DATABRICKS_HOST }}` → `DATABRICKS_HOST` env var |
| Service Principal UUID | GitHub Environment Secret | `${{ secrets.DATABRICKS_CLIENT_ID }}` → `--var="service_principal_id=..."` |
| Admin user email | GitHub Environment Variable | `${{ vars.ADMIN_USER_EMAIL }}` → `--var="admin_user_email=..."` |
| Catalog name | `databricks.yml` target `variables:` | `${var.catalog}` |
| Schema name | `databricks.yml` target `variables:` | `${var.schema}` |
| Any sensitive runtime value | GitHub Environment Secret | `${{ secrets.MY_SECRET }}` → `--var="my_var=..."` |

---

## Workflow Templates

Two variants based on the user's choice in Step 1 question 7. Replace all `<PLACEHOLDERS>` with actual values.

### Variant A — Validate + Deploy (recommended)

**Filename:** `validate_and_deploy_to_<env_name>.yml`

```yaml
name: Validate and Deploy to <ENV_NAME>

concurrency: <env_name>_environment

on:
  push:
    branches:
      - <branch_name>
    paths:
      - '<bundle_folder>/**'
      - '.github/workflows/**'

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    name: 'Validate and Deploy to <ENV_NAME>'
    environment: <ENV_NAME>
    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}

    steps:
      - uses: actions/checkout@v3

      # ── Include only if bundle has a Python whl artifact ──────────────
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install uv
        run: pip install uv
      # ─────────────────────────────────────────────────────────────────

      - name: Install Databricks CLI
        uses: databricks/setup-cli@main

      # ── Include only if using Databricks Git Folders (Repos) ──────────
      - name: Sync Git Folder
        run: databricks repos update <workspace_repo_path> --branch <branch_name>
      # ─────────────────────────────────────────────────────────────────

      - name: Validate bundle
        working-directory: ./<bundle_folder>
        run: databricks bundle validate --target <target_name>

      - name: Deploy bundle
        working-directory: ./<bundle_folder>
        run: |
          databricks bundle deploy --target <target_name> \
            --var="service_principal_id=${{ secrets.DATABRICKS_CLIENT_ID }}"
          # Add further --var flags for values not set as defaults in databricks.yml targets
```

### Variant B — Deploy Only (no validate)

**Filename:** `deploy_to_<env_name>.yml`

```yaml
name: Deploy to <ENV_NAME>

concurrency: <env_name>_environment

on:
  push:
    branches:
      - <branch_name>
    paths:
      - '<bundle_folder>/**'
      - '.github/workflows/**'

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    name: 'Deploy to <ENV_NAME>'
    environment: <ENV_NAME>
    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}

    steps:
      - uses: actions/checkout@v3

      # ── Include only if bundle has a Python whl artifact ──────────────
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install uv
        run: pip install uv
      # ─────────────────────────────────────────────────────────────────

      - name: Install Databricks CLI
        uses: databricks/setup-cli@main

      # ── Include only if using Databricks Git Folders (Repos) ──────────
      - name: Sync Git Folder
        run: databricks repos update <workspace_repo_path> --branch <branch_name>
      # ─────────────────────────────────────────────────────────────────

      - name: Deploy bundle
        working-directory: ./<bundle_folder>
        run: |
          databricks bundle deploy --target <target_name> \
            --var="service_principal_id=${{ secrets.DATABRICKS_CLIENT_ID }}"
          # Add further --var flags for values not set as defaults in databricks.yml targets
```

---

## GitHub Environments Checklist

Always provide this after generating the pipeline files:

**In GitHub → Settings → Environments → Create one per environment:**

| Environment | Variables | Secrets |
|-------------|-----------|---------|
| Dev | `DATABRICKS_HOST=https://dev.azuredatabricks.net` | `DATABRICKS_CLIENT_ID=<SP UUID>` |
| Staging | `DATABRICKS_HOST=https://staging.azuredatabricks.net` | `DATABRICKS_CLIENT_ID=<SP UUID>` |
| Prod | `DATABRICKS_HOST=https://prod.azuredatabricks.net`, `ADMIN_USER_EMAIL=admin@co.com` | `DATABRICKS_CLIENT_ID=<SP UUID>` |

---

## Quick Reference: Bundle CLI Commands Used in Pipelines

```bash
# Validate (always run before deploy)
databricks bundle validate --target dev

# Deploy with variable overrides
databricks bundle deploy --target dev \
  --var="service_principal_id=<uuid>" \
  --var="catalog=my_catalog"

# Sync Databricks Repo / Git Folder
databricks repos update /Workspace/Shared/my-repo --branch dev
```

---

## Related Skills

- **databricks-asset-bundles** — `databricks.yml` structure, resource definitions (jobs, pipelines, schemas), `presets`, `run_as`, artifact builds, deployment modes. Load this skill for all questions about bundle configuration syntax and Databricks resource definitions.
- **databricks-config** — Service principal setup, local auth profiles, OIDC federated credential configuration. Load this skill for SP setup and workspace authentication details.
- **databricks-jobs** — Job task definitions used inside bundles.

## Reference Files

- `1-github-actions-workflows.md` — Complete annotated examples for 2 and 3 environments, PR-only validate workflow, and common errors with fixes
- `2-databricks-yml-variables.md` — Full `databricks.yml` template with variables, multi-target config, and variable resolution reference
