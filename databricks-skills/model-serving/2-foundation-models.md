# Foundation Model Serving

Serve Databricks-hosted foundation models (DBRX, Llama, Mistral, etc.) with pay-per-token or provisioned throughput.

---

## Available Models

### Pay-Per-Token Models (Serverless)

These are pre-deployed and ready to use immediately:

| Model | Endpoint Name | Context | Best For |
|-------|---------------|---------|----------|
| **DBRX Instruct** | `databricks-dbrx-instruct` | 32k | General purpose, code |
| **Meta Llama 3.1 70B** | `databricks-meta-llama-3-1-70b-instruct` | 128k | Long context, reasoning |
| **Meta Llama 3.1 405B** | `databricks-meta-llama-3-1-405b-instruct` | 128k | Most capable |
| **Mixtral 8x7B** | `databricks-mixtral-8x7b-instruct` | 32k | Fast, efficient |
| **BGE Large** | `databricks-bge-large-en` | - | Embeddings |
| **GTE Large** | `databricks-gte-large-en` | - | Embeddings |

### Provisioned Throughput Models

Deploy your own instance with guaranteed capacity:

| Model | Min Tokens/sec | Use Case |
|-------|----------------|----------|
| Llama 3.1 8B | 1,000 | Cost-effective |
| Llama 3.1 70B | 500 | Balanced |
| Llama 3.1 405B | 100 | Maximum capability |
| Fine-tuned models | Varies | Custom models |

---

## Pay-Per-Token (Serverless)

### Query Pre-deployed Model

No endpoint creation needed - query directly:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

w = WorkspaceClient()

# Chat completion - SDK requires ChatMessage objects with ChatMessageRole enum
response = w.serving_endpoints.query(
    name="databricks-meta-llama-3-1-70b-instruct",
    messages=[
        ChatMessage(role=ChatMessageRole.SYSTEM, content="You are a helpful assistant."),
        ChatMessage(role=ChatMessageRole.USER, content="Explain quantum computing in simple terms."),
    ],
    max_tokens=500,
    temperature=0.7,
)

print(response.choices[0].message.content)
```

### Embeddings

```python
response = w.serving_endpoints.query(
    name="databricks-bge-large-en",
    input=["Hello world", "How are you?"],
)

embeddings = response.data  # List of embedding vectors
print(f"Embedding dimension: {len(embeddings[0].embedding)}")
```

### Streaming Responses

```python
# Note: SDK streaming requires manual handling
import requests

response = requests.post(
    f"{w.config.host}/serving-endpoints/databricks-meta-llama-3-1-70b-instruct/invocations",
    headers={"Authorization": f"Bearer {w.config.token}"},
    json={
        "messages": [{"role": "user", "content": "Write a story"}],
        "stream": True,
    },
    stream=True,
)

for line in response.iter_lines():
    if line:
        print(line.decode())
```

---

## Provisioned Throughput

### When to Use

- **Predictable costs**: Fixed monthly cost vs variable token costs
- **Guaranteed capacity**: No throttling during traffic spikes  
- **Low latency**: Dedicated resources, no cold starts
- **Compliance**: Dedicated infrastructure for sensitive workloads

### Create Provisioned Throughput Endpoint

```python
from databricks.sdk.service.serving import PtEndpointCoreConfig, PtServedModel

endpoint = w.serving_endpoints.create_provisioned_throughput_endpoint_and_wait(
    name="my-llama-pt",
    config=PtEndpointCoreConfig(
        served_entities=[
            PtServedModel(
                entity_name="system.ai.meta_llama_3_1_70b_instruct",
                provisioned_model_units=1,  # Number of provisioned units
                name="llama-3-1-70b",
            )
        ]
    ),
)
```

### Fine-Tuned Model with Provisioned Throughput

```python
# First, register your fine-tuned model to Unity Catalog
# Then deploy with provisioned throughput

endpoint = w.serving_endpoints.create_provisioned_throughput_endpoint_and_wait(
    name="my-finetuned-llama",
    config=PtEndpointCoreConfig(
        served_entities=[
            PtServedModel(
                entity_name="catalog.schema.my_finetuned_llama",
                provisioned_model_units=1,
                entity_version="1",
                name="finetuned-model",
            )
        ]
    ),
)
```

### Update Provisioned Throughput

```python
# Scale up/down throughput
w.serving_endpoints.update_provisioned_throughput_endpoint_config(
    name="my-llama-pt",
    config=PtEndpointCoreConfig(
        served_entities=[
            PtServedModel(
                entity_name="system.ai.meta_llama_3_1_70b_instruct",
                provisioned_model_units=2,  # Increased
                name="llama-3-1-70b",
            )
        ]
    ),
)
```

---

## Query Parameters

### Chat Completions

```python
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

response = w.serving_endpoints.query(
    name="databricks-meta-llama-3-1-70b-instruct",
    messages=[
        ChatMessage(role=ChatMessageRole.SYSTEM, content="You are helpful."),
        ChatMessage(role=ChatMessageRole.USER, content="Hello!"),
    ],
    max_tokens=500,       # Maximum tokens to generate
    temperature=0.7,      # 0.0-2.0, higher = more random
    n=1,                  # Number of completions (1-5)
    stop=["END", "###"],  # Stop sequences
)
```

### Completions (Text Generation)

```python
response = w.serving_endpoints.query(
    name="databricks-dbrx-instruct",
    prompt="Complete this code:\ndef fibonacci(n):",
    max_tokens=200,
    temperature=0.0,  # Deterministic for code
)
print(response.choices[0].text)
```

### Embeddings

```python
response = w.serving_endpoints.query(
    name="databricks-bge-large-en",
    input=["text to embed", "another text"],
)

# Access embeddings
for item in response.data:
    print(f"Index {item.index}: {len(item.embedding)} dimensions")
```

---

## Cost Comparison

### Pay-Per-Token Example

| Model | Input ($/1M tokens) | Output ($/1M tokens) | 1M requests (100 tokens each) |
|-------|---------------------|----------------------|-------------------------------|
| Llama 3.1 8B | $0.05 | $0.10 | ~$15 |
| Llama 3.1 70B | $0.50 | $1.00 | ~$150 |
| DBRX Instruct | $0.75 | $2.25 | ~$225 |

### Provisioned Throughput Example

| Model | Tokens/sec | Approx Monthly Cost |
|-------|------------|---------------------|
| Llama 3.1 8B @ 1000 t/s | 1,000 | ~$2,000 |
| Llama 3.1 70B @ 500 t/s | 500 | ~$8,000 |

**Break-even**: Provisioned throughput typically makes sense at 50M+ tokens/month.

---

## OpenAI-Compatible API

Foundation model endpoints are OpenAI-compatible:

```python
from openai import OpenAI

client = OpenAI(
    api_key=w.config.token,
    base_url=f"{w.config.host}/serving-endpoints"
)

response = client.chat.completions.create(
    model="databricks-meta-llama-3-1-70b-instruct",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
)
print(response.choices[0].message.content)
```

### Get OpenAI Client from SDK

```python
# Convenience method
client = w.serving_endpoints.get_open_ai_client()

response = client.chat.completions.create(
    model="databricks-meta-llama-3-1-70b-instruct",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

---

## Best Practices

1. **Start with pay-per-token** for development and testing
2. **Use provisioned throughput** when you have predictable, high-volume workloads
3. **Monitor token usage** to optimize costs
4. **Use smaller models first** (8B) and scale up only if needed
5. **Cache embeddings** to reduce redundant API calls
6. **Set appropriate max_tokens** to control costs

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Rate limited** | Use provisioned throughput or add AI Gateway rate limits |
| **High latency** | Try smaller model or provisioned throughput |
| **Token limit exceeded** | Reduce input size or use model with larger context |
| **Model not available** | Check region availability in Databricks docs |
| **Unexpected costs** | Monitor usage, set alerts, consider provisioned throughput |
