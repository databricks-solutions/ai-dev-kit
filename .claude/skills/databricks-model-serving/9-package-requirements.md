# Package Requirements

Databricks Runtime versions and pip package compatibility.

## Recommended Databricks Runtime

| DBR Version | Status | Notes |
|-------------|--------|-------|
| **16.1+** | Recommended | Latest GenAI packages pre-installed |
| **15.4 LTS** | Supported | May need more pip installs |
| **14.x** | Legacy | Missing many GenAI features |

**Use DBR 16.1+ for agent development** - it has most packages pre-installed.

## Pre-installed Packages (DBR 16.1+)

These are available without `%pip install`:

- `mlflow` (3.x)
- `langchain`
- `pydantic`
- `pandas`, `numpy`, `scipy`
- `scikit-learn`
- `databricks-sdk`

## Packages to Install

For GenAI agents, install these:

```python
%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic
dbutils.library.restartPython()
```

### Package Breakdown

| Package | Purpose | Version |
|---------|---------|---------|
| `mlflow` | Model logging, serving | `==3.6.0` |
| `databricks-langchain` | ChatDatabricks, UCFunctionToolkit | Latest |
| `langgraph` | Agent graph framework | `==0.3.4` |
| `databricks-agents` | `agents.deploy()` | Latest |
| `pydantic` | Data validation | Latest |

### With Memory/Lakebase Support

```python
%pip install -U mlflow==3.6.0 databricks-langchain[memory] langgraph==0.3.4 databricks-agents
```

### For Vector Search

```python
%pip install -U mlflow==3.6.0 databricks-langchain databricks-vectorsearch langgraph==0.3.4
```

### Minimal for Testing

```python
%pip install -U mlflow-skinny[databricks] databricks-agents
```

## pip_requirements for Model Logging

When logging models, specify exact versions:

```python
pip_requirements=[
    "mlflow==3.6.0",
    "databricks-langchain",
    "langgraph==0.3.4",
    "pydantic",
]
```

### Get Current Versions Dynamically

```python
from pkg_resources import get_distribution

pip_requirements=[
    f"mlflow=={get_distribution('mlflow').version}",
    f"databricks-langchain=={get_distribution('databricks-langchain').version}",
    f"langgraph=={get_distribution('langgraph').version}",
]
```

## Tested Combinations

### Agent Development (Recommended)

```
mlflow==3.6.0
databricks-langchain>=0.3.0
langgraph==0.3.4
databricks-agents>=0.20.0
pydantic>=2.0
```

### LangChain Tracing

```
mlflow==2.14.0
langchain==0.2.1
langchain-openai==0.1.8
langchain-community==0.2.1
```

### Classical ML

```
mlflow>=2.10.0
scikit-learn>=1.3.0
pandas>=2.0.0
```

## Common Version Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **ImportError: ResponsesAgent** | Old mlflow | `pip install mlflow>=3.0` |
| **LangGraph errors** | Version mismatch | Pin to `langgraph==0.3.4` |
| **Pydantic validation error** | v1 vs v2 | Use `pydantic>=2.0` |
| **ChatDatabricks not found** | Missing package | `pip install databricks-langchain` |
| **agents.deploy fails** | Missing package | `pip install databricks-agents` |

## Environment Variables

Set these for authentication:

```bash
# Option 1: Host + Token
export DATABRICKS_HOST="https://your-workspace.databricks.com"
export DATABRICKS_TOKEN="your-token"

# Option 2: Profile
export DATABRICKS_CONFIG_PROFILE="your-profile"
```

## Installing Packages via MCP

Use `execute_databricks_command`:

```
execute_databricks_command(
    code="%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic"
)
```

Then restart Python:

```
execute_databricks_command(
    code="dbutils.library.restartPython()",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

## Checking Installed Versions

```python
import pkg_resources

packages = ['mlflow', 'langchain', 'langgraph', 'pydantic', 'databricks-langchain']
for pkg in packages:
    try:
        version = pkg_resources.get_distribution(pkg).version
        print(f"{pkg}: {version}")
    except pkg_resources.DistributionNotFound:
        print(f"{pkg}: NOT INSTALLED")
```

Via MCP:

```
execute_databricks_command(
    code="""
import pkg_resources
for pkg in ['mlflow', 'langchain', 'langgraph', 'pydantic', 'databricks-langchain']:
    try:
        print(f"{pkg}: {pkg_resources.get_distribution(pkg).version}")
    except:
        print(f"{pkg}: NOT INSTALLED")
    """
)
```
