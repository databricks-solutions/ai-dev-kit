# Tools Integration

Add Unity Catalog Functions and Vector Search to your agents.

## Unity Catalog Functions (UCFunctionToolkit)

UC Functions are SQL/Python UDFs registered in Unity Catalog that agents can call as tools.

### Setup

```python
from databricks_langchain import UCFunctionToolkit

# Specify functions by name
uc_toolkit = UCFunctionToolkit(
    function_names=[
        "catalog.schema.my_function",
        "catalog.schema.another_function",
        "system.ai.python_exec",  # Built-in Python interpreter
    ]
)

# Add to your tools list
tools = []
tools.extend(uc_toolkit.tools)
```

### Wildcard Selection

```python
# All functions in a schema
uc_toolkit = UCFunctionToolkit(
    function_names=["catalog.schema.*"]
)
```

### Built-in UC Tools

| Function | Purpose |
|----------|---------|
| `system.ai.python_exec` | Execute Python code |
| `system.ai.similarity_search` | Vector similarity search |

### Creating a UC Function

```sql
-- In a notebook or SQL editor
CREATE OR REPLACE FUNCTION catalog.schema.get_customer_info(customer_id STRING)
RETURNS TABLE(name STRING, email STRING, tier STRING)
LANGUAGE SQL
COMMENT 'Get customer information by ID'
RETURN
  SELECT name, email, tier
  FROM catalog.schema.customers
  WHERE id = customer_id;
```

### Register Resources for Auth Passthrough

When logging the model, include UC functions as resources:

```python
from mlflow.models.resources import DatabricksFunction

resources = []
for tool in tools:
    if hasattr(tool, "uc_function_name"):
        resources.append(DatabricksFunction(function_name=tool.uc_function_name))
```

## Vector Search (VectorSearchRetrieverTool)

Add RAG capabilities with Databricks Vector Search indexes.

### Setup

```python
from databricks_langchain import VectorSearchRetrieverTool

# Create retriever tool
vs_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.my_vector_index",
    num_results=5,
    # Optional: filter results
    # filters={"category": "documentation"}
)

tools = [vs_tool]
```

### With Filters

```python
vs_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.docs_index",
    num_results=10,
    filters={"doc_type": "technical", "status": "published"},
    columns=["content", "title", "url"],  # Columns to return
)
```

### Register Resources

Vector Search tools provide their resources automatically:

```python
from mlflow.models.resources import DatabricksServingEndpoint

resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

for tool in tools:
    if isinstance(tool, VectorSearchRetrieverTool):
        resources.extend(tool.resources)  # Includes VS index and embedding endpoint
```

## Custom Tools with @tool Decorator

Create custom tools for your agent:

```python
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

@tool
def get_current_time(timezone: str = "UTC") -> str:
    """Get the current time in the specified timezone.
    
    Args:
        timezone: The timezone (e.g., 'UTC', 'America/New_York')
    """
    from datetime import datetime
    import pytz
    
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")

@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression.
    
    Args:
        expression: A math expression like '2 + 2' or 'sqrt(16)'
    """
    import math
    # Safe eval with math functions
    allowed = {k: v for k, v in math.__dict__.items() if not k.startswith('_')}
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)
    except Exception as e:
        return f"Error: {e}"

# Add to tools
tools = [get_current_time, calculate]
```

### Tools with Config Access

Access runtime config (user_id, etc.) in tools:

```python
@tool
def get_user_preferences(config: RunnableConfig) -> str:
    """Get preferences for the current user."""
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return "No user ID provided"
    
    # Fetch from database
    # ...
    return f"Preferences for {user_id}: ..."
```

## Combining All Tool Types

```python
from databricks_langchain import ChatDatabricks, UCFunctionToolkit, VectorSearchRetrieverTool
from langchain_core.tools import tool

# LLM
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

# All tools
tools = []

# 1. UC Functions
uc_toolkit = UCFunctionToolkit(function_names=["catalog.schema.*"])
tools.extend(uc_toolkit.tools)

# 2. Vector Search
vs_tool = VectorSearchRetrieverTool(index_name="catalog.schema.docs_index")
tools.append(vs_tool)

# 3. Custom tools
@tool
def my_custom_tool(query: str) -> str:
    """Custom tool description."""
    return f"Result for: {query}"

tools.append(my_custom_tool)

# Bind to LLM
llm_with_tools = llm.bind_tools(tools)
```

## Resources for Model Logging

Collect all resources for auto authentication:

```python
from mlflow.models.resources import (
    DatabricksServingEndpoint,
    DatabricksFunction,
    DatabricksVectorSearchIndex,
)
from unitycatalog.ai.langchain.toolkit import UnityCatalogTool

resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

for tool in tools:
    # UC Functions
    if isinstance(tool, UnityCatalogTool):
        resources.append(DatabricksFunction(function_name=tool.uc_function_name))
    # Vector Search
    elif isinstance(tool, VectorSearchRetrieverTool):
        resources.extend(tool.resources)
    # Custom tools don't need resources (they run in the endpoint)

# Log model with resources
mlflow.pyfunc.log_model(
    name="agent",
    python_model="agent.py",
    resources=resources,
    # ...
)
```

## Best Practices

1. **Limit tool count** - Agents work best with 5-10 focused tools
2. **Clear descriptions** - Tool docstrings are shown to the LLM
3. **Type hints** - Always include type hints for parameters
4. **Error handling** - Return error messages, don't raise exceptions
5. **Test tools independently** - Verify each tool works before adding to agent
