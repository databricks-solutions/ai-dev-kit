# Guardrails

Filter and transform LLM input and output with safety, PII, keyword, topic, and custom guardrails applied at the AI Gateway layer.

## Request Flow

```
Client → [Input Guardrails] → LLM → [Output Guardrails] → Client
```

Input guardrails inspect and can reject or modify the request before it reaches the model. Output guardrails inspect and can reject or modify the response before it reaches the client.

## Guardrail Types Reference

| Type | What it does | Input supported | Output supported |
|------|-------------|----------------|-----------------|
| Safety | Blocks unsafe content (hate speech, self-harm, sexual content, violence) | Yes | Yes |
| PII Detection | Detects PII and blocks, masks, or allows based on config | Yes | Yes |
| Keyword Blocking | Rejects requests/responses containing specified keywords | Yes | Yes |
| Topic Restrictions | Restricts conversations to specified valid topics | Yes | No |
| LLM Judge (Beta) | Uses an LLM with editable prompts to evaluate content | Yes | Yes |
| Custom Guardrails (Private Preview) | Routes content to a separate model serving endpoint for evaluation | Yes | Yes |

## PII Detection

### PII BLOCK

Reject any request or response containing PII.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior,
    AiGatewayGuardrailPiiBehaviorBehavior,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK
            )
        ),
        output=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK
            )
        ),
    ),
)
```

### PII MASK

Redact detected PII (e.g., replace SSNs with `[REDACTED]`) and pass the sanitized content through.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior,
    AiGatewayGuardrailPiiBehaviorBehavior,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.MASK
            )
        ),
        output=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.MASK
            )
        ),
    ),
)
```

### PII NONE

Detect PII and log it (visible in inference tables) but allow the request/response through unchanged.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior,
    AiGatewayGuardrailPiiBehaviorBehavior,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.NONE
            )
        ),
    ),
)
```

## Safety Filters

Enable built-in safety classification on both input and output. Blocks content flagged as hate speech, self-harm, sexual content, or violence.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(safety=True),
        output=AiGatewayGuardrailParameters(safety=True),
    ),
)
```

## Keyword Blocking

Reject requests or responses containing any of the specified keywords. Matching is case-insensitive.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            invalid_keywords=["competitor_name", "confidential"]
        ),
        output=AiGatewayGuardrailParameters(
            invalid_keywords=["competitor_name", "confidential"]
        ),
    ),
)
```

## Topic Restrictions

Restrict the endpoint to only respond about specified topics. Requests outside these topics are rejected. Topic restrictions apply to input only.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            valid_topics=["databricks", "data engineering", "machine learning"]
        ),
    ),
)
```

## LLM Judge Guardrails (Beta)

LLM judge guardrails use an LLM to evaluate input or output against a custom prompt you define. The judge model, prompt, and pass/fail criteria are fully configurable. This allows guardrail logic beyond what keyword or safety filters can express.

LLM judge guardrails are configured via the UI or REST API. They are not yet represented in the Python SDK classes above.

**REST API example** -- LLM judge that detects financial advice:

```bash
curl -X PUT \
  "${DATABRICKS_HOST}/api/2.0/serving-endpoints/my-llm-endpoint/ai-gateway" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "guardrails": {
      "input": {
        "llm_judge": {
          "model": "databricks-meta-llama-3-3-70b-instruct",
          "prompt": "Evaluate whether the following message is asking for personalized financial advice (e.g., specific investment recommendations, portfolio allocation, tax strategies for an individual). General educational content about financial concepts is allowed. Respond with PASS if the message is safe, or FAIL if it requests personalized financial advice.",
          "behaviour": "BLOCK"
        }
      },
      "output": {
        "llm_judge": {
          "model": "databricks-meta-llama-3-3-70b-instruct",
          "prompt": "Evaluate whether the following response contains personalized financial advice. General educational content is allowed. Respond with PASS if the response is safe, or FAIL if it contains personalized financial advice.",
          "behaviour": "BLOCK"
        }
      }
    }
  }'
```

## Custom Guardrails (Private Preview)

> **Private Preview** -- Contact your Databricks account team to enable this feature.

Custom guardrails let you deploy a separate model serving endpoint as the guardrail evaluator. The gateway routes input or output to your custom endpoint, which returns a pass/fail decision. This is useful when you need proprietary evaluation logic (e.g., a fine-tuned classifier for domain-specific compliance).

**Conceptual REST API example:**

```bash
curl -X PUT \
  "${DATABRICKS_HOST}/api/2.0/serving-endpoints/my-llm-endpoint/ai-gateway" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "guardrails": {
      "input": {
        "custom": {
          "endpoint_name": "my-compliance-classifier",
          "behaviour": "BLOCK"
        }
      },
      "output": {
        "custom": {
          "endpoint_name": "my-compliance-classifier",
          "behaviour": "BLOCK"
        }
      }
    }
  }'
```

The custom guardrail endpoint must accept the same input format and return a response with a `pass` boolean field.

## Combined Example

Full configuration combining PII BLOCK on input, PII MASK on output, safety on both, keyword blocking on input, and topic restrictions on input.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior,
    AiGatewayGuardrailPiiBehaviorBehavior,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK
            ),
            safety=True,
            invalid_keywords=["competitor_name", "confidential"],
            valid_topics=["databricks", "data engineering", "machine learning"],
        ),
        output=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.MASK
            ),
            safety=True,
        ),
    ),
)
```

## Limitations

- Output guardrails are not supported for embedding endpoints
- Output guardrails are not supported for streaming responses
- Input guardrails add ~100-500ms latency
- Custom guardrails (Private Preview) require a separate serving endpoint
- LLM judge guardrails add latency proportional to the judge model's response time

## SA Scenario

**Customer wants GPT-4 endpoint with PII protection and per-team rate limits.**

**Approach:**

1. Configure PII BLOCK on input to reject any request containing PII before it reaches the model:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior,
    AiGatewayGuardrailPiiBehaviorBehavior,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="gpt-4-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK
            )
        ),
        output=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.MASK
            )
        ),
    ),
)
```

2. PII BLOCK on input ensures no PII reaches the model. PII MASK on output catches any PII the model generates in its response and redacts it before returning to the client.

3. For per-team rate limits, see [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md) -- use `AiGatewayRateLimitKey.USER_GROUP` with team group names to set QPM/TPM limits per team.
