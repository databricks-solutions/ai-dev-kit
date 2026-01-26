# Databricks Skills for Claude Code

Skills that teach Claude Code how to work effectively with Databricks. These skills provide domain knowledge, patterns, and best practices for building on the Databricks platform.

## What are Skills?

Skills are markdown files that give Claude Code specialized knowledge about specific domains. When you add these skills to your project, Claude learns:

- **Best practices** for Databricks development
- **Patterns** for common tasks (DABs, pipelines, data generation)
- **Code examples** that work with Databricks MCP tools
- **Conventions** and naming standards

## Quick Install

Run this command in your project root:

```bash
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash
```

Or clone and run locally:

```bash
git clone https://github.com/databricks-solutions/ai-dev-kit.git
cd ai-dev-kit/databricks-skills
./install_skills.sh
```

The installer will:
1. Create `.claude/skills/` in your project (if needed)
2. Download each skill
3. Ask before overwriting existing skills

## Available Skills

| Skill | Description |
|-------|-------------|
| **asset-bundles** | Create and configure Databricks Asset Bundles (DABs) with best practices for multi-environment deployments |
| **databricks-app-apx** | Build full-stack Databricks apps using APX framework (FastAPI + React) |
| **databricks-app-python** | Build Python-based Databricks apps with Dash, Streamlit, Flask, or other Python web frameworks |
| **databricks-python-sdk** | Python SDK, Databricks Connect, CLI, and REST API guidance |
| **mlflow-evaluation** | MLflow evaluation, scoring, and trace analysis patterns |
| **model-serving** | Deploy and manage model serving endpoints for custom models, foundation models, external LLM proxies (OpenAI, Anthropic), and AI agents |
| **spark-declarative-pipelines** | Spark Declarative Pipelines (SDP) patterns in SQL and Python - formerly Delta Live Tables |
| **synthetic-data-generation** | Generate realistic test data using Faker and Spark with non-linear distributions |

## How Skills Work with MCP

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Project                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────────────────────┐  │
│  │  .claude/skills/ │    │  .claude/mcp.json                │  │
│  │                  │    │                                  │  │
│  │  • asset-bundles           │    │  Configures MCP server that      │  │
│  │  • spark-declarative-      │    │  provides Databricks tools:      │  │
│  │    pipelines               │    │  • execute_sql                   │  │
│  │  • synthetic-data-gen      │    │  • get_table_details             │  │
│  │  • databricks-   │    │  • run_python_file_on_databricks │  │
│  │    python-sdk    │    │  • ka_create, mas_create, etc.   │  │
│  │                  │    │                                  │  │
│  └────────┬─────────┘    └───────────────┬──────────────────┘  │
│           │                              │                      │
│           ▼                              ▼                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                     Claude Code                           │  │
│  │                                                           │  │
│  │  Uses SKILLS to know HOW to do things                    │  │
│  │  Uses MCP TOOLS to actually DO things on Databricks      │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Skills** = Knowledge (patterns, examples, best practices)
**MCP Tools** = Actions (execute SQL, create tables, run code)

## Manual Installation

If you prefer to install skills manually:

1. Create the skills directory:
   ```bash
   mkdir -p .claude/skills
   ```

2. Copy the skills you want:
   ```bash
   # From a cloned repo
   cp -r ai-dev-kit/databricks-skills/asset-bundles .claude/skills/
   cp -r ai-dev-kit/databricks-skills/spark-declarative-pipelines .claude/skills/
   ```

## Skill Structure

Each skill follows this structure:

```
skill-name/
├── SKILL.md          # Main skill file (required)
├── examples.md       # Code examples (optional)
├── patterns.md       # Common patterns (optional)
└── reference.md      # API reference (optional)
```

The `SKILL.md` file contains:
- Frontmatter with name and description
- When to use the skill
- Best practices and patterns
- Code examples

## Creating Custom Skills

You can create your own skills for your organization:

```markdown
---
name: my-custom-skill
description: "Description of what this skill teaches"
---

# My Custom Skill

## When to Use
...

## Patterns
...

## Examples
...
```

## Requirements

- Claude Code CLI installed
- Databricks workspace access (for using MCP tools)
- Optional: Databricks MCP server configured in `.claude/mcp.json`

## Related

- [databricks-tools-core](../databricks-tools-core/) - Python library with Databricks functions
- [databricks-mcp-server](../databricks-mcp-server/) - MCP server exposing tools to Claude
- [Databricks Asset Bundles](https://docs.databricks.com/dev-tools/bundles/) - Official DABs documentation
- [Spark Declarative Pipelines](https://docs.databricks.com/delta-live-tables/) - Official DLT/SDP documentation
