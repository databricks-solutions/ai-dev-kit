> ⚠️ **Experimental — best-effort, not officially supported**
>
> The skills in this directory are imported from
> [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
> on a best-effort basis. They may be useful, but they are **not officially
> supported** as part of `databricks-agent-skills`:
>
> - They do not follow the same review / quality bar as the skills in
>   [`../skills/`](../skills/).
> - They may be out of date relative to upstream `ai-dev-kit`.
> - They may overlap or conflict with the stable skills (e.g.
>   `databricks-jobs`, `databricks-model-serving` exist in both directories).
> - They are not installed by `databricks experimental aitools skills install`
>   by default — you have to opt in (see the root README).
>
> File issues against this directory in this repo; do not file issues against
> `ai-dev-kit` for skills installed via `databricks-agent-skills`.

---

# Databricks Skills for Claude Code

Skills that teach Claude Code how to work effectively with Databricks - providing patterns, best practices, and code examples that work with Databricks MCP tools.

## Installation

These experimental skills are **not** installed by default. To install them via the Databricks CLI:

```bash
# Install all experimental skills at once
databricks experimental aitools skills install --experimental

# Install a single experimental skill by name
databricks experimental aitools skills install databricks-iceberg
```

See the root [README](../README.md) for details on the stable install path.

## Available Skills

### 🤖 AI & Agents
- **databricks-ai-functions** - Built-in AI Functions (ai_classify, ai_extract, ai_summarize, ai_query, ai_forecast, ai_parse_document, and more) with SQL and PySpark patterns, function selection guidance, document processing pipelines, and custom RAG (parse → chunk → index → query)
- **databricks-agent-bricks** - Knowledge Assistants, Genie Spaces, Supervisor Agents
- **databricks-genie** - Genie Spaces: create, curate, and query via Conversation API
- **databricks-mlflow-evaluation** - End-to-end agent evaluation workflow
- **databricks-unstructured-pdf-generation** - Generate synthetic PDFs for RAG
- **databricks-vector-search** - Vector similarity search for RAG and semantic search

### 📊 Analytics & Dashboards
- **databricks-aibi-dashboards** - Databricks AI/BI dashboards (with SQL validation workflow)
- **databricks-metric-views** - Metric Views for governed metrics
- **databricks-unity-catalog** - System tables for lineage, audit, billing

### 🔧 Data Engineering
- **databricks-dbsql** - Databricks SQL warehouse patterns
- **databricks-iceberg** - Apache Iceberg tables (Managed/Foreign), UniForm, Iceberg REST Catalog, Iceberg Clients Interoperability
- **databricks-spark-declarative-pipelines** - SDP (formerly DLT) in SQL/Python
- **databricks-spark-structured-streaming** - Spark Structured Streaming patterns
- **databricks-jobs** - Multi-task workflows, triggers, schedules *(also available as stable skill)*
- **databricks-synthetic-data-gen** - Realistic test data with Faker
- **databricks-zerobus-ingest** - Zerobus ingest patterns
- **spark-python-data-source** - Python data sources for Spark

### 🚀 Development & Deployment
- **databricks-bundles** - DABs for multi-environment deployments
- **databricks-apps-python** - Python web apps (Dash, Streamlit, Flask) with foundation model integration
- **databricks-python-sdk** - Python SDK, Connect, CLI, REST API
- **databricks-config** - Profile authentication setup
- **databricks-execution-compute** - Execute on Databricks compute
- **databricks-lakebase-autoscale** - Autoscaling for Lakebase
- **databricks-lakebase-provisioned** - Managed PostgreSQL for OLTP workloads

### 📚 Reference
- **databricks-docs** - Documentation index via llms.txt

## Provenance & sync model

These skills are imported as a snapshot from
[`databricks-solutions/ai-dev-kit/databricks-skills/`](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-skills).

**Transition phase (until `ai-dev-kit` skills are locked):**
- Source of truth is **upstream `ai-dev-kit`**. New work and bug fixes go there.
- This directory receives **periodic manual re-syncs** — someone opens a PR
  to bring drift from upstream into `experimental/`.

**Post-lock (after `ai-dev-kit` skill contributions are stopped):**
- Source of truth is **this repo**. New work and bug fixes go directly to
  `experimental/<skill>/`.
- `ai-dev-kit/databricks-skills/` becomes read-only and points here.
