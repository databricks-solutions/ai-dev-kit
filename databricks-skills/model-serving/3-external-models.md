# External Model Serving

Proxy external LLM APIs (OpenAI, Anthropic, Azure OpenAI, AWS Bedrock, Google Vertex, Cohere) through Databricks AI Gateway.

---

## Why Use External Models via Databricks?

- **Unified interface**: Single API for all providers
- **Governance**: Rate limits, guardrails, usage tracking
- **Secrets management**: Centralized API key storage
- **Monitoring**: Inference tables for logging all requests/responses
- **Cost tracking**: Usage metrics across providers
- **Fallbacks**: Route between providers for resilience

---

## Provider Configurations

### OpenAI

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
    ExternalModel,
    ExternalModelProvider,  # SDK requires enum, not string
    OpenAiConfig,
)

w = WorkspaceClient()

# Create OpenAI proxy endpoint
endpoint = w.serving_endpoints.create_and_wait(
    name="openai-gpt4o",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                name="gpt-4o",
                external_model=ExternalModel(
                    name="gpt-4o",
                    provider=ExternalModelProvider.OPENAI,  # Use enum!
                    task="llm/v1/chat",
                    openai_config=OpenAiConfig(
                        openai_api_key="{{secrets/llm-keys/openai-api-key}}",
                    ),
                ),
            )
        ]
    ),
)
```

### Azure OpenAI

```python
from databricks.sdk.service.serving import OpenAiConfig

ServedEntityInput(
    name="azure-gpt4",
    external_model=ExternalModel(
        name="gpt-4",
        provider="openai",
        task="llm/v1/chat",
        openai_config=OpenAiConfig(
            openai_api_type="azure",
            openai_api_key="{{secrets/llm-keys/azure-openai-key}}",
            openai_api_base="https://my-resource.openai.azure.com",
            openai_api_version="2024-02-15-preview",
            openai_deployment_name="my-gpt4-deployment",
        ),
    ),
)
```

### Azure OpenAI with Entra ID (Service Principal)

```python
ServedEntityInput(
    name="azure-gpt4-entra",
    external_model=ExternalModel(
        name="gpt-4",
        provider="openai",
        task="llm/v1/chat",
        openai_config=OpenAiConfig(
            openai_api_type="azure",
            openai_api_base="https://my-resource.openai.azure.com",
            openai_api_version="2024-02-15-preview",
            openai_deployment_name="my-gpt4-deployment",
            microsoft_entra_tenant_id="your-tenant-id",
            microsoft_entra_client_id="your-client-id",
            microsoft_entra_client_secret="{{secrets/llm-keys/entra-secret}}",
        ),
    ),
)
```

### Anthropic (Claude)

```python
from databricks.sdk.service.serving import AnthropicConfig

ServedEntityInput(
    name="claude-3-opus",
    external_model=ExternalModel(
        name="claude-3-opus-20240229",
        provider="anthropic",
        task="llm/v1/chat",
        anthropic_config=AnthropicConfig(
            anthropic_api_key="{{secrets/llm-keys/anthropic-key}}",
        ),
    ),
)
```

### AWS Bedrock

```python
from databricks.sdk.service.serving import (
    AmazonBedrockConfig,
    AmazonBedrockConfigBedrockProvider,
    ExternalModelProvider,
)

# Using access keys
ServedEntityInput(
    name="bedrock-claude",
    external_model=ExternalModel(
        name="anthropic.claude-3-sonnet-20240229-v1:0",
        provider=ExternalModelProvider.AMAZON_BEDROCK,  # Use enum!
        task="llm/v1/chat",
        amazon_bedrock_config=AmazonBedrockConfig(
            aws_region="us-east-1",
            bedrock_provider=AmazonBedrockConfigBedrockProvider.ANTHROPIC,  # Use enum!
            aws_access_key_id="{{secrets/aws/access-key-id}}",
            aws_secret_access_key="{{secrets/aws/secret-access-key}}",
        ),
    ),
)

# Using instance profile (IAM role)
ServedEntityInput(
    name="bedrock-claude-iam",
    external_model=ExternalModel(
        name="anthropic.claude-3-sonnet-20240229-v1:0",
        provider=ExternalModelProvider.AMAZON_BEDROCK,
        task="llm/v1/chat",
        amazon_bedrock_config=AmazonBedrockConfig(
            aws_region="us-east-1",
            bedrock_provider=AmazonBedrockConfigBedrockProvider.ANTHROPIC,
            instance_profile_arn="arn:aws:iam::123456789:instance-profile/my-profile",
        ),
    ),
)
```

**Bedrock provider enum values:** `ANTHROPIC`, `AMAZON`, `AI21LABS`, `COHERE`

### Google Vertex AI

```python
from databricks.sdk.service.serving import GoogleCloudVertexAiConfig

ServedEntityInput(
    name="vertex-gemini",
    external_model=ExternalModel(
        name="gemini-1.5-pro",
        provider="google-cloud-vertex-ai",
        task="llm/v1/chat",
        google_cloud_vertex_ai_config=GoogleCloudVertexAiConfig(
            project_id="my-gcp-project",
            region="us-central1",
            private_key="{{secrets/gcp/service-account-key}}",
        ),
    ),
)
```

### Cohere

```python
from databricks.sdk.service.serving import CohereConfig

ServedEntityInput(
    name="cohere-command",
    external_model=ExternalModel(
        name="command-r-plus",
        provider="cohere",
        task="llm/v1/chat",
        cohere_config=CohereConfig(
            cohere_api_key="{{secrets/llm-keys/cohere-key}}",
        ),
    ),
)
```

### Custom Provider (Any OpenAI-Compatible API)

```python
from databricks.sdk.service.serving import CustomProviderConfig, ApiKeyAuth

ServedEntityInput(
    name="custom-llm",
    external_model=ExternalModel(
        name="my-custom-model",
        provider="custom",
        task="llm/v1/chat",
        custom_provider_config=CustomProviderConfig(
            custom_provider_url="https://my-llm-provider.com/v1",
            api_key_auth=ApiKeyAuth(
                key="Authorization",
                value="{{secrets/llm-keys/custom-api-key}}",
            ),
        ),
    ),
)

# Or with bearer token
ServedEntityInput(
    name="custom-llm-bearer",
    external_model=ExternalModel(
        name="my-custom-model",
        provider="custom",
        task="llm/v1/chat",
        custom_provider_config=CustomProviderConfig(
            custom_provider_url="https://my-llm-provider.com/v1",
            bearer_token_auth=BearerTokenAuth(
                token="{{secrets/llm-keys/bearer-token}}",
            ),
        ),
    ),
)
```

---

## Task Types

| Task | Description | Providers |
|------|-------------|-----------|
| `llm/v1/chat` | Chat completions | All |
| `llm/v1/completions` | Text completions | OpenAI, Cohere |
| `llm/v1/embeddings` | Text embeddings | OpenAI, Cohere, Vertex |

---

## Multi-Model Endpoint

Serve multiple models from same endpoint with routing:

```python
from databricks.sdk.service.serving import TrafficConfig, Route, ExternalModelProvider

endpoint = w.serving_endpoints.create_and_wait(
    name="multi-provider-llm",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                name="openai-gpt4o",
                external_model=ExternalModel(
                    name="gpt-4o",
                    provider=ExternalModelProvider.OPENAI,
                    task="llm/v1/chat",
                    openai_config=OpenAiConfig(
                        openai_api_key="{{secrets/llm-keys/openai-key}}",
                    ),
                ),
            ),
            ServedEntityInput(
                name="anthropic-claude",
                external_model=ExternalModel(
                    name="claude-3-opus-20240229",
                    provider=ExternalModelProvider.ANTHROPIC,
                    task="llm/v1/chat",
                    anthropic_config=AnthropicConfig(
                        anthropic_api_key="{{secrets/llm-keys/anthropic-key}}",
                    ),
                ),
            ),
        ],
        traffic_config=TrafficConfig(
            routes=[
                Route(served_model_name="openai-gpt4o", traffic_percentage=80),
                Route(served_model_name="anthropic-claude", traffic_percentage=20),
            ]
        ),
    ),
)
```

---

## Querying External Model Endpoints

### Chat Completions

```python
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

response = w.serving_endpoints.query(
    name="openai-gpt4o",
    messages=[
        ChatMessage(role=ChatMessageRole.SYSTEM, content="You are a helpful assistant."),
        ChatMessage(role=ChatMessageRole.USER, content="What is the capital of France?"),
    ],
    max_tokens=100,
    temperature=0.7,
)

print(response.choices[0].message.content)
```

### With Extra Parameters

```python
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

response = w.serving_endpoints.query(
    name="openai-gpt4o",
    messages=[ChatMessage(role=ChatMessageRole.USER, content="Hello!")],
    max_tokens=100,
    extra_params={
        "top_p": "0.9",
        "presence_penalty": "0.5",
    },
)
```

### Embeddings

```python
response = w.serving_endpoints.query(
    name="openai-embeddings",
    input=["Hello world", "How are you?"],
)

for item in response.data:
    print(f"Embedding: {len(item.embedding)} dimensions")
```

---

## Setting Up Secrets

### Create Secret Scope

```bash
# Create scope
databricks secrets create-scope llm-keys

# Add API keys
databricks secrets put-secret llm-keys openai-api-key --string-value "sk-..."
databricks secrets put-secret llm-keys anthropic-key --string-value "sk-ant-..."
databricks secrets put-secret llm-keys azure-openai-key --string-value "..."
```

### Using Python SDK

```python
w.secrets.create_scope(scope="llm-keys")

w.secrets.put_secret(
    scope="llm-keys",
    key="openai-api-key",
    string_value="sk-...",
)
```

---

## Best Practices

1. **Always use secrets** - Never hardcode API keys
2. **Use AI Gateway features** - Enable rate limits, guardrails, inference tables
3. **Monitor costs** - External models bill through the provider
4. **Test failover** - Use multi-model endpoints for resilience
5. **Cache responses** - Reduce API calls for repeated queries
6. **Set sensible defaults** - max_tokens, temperature for your use case

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Authentication failed** | Verify secret path, check API key is valid |
| **"Provider not supported"** | Check provider name spelling, use lowercase |
| **Azure deployment not found** | Verify deployment name matches exactly |
| **Bedrock access denied** | Check IAM permissions, region availability |
| **Rate limited by provider** | Add AI Gateway rate limits to smooth traffic |
| **High latency** | External calls add network hops; consider caching |
