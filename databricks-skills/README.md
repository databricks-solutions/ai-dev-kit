# Databricks Skills for Claude Code — moved

> ⚠️ **The skills in this directory are no longer maintained here.**
>
> Databricks skills now live in [`databricks/databricks-agent-skills`](https://github.com/databricks/databricks-agent-skills), and are installed via the Databricks CLI.

## Installation

```bash
# All stable skills
databricks aitools install

# All stable + experimental skills
databricks aitools install --experimental

# One specific skill (stable or experimental)
databricks aitools install <name> [--experimental]
```

CLI install handles agent detection (Claude Code, Cursor, Codex CLI, OpenCode, GitHub Copilot, Antigravity) and writes skills into the right per-agent directory.

## Skill index

Each subdirectory here contains a tombstone `SKILL.md` pointing at the corresponding skill in `databricks-agent-skills`:

| a-d-k name | install with |
|---|---|
| `databricks-agent-bricks` | `databricks aitools install databricks-agent-bricks --experimental` |
| `databricks-ai-functions` | `databricks aitools install databricks-ai-functions --experimental` |
| `databricks-aibi-dashboards` | `databricks aitools install databricks-aibi-dashboards --experimental` |
| `databricks-apps-python` | `databricks aitools install databricks-apps-python --experimental` |
| `databricks-bundles` | `databricks aitools install databricks-dabs` *(merged into stable `databricks-dabs`)* |
| `databricks-config` | `databricks aitools install databricks-core` *(merged into stable `databricks-core`)* |
| `databricks-dbsql` | `databricks aitools install databricks-dbsql --experimental` |
| `databricks-docs` | `databricks aitools install databricks-docs --experimental` |
| `databricks-execution-compute` | `databricks aitools install databricks-execution-compute --experimental` |
| `databricks-genie` | *no longer published; may return in a future release* |
| `databricks-iceberg` | `databricks aitools install databricks-iceberg --experimental` |
| `databricks-jobs` | `databricks aitools install databricks-jobs` *(merged into stable `databricks-jobs`)* |
| `databricks-lakebase-autoscale` | `databricks aitools install databricks-lakebase` *(merged into stable `databricks-lakebase`)* |
| `databricks-lakebase-provisioned` | `databricks aitools install databricks-lakebase` *(merged into stable `databricks-lakebase`)* |
| `databricks-metric-views` | `databricks aitools install databricks-metric-views --experimental` |
| `databricks-mlflow-evaluation` | `databricks aitools install databricks-mlflow-evaluation --experimental` |
| `databricks-model-serving` | `databricks aitools install databricks-model-serving` *(stable)* |
| `databricks-python-sdk` | `databricks aitools install databricks-python-sdk --experimental` |
| `databricks-spark-declarative-pipelines` | `databricks aitools install databricks-pipelines` *(stable; port in progress)* |
| `databricks-spark-structured-streaming` | `databricks aitools install databricks-spark-structured-streaming --experimental` |
| `databricks-synthetic-data-gen` | `databricks aitools install databricks-synthetic-data-gen --experimental` |
| `databricks-unity-catalog` | `databricks aitools install databricks-unity-catalog --experimental` |
| `databricks-unstructured-pdf-generation` | `databricks aitools install databricks-unstructured-pdf-generation --experimental` |
| `databricks-vector-search` | `databricks aitools install databricks-vector-search --experimental` |
| `databricks-zerobus-ingest` | `databricks aitools install databricks-zerobus-ingest --experimental` |
| `spark-python-data-source` | `databricks aitools install spark-python-data-source --experimental` |

## Contributing

File issues and PRs against [`databricks/databricks-agent-skills`](https://github.com/databricks/databricks-agent-skills). The tombstones in this directory are kept only so that existing checkouts and links to a-d-k continue to redirect cleanly; new skill content lands in `databricks-agent-skills` directly.

`TEMPLATE/` is preserved as a starter template for skills that live elsewhere (or for upstream a-d-k tooling that depends on it).
