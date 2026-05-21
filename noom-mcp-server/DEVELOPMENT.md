# Development Guide

## Opening pull requests

This repo is a fork of `databricks-solutions/ai-dev-kit`.  GitHub defaults to
targeting the **upstream** repo when you click the "Create pull request" link
from a push notification.  Before submitting, check the base repository
dropdown — it should say `noom/databricks-ai-dev-kit`, not `databricks-solutions/ai-dev-kit`.

To skip the UI entirely:

```bash
gh pr create --repo noom/databricks-ai-dev-kit --base main
```

---

## Linting (pre-commit)

Install the pre-commit hooks once after cloning:

```bash
pip install pre-commit
pre-commit install
```

Ruff will then run automatically on `noom-mcp-server/` files before every commit.
To run manually across all files:

```bash
pre-commit run --all-files
```

---

## Running the test suite

**Unit tests** (no credentials needed):

```bash
uv sync --extra dev
uv run pytest tests/ -v
```

**Integration tests** (live Databricks required):

```bash
./run_integration_tests.sh
```

---

## SQL Service Principal credentials

An admin must provision the secret scope once. End users need READ access on
the scope but never interact with the secret values directly.

```bash
databricks secrets create-scope dbrix_mcp_secret
databricks secrets put-secret dbrix_mcp_secret sql-sp-client-id     --string-value <client-id>
databricks secrets put-secret dbrix_mcp_secret sql-sp-client-secret --string-value <client-secret>
databricks secrets put-acl    dbrix_mcp_secret <group-or-user> READ
```

Users need READ on the scope but never see the raw secret values.
