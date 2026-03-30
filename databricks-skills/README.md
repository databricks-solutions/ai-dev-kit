# Databricks Skills for Claude Code

Skills that teach Claude Code how to work effectively with Databricks - providing patterns, best practices, and code examples that work with Databricks MCP tools.

## Installation

Run in your project root:

```bash
# Install all skills (Databricks + MLflow)
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash

# Install specific skills
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- databricks-bundles agent-evaluation

# Pin MLflow skills to a specific version
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --mlflow-version v1.0.0

# List available skills
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --list
```

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
4. Calls `create_or_update_dashboard()` → deploys
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
