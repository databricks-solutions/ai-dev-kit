# GenAI Agents with ResponsesAgent

Build and deploy LLM-powered agents using MLflow 3's ResponsesAgent interface.

## ResponsesAgent Overview

`ResponsesAgent` is MLflow 3's recommended interface for building conversational agents. It provides:

- Standardized input/output format (OpenAI-compatible)
- Streaming support
- Integration with Databricks features (tracing, evaluation)

## Basic Agent Structure

```python
# agent.py
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from typing import Generator

class MyAgent(ResponsesAgent):
    def __init__(self):
        from databricks_langchain import ChatDatabricks
        self.llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
    
    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        """Non-streaming prediction."""
        messages = [{"role": m.role, "content": m.content} for m in request.input]
        response = self.llm.invoke(messages)
        # MUST use helper methods for output items
        return ResponsesAgentResponse(
            output=[self.create_text_output_item(text=response.content, id="msg_1")]
        )
    
    def predict_stream(
        self, request: ResponsesAgentRequest
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """Streaming prediction."""
        # Collect from non-streaming for simplicity
        result = self.predict(request)
        for item in result.output:
            yield ResponsesAgentStreamEvent(
                type="response.output_item.done",
                item=item
            )

# Export for MLflow
AGENT = MyAgent()
mlflow.models.set_model(AGENT)
```

## LangGraph Agent Pattern

For agents with tools and complex logic, use LangGraph:

```python
# agent.py
import mlflow
from mlflow.pyfunc import ResponsesAgent
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
from typing import Annotated, Any, Generator, Sequence, TypedDict

# Configuration
LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
SYSTEM_PROMPT = "You are a helpful assistant."

# State definition
class AgentState(TypedDict):
    messages: Annotated[Sequence, add_messages]

class LangGraphAgent(ResponsesAgent):
    def __init__(self):
        self.llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
        self.tools = []
        
        # Add UC Function tools
        # uc_toolkit = UCFunctionToolkit(function_names=["catalog.schema.function"])
        # self.tools.extend(uc_toolkit.tools)
        
        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm
    
    def _build_graph(self):
        def should_continue(state):
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and last.tool_calls:
                return "tools"
            return "end"
        
        def call_model(state):
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + state["messages"]
            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}
        
        graph = StateGraph(AgentState)
        graph.add_node("agent", RunnableLambda(call_model))
        
        if self.tools:
            graph.add_node("tools", ToolNode(self.tools))
            graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
            graph.add_edge("tools", "agent")
        else:
            graph.add_edge("agent", END)
        
        graph.set_entry_point("agent")
        return graph.compile()
    
    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        # Collect output items from streaming
        outputs = [
            event.item
            for event in self.predict_stream(request)
            if event.type == "response.output_item.done"
        ]
        return ResponsesAgentResponse(output=outputs)
    
    # Helper methods inherited from ResponsesAgent:
    # - self.create_text_output_item(text, id) - for text responses
    # - self.create_function_call_item(id, call_id, name, arguments) - for tool calls
    # - self.create_function_call_output_item(call_id, output) - for tool results
    
    def predict_stream(
        self, request: ResponsesAgentRequest
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        messages = to_chat_completions_input([m.model_dump() for m in request.input])
        graph = self._build_graph()
        
        for event in graph.stream({"messages": messages}, stream_mode=["updates"]):
            if event[0] == "updates":
                for node_data in event[1].values():
                    if node_data.get("messages"):
                        yield from output_to_responses_items_stream(node_data["messages"])

# Export
mlflow.langchain.autolog()
AGENT = LangGraphAgent()
mlflow.models.set_model(AGENT)
```

## Using Databricks-Hosted Models

```python
from databricks_langchain import ChatDatabricks

# Foundation Model APIs (pay-per-token)
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
llm = ChatDatabricks(endpoint="databricks-claude-3-7-sonnet")
llm = ChatDatabricks(endpoint="databricks-dbrx-instruct")

# Custom fine-tuned model endpoint
llm = ChatDatabricks(endpoint="my-finetuned-model-endpoint")

# With parameters
llm = ChatDatabricks(
    endpoint="databricks-meta-llama-3-3-70b-instruct",
    temperature=0.1,
    max_tokens=1000,
)
```

## ChatContext for User/Conversation Info

```python
from mlflow.types.responses import ResponsesAgentRequest, ChatContext

# Request with context
request = ResponsesAgentRequest(
    input=[{"role": "user", "content": "Hello!"}],
    context=ChatContext(
        user_id="user@company.com",
        conversation_id="conv-123"
    )
)

# Access in agent
class MyAgent(ResponsesAgent):
    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        user_id = request.context.user_id if request.context else None
        conv_id = request.context.conversation_id if request.context else None
        # Use for personalization, memory, etc.
```

## Testing the Agent Locally

```python
# test_agent.py
from agent import AGENT
from mlflow.types.responses import ResponsesAgentRequest, ChatContext

# Test request
request = ResponsesAgentRequest(
    input=[{"role": "user", "content": "What is Databricks?"}],
    context=ChatContext(user_id="test@example.com")
)

# Non-streaming
result = AGENT.predict(request)
print(result.model_dump(exclude_none=True))

# Streaming
for event in AGENT.predict_stream(request):
    print(event)
```

Run via MCP:

```
run_python_file_on_databricks(file_path="./my_agent/test_agent.py")
```

## Logging the Agent

See [6-logging-registration.md](6-logging-registration.md) for full details.

```python
import mlflow
from agent import AGENT, LLM_ENDPOINT
from mlflow.models.resources import DatabricksServingEndpoint

mlflow.set_registry_uri("databricks-uc")

resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",
        resources=resources,
        pip_requirements=[
            "mlflow==3.6.0",
            "databricks-langchain",
            "langgraph==0.3.4",
        ],
        input_example={
            "input": [{"role": "user", "content": "Hello!"}]
        },
        registered_model_name="main.agents.my_agent"
    )
```

## Deployment

See [7-deployment.md](7-deployment.md) for async job-based deployment.

```python
from databricks import agents

agents.deploy(
    "main.agents.my_agent", 
    version="1",
    tags={"source": "mcp"}
)
# Takes ~15 minutes
```

## Query Deployed Agent

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[{"role": "user", "content": "What is Databricks?"}],
    max_tokens=500
)
```
