# Agent Serving

Deploy AI agents (LangChain, LangGraph, custom agents, RAG applications) as production-ready endpoints.

---

## Critical: Packaging Agents for Unity Catalog

Before an agent can be served, it must be:
1. **Logged to MLflow** with proper signature and dependencies
2. **Registered to Unity Catalog** 
3. **Tested locally** to verify it works

### The #1 Cause of Deployment Failures: Bad Signatures

The **MLflow signature** tells the serving endpoint what input/output format to expect. Without it, queries will fail.

```python
from mlflow.models import infer_signature

# ALWAYS define input/output examples
input_example = {
    "messages": [
        {"role": "user", "content": "Hello!"}
    ]
}

output_example = {
    "choices": [
        {"message": {"role": "assistant", "content": "Hi there!"}}
    ]
}

# Infer signature from examples
signature = infer_signature(input_example, output_example)

# Log with signature
mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),
    signature=signature,  # REQUIRED for serving!
    input_example=input_example,
    registered_model_name="catalog.schema.my_agent",
)
```

### Choose the Right MLflow Flavor

| Flavor | When to Use | Signature |
|--------|-------------|-----------|
| `mlflow.langchain.log_model()` | LangChain/LangGraph agents | Auto-inferred |
| `mlflow.pyfunc.log_model()` | Custom Python agents | Must specify |
| ChatModel (MLflow 2.12+) | Chat-compatible agents | Auto chat format |

### Dependencies Are Critical

Missing dependencies = deployment failure. Always specify:

```python
mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),
    signature=signature,
    pip_requirements=[
        "langchain>=0.2.0",
        "langchain-openai>=0.1.0",
        "openai>=1.0.0",
        # Pin versions to avoid surprises!
    ],
    # OR use conda environment
    conda_env={
        "dependencies": [
            "python=3.10",
            {"pip": ["langchain>=0.2.0", "openai>=1.0.0"]}
        ]
    },
)
```

### Test Before Registering

Always test locally before pushing to UC:

```python
# Load the logged model (not registered yet)
loaded_agent = mlflow.pyfunc.load_model(model_info.model_uri)

# Test with example input
result = loaded_agent.predict({
    "messages": [{"role": "user", "content": "Hello!"}]
})
print(result)  # Verify output format matches expected schema

# Only then register to UC
mlflow.register_model(model_info.model_uri, "catalog.schema.my_agent")
```

---

## Overview

Agent serving enables you to deploy:
- **LangChain/LangGraph agents** with tools and memory
- **RAG applications** with vector search and retrieval
- **Custom Python agents** with arbitrary logic
- **Multi-turn conversational agents** with session state

Agents are deployed as MLflow PyFunc models with a chat interface.

---

## Agent Deployment Workflow

```
1. Define agent (LangChain, custom Python)
        ↓
2. Log agent to MLflow with mlflow.langchain or mlflow.pyfunc
        ↓
3. Register to Unity Catalog
        ↓
4. Create serving endpoint
        ↓
5. Query via chat API
```

---

## LangChain Agent Deployment

### Simple LangChain Agent

```python
import mlflow
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# Define tools
@tool
def get_weather(location: str) -> str:
    """Get current weather for a location."""
    return f"Weather in {location}: 72°F, sunny"

@tool
def search_database(query: str) -> str:
    """Search the company database."""
    return f"Found 3 results for: {query}"

# Create agent
llm = ChatOpenAI(model="gpt-4o")
tools = [get_weather, search_database]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with access to tools."),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Log to MLflow
mlflow.set_registry_uri("databricks-uc")

with mlflow.start_run():
    model_info = mlflow.langchain.log_model(
        lc_model=agent_executor,
        artifact_path="agent",
        registered_model_name="catalog.schema.weather_agent",
        input_example={"input": "What's the weather in NYC?"},
    )
```

### Deploy LangChain Agent

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="weather-agent",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                entity_name="catalog.schema.weather_agent",
                entity_version="1",
                workload_size="Small",
                scale_to_zero_enabled=True,
                environment_vars={
                    # Pass API keys for tools/LLMs
                    "OPENAI_API_KEY": "{{secrets/llm-keys/openai-key}}",
                },
            )
        ]
    ),
)
```

---

## LangGraph Agent Deployment

### Define LangGraph Agent

```python
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from typing import TypedDict, Annotated, Sequence
import operator

# Define state
class AgentState(TypedDict):
    messages: Annotated[Sequence[HumanMessage | AIMessage], operator.add]
    next_step: str

# Define nodes
def call_model(state: AgentState) -> AgentState:
    llm = ChatOpenAI(model="gpt-4o")
    response = llm.invoke(state["messages"])
    return {"messages": [response], "next_step": "end"}

def should_continue(state: AgentState) -> str:
    return state.get("next_step", "end")

# Build graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"end": END})

app = workflow.compile()

# Log to MLflow
with mlflow.start_run():
    mlflow.langchain.log_model(
        lc_model=app,
        artifact_path="agent",
        registered_model_name="catalog.schema.langgraph_agent",
    )
```

---

## Custom Python Agent (PyFunc)

For full control, use MLflow PyFunc:

```python
import mlflow
from mlflow.pyfunc import PythonModel
import pandas as pd

class CustomAgent(PythonModel):
    def load_context(self, context):
        """Load model artifacts and initialize resources."""
        import openai
        import os
        
        # Initialize LLM client
        self.client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        
        # Load any artifacts (e.g., prompts, configs)
        # self.config = json.load(open(context.artifacts["config"]))
    
    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        """
        Handle chat requests.
        
        Input DataFrame columns:
        - messages: List of {"role": str, "content": str}
        
        Output DataFrame columns:
        - response: str (assistant's response)
        """
        results = []
        
        for _, row in model_input.iterrows():
            messages = row["messages"]
            
            # Your custom agent logic here
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
            )
            
            results.append({
                "response": response.choices[0].message.content
            })
        
        return pd.DataFrame(results)

# Log to MLflow
with mlflow.start_run():
    mlflow.pyfunc.log_model(
        artifact_path="agent",
        python_model=CustomAgent(),
        registered_model_name="catalog.schema.custom_agent",
        pip_requirements=[
            "openai>=1.0",
            "pandas",
        ],
        input_example=pd.DataFrame({
            "messages": [[{"role": "user", "content": "Hello!"}]]
        }),
    )
```

---

## RAG Agent Deployment

### RAG with Vector Search

```python
from langchain_community.vectorstores import DatabricksVectorSearch
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.chains import RetrievalQA

# Setup vector store
embeddings = OpenAIEmbeddings()
vectorstore = DatabricksVectorSearch(
    endpoint="my-vs-endpoint",
    index_name="catalog.schema.documents_index",
    embedding=embeddings,
    text_column="content",
)

# Create RAG chain
llm = ChatOpenAI(model="gpt-4o")
rag_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=vectorstore.as_retriever(search_kwargs={"k": 5}),
)

# Log to MLflow
with mlflow.start_run():
    mlflow.langchain.log_model(
        lc_model=rag_chain,
        artifact_path="rag_agent",
        registered_model_name="catalog.schema.rag_agent",
    )
```

---

## Agent Input/Output Schemas

### Chat Schema (Recommended)

Agents should accept chat messages format:

```python
# Input
{
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "What's 2+2?"}
    ]
}

# Output
{
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "2+2 equals 4."
            }
        }
    ]
}
```

### Query Endpoint with Chat Messages

```python
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

response = w.serving_endpoints.query(
    name="my-agent",
    messages=[
        ChatMessage(role=ChatMessageRole.SYSTEM, content="You are a helpful assistant."),
        ChatMessage(role=ChatMessageRole.USER, content="What's the weather in NYC?"),
    ],
)

print(response.choices[0].message.content)
```

---

## Agent with MLflow Tracing

Enable tracing for observability:

```python
import mlflow

# Enable autologging with tracing
mlflow.langchain.autolog(log_traces=True)

# Or manual tracing
@mlflow.trace
def my_agent_function(query: str) -> str:
    # Your agent logic
    with mlflow.start_span("retrieval") as span:
        docs = retrieve_documents(query)
        span.set_inputs({"query": query})
        span.set_outputs({"num_docs": len(docs)})
    
    with mlflow.start_span("generation") as span:
        response = generate_response(query, docs)
        span.set_inputs({"query": query, "context": docs})
        span.set_outputs({"response": response})
    
    return response
```

---

## Agent Environment Variables

Pass secrets and configuration at runtime:

```python
ServedEntityInput(
    entity_name="catalog.schema.my_agent",
    entity_version="1",
    workload_size="Medium",
    environment_vars={
        # LLM API keys
        "OPENAI_API_KEY": "{{secrets/llm-keys/openai-key}}",
        "ANTHROPIC_API_KEY": "{{secrets/llm-keys/anthropic-key}}",
        
        # Vector search configuration
        "VS_ENDPOINT": "my-vs-endpoint",
        "VS_INDEX": "catalog.schema.documents_index",
        
        # Application config
        "LOG_LEVEL": "INFO",
        "MAX_RETRIES": "3",
        
        # Database connections
        "DATABASE_URL": "{{secrets/db/connection-string}}",
    },
)
```

---

## Multi-Agent Deployment

Deploy multiple agent versions for A/B testing:

```python
from databricks.sdk.service.serving import TrafficConfig, Route

endpoint = w.serving_endpoints.create_and_wait(
    name="multi-agent",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                name="agent-v1",
                entity_name="catalog.schema.my_agent",
                entity_version="1",
                workload_size="Small",
            ),
            ServedEntityInput(
                name="agent-v2",
                entity_name="catalog.schema.my_agent",
                entity_version="2",
                workload_size="Small",
            ),
        ],
        traffic_config=TrafficConfig(
            routes=[
                Route(served_model_name="agent-v1", traffic_percentage=90),
                Route(served_model_name="agent-v2", traffic_percentage=10),
            ]
        ),
    ),
)
```

---

## Agent with Tool Calling

### Define Tools for Serving

```python
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun

@tool
def query_database(sql: str) -> str:
    """Execute SQL query against the data warehouse."""
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    result = w.statement_execution.execute_statement(
        warehouse_id=os.environ["WAREHOUSE_ID"],
        statement=sql,
    )
    return str(result.result.data_array[:10])

@tool  
def get_customer_info(customer_id: str) -> dict:
    """Retrieve customer information by ID."""
    # Query Unity Catalog table
    return {"customer_id": customer_id, "name": "John Doe", "tier": "Gold"}

# Web search
search_tool = DuckDuckGoSearchRun()

tools = [query_database, get_customer_info, search_tool]
```

---

## GPU Configuration for Agents

For agents with local model inference:

```python
ServedEntityInput(
    entity_name="catalog.schema.local_llm_agent",
    entity_version="1",
    workload_type="GPU_MEDIUM",  # A10G GPU
    workload_size="Small",
    scale_to_zero_enabled=False,  # Keep warm
    environment_vars={
        "MODEL_PATH": "/dbfs/models/llama-7b",
        "DEVICE": "cuda",
    },
)
```

---

## Inference Tables for Agent Monitoring

Enable logging of all agent requests/responses:

```python
from databricks.sdk.service.serving import AiGatewayConfig, AiGatewayInferenceTableConfig

endpoint = w.serving_endpoints.create_and_wait(
    name="monitored-agent",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                entity_name="catalog.schema.my_agent",
                entity_version="1",
                workload_size="Small",
            )
        ],
    ),
    ai_gateway=AiGatewayConfig(
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name="catalog",
            schema_name="schema",
            table_name_prefix="agent_logs",
            enabled=True,
        ),
    ),
)
```

Query the inference table:
```sql
SELECT 
    request_id,
    timestamp,
    request,
    response,
    latency_ms
FROM catalog.schema.agent_logs_request_response
WHERE timestamp > current_date() - INTERVAL 1 DAY
```

---

## Best Practices

1. **Use chat message format** for consistent input/output
2. **Enable MLflow tracing** for debugging and observability
3. **Pass secrets via environment_vars** - never hardcode
4. **Test locally first** before deploying to endpoint
5. **Use inference tables** to monitor agent behavior
6. **Implement error handling** in your agent code
7. **Set appropriate timeouts** for tool calls
8. **Version your agents** for rollback capability
9. **Use GPU only when needed** (local LLM inference)
10. **Cache tool results** when appropriate

---

## Testing Agents Locally

Before deploying, test with MLflow:

```python
import mlflow

# Load registered model
agent = mlflow.pyfunc.load_model("models:/catalog.schema.my_agent/1")

# Test prediction
result = agent.predict({
    "messages": [{"role": "user", "content": "Hello!"}]
})
print(result)
```

---

## Common Packaging Mistakes

### Mistake 1: No Signature

```python
# WRONG - no signature, deployment will fail
mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),
)

# CORRECT - always include signature
from mlflow.models import infer_signature

signature = infer_signature(
    {"messages": [{"role": "user", "content": "test"}]},
    {"choices": [{"message": {"role": "assistant", "content": "response"}}]}
)

mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),
    signature=signature,
    input_example={"messages": [{"role": "user", "content": "test"}]},
)
```

### Mistake 2: Wrong Input Format in predict()

```python
# WRONG - expects dict but serving sends DataFrame
class BadAgent(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input):
        messages = model_input["messages"]  # Fails!

# CORRECT - handle DataFrame input
class GoodAgent(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input):
        # model_input is a pandas DataFrame
        if isinstance(model_input, pd.DataFrame):
            messages = model_input.iloc[0]["messages"]
        else:
            messages = model_input.get("messages", [])
        # ... process messages
```

### Mistake 3: Missing Dependencies

```python
# WRONG - missing langchain dependency
mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),  # Uses langchain internally
    pip_requirements=["openai"],  # Forgot langchain!
)

# CORRECT - list ALL dependencies
mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),
    pip_requirements=[
        "langchain>=0.2.0",
        "langchain-openai>=0.1.0",
        "langchain-community>=0.2.0",
        "openai>=1.0.0",
    ],
)
```

### Mistake 4: Hardcoded Secrets

```python
# WRONG - secret in code (won't work in serving)
class BadAgent(mlflow.pyfunc.PythonModel):
    def __init__(self):
        self.api_key = "sk-abc123..."  # Exposed!

# CORRECT - read from environment
class GoodAgent(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import os
        self.api_key = os.environ["OPENAI_API_KEY"]  # Injected by serving
```

### Mistake 5: Not Setting Registry URI

```python
# WRONG - logs to local MLflow, not Unity Catalog
mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),
    registered_model_name="my_agent",  # Goes to local registry!
)

# CORRECT - set UC registry first
mlflow.set_registry_uri("databricks-uc")  # Required!

mlflow.pyfunc.log_model(
    artifact_path="agent",
    python_model=MyAgent(),
    registered_model_name="catalog.schema.my_agent",  # Full UC path
)
```

### Mistake 6: Wrong Output Format

```python
# WRONG - returns string (doesn't match chat schema)
class BadAgent(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input):
        return "Hello!"  # Wrong format!

# CORRECT - return chat-compatible dict
class GoodAgent(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input):
        response = "Hello!"
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": response
                }
            }]
        }
```

---

## Common Issues

### Packaging & Registration Issues

| Issue | Solution |
|-------|----------|
| **"Signature missing"** | Add `signature` parameter to log_model() |
| **"Model not found in UC"** | Set `mlflow.set_registry_uri("databricks-uc")` before logging |
| **Wrong UC path format** | Use `catalog.schema.model_name`, not just `model_name` |
| **"ModuleNotFoundError" in serving** | Add missing package to `pip_requirements` |
| **"Invalid input" errors** | Check signature matches actual input format |
| **Model works locally, fails in serving** | Test with `mlflow.pyfunc.load_model()` first |

### Deployment & Runtime Issues

| Issue | Solution |
|-------|----------|
| **"Missing API key"** | Add to environment_vars with secrets reference |
| **Endpoint stuck PENDING** | Check build logs: `get_serving_endpoint_logs` |
| **Agent timeout** | Increase request timeout, optimize tool calls |
| **Memory errors** | Increase workload_size, reduce context |
| **Tool execution fails** | Check tool has access to required resources |
| **Tracing not working** | Ensure mlflow.langchain.autolog() is called |
| **Version mismatch** | Pin dependency versions in pip_requirements |
| **Cold start slow** | Disable scale_to_zero or use keep-warm requests |
| **Vector search fails** | Verify VS endpoint accessible from serving compute |
| **Secrets not found** | Check secret scope/key exists and endpoint has permission |
