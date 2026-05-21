# Custom GenAI agents with MLflow ResponsesAgent

Edge case. **For most demos, use [databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — pre-built Knowledge Assistants and Supervisor Agents wire up Genie + KAs + tools without any agent code. Hand-roll a `ResponsesAgent` only when you need a custom orchestration the supervisor can't express (custom routing logic, multi-step plans, agent that calls another agent over HTTP).

## What ResponsesAgent is

MLflow 3's standardized agent interface. OpenAI-compatible request/response (`{input: [{role, content}]}` → `{output: [...]}`). Supports streaming. Logs with `python_model="agent.py"` (file-based) and deploys via `databricks.agents.deploy()` to a serving endpoint with built-in tracing and eval hooks.

## Full example: LangGraph agent with UC Function + Vector Search tools

Project layout:

```
my_agent/
├── agent.py          # LangGraphAgent + tools + mlflow.models.set_model(...)
├── log_model.py      # Logs with resources= for auto-auth, registers to UC
└── deploy_agent.py   # Submitted as a job because deploy takes ~15 min
```

```python
# agent.py
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest, ResponsesAgentResponse, ResponsesAgentStreamEvent,
    output_to_responses_items_stream, to_chat_completions_input,
)
from databricks_langchain import (
    ChatDatabricks, UCFunctionToolkit, VectorSearchRetrieverTool,
)
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt.tool_node import ToolNode
from typing import Annotated, Generator, Sequence, TypedDict

LLM_ENDPOINT = "databricks-claude-sonnet-4-6"   # resolve at runtime — see SKILL.md
VS_INDEX     = "ai_demo_gen.wind_farm.docs_index"
UC_FUNCTIONS = ["ai_demo_gen.wind_farm.lookup_turbine_history"]
SYSTEM_PROMPT = (
    "You are a turbine ops assistant. Use lookup_turbine_history for hardware "
    "history queries, the docs retriever for procedure questions."
)

class State(TypedDict):
    messages: Annotated[Sequence, add_messages]

class TurbineAgent(ResponsesAgent):
    def __init__(self):
        self.llm = ChatDatabricks(endpoint=LLM_ENDPOINT, temperature=0.1)
        # Tools — UC functions and Vector Search both come from databricks_langchain.
        self.tools = list(UCFunctionToolkit(function_names=UC_FUNCTIONS).tools)
        self.vs_tool = VectorSearchRetrieverTool(
            index_name=VS_INDEX, num_results=5,
            columns=["content", "doc_uri", "title"],
        )
        self.tools.append(self.vs_tool)
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    def _graph(self):
        def call_model(state):
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + state["messages"]
            return {"messages": [self.llm_with_tools.invoke(msgs)]}
        def should_continue(state):
            last = state["messages"][-1]
            return "tools" if isinstance(last, AIMessage) and last.tool_calls else "end"

        g = StateGraph(State)
        g.add_node("agent", RunnableLambda(call_model))
        g.add_node("tools", ToolNode(self.tools))
        g.set_entry_point("agent")
        g.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
        g.add_edge("tools", "agent")
        return g.compile()

    def predict_stream(self, req: ResponsesAgentRequest) -> Generator[ResponsesAgentStreamEvent, None, None]:
        msgs = to_chat_completions_input([m.model_dump() for m in req.input])
        for kind, payload in self._graph().stream({"messages": msgs}, stream_mode=["updates"]):
            if kind != "updates": continue
            for node in payload.values():
                if node.get("messages"):
                    yield from output_to_responses_items_stream(node["messages"])

    def predict(self, req: ResponsesAgentRequest) -> ResponsesAgentResponse:
        items = [ev.item for ev in self.predict_stream(req)
                 if ev.type == "response.output_item.done"]
        return ResponsesAgentResponse(output=items)

mlflow.langchain.autolog()
mlflow.models.set_model(TurbineAgent())
```

### CRITICAL: output items must use helper methods

The supervisor will silently drop your output if you return raw dicts:

```python
# WRONG — raw dicts silently fail
return ResponsesAgentResponse(output=[{"role": "assistant", "content": "..."}])

# CORRECT
return ResponsesAgentResponse(output=[
    self.create_text_output_item(text="...", id="msg_1"),
])
```

Three helpers on `ResponsesAgent`:
- `self.create_text_output_item(text, id)` — text response.
- `self.create_function_call_item(id, call_id, name, arguments)` — tool call.
- `self.create_function_call_output_item(call_id, output)` — tool result.

LangGraph's `output_to_responses_items_stream` (used above) emits these correctly, so the helpers are mainly relevant when hand-building events.

## Log + register

The non-obvious bit: `resources=[...]` is mandatory for auto-passthrough auth. Without it the deployed endpoint has no creds for the LLM, the UC functions, or the Vector Search index — every query returns `PERMISSION_DENIED` and the error doesn't explain why.

```python
# log_model.py
import mlflow
from mlflow.models.resources import (
    DatabricksServingEndpoint, DatabricksFunction, DatabricksVectorSearchIndex,
)
from mlflow.tracking import MlflowClient
from agent import LLM_ENDPOINT, VS_INDEX, UC_FUNCTIONS

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/me@example.com/turbine_agent")

FULL_NAME = "ai_demo_gen.wind_farm.turbine_agent"

resources = [
    DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT),
    DatabricksVectorSearchIndex(index_name=VS_INDEX),
    *[DatabricksFunction(function_name=f) for f in UC_FUNCTIONS],
]

with mlflow.start_run():
    info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",         # file path; agent.py calls set_model()
        resources=resources,             # auto-auth — DO NOT skip
        input_example={"input": [{"role": "user", "content": "What's the maintenance history for turbine WTG-12?"}]},
        pip_requirements=[
            "mlflow==2.22.0",
            "databricks-langchain",
            "langgraph==0.3.4",
            "databricks-agents",
            "pydantic>=2",
        ],
        registered_model_name=FULL_NAME,
    )

# Pre-deploy validation — rebuild the env, run a request, surface failures early.
mlflow.models.predict(
    model_uri=info.model_uri,
    input_data={"input": [{"role": "user", "content": "ping"}]},
    env_manager="uv",
)

client = MlflowClient(registry_uri="databricks-uc")
v = max(client.search_model_versions(f"name='{FULL_NAME}'"), key=lambda x: int(x.version)).version
client.set_registered_model_alias(FULL_NAME, "prod", v)
```

### Resources that need passthrough auth

| Resource | Import (`mlflow.models.resources`) |
|---|---|
| Foundation Model API / custom serving endpoint | `DatabricksServingEndpoint(endpoint_name=...)` |
| UC SQL/Python function | `DatabricksFunction(function_name=...)` |
| Vector Search index | `DatabricksVectorSearchIndex(index_name=...)` |
| Lakebase Postgres | `DatabricksLakebase(database_instance_name=...)` |

Anything the agent calls that isn't covered here will hit auth errors at the endpoint.

## Deploy (async job, ~15 min)

`databricks.agents.deploy()` blocks for ~15 minutes — don't run it inline from the CLI. Submit as a serverless job so the chat session doesn't hold the connection.

```python
# deploy_agent.py
import json, sys
from databricks import agents

model_name    = sys.argv[1]
version       = sys.argv[2]
endpoint_name = sys.argv[3] if len(sys.argv) > 3 else None

# Always pass endpoint_name explicitly — auto-derived names are
# `agents_<catalog>-<schema>-<model>` with dots → dashes, which is unpredictable.
kwargs = {"tags": {"aidevkit_project": "ai-dev-kit"}}
if endpoint_name:
    kwargs["endpoint_name"] = endpoint_name

deployment = agents.deploy(model_name, version, **kwargs)

# Land structured output via dbutils.notebook.exit — print() unreliable on serverless.
dbutils.notebook.exit(json.dumps({
    "endpoint_name":  deployment.endpoint_name,
    "query_endpoint": deployment.query_endpoint,
}))
```

Submit via `databricks jobs submit --no-wait --json '{...}'`; full job pattern (including the `spec.client: "4"` requirement and the TASK-run-id vs submit-run-id trap on `get-run-output`) is in [databricks-jobs](../databricks-jobs/SKILL.md).

## Query

```bash
databricks serving-endpoints query turbine-agent-endpoint --json '{
  "messages": [{"role": "user", "content": "What is the maintenance history for WTG-12?"}],
  "max_tokens": 800
}'
```

OpenAI-compatible client also works:

```python
from openai import OpenAI
client = OpenAI(
    base_url=f"{WORKSPACE_URL}/serving-endpoints/turbine-agent-endpoint",
    api_key=DATABRICKS_TOKEN,
)
client.chat.completions.create(
    model="turbine-agent-endpoint",
    messages=[{"role": "user", "content": "..."}],
)
```

## Iteration loop

Once `agent.py` is uploaded to the workspace, rerunning is fast:

```bash
databricks workspace import-dir ./my_agent /Workspace/Users/$USER/my_agent --overwrite
# Then re-run log_model.py via jobs submit (~30s), and only re-deploy if you
# want a new endpoint version (~15min). Most iterations don't need re-deploy —
# `agents.deploy()` with a new version updates the existing endpoint in place.
```

## Packages

- DBR 16.1+ has `mlflow` 3.x, `langchain`, `pydantic`, `databricks-sdk` pre-installed. You usually only need `%pip install -q databricks-langchain langgraph databricks-agents`.
- Pin `mlflow`, `langgraph`, and `databricks-agents` exactly in `pip_requirements` — version drift between training notebook and endpoint env is the #1 cause of "model loaded fine locally but the endpoint crashes at startup".
