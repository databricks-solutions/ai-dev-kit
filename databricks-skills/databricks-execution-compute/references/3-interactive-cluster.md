# Interactive Cluster Execution

**Use when:** You have an existing running cluster and need to preserve state across multiple tool calls, or need Scala/R support.

> `<SKILL_ROOT>` in examples = the directory containing the parent SKILL.md — substitute the absolute install path (e.g. `~/.claude/skills/databricks-execution-compute`).

## When to Choose Interactive Cluster

- Multiple sequential commands where variables must persist
- Scala or R code (serverless only supports Python/SQL)
- Existing running cluster available

## Trade-offs

| Pro | Con |
|-----|-----|
| State persists via `context_id` | Cluster startup ~5 min if not running |
| Near-instant follow-up commands | Costs money while running |
| Scala/R/SQL support | Must manage cluster lifecycle |

## Critical: Never Start a Cluster Without Asking

**Starting a cluster takes 3-8 minutes and costs money.** Always check first:

```bash
python <SKILL_ROOT>/scripts/compute.py list-compute --resource clusters
```

If no cluster is running, ask the user:
> "No running cluster. Options:
> 1. Start 'my-dev-cluster' (~5 min startup, costs money)
> 2. Use serverless (instant, no setup)
> Which do you prefer?"

## Basic Usage

### First Command: Creates Context

```bash
python <SKILL_ROOT>/scripts/compute.py execute-code \
    --code "import pandas as pd; df = pd.DataFrame({'a': [1, 2, 3]}); print(df)" \
    --compute-type cluster \
    --cluster-id "1234-567890-abcdef"
```

Response includes `context_id` for reuse:
```json
{
  "success": true,
  "output": "   a\n0  1\n1  2\n2  3",
  "context_id": "ctx_abc123",
  "cluster_id": "1234-567890-abcdef"
}
```

### Follow-up Commands: Reuse Context

```bash
# Variables from first command still available
python <SKILL_ROOT>/scripts/compute.py execute-code \
    --code "print(df.shape)" \
    --compute-type cluster \
    --cluster-id "1234-567890-abcdef" \
    --context-id "ctx_abc123"
```

### Auto-Select Best Running Cluster

```bash
# Get best running cluster
python <SKILL_ROOT>/scripts/compute.py list-compute --auto-select
# Returns: {"cluster_id": "1234-567890-abcdef"}

# Then execute on it
python <SKILL_ROOT>/scripts/compute.py execute-code \
    --code "spark.range(100).show()" \
    --compute-type cluster \
    --cluster-id "1234-567890-abcdef"
```

## Language Support

```bash
# Scala
python <SKILL_ROOT>/scripts/compute.py execute-code --code 'println("Hello")' --compute-type cluster --language scala --cluster-id ...
                   
# SQL
python <SKILL_ROOT>/scripts/compute.py execute-code --code "SELECT * FROM table LIMIT 10" --compute-type cluster --language sql --cluster-id ...

# R
python <SKILL_ROOT>/scripts/compute.py execute-code --code 'print("Hello")' --compute-type cluster --language r --cluster-id ...
```

## Installing Libraries

Install pip packages directly in the execution context:

```bash
python <SKILL_ROOT>/scripts/compute.py execute-code \
    --code "%pip install faker" \
    --compute-type cluster \
    --cluster-id "..." \
    --context-id "..."
```

If needed, restart Python to pick up new packages:
```bash
python <SKILL_ROOT>/scripts/compute.py execute-code \
    --code "dbutils.library.restartPython()" \
    --compute-type cluster \
    --cluster-id "..." \
    --context-id "..."
```

## Context Lifecycle

**Keep alive (default):** Context persists until cluster terminates.

**Destroy when done:**
```bash
python <SKILL_ROOT>/scripts/compute.py execute-code \
    --code "print('Done!')" \
    --compute-type cluster \
    --cluster-id "..." \
    --destroy-context
```

## Managing Clusters

Two equivalent paths: the standalone script (convenience wrapper) or the raw `databricks` CLI (more fields exposed). Prefer the script for the common operations listed here.

```bash
# List all clusters
python <SKILL_ROOT>/scripts/compute.py list-compute --resource clusters

# Get specific cluster status
python <SKILL_ROOT>/scripts/compute.py list-compute --cluster-id "1234-567890-abcdef"

# Start a cluster (WITH USER APPROVAL ONLY - costs money, 3-8min startup)
python <SKILL_ROOT>/scripts/compute.py manage-cluster --action start --cluster-id "1234-567890-abcdef"

# Terminate a cluster (reversible)
python <SKILL_ROOT>/scripts/compute.py manage-cluster --action terminate --cluster-id "1234-567890-abcdef"

# Create a new cluster
python <SKILL_ROOT>/scripts/compute.py manage-cluster --action create --name "my-cluster" --num-workers 2
```

### Filter running interactive clusters only (raw CLI)

Useful before asking the user which cluster to reuse. `--cluster-sources UI,API` excludes job clusters (which would otherwise dominate the list on busy workspaces):

```bash
databricks clusters list --cluster-sources UI,API --output json \
  | jq '.[] | select(.state == "RUNNING")'
```

### Create with a full spec (raw CLI)

The script's `manage-cluster --action create` is fine for quick defaults; for full control (DBR version, instance type, tags) use the raw CLI:

```bash
# SPARK_VERSION is positional; custom_tags recommended for resource tracking
databricks clusters create 15.4.x-scala2.12 --json '{
  "cluster_name": "my-cluster",
  "node_type_id": "i3.xlarge",
  "num_workers": 2,
  "autotermination_minutes": 60,
  "custom_tags": {"aidevkit_project": "ai-dev-kit"}
}'
```

## Common Issues

| Issue | Solution |
|-------|----------|
| "No running cluster" | Ask user to start or use serverless |
| Context not found | Context expired; create new one |
| Library not found | `%pip install <library>` then restart Python if needed |

## When NOT to Use

Switch to **[Databricks Connect](1-databricks-connect.md)** when:
- Developing Spark code with local debugging
- Want instant iteration without cluster concerns

Switch to **[Serverless Job](2-serverless-job.md)** when:
- No cluster running and user doesn't want to wait
- One-off execution without state needs
