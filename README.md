# Databricks AI Dev Kit

Build Databricks projects with AI coding assistants (Claude Code, Cursor, etc.) using MCP (Model Context Protocol).

## Overview

The AI Dev Kit bridges the gap between AI coding assistants and the Databricks platform. It provides:

- **Skills** - Teach AI assistants Databricks best practices and patterns
- **MCP Tools** - Enable AI assistants to execute actions on your Databricks workspace
- **Core Library** - Framework-agnostic Python functions for any integration

```
                    ┌─────────────────────────────────────────┐
                    │           AI Coding Assistant           │
                    │       (Claude Code, Cursor, etc.)       │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────┼───────────────────────┐
                    │                 │                       │
                    ▼                 ▼                       ▼
            ┌───────────────┐ ┌───────────────┐ ┌─────────────────────┐
            │    Skills     │ │  MCP Server   │ │    Core Library     │
            │               │ │               │ │                     │
            │  Knowledge &  │ │  Tool Bridge  │ │  Python Functions   │
            │   Patterns    │ │   (stdio)     │ │  (Framework-agnostic)│
            └────────────┬──┘ └───────┬───────┘ └─────────────────────┘
                         │            │
                         ▼            ▼
                    ┌─────────────────────────────────────────┐
                    │          Databricks Workspace           │
                    │                                         │
                    │  SQL Warehouses • Clusters • Jobs       │
                    │  Unity Catalog • Pipelines • Files      │
                    └─────────────────────────────────────────┘
```

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/databricks-solutions/ai-dev-kit.git
cd ai-dev-kit/databricks-mcp-server
./setup.sh
```

### 2. Configure Authentication

```bash
# Option 1: Environment variables
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-token"

# Option 2: Profile from ~/.databrickscfg
export DATABRICKS_CONFIG_PROFILE="your-profile"
```

### 3. Register MCP Server

In your project directory:

```bash
claude mcp add-json databricks '{
  "command": "/path/to/ai-dev-kit/databricks-mcp-server/.venv/bin/python",
  "args": ["/path/to/ai-dev-kit/databricks-mcp-server/run_server.py"]
}'
```

### 4. Install Skills (Recommended)

```bash
/path/to/ai-dev-kit/databricks-skills/install_skills.sh
```

### 5. Start Claude Code

```bash
claude
```

Verify the MCP connection with `/mcp`. Claude now has both **skills** (knowledge) and **MCP tools** (actions) for Databricks!

---

## Components

### [databricks-tools-core](databricks-tools-core/)

Pure Python library with high-level Databricks functions. Framework-agnostic and reusable.

| Module | Description |
|--------|-------------|
| `sql/` | SQL execution, warehouse management, table statistics |
| `jobs/` | Job creation, run management, status monitoring |
| `unity_catalog/` | Catalogs, schemas, tables management |
| `compute/` | Cluster code execution, execution contexts |
| `spark_declarative_pipelines/` | SDP/DLT pipeline creation and management |
| `agent_bricks/` | Genie, Knowledge Assistants, Multi-Agent Supervisor |
| `aibi_dashboards/` | AI/BI dashboard creation and management |
| `file/` | Workspace file upload operations |

### [databricks-mcp-server](databricks-mcp-server/)

FastMCP server that exposes core library functions as MCP tools for AI assistants.

**Available Tools:**
- **SQL**: `execute_sql`, `execute_sql_multi`, `get_table_details`, `list_warehouses`
- **Jobs**: `create_job`, `run_job_now`, `wait_for_run`, `get_run_output`, and more
- **Pipelines**: `create_pipeline`, `start_update`, `get_pipeline_events`, and more
- **Compute**: `execute_databricks_command`, `run_python_file_on_databricks`
- **Files**: `upload_folder`, `upload_file`
- **Agent Bricks**: Knowledge Assistant, Genie, and MAS management
- **Dashboards**: AI/BI dashboard creation and publishing

### [databricks-skills](databricks-skills/)

Markdown-based skills that teach AI assistants Databricks patterns and best practices.

| Skill | Description |
|-------|-------------|
| **spark-declarative-pipelines** | SDP/DLT patterns (streaming, CDC, SCD Type 2, Auto Loader) |
| **asset-bundles** | Databricks Asset Bundles for multi-environment deployment |
| **databricks-python-sdk** | SDK, Databricks Connect, CLI, and REST API |
| **synthetic-data-generation** | Realistic test data with Faker and Spark |
| **mlflow-evaluation** | MLflow evaluation, scoring, and trace analysis |
| **databricks-app** | Python web apps (Dash, Streamlit, Flask) |
| **agent-bricks** | Knowledge Assistants, Genie, Multi-Agent Supervisor |
| **aibi-dashboards** | AI/BI dashboard creation patterns |
| **databricks-jobs** | Job management best practices |
| **databricks-config** | Configuration and environment setup |

### [databricks-builder-app](databricks-builder-app/)

Full-stack web application providing a Claude Code agent interface for Databricks Apps deployment.

- **Frontend**: React with chat UI, project selector, conversation history
- **Backend**: FastAPI with SSE streaming
- **Agent**: Claude Code integration via `claude-agent-sdk`

---

## Using the Core Library

The core library is framework-agnostic. Use it directly or integrate with any AI agent framework.

### Direct Python Usage

```python
from databricks_tools_core.sql import execute_sql, get_table_details, TableStatLevel

# Execute SQL
results = execute_sql("SELECT * FROM my_catalog.my_schema.customers LIMIT 10")

# Get table statistics
stats = get_table_details(
    catalog="my_catalog",
    schema="my_schema",
    table_names=["customers", "orders"],
    table_stat_level=TableStatLevel.DETAILED
)
```

### With LangChain

```python
from langchain_core.tools import tool
from databricks_tools_core.sql import execute_sql

@tool
def run_sql(query: str) -> list:
    """Execute a SQL query on Databricks and return results."""
    return execute_sql(query)

tools = [run_sql]
```

### With OpenAI Agents SDK

```python
from agents import Agent, function_tool
from databricks_tools_core.sql import execute_sql

@function_tool
def run_sql(query: str) -> list:
    """Execute a SQL query on Databricks."""
    return execute_sql(query)

agent = Agent(name="Databricks Agent", tools=[run_sql])
```

---

## Development

```bash
# Clone the repo
git clone https://github.com/databricks-solutions/ai-dev-kit.git
cd ai-dev-kit

# Setup MCP server (includes databricks-tools-core)
cd databricks-mcp-server
./setup.sh

# Run integration tests
cd ../databricks-tools-core
uv run pytest tests/integration/ -v
```

### Test Project

```bash
cd databricks-claude-test-project
./setup.sh   # Requires databricks-mcp-server setup first
claude
```

---

## Project Structure

```
ai-dev-kit/
├── databricks-tools-core/          # Core Python library
├── databricks-mcp-server/          # MCP server for AI assistants
├── databricks-skills/              # Knowledge base for AI assistants
│   ├── asset-bundles/
│   ├── spark-declarative-pipelines/
│   ├── synthetic-data-generation/
│   ├── databricks-python-sdk/
│   ├── databricks-app-apx/
│   ├── databricks-app-python/
│   ├── mlflow-evaluation/
│   ├── agent-bricks/
│   ├── aibi-dashboards/
│   └── ...
├── databricks-builder-app/         # Full-stack web application
└── databricks-claude-test-project/ # Test sandbox
```

---

## Acknowledgments

MCP Databricks Command Execution API from [databricks-exec-code](https://github.com/databricks-solutions/databricks-exec-code-mcp) by Natyra Bajraktari and Henryk Borzymowski.

---

## License

© 2026 Databricks, Inc. All rights reserved.

The source in this project is provided subject to the [Databricks License](https://databricks.com/db-license-source). See [LICENSE.md](LICENSE.md) for details.

---

## Third-Party Package Licenses

The following packages are used by this project and are **not** included in the Databricks Runtime. Their licenses are listed below for attribution.

| Package | Version | License | Project URL |
|---------|---------|---------|-------------|
| [fastmcp](https://github.com/jlowin/fastmcp) | ≥0.1.0 | MIT | https://github.com/jlowin/fastmcp |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | ≥1.0.0 | MIT | https://github.com/modelcontextprotocol/python-sdk |
| [sqlglot](https://github.com/tobymao/sqlglot) | ≥20.0.0 | MIT | https://github.com/tobymao/sqlglot |
| [sqlfluff](https://github.com/sqlfluff/sqlfluff) | ≥3.0.0 | MIT | https://github.com/sqlfluff/sqlfluff |
| [litellm](https://github.com/BerriAI/litellm) | ≥1.0.0 | MIT | https://github.com/BerriAI/litellm |
| [pymupdf](https://github.com/pymupdf/PyMuPDF) | ≥1.24.0 | AGPL-3.0 | https://github.com/pymupdf/PyMuPDF |
| [claude-agent-sdk](https://github.com/anthropics/claude-code) | ≥0.1.19 | MIT | https://github.com/anthropics/claude-code |
| [fastapi](https://github.com/fastapi/fastapi) | ≥0.115.8 | MIT | https://github.com/fastapi/fastapi |
| [uvicorn](https://github.com/encode/uvicorn) | ≥0.34.0 | BSD-3-Clause | https://github.com/encode/uvicorn |
| [httpx](https://github.com/encode/httpx) | ≥0.28.0 | BSD-3-Clause | https://github.com/encode/httpx |
| [sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) | ≥2.0.41 | MIT | https://github.com/sqlalchemy/sqlalchemy |
| [alembic](https://github.com/sqlalchemy/alembic) | ≥1.16.1 | MIT | https://github.com/sqlalchemy/alembic |
| [asyncpg](https://github.com/MagicStack/asyncpg) | ≥0.30.0 | Apache-2.0 | https://github.com/MagicStack/asyncpg |
| [greenlet](https://github.com/python-greenlet/greenlet) | ≥3.0.0 | MIT | https://github.com/python-greenlet/greenlet |
| [psycopg2-binary](https://github.com/psycopg/psycopg2) | ≥2.9.11 | LGPL-3.0 | https://github.com/psycopg/psycopg2 |
