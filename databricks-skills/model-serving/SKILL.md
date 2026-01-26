---
name: model-serving
description: "Deploy and manage Databricks Model Serving endpoints for custom ML models, foundation models (LLMs), external model proxies (OpenAI, Anthropic, Azure), and AI agents. Use when creating serving endpoints, querying models, configuring autoscaling/GPU, setting up AI Gateway features (guardrails, rate limits, inference tables), or deploying LangChain/custom agents as production endpoints."
---

# Databricks Model Serving

## Overview

Model Serving exposes ML models and AI agents as scalable REST API endpoints with serverless compute managed by Databricks.

**Endpoint Types:**

| Type | Use Case | Billing |
|------|----------|---------|
| **Custom Models** | Your ML/Python models from Unity Catalog | Pay-per-request |
| **Foundation Models** | Pre-built LLMs (DBRX, Llama, Mistral) | Pay-per-token or Provisioned Throughput |
| **External Models** | Proxy to OpenAI, Anthropic, Azure, Bedrock | Pass-through + gateway fees |
| **Agents** | LangChain, custom agents, RAG applications | Pay-per-request |

## Decision Flowchart

```
What are you deploying?
│
├─► Custom ML model (sklearn, XGBoost, PyTorch, etc.)
│   └─► See [1-custom-models.md](1-custom-models.md)
│
├─► Foundation LLM (need Databricks-hosted model)
│   ├─► Variable load → Pay-per-token
│   └─► Predictable load → Provisioned Throughput
│   └─► See [2-foundation-models.md](2-foundation-models.md)
│
├─► External API (OpenAI, Anthropic, Azure OpenAI, Bedrock)
│   └─► See [3-external-models.md](3-external-models.md)
│
├─► AI Agent (LangChain, custom agent, RAG)
│   └─► See [4-agents.md](4-agents.md)
│
└─► Need governance (rate limits, guardrails, logging)
    └─► See [5-ai-gateway.md](5-ai-gateway.md)
```

---

## Quick Start: Python SDK

All examples use the Databricks Python SDK. No MCP tools required.

### Setup

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
    ServedModelInput,
    TrafficConfig,
    Route,
)

w = WorkspaceClient()  # Auto-detects credentials
```

### Create Custom Model Endpoint

```python
# Deploy a model from Unity Catalog
endpoint = w.serving_endpoints.create_and_wait(
    name="my-model-endpoint",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                entity_name="catalog.schema.my_model",  # UC model path
                entity_version="1",
                workload_size="Small",
                scale_to_zero_enabled=True,
            )
        ]
    ),
)
print(f"Endpoint ready: {endpoint.name}")
```

### Create External Model Endpoint (OpenAI Proxy)

```python
from databricks.sdk.service.serving import (
    ExternalModel,
    ExternalModelProvider,  # SDK requires enum, not string
    OpenAiConfig,
)

endpoint = w.serving_endpoints.create_and_wait(
    name="openai-proxy",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                name="gpt-4o",
                external_model=ExternalModel(
                    name="gpt-4o",
                    provider=ExternalModelProvider.OPENAI,  # Use enum!
                    task="llm/v1/chat",
                    openai_config=OpenAiConfig(
                        openai_api_key="{{secrets/my-scope/openai-key}}"
                    ),
                ),
            )
        ]
    ),
)
```

### Query Endpoint

```python
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

# Chat completion - SDK requires ChatMessage objects, not dicts
response = w.serving_endpoints.query(
    name="my-endpoint",
    messages=[
        ChatMessage(role=ChatMessageRole.USER, content="Hello, how are you?")
    ],
    max_tokens=100,
)
print(response.choices[0].message.content)

# Custom model (dataframe input)
response = w.serving_endpoints.query(
    name="my-ml-model",
    dataframe_records=[
        {"feature1": 1.0, "feature2": "value"},
    ],
)
print(response.predictions)
```

### List and Get Endpoints

```python
# List all endpoints
for ep in w.serving_endpoints.list():
    print(f"{ep.name}: {ep.state.ready}")

# Get endpoint details
endpoint = w.serving_endpoints.get(name="my-endpoint")
print(f"State: {endpoint.state.ready}")
print(f"URL: {endpoint.pending_config}")
```

---

## Reference Files

| File | Content |
|------|---------|
| [1-custom-models.md](1-custom-models.md) | Unity Catalog models, GPU config, autoscaling, workload sizes |
| [2-foundation-models.md](2-foundation-models.md) | DBRX, Llama, Mistral - pay-per-token vs provisioned throughput |
| [3-external-models.md](3-external-models.md) | OpenAI, Anthropic, Azure OpenAI, Bedrock proxy configuration |
| [4-agents.md](4-agents.md) | **Deploy LangChain/custom agents**, input/output schemas, tracing |
| [5-ai-gateway.md](5-ai-gateway.md) | Guardrails, rate limits, inference tables, usage tracking |
| [6-common-patterns.md](6-common-patterns.md) | Error handling, streaming, A/B testing, async usage |

---

## Key Concepts

### Workload Sizes

| Size | CPU Cores | Memory | Use Case |
|------|-----------|--------|----------|
| `Small` | 4 | 16GB | Light models, testing |
| `Medium` | 8 | 32GB | Production models |
| `Large` | 16 | 64GB | Large models, high throughput |

### GPU Workload Types

| Type | GPU | Memory | Use Case |
|------|-----|--------|----------|
| `GPU_SMALL` | 1x T4 | 16GB | Small inference models |
| `GPU_MEDIUM` | 1x A10G | 24GB | Medium LLMs, embeddings |
| `GPU_LARGE` | 1x A100 | 40GB | Large LLMs |
| `GPU_LARGE_2` | 2x A100 | 80GB | Very large models |

### Scale-to-Zero

- `scale_to_zero_enabled=True`: Endpoint scales down when idle (cost savings)
- `scale_to_zero_enabled=False`: Always warm (faster cold start, higher cost)
- **Cold start**: 30-60 seconds for CPU, 2-5 minutes for GPU

### Secrets Reference Format

Always use Databricks Secrets for API keys:

```python
# Format: {{secrets/scope-name/key-name}}
openai_api_key="{{secrets/my-scope/openai-key}}"
```

Create secrets first:
```bash
databricks secrets create-scope my-scope
databricks secrets put-secret my-scope openai-key --string-value "sk-..."
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Endpoint stuck PENDING** | Check model exists in UC, verify permissions on model and compute |
| **"Model not found"** | Use full path: `catalog.schema.model_name` |
| **Cold start too slow** | Disable `scale_to_zero_enabled` or use provisioned throughput |
| **Rate limited** | Configure AI Gateway rate limits or use provisioned throughput |
| **Secrets not found** | Verify scope/key exist: `databricks secrets list-secrets my-scope` |
| **GPU unavailable** | Check region supports GPU type, try different workload type |
| **Query timeout** | Increase client timeout, check model inference time |
| **Agent returning errors** | Check logs: `w.serving_endpoints.logs(name="...", served_model_name="...")` |

---

## SDK Type Requirements (Important!)

The Databricks Python SDK requires **strongly typed objects**, not plain Python dicts:

### Chat Messages

```python
# WRONG - will fail with AttributeError
messages=[{"role": "user", "content": "Hello"}]

# CORRECT - use ChatMessage with ChatMessageRole enum
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

messages=[
    ChatMessage(role=ChatMessageRole.SYSTEM, content="You are helpful."),
    ChatMessage(role=ChatMessageRole.USER, content="Hello"),
]
```

### External Model Provider

```python
# WRONG - will fail with AttributeError  
provider="openai"

# CORRECT - use ExternalModelProvider enum
from databricks.sdk.service.serving import ExternalModelProvider

provider=ExternalModelProvider.OPENAI
# Other values: ANTHROPIC, AMAZON_BEDROCK, GOOGLE_CLOUD_VERTEX_AI, COHERE, CUSTOM
```

---

## SDK Reference

### Core Methods

```python
# Create endpoint (async)
wait = w.serving_endpoints.create(name="...", config=...)
endpoint = wait.result()  # Wait for ready

# Create endpoint (blocking)
endpoint = w.serving_endpoints.create_and_wait(name="...", config=..., timeout=timedelta(minutes=30))

# Update endpoint config
w.serving_endpoints.update_config_and_wait(name="...", served_entities=[...])

# Query endpoint
response = w.serving_endpoints.query(name="...", messages=[...])

# Delete endpoint
w.serving_endpoints.delete(name="...")

# Get build logs (for debugging)
logs = w.serving_endpoints.build_logs(name="...", served_model_name="...")
```

### Async Pattern (for FastAPI)

```python
import asyncio
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

async def query_endpoint(messages: list) -> str:
    # SDK is synchronous - wrap in thread
    response = await asyncio.to_thread(
        w.serving_endpoints.query,
        name="my-endpoint",
        messages=messages,
    )
    return response.choices[0].message.content
```

---

## Official Documentation

- [Model Serving Overview](https://docs.databricks.com/en/machine-learning/model-serving/)
- [Create Custom Endpoints](https://docs.databricks.com/en/machine-learning/model-serving/create-manage-serving-endpoints)
- [Foundation Model Endpoints](https://docs.databricks.com/en/machine-learning/model-serving/create-foundation-model-endpoints)
- [External Models](https://docs.databricks.com/en/generative-ai/external-models/)
- [AI Gateway](https://docs.databricks.com/en/generative-ai/ai-gateway/)
- [Python SDK - Serving Endpoints](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html)
