# Databricks Skills for Claude Code

Skills that teach Claude Code how to work effectively with Databricks - providing patterns, best practices, and code examples that work with Databricks MCP tools.

## Installation

Run from your **project root** (the directory where you want `.claude/skills` created).

### From this repository (local script)

If you already have the repo (fork or clone), use the script on disk:

```bash
# Install all skills (Databricks + MLflow + APX) — downloads from GitHub by default
./databricks-skills/install_skills.sh

# Install Databricks skills only from this checkout (no network for those skills)
./databricks-skills/install_skills.sh --local

# Install specific skills
./databricks-skills/install_skills.sh databricks-bundles agent-evaluation

# Pin MLflow / APX versions
./databricks-skills/install_skills.sh --mlflow-version v1.0.0

# List available skills
./databricks-skills/install_skills.sh --list

# Install + upload to workspace for Genie Code (/Workspace/Users/<you>/.assistant/skills)
./databricks-skills/install_skills.sh --install-to-genie

./databricks-skills/install_skills.sh --install-to-genie --profile prod

# Local Databricks skills + Genie upload
./databricks-skills/install_skills.sh --local --install-to-genie
```

Paths assume you are at the **ai-dev-kit** repo root. From another project, copy or symlink the script, or use the `curl` flow below.

### Without cloning (curl)

Use this when you only want the installer and not the full repo:

```bash
# Install all skills
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash

# Install specific skills (pass args after bash -s --)
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- databricks-bundles agent-evaluation

curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --mlflow-version v1.0.0

curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --list

curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --install-to-genie

curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --install-to-genie --profile prod
```

`--install-to-genie` uploads the tree under `./.claude/skills` to the workspace (requires the `databricks` CLI).

This creates `.claude/skills/` and downloads all skills. Claude Code loads them automatically.
- **Databricks skills** are downloaded from this repository
- **MLflow skills** are fetched dynamically from [github.com/mlflow/skills](https://github.com/mlflow/skills)

**Manual install:**
```bash
mkdir -p .claude/skills
cp -r ai-dev-kit/databricks-skills/databricks-agent-bricks .claude/skills/
```

## Available Skills

### 🤖 AI & Agents
- **databricks-ai-functions** - Built-in AI Functions (ai_classify, ai_extract, ai_summarize, ai_query, ai_forecast, ai_parse_document, and more) with SQL and PySpark patterns, function selection guidance, document processing pipelines, and custom RAG (parse → chunk → index → query)
- **databricks-agent-bricks** - Knowledge Assistants, Genie Spaces, Supervisor Agents
- **databricks-genie** - Genie Spaces: create, curate, and query via Conversation API
- **databricks-model-serving** - Deploy MLflow models and AI agents to endpoints
- **databricks-unstructured-pdf-generation** - Generate synthetic PDFs for RAG
- **databricks-vector-search** - Vector similarity search for RAG and semantic search

### 📊 MLflow (from [mlflow/skills](https://github.com/mlflow/skills))
- **agent-evaluation** - End-to-end agent evaluation workflow
- **analyze-mlflow-chat-session** - Debug multi-turn conversations
- **analyze-mlflow-trace** - Debug traces, spans, and assessments
- **instrumenting-with-mlflow-tracing** - Add MLflow tracing to Python/TypeScript
- **mlflow-onboarding** - MLflow setup guide for new users
- **querying-mlflow-metrics** - Aggregated metrics and time-series analysis
- **retrieving-mlflow-traces** - Trace search and filtering
- **searching-mlflow-docs** - Search MLflow documentation

### 📊 Analytics & Dashboards
- **databricks-aibi-dashboards** - Databricks AI/BI dashboards (with SQL validation workflow)
- **databricks-unity-catalog** - System tables for lineage, audit, billing

### 🔧 Data Engineering
- **databricks-iceberg** - Apache Iceberg tables (Managed/Foreign), UniForm, Iceberg REST Catalog, Iceberg Clients Interoperability
- **databricks-spark-declarative-pipelines** - SDP (formerly DLT) in SQL/Python
- **databricks-jobs** - Multi-task workflows, triggers, schedules
- **databricks-synthetic-data-gen** - Realistic test data with Faker

### 🚀 Development & Deployment
- **databricks-bundles** - DABs for multi-environment deployments
- **databricks-app-apx** - Full-stack apps (FastAPI + React)
- **databricks-app-python** - Python web apps (Dash, Streamlit, Flask) with foundation model integration
- **databricks-python-sdk** - Python SDK, Connect, CLI, REST API
- **databricks-config** - Profile authentication setup
- **databricks-lakebase-provisioned** - Managed PostgreSQL for OLTP workloads

### 📚 Reference
- **databricks-docs** - Documentation index via llms.txt

## How It Works

```
┌────────────────────────────────────────────────┐
│  .claude/skills/     +    .claude/mcp.json     │
│  (Knowledge)               (Actions)           │
│                                                │
│  Skills teach HOW    +    MCP does it          │
│  ↓                        ↓                    │
│  Claude Code learns patterns and executes      │
└────────────────────────────────────────────────┘
```

**Example:** User says "Create a sales dashboard"
1. Claude loads `databricks-aibi-dashboards` skill → learns validation workflow
2. Calls `get_table_stats_and_schema()` → gets schemas
3. Calls `execute_sql()` → tests queries
4. Calls `manage_dashboard(action="create_or_update")` → deploys
5. Returns working dashboard URL

## Custom Skills

Create your own in `.claude/skills/my-skill/SKILL.md`:

```markdown
---
name: my-skill
description: "What this teaches"
---

# My Skill

## When to Use
...

## Patterns
...
```

## Troubleshooting

**Skills not loading?** Check `.claude/skills/` exists and each skill has `SKILL.md`

**Install fails?** Run `bash install_skills.sh` or check write permissions

## Related

- [databricks-tools-core](../databricks-tools-core/) - Python library
- [databricks-mcp-server](../databricks-mcp-server/) - MCP server
- [Databricks Docs](https://docs.databricks.com/) - Official documentation
- [MLflow Skills](https://github.com/mlflow/skills) - Upstream MLflow skills repository
