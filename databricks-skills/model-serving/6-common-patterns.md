# Common Patterns

Error handling, streaming, A/B testing, async usage, and other common patterns for model serving.

---

## Error Handling

### SDK Error Types

```python
from databricks.sdk.errors import (
    NotFound,
    ResourceAlreadyExists,
    PermissionDenied,
    InvalidParameterValue,
    ResourceConflict,
    DeadlineExceeded,
    ServiceError,
)

try:
    endpoint = w.serving_endpoints.get(name="my-endpoint")
except NotFound:
    print("Endpoint does not exist")
except PermissionDenied:
    print("No access to endpoint")
```

### Create If Not Exists

```python
def get_or_create_endpoint(w, name, config):
    """Get existing endpoint or create new one."""
    try:
        return w.serving_endpoints.get(name=name)
    except NotFound:
        return w.serving_endpoints.create_and_wait(name=name, config=config)

endpoint = get_or_create_endpoint(
    w, 
    name="my-endpoint",
    config=EndpointCoreConfigInput(...)
)
```

### Retry Pattern for Queries

```python
import time
from databricks.sdk.errors import ServiceError, DeadlineExceeded

def query_with_retry(w, name, messages, max_retries=3, backoff=1.0):
    """Query endpoint with exponential backoff."""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return w.serving_endpoints.query(
                name=name,
                messages=messages,
            )
        except (ServiceError, DeadlineExceeded) as e:
            last_error = e
            if attempt < max_retries - 1:
                sleep_time = backoff * (2 ** attempt)
                print(f"Retry {attempt + 1}/{max_retries} after {sleep_time}s")
                time.sleep(sleep_time)
    
    raise last_error
```

### Handle Rate Limits

```python
from databricks.sdk.errors import TooManyRequests
import time

def query_with_rate_limit_handling(w, name, messages):
    """Handle rate limits gracefully."""
    while True:
        try:
            return w.serving_endpoints.query(name=name, messages=messages)
        except TooManyRequests as e:
            # Extract retry-after if available
            retry_after = getattr(e, 'retry_after', 60)
            print(f"Rate limited. Waiting {retry_after}s")
            time.sleep(retry_after)
```

---

## Streaming Responses

The SDK doesn't natively support streaming, use requests directly:

### Basic Streaming

```python
import requests
import json

def stream_response(host, token, endpoint_name, messages):
    """Stream responses from endpoint."""
    response = requests.post(
        f"{host}/serving-endpoints/{endpoint_name}/invocations",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "messages": messages,
            "stream": True,
        },
        stream=True,
    )
    
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = line[6:]  # Remove 'data: ' prefix
                if data == '[DONE]':
                    break
                chunk = json.loads(data)
                if chunk.get('choices'):
                    delta = chunk['choices'][0].get('delta', {})
                    if 'content' in delta:
                        yield delta['content']

# Usage
w = WorkspaceClient()
for chunk in stream_response(
    w.config.host,
    w.config.token,
    "my-endpoint",
    [{"role": "user", "content": "Write a story"}]
):
    print(chunk, end='', flush=True)
```

### Streaming with FastAPI

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import requests

app = FastAPI()

@app.post("/chat")
async def chat(messages: list):
    async def generate():
        response = requests.post(
            f"{DATABRICKS_HOST}/serving-endpoints/{ENDPOINT_NAME}/invocations",
            headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}"},
            json={"messages": messages, "stream": True},
            stream=True,
        )
        
        for line in response.iter_lines():
            if line:
                yield line.decode('utf-8') + '\n'
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## Async Usage (FastAPI)

### Wrap Synchronous SDK

```python
import asyncio
from databricks.sdk import WorkspaceClient
from fastapi import FastAPI

app = FastAPI()
w = WorkspaceClient()

@app.post("/query")
async def query_endpoint(messages: list):
    """Query endpoint asynchronously."""
    response = await asyncio.to_thread(
        w.serving_endpoints.query,
        name="my-endpoint",
        messages=messages,
    )
    return {"response": response.choices[0].message.content}

@app.get("/endpoints")
async def list_endpoints():
    """List all endpoints asynchronously."""
    endpoints = await asyncio.to_thread(
        lambda: list(w.serving_endpoints.list())
    )
    return [{"name": ep.name, "state": ep.state.ready} for ep in endpoints]
```

### Connection Pool Pattern

```python
from databricks.sdk import WorkspaceClient
from contextlib import asynccontextmanager
import asyncio

class AsyncDatabricksClient:
    def __init__(self):
        self._client = WorkspaceClient()
    
    async def query(self, endpoint_name: str, messages: list):
        return await asyncio.to_thread(
            self._client.serving_endpoints.query,
            name=endpoint_name,
            messages=messages,
        )
    
    async def list_endpoints(self):
        return await asyncio.to_thread(
            lambda: list(self._client.serving_endpoints.list())
        )

# Use as singleton
db_client = AsyncDatabricksClient()

@app.post("/chat")
async def chat(messages: list):
    response = await db_client.query("my-endpoint", messages)
    return {"response": response.choices[0].message.content}
```

---

## A/B Testing

### Traffic Splitting

```python
from databricks.sdk.service.serving import TrafficConfig, Route

# Deploy two versions
endpoint = w.serving_endpoints.create_and_wait(
    name="ab-test-endpoint",
    config=EndpointCoreConfigInput(
        name="ab-test-endpoint",  # Required: must match endpoint name
        served_entities=[
            ServedEntityInput(
                name="model-control",
                entity_name="catalog.schema.my_model",
                entity_version="1",
                workload_size="Small",
            ),
            ServedEntityInput(
                name="model-treatment",
                entity_name="catalog.schema.my_model",
                entity_version="2",
                workload_size="Small",
            ),
        ],
        traffic_config=TrafficConfig(
            routes=[
                Route(served_model_name="model-control", traffic_percentage=50),
                Route(served_model_name="model-treatment", traffic_percentage=50),
            ]
        ),
    ),
)
```

### Gradual Rollout

```python
# Start with 10% traffic to new version
w.serving_endpoints.update_config_and_wait(
    name="ab-test-endpoint",
    traffic_config=TrafficConfig(
        routes=[
            Route(served_model_name="model-control", traffic_percentage=90),
            Route(served_model_name="model-treatment", traffic_percentage=10),
        ]
    ),
)

# After validation, increase to 50%
w.serving_endpoints.update_config_and_wait(
    name="ab-test-endpoint",
    traffic_config=TrafficConfig(
        routes=[
            Route(served_model_name="model-control", traffic_percentage=50),
            Route(served_model_name="model-treatment", traffic_percentage=50),
        ]
    ),
)

# Full rollout
w.serving_endpoints.update_config_and_wait(
    name="ab-test-endpoint",
    traffic_config=TrafficConfig(
        routes=[
            Route(served_model_name="model-treatment", traffic_percentage=100),
        ]
    ),
    served_entities=[
        ServedEntityInput(
            name="model-treatment",
            entity_name="catalog.schema.my_model",
            entity_version="2",
            workload_size="Small",
        ),
    ],
)
```

### Analyze A/B Results

```sql
-- Compare model versions using inference table
SELECT 
    get_json_object(response, '$.model') as model_version,
    count(*) as requests,
    avg(execution_time_ms) as avg_latency,
    percentile(execution_time_ms, 0.95) as p95_latency,
    sum(case when status_code = 200 then 1 else 0 end) / count(*) as success_rate
FROM catalog.schema.endpoint_logs_request_response
WHERE timestamp_ms > unix_timestamp(current_date() - INTERVAL 7 DAY) * 1000
GROUP BY 1;
```

---

## Caching Responses

### Simple LRU Cache

```python
from functools import lru_cache
import hashlib
import json

def hash_messages(messages: list) -> str:
    """Create deterministic hash of messages."""
    return hashlib.md5(json.dumps(messages, sort_keys=True).encode()).hexdigest()

@lru_cache(maxsize=1000)
def cached_query(w, endpoint_name: str, messages_hash: str, messages_json: str):
    """Cache responses by message hash."""
    messages = json.loads(messages_json)
    return w.serving_endpoints.query(
        name=endpoint_name,
        messages=messages,
    )

def query_with_cache(w, endpoint_name: str, messages: list):
    """Query with caching."""
    messages_json = json.dumps(messages)
    messages_hash = hash_messages(messages)
    return cached_query(w, endpoint_name, messages_hash, messages_json)
```

### Redis Cache for Production

```python
import redis
import json
import hashlib

redis_client = redis.Redis(host='localhost', port=6379, db=0)
CACHE_TTL = 3600  # 1 hour

def query_with_redis_cache(w, endpoint_name: str, messages: list):
    """Query with Redis caching."""
    cache_key = f"llm:{endpoint_name}:{hashlib.md5(json.dumps(messages).encode()).hexdigest()}"
    
    # Check cache
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Query endpoint
    response = w.serving_endpoints.query(
        name=endpoint_name,
        messages=messages,
    )
    
    # Cache response
    response_dict = {
        "content": response.choices[0].message.content,
        "usage": {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }
    }
    redis_client.setex(cache_key, CACHE_TTL, json.dumps(response_dict))
    
    return response_dict
```

---

## Batch Processing

### Concurrent Queries

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def batch_query(w, endpoint_name: str, messages_batch: list, max_concurrent: int = 10):
    """Process batch of queries concurrently."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def query_one(messages):
        async with semaphore:
            return await asyncio.to_thread(
                w.serving_endpoints.query,
                name=endpoint_name,
                messages=messages,
            )
    
    tasks = [query_one(messages) for messages in messages_batch]
    return await asyncio.gather(*tasks, return_exceptions=True)

# Usage
messages_batch = [
    [{"role": "user", "content": f"Question {i}"}]
    for i in range(100)
]

results = asyncio.run(batch_query(w, "my-endpoint", messages_batch))
```

### Progress Tracking

```python
from tqdm import tqdm
import asyncio

async def batch_query_with_progress(w, endpoint_name: str, messages_batch: list):
    """Batch query with progress bar."""
    results = []
    
    async def process_one(messages, pbar):
        result = await asyncio.to_thread(
            w.serving_endpoints.query,
            name=endpoint_name,
            messages=messages,
        )
        pbar.update(1)
        return result
    
    with tqdm(total=len(messages_batch), desc="Processing") as pbar:
        tasks = [process_one(m, pbar) for m in messages_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results
```

---

## Health Checks

### Endpoint Health Check

```python
def check_endpoint_health(w, endpoint_name: str) -> dict:
    """Check if endpoint is healthy."""
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
    
    try:
        endpoint = w.serving_endpoints.get(name=endpoint_name)
        
        if endpoint.state.ready == "READY":
            # Test with simple query
            response = w.serving_endpoints.query(
                name=endpoint_name,
                messages=[ChatMessage(role=ChatMessageRole.USER, content="ping")],
                max_tokens=1,
            )
            return {"status": "healthy", "ready": True}
        else:
            return {
                "status": "not_ready",
                "ready": False,
                "state": endpoint.state.ready,
            }
    except Exception as e:
        return {"status": "error", "ready": False, "error": str(e)}
```

### FastAPI Health Endpoint

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health = await asyncio.to_thread(check_endpoint_health, w, "my-endpoint")
    
    if not health["ready"]:
        raise HTTPException(status_code=503, detail=health)
    
    return health
```

---

## Timeouts

### Query with Timeout

```python
import asyncio
from concurrent.futures import TimeoutError

async def query_with_timeout(w, endpoint_name: str, messages: list, timeout_seconds: float = 30):
    """Query with timeout."""
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                w.serving_endpoints.query,
                name=endpoint_name,
                messages=messages,
            ),
            timeout=timeout_seconds,
        )
        return response
    except asyncio.TimeoutError:
        raise TimeoutError(f"Query timed out after {timeout_seconds}s")
```

### Create with Extended Timeout

```python
from datetime import timedelta

# Large models may take longer to deploy
endpoint = w.serving_endpoints.create_and_wait(
    name="large-model-endpoint",
    config=EndpointCoreConfigInput(
        name="large-model-endpoint",  # Required: must match endpoint name
        served_entities=[
            ServedEntityInput(
                entity_name="catalog.schema.large_model",
                entity_version="1",
                workload_type="GPU_LARGE",
                workload_size="Medium",
            )
        ]
    ),
    timeout=timedelta(minutes=60),  # 1 hour timeout
)
```

---

## Logging and Observability

### Structured Logging

```python
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def query_with_logging(w, endpoint_name: str, messages: list):
    """Query with structured logging."""
    request_id = str(uuid.uuid4())
    start_time = datetime.now()
    
    logger.info(json.dumps({
        "event": "query_start",
        "request_id": request_id,
        "endpoint": endpoint_name,
        "input_length": len(str(messages)),
    }))
    
    try:
        response = w.serving_endpoints.query(
            name=endpoint_name,
            messages=messages,
        )
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(json.dumps({
            "event": "query_success",
            "request_id": request_id,
            "endpoint": endpoint_name,
            "duration_ms": duration_ms,
            "input_tokens": response.usage.prompt_tokens if response.usage else None,
            "output_tokens": response.usage.completion_tokens if response.usage else None,
        }))
        
        return response
        
    except Exception as e:
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.error(json.dumps({
            "event": "query_error",
            "request_id": request_id,
            "endpoint": endpoint_name,
            "duration_ms": duration_ms,
            "error": str(e),
        }))
        raise
```

---

## Best Practices Summary

1. **Error handling**: Always catch specific exceptions, implement retries
2. **Async**: Wrap SDK calls with `asyncio.to_thread()` in async apps
3. **Streaming**: Use requests library for streaming responses
4. **Caching**: Cache deterministic queries to reduce costs
5. **Batching**: Use concurrent queries with semaphore for rate limiting
6. **Health checks**: Implement health endpoints for monitoring
7. **Timeouts**: Set appropriate timeouts for queries and deployments
8. **Logging**: Use structured logging for observability
9. **Graceful degradation**: Handle rate limits and errors gracefully
