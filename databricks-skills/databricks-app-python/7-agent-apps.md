# Deploying AI Agents as Databricks Apps

Databricks supports two deployment paths for AI agents. This guide covers deploying agents as Databricks Apps (recommended for new projects) and provides a reference to Model Serving for traditional deployments.

**Docs**: https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent

---

## Deployment Paths: Apps vs Model Serving

| Criteria | Databricks Apps (recommended) | Model Serving (traditional) |
|----------|-------------------------------|----------------------------|
| **Best for** | New agents, rapid iteration, custom UIs | Auto-scaling endpoints, inference tables, A/B testing |
| **Deployment** | `databricks bundle deploy` (DABs) | `agents.deploy()` via MLflow |
| **Versioning** | Git-based via DABs | UC model registry versions |
| **Frontend** | Built-in chat UI (auto-bundled) | AI Playground or custom client |
| **Agent interface** | `@invoke()` / `@stream()` module-level functions | `ResponsesAgent` class with `predict()` / `predict_stream()` |
| **Async support** | Native `async def` + `await` (recommended) | Not available |
| **Local development** | Full local dev/debug cycle | Limited (notebook-based) |
| **Compute** | App runtime (2 vCPU, 6 GB) | Serverless or provisioned |
| **Tracing** | MLflow tracing (auto-configured) | MLflow tracing (auto-configured) |
| **Auth** | OAuth token required | OAuth or PAT |
| **Query endpoint** | `<app-url>.databricksapps.com/responses` | `/serving-endpoints/<name>/invocations` |

**Decision guide**: Use **Apps** when you need rapid iteration, a built-in chat UI, git-based versioning, or async request handling. Use **Model Serving** when you need auto-scaling to zero, inference tables for monitoring, traffic splitting (A/B testing), or integration with `ai_query()` SQL function. See [databricks-model-serving/3-genai-agents.md](../databricks-model-serving/3-genai-agents.md) for Model Serving details.

---

## Path 1: Agents as Databricks Apps (Recommended)

### Project Structure

Agent apps use Databricks Asset Bundles (DABs) for deployment:

```
my-agent-app/
├── agent.py              # Agent logic with @invoke() and @stream()
├── app.yaml              # App runtime configuration
├── databricks.yml        # DABs config with resources
├── pyproject.toml        # Python dependencies
├── requirements.txt      # Additional pip dependencies
└── input_example.json    # Test payload for local development
```

### Agent Code: @invoke() and @stream()

On Databricks Apps, the MLflow `AgentServer` serves module-level functions decorated with `@invoke()` (non-streaming) and `@stream()` (streaming). This replaces the class-based `ResponsesAgent.predict()` pattern used in Model Serving.

**Async pattern (recommended)** -- handles multiple requests concurrently:

```python
# agent.py
import mlflow
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from databricks_langchain import ChatDatabricks
from typing import AsyncGenerator

LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
SYSTEM_PROMPT = "You are a helpful assistant."

# Initialize LLM
llm = ChatDatabricks(endpoint=LLM_ENDPOINT)

@invoke
async def handle_request(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    """Non-streaming invocation."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in request.input]
    response = await llm.ainvoke(messages)
    return ResponsesAgentResponse(
        output=[mlflow.pyfunc.ResponsesAgent.create_text_output_item(
            text=response.content, id="msg_1"
        )]
    )

@stream
async def handle_stream(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    """Streaming invocation."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in request.input]
    
    collected = []
    async for chunk in llm.astream(messages):
        collected.append(chunk.content)
    
    full_text = "".join(collected)
    yield ResponsesAgentStreamEvent(
        type="response.output_item.done",
        item=mlflow.pyfunc.ResponsesAgent.create_text_output_item(
            text=full_text, id="msg_1"
        ),
    )
```

**Sync pattern** -- for minimal migration or synchronous-only libraries:

```python
# agent.py
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from databricks_langchain import ChatDatabricks
from typing import Generator

llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

@invoke
def handle_request(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    messages = [{"role": m.role, "content": m.content} for m in request.input]
    response = llm.invoke(messages)
    return ResponsesAgentResponse(
        output=[mlflow.pyfunc.ResponsesAgent.create_text_output_item(
            text=response.content, id="msg_1"
        )]
    )

@stream
def handle_stream(
    request: ResponsesAgentRequest,
) -> Generator[ResponsesAgentStreamEvent, None, None]:
    result = handle_request(request)
    for item in result.output:
        yield ResponsesAgentStreamEvent(
            type="response.output_item.done", item=item
        )
```

### Configuration: databricks.yml

Declare agent resources in `databricks.yml` using DABs syntax. This replaces the `MLmodel` resource declarations used in Model Serving.

```yaml
# databricks.yml
bundle:
  name: my-agent-app

resources:
  apps:
    my-agent:
      name: my-agent-app
      description: "My AI agent deployed as a Databricks App"
      source_code_path: .
      config:
        # Serving endpoint for LLM
        - name: DATABRICKS_MODEL_SERVING_ENDPOINT
          value_from:
            serving_endpoint: databricks-meta-llama-3-3-70b-instruct
        # Vector search index (optional, for RAG)
        - name: DATABRICKS_VECTOR_SEARCH_INDEX
          value_from:
            vector_search_index: catalog.schema.my_index
        # Secret (optional, for API keys)
        - name: MY_API_KEY
          value_from:
            secret:
              scope: my-scope
              key: api-key

targets:
  dev:
    mode: development
    default: true
  prod:
    mode: production
```

### Configuration: app.yaml

The `app.yaml` defines the app runtime command:

```yaml
# app.yaml
command:
  - "mlflow"
  - "genai"
  - "agent-server"
  - "--module"
  - "agent"
```

### Deploy with DABs

```bash
# Validate configuration
databricks bundle validate -t dev

# Deploy the agent app
databricks bundle deploy -t dev

# Start the app (required after first deployment)
databricks bundle run my-agent -t dev

# Check app status
databricks apps get my-agent-app
```

### Built-in Chat UI

Agent apps automatically include a chat frontend. The template fetches and bundles a chat app alongside your agent -- no additional setup required. Access the chat UI at the app URL returned by `databricks apps get`.

---

## Agent Templates

Databricks provides pre-built templates in [github.com/databricks/app-templates](https://github.com/databricks/app-templates):

| Template | Description |
|----------|-------------|
| `agent-openai-agents-sdk` | OpenAI Agents SDK with code interpreter tool |
| `agent-openai-agents-sdk-short-term-memory` | Conversational agent with Lakebase-backed session memory |
| `agent-openai-agents-sdk-multiagent` | Multi-agent orchestrator scaffolding |
| `agent-langgraph-short-term-memory` | LangGraph agent with conversation context |
| `agent-langgraph-long-term-memory` | LangGraph agent with persistent memory |

### Clone and customize a template

```bash
# Clone the templates repo
git clone https://github.com/databricks/app-templates.git

# Copy the template you want
cp -r app-templates/agent-openai-agents-sdk my-agent-app
cd my-agent-app

# Customize agent.py, databricks.yml, then deploy
databricks bundle deploy -t dev
databricks bundle run my-agent -t dev
```

---

## Tool Integration for Agent Apps

Agent apps support the same tool types as Model Serving agents. Declare resources in `databricks.yml` so the app's service principal gets automatic access.

### UC Functions

```python
from databricks_langchain import UCFunctionToolkit

uc_toolkit = UCFunctionToolkit(
    function_names=["catalog.schema.my_function", "system.ai.python_exec"]
)
tools = uc_toolkit.tools
```

Add to `databricks.yml`:

```yaml
config:
  - name: UC_FUNCTION_NAMES
    value: "catalog.schema.my_function"
```

### Vector Search (RAG)

```python
from databricks_langchain import VectorSearchRetrieverTool

vs_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.docs_index",
    num_results=5,
)
tools = [vs_tool]
```

Add to `databricks.yml`:

```yaml
config:
  - name: DATABRICKS_VECTOR_SEARCH_INDEX
    value_from:
      vector_search_index: catalog.schema.docs_index
```

### Managed MCP Servers

Databricks managed MCP servers connect agents to Unity Catalog data, Vector Search, and Genie spaces with built-in permission enforcement.

**Docs**: https://docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp

### External MCP Servers and REST APIs

Agents can connect to external MCP servers (GitHub, Glean, etc.) via managed OAuth. Databricks handles OAuth flows and token refresh automatically -- no exposed credentials.

**Docs**: https://docs.databricks.com/aws/en/generative-ai/mcp/external-mcp

### Custom Python Tools

Use the `@tool` decorator from LangChain for custom business logic:

```python
from langchain_core.tools import tool

@tool
def lookup_customer(customer_id: str) -> str:
    """Look up customer details by ID."""
    # Custom logic -- runs inside the app runtime
    return f"Customer {customer_id}: Active, Premium tier"

tools = [lookup_customer]
```

For complete tool integration patterns (combining UC Functions, Vector Search, and custom tools), see [databricks-model-serving/4-tools-integration.md](../databricks-model-serving/4-tools-integration.md).

---

## LangGraph Agent on Apps

For agents with tools and complex control flow, use LangGraph with the `@invoke()` / `@stream()` pattern:

```python
# agent.py
import mlflow
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    output_to_responses_items_stream,
    to_chat_completions_input,
)
from databricks_langchain import ChatDatabricks, UCFunctionToolkit
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt.tool_node import ToolNode
from typing import Annotated, AsyncGenerator, Sequence, TypedDict

LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
SYSTEM_PROMPT = "You are a helpful assistant with access to tools."

# State
class AgentState(TypedDict):
    messages: Annotated[Sequence, add_messages]

# Tools
tools = []
# uc_toolkit = UCFunctionToolkit(function_names=["catalog.schema.*"])
# tools.extend(uc_toolkit.tools)

# LLM
llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
llm_with_tools = llm.bind_tools(tools) if tools else llm

def _build_graph():
    def should_continue(state):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "end"

    def call_model(state):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + state["messages"]
        return {"messages": [llm_with_tools.invoke(messages)]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", RunnableLambda(call_model))

    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    graph.set_entry_point("agent")
    return graph.compile()

@invoke
async def handle_request(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs = []
    async for event in handle_stream(request):
        if event.type == "response.output_item.done":
            outputs.append(event.item)
    return ResponsesAgentResponse(output=outputs)

@stream
async def handle_stream(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    messages = to_chat_completions_input([m.model_dump() for m in request.input])
    graph = _build_graph()

    for event in graph.stream({"messages": messages}, stream_mode=["updates"]):
        if event[0] == "updates":
            for node_data in event[1].values():
                if node_data.get("messages"):
                    for item in output_to_responses_items_stream(node_data["messages"]):
                        yield item
```

---

## Authentication and User Auth

### App auth (service principal)

Agent apps get a dedicated service principal. Credentials (`DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`) are auto-injected. The SDK `Config()` detects them automatically. See [1-authorization.md](1-authorization.md) for details.

### User auth forwarding

Forward the user's identity for per-user access control (Unity Catalog row/column filters, audit trails):

```python
from fastapi import Request

@invoke
async def handle_request(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    # Access user context from the request
    user_id = request.context.user_id if request.context else None
    # Use for personalization, per-user data access, etc.
```

### Resource permissions

Resources declared in `databricks.yml` automatically grant the app's service principal the required permissions:
- **Serving endpoint**: Can query
- **Vector search index**: USE CATALOG + USE SCHEMA + SELECT
- **Secret**: Can read
- **UC function**: Can execute

---

## Querying Deployed Agent Apps

### Databricks OpenAI Client (recommended)

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
client = w.serving_endpoints.get_open_ai_client()

response = client.responses.create(
    model="my-agent-app",
    input="What is Databricks?"
)
print(response.output_text)
```

### REST API (curl)

```bash
curl -X POST "https://<app-url>.databricksapps.com/responses" \
  -H "Authorization: Bearer $(databricks auth token)" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"role": "user", "content": "What is Databricks?"}]
  }'
```

### MCP tool

```
create_or_update_app(
    name="my-agent-app",
    description="AI agent with RAG capabilities",
    source_code_path="/Workspace/Users/user@example.com/my-agent-app"
)
```

For app lifecycle management via MCP, see [6-mcp-approach.md](6-mcp-approach.md).

---

## Local Development and Testing

### Test locally

```bash
# Start the agent server locally
mlflow genai agent-server --module agent

# Test with curl
curl -X POST http://localhost:5000/invocations \
  -H "Content-Type: application/json" \
  -d @input_example.json
```

### input_example.json

```json
{
  "input": [{"role": "user", "content": "Hello, what can you help me with?"}]
}
```

### Debug a deployed agent

```bash
# Check app logs
databricks apps logs my-agent-app

# Get app status and URL
databricks apps get my-agent-app
```

**Docs**: https://docs.databricks.com/aws/en/generative-ai/agent-framework/debug-agent

---

## Migrating from Model Serving to Apps

If you have an existing `ResponsesAgent` class deployed on Model Serving, migration is straightforward:

1. **Extract** `predict()` logic into an `@invoke()` function
2. **Extract** `predict_stream()` logic into a `@stream()` function
3. **Convert** to async (recommended) using `async def` and `await`
4. **Move** resource declarations from `MLmodel` to `databricks.yml`
5. **Test** locally with `mlflow genai agent-server --module agent`
6. **Deploy** with `databricks bundle deploy`

**Before (Model Serving)**:
```python
class MyAgent(ResponsesAgent):
    def predict(self, request):
        response = self.llm.invoke(messages)
        return ResponsesAgentResponse(output=[...])
```

**After (Databricks Apps)**:
```python
@invoke
async def handle_request(request):
    response = await llm.ainvoke(messages)
    return ResponsesAgentResponse(output=[...])
```

**Docs**: https://docs.databricks.com/aws/en/generative-ai/agent-framework/migrate-agent-to-apps

---

## ChatAgent Migration Note

`ChatAgent` is the legacy agent interface. Databricks recommends `ResponsesAgent` for all new agents.

Key differences:
- **ResponsesAgent**: Flat output items (`ResponsesAgentResponse.output`), OpenAI Responses API-compatible
- **ChatAgent**: Nested message-level `tool_calls` in `ChatAgentResponse`, Chat Completions API format

If you have an existing ChatAgent, migrate to ResponsesAgent first, then deploy as an App. See [databricks-model-serving/3-genai-agents.md](../databricks-model-serving/3-genai-agents.md) for the ResponsesAgent pattern.

---

## Multi-Agent Systems

Deploy supervisor + specialist agent architectures as a single App:

**Template**: `agent-openai-agents-sdk-multiagent` from [app-templates](https://github.com/databricks/app-templates)

**Docs**: https://docs.databricks.com/aws/en/generative-ai/agent-framework/multi-agent-apps

---

## Official Documentation

- **[Author and Deploy Agents on Apps](https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent)** -- main guide
- **[Create an AI Agent](https://docs.databricks.com/aws/en/generative-ai/agent-framework/create-agent)** -- agent creation patterns
- **[Query Deployed Agents](https://docs.databricks.com/aws/en/generative-ai/agent-framework/query-agent)** -- querying Apps and Model Serving
- **[Migrate to Apps](https://docs.databricks.com/aws/en/generative-ai/agent-framework/migrate-agent-to-apps)** -- migration guide
- **[Debug Agents](https://docs.databricks.com/aws/en/generative-ai/agent-framework/debug-agent)** -- debugging deployed agents
- **[Agent Tools](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)** -- UC Functions, Vector Search, MCP, custom tools
- **[Managed MCP Servers](https://docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp)** -- pre-configured MCP servers for Databricks data
- **[App Templates](https://github.com/databricks/app-templates)** -- production-ready agent templates
- **[Apps Cookbook](https://apps-cookbook.dev/)** -- recipes for data access patterns (not agent-specific)
