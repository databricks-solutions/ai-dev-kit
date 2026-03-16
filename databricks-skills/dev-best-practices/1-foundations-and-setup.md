# Part I: Foundations & Setup + Part II: Development Workflow

## 2. Development Environment Setup

### 2.2 Python Environment (uv)

Use [uv](https://github.com/astral-sh/uv) for Python dependency management — fast, Rust-based, uses standard `pyproject.toml`.

```bash
# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# install Python matching Databricks Runtime
pyenv install 3.12.3
pyenv local 3.12.3

# install project dependencies
uv sync --all-groups

# add new dependency
uv add mlflow

# add dev dependency
uv add --dev pytest
```

**Example `pyproject.toml`:**

```toml
[project]
name = "customer-project"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "databricks-sdk>=0.52.0",
    "mlflow[databricks]>=3.1",
    "pydantic>=2.10.0",
]

[dependency-groups]
dev = [
    "pytest>=7.4.0",
    "ruff>=0.11.9",
    "pre-commit>=3.7.1",
]
```

**Generating `requirements.txt` for Databricks notebooks:**

Only include direct dependencies — NOT transitive ones. The Databricks Runtime already includes pyspark, pandas, numpy, etc.

```
databricks-sdk[openai]>=0.69.0
databricks-vectorsearch>=0.63
mlflow==3.7.0
beautifulsoup4>=4.12.0
```

> **Note:** `uv export` outputs all transitive dependencies — don't use it for `requirements.txt`. Extract only `[project.dependencies]` from `pyproject.toml`.

### 2.3 Code Quality Tools (Ruff)

Use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting — replaces Black, flake8, isort.

**`.pre-commit-config.yaml`:**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.11
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: detect-private-key
```

```bash
# install hooks
uv run pre-commit install

# run manually
uv run ruff check . --fix
uv run ruff format .
```

### 2.4 IDE Setup (VSCode / Cursor)

See [Databricks documentation](https://docs.databricks.com/) for IDE setup and extension guidance.

### 2.5 Databricks CLI Setup

The Databricks CLI is a required dependency — install it for your platform via the [official instructions](https://docs.databricks.com/en/dev-tools/cli/install.html).

```bash
# authenticate (OAuth)
databricks auth login --host https://workspace.cloud.databricks.com

# verify
databricks current-user me

# multiple workspaces
databricks auth login --host https://dev.databricks.com --profile dev
databricks auth login --host https://prod.databricks.com --profile prod
```

---

## 3. Git & Collaboration

Adopt customer Git workflows when they exist. When building from scratch, use the following practices.

### 3.1 Git Fundamentals

- Main branch is protected (requires PR to merge)
- Main is always deployable
- Use `.gitignore` to exclude generated files, secrets, and IDE artifacts

**Never Commit Secrets:**
- No API keys, tokens, or passwords in code
- Use Databricks Secrets for credentials
- Add `detect-private-key` to pre-commit hooks
- If you accidentally commit a secret, **rotate it immediately** (git history preserves it)

### 3.2 Branch Strategy

**Branch Naming: `{username}/{description}`**

```bash
# Good - clear ownership
{username}/add-billing-retry-logic
{username}/fix-vector-search-timeout
{username}/update-agent-config

# Bad - who owns this?
feature/billing
fix/timeout-issue
```

**Branch Lifecycle:**

```bash
# 1. Start fresh from main
git checkout main && git pull origin main

# 2. Create your branch
git checkout -b {username}/add-billing-tool

# 3. Stay synced (daily)
git fetch origin && git rebase origin/main

# 4. Push and create PR
git push origin {username}/add-billing-tool
gh pr create --title "[feature] Add billing tool"

# 5. After merge, delete the branch
git checkout main && git pull origin main
git branch -d {username}/add-billing-tool
git push origin --delete {username}/add-billing-tool
```

**Key Principles:** Short-lived branches (days, not weeks), rebase daily, delete after merge, never push directly to main.

### 3.3 Commit Best Practices

**Atomic commits** — one logical change per commit:

```bash
git commit -m "add retry logic to billing API client"
git commit -m "add unit tests for billing retry logic"
```

**Imperative mood** in messages:

```
# GOOD
add customer lookup tool
fix timeout in vector search

# BAD
added customer lookup tool
fixing timeout
```

**Message structure:**

```
Short summary (50 chars or less)

Longer description if needed. Explain WHY, not just WHAT.

- Bullet points for multiple related points
- Reference ticket numbers if applicable
```

Commit at every logical stopping point: feature complete, tests passing, about to try something risky.

### 3.4 Pull Requests

**Size guidelines:**

| PR Size | Lines Changed | Recommendation |
|---------|--------------|----------------|
| Small | <200 | Ideal |
| Medium | 200–400 | Good |
| Large | 400–800 | Split if possible |
| Too Large | >800 | Must split |

**PR Titles — use prefixes:**

```
[feature] Add billing tool
[fix] Resolve vector search timeout
[refactor] Simplify retry logic
[docs] Update onboarding guide
[chore] Update dependencies
```

**PR Description template:**

```markdown
## What
Quick summary of the change(s)

## Why
Why the change is required

## Key Changes
- What changed
- What else changed

## Testing
- How you tested it (e.g., runs successfully in notebook, dev model deployed)
- Link to JIRA ticket if applicable
```

**Self-review before requesting review:**
1. Read through your own diff (use AI tools to help)
2. Check for debug code, TODOs, commented code
3. Ensure tests pass
4. Verify description is clear
5. Link related tickets

### 3.5 Draft PRs vs Ready PRs

Use **Draft PR** for: early feedback, WIP with team visibility, complex changes needing incremental review.

```bash
gh pr create --draft --title "WIP: Add billing retry logic"
gh pr ready  # convert to ready
```

Use **Ready PR** when: code is complete and tested, all checklist items done, self-reviewed.

### 3.6 Code Review Culture

**Reviewer:** Review within 4 hours during active engagement. Distinguish blockers from suggestions.

**Author:** Respond to every comment. Push back respectfully if you disagree.

**Comment prefixes:**

```
nit: Consider renaming this variable for clarity         (non-blocking)
suggestion: Could use a list comprehension here          (non-blocking)
question: Why did we choose this approach over X?        (non-blocking)
blocker: This will cause a null pointer exception        (must fix)
```

### 3.7 Git Hygiene

- Squash commits before merge (use "Squash and merge" in GitHub)
- Delete merged branches immediately
- Never rewrite shared history (`git push --force origin main` — DANGEROUS)
- Tag releases with semantic versioning: `git tag -a v1.2.0 -m "Release 1.2.0"`

**Typical release flow:**

Development:
1. PR → automated CI (unit tests, lint, secrets check)
2. Code review and merge to main
3. Merge triggers CI/CD → deploys to staging workspace

Production:
1. Create semantic version release tag (e.g., `v0.1.0`) on `main` via GitHub UI
2. Tag creation triggers CI/CD → validates and deploys to PROD

```bash
# Clean up merged branches
git branch --merged main | grep -v main | xargs git branch -d
git fetch --prune
```

---

## 5. Daily Development Cycle

### 5.1 Start of Day

```bash
git checkout main && git pull origin main
git checkout -b {username}/my-feature   # or checkout existing + rebase
git rebase origin/main
```

Rebase daily — small frequent rebases are easier than resolving large conflicts.

### 5.2 Development Loop

```bash
# run tests frequently
uv run pytest tests/unit/ -x

# commit at logical stopping points
git add . && git commit -m "add customer lookup tool"

# push regularly for backup and visibility
git push origin {username}/my-feature
```

### 5.3 Testing in Databricks

**Option 1: DAB Deployment** (for jobs and pipelines)

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run job_name -t dev
```

DAB dev mode auto-prefixes resources with `[dev your.name]` to prevent conflicts. Note: written artifacts (Delta tables, MLflow models) are shared — use dev-prefixed catalogs.

**Option 2: Git-Connected Notebooks** (for interactive testing)

1. Push your branch: `git push origin {username}/my-feature`
2. In Databricks, open a Git-connected notebook
3. Switch branches and pull via the Git dialog
4. Import and test interactively

Preferred for AI/agent development — enables MLflow Trace inspection.

**Option 3: VS Code Extension with Databricks Connect**

Run notebooks/Python files from VS Code against a remote cluster. Limitation: can't inspect MLflow Traces — use Option 2 for AI use cases.

### 5.4 Opening and Merging PRs

```bash
gh pr create --title "[feature] Add customer lookup tool"

# After merge, clean up immediately
git checkout main && git pull origin main
git branch -d {username}/my-feature
databricks bundle destroy -t dev   # clean up dev resources
```

### 5.5 End of Day

- **Terminate clusters** — don't leave them running overnight
- **Push your work** — even WIP; protects against laptop loss
- **Update the team** — quick Slack: "finished X, starting Y tomorrow, blocked on Z"

### 5.7 Cost Consciousness

Databricks compute costs accrue whenever clusters are running — treat compute as a shared resource.

**Clusters:**
- Terminate clusters when not actively using them — never leave them running overnight
- Configure auto-termination: 30–60 minutes for interactive clusters, shorter for job clusters
- Right-size your cluster: start with the smallest instance that meets your needs, scale up only when needed
- Use single-node clusters for development and testing when distributed compute isn't required
- Use Databricks Connect from VS Code/Cursor to avoid launching a full cluster for lightweight tasks

**Tables & Storage:**
- Delete test/scratch tables when done with a task
- Use `dev_{username}_*` naming for all dev tables (e.g., `dev_{username}_customer_data`)
- Never write to prod catalogs during development
- Clean up intermediate checkpoint files from streaming jobs

**MLflow:**
- Delete failed or abandoned experiment runs
- Clean up unused model versions in the registry
- Don't log unnecessary artifacts (large DataFrames, full datasets)

**DABs & Resources:**
- Destroy dev bundle resources when a feature branch is complete
- Don't leave deployed dev jobs running on schedules

```sql
-- find tables you created in dev
SHOW TABLES IN dev_catalog.dev_schema LIKE '*{username}*';

-- drop dev tables when done
DROP TABLE IF EXISTS dev_catalog.dev_schema.dev_{username}_scratch;
```

```bash
# destroy DAB dev resources when done with a feature
databricks bundle destroy -t dev

# check for running clusters you own
databricks clusters list --output json | jq '.[] | select(.state == "RUNNING") | {id: .cluster_id, name: .cluster_name}'
```
