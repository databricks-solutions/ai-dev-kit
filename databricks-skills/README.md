# Databricks Skills

Skills teach your AI coding assistant how to work effectively with Databricks — patterns, best
practices, and code examples — and pair well with the Databricks MCP tools.

## Install skills (supported path)

Skills are installed and maintained through the Databricks CLI:

```bash
databricks aitools install
```

Requires Databricks CLI **v1.0.0+**. Skills come from
[github.com/databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills)
and stay up to date — no manual copying.

The AI Dev Kit installer already delegates to this, so a normal install gets you the skills too:

```bash
# From the directory where you want skills configured
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh)
```

See the root [README](../README.md) for installer options.

## Genie Code (upload skills to a workspace)

To use skills inside **Genie Code** in a Databricks workspace, upload them to
`/Workspace/Users/<you>/.assistant/skills`. `databricks aitools install` does not cover this, so use
one of the fallbacks below.

**Recommended — notebook uploader (no local clone):**
Import [`install_genie_code_skills.py`](install_genie_code_skills.py) into your workspace as a
notebook and run it. It downloads skills from GitHub and uploads them via the Databricks SDK. Works
on any compute, including serverless.

**Fallback — shell script (downloads from the last release):**

```bash
# Run from the directory where you want ./.claude/skills created
./install_skills.sh --install-to-genie --profile YOUR_PROFILE  # download (pinned to v0.1.13), then upload
./install_skills.sh --local --install-to-genie                 # offline: source frozen DEPRECATED-databricks-skills/ copies instead
```

Run `./install_skills.sh --help` for all options.

## Deprecated: bundled skill copies

The skill folders that used to live here are frozen legacy copies under
[`DEPRECATED-databricks-skills/`](../DEPRECATED-databricks-skills/). They are **no longer maintained**
and exist only so older tooling keeps working. Prefer `databricks aitools install`. If you need the
exact historical files, use git tag `v0.1.13`. See
[`DEPRECATED-databricks-skills/README.md`](../DEPRECATED-databricks-skills/README.md) for migration
guidance (skill renames
are documented in the root README "breaking change" note).

## Custom / Genie Code skills

After uploading, skills live at `/Workspace/Users/<you>/.assistant/skills`. You can edit or remove
skills there, or add your own skill folders (each with a `SKILL.md`) — Genie Code picks them up
automatically. Use [`TEMPLATE/`](TEMPLATE/) as a starting point for authoring a new skill.

## Related

- [databricks-tools-core](../databricks-tools-core/) — Python library
- [databricks-mcp-server](../databricks-mcp-server/) — MCP server
- [databricks-agent-skills](https://github.com/databricks/databricks-agent-skills) — upstream skills source
- [MLflow Skills](https://github.com/mlflow/skills) — upstream MLflow skills
