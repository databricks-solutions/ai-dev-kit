# Endpoint Management

## When to Use

Use these patterns when creating, updating, or monitoring Model Serving endpoints for deployed agents.

## Deployment Timing

| Operation | Expected Duration |
|-----------|------------------|
| New endpoint creation | 10–20 minutes |
| Config update on existing endpoint | 5–15 minutes |
| `agents.deploy()` return | Immediate (async) |

Set wait loops to **40 iterations × 30s = 20 min** minimum.

## Creating Endpoints via REST API

When `agents.deploy()` fails (e.g., endpoint already updating), create directly:

```bash
curl -X POST "$HOST/api/2.0/serving-endpoints" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "my-agent-endpoint",
    "config": {
      "served_entities": [{
        "entity_name": "catalog.schema.my_agent",
        "entity_version": "1",
        "scale_to_zero_enabled": true,
        "workload_size": "Small",
        "environment_vars": {
          "MY_PATH": "/Volumes/catalog/schema/volume"
        }
      }]
    }
  }'
```

**Required field:** `workload_size` — omitting it causes `INVALID_PARAMETER_VALUE`.

## Updating Endpoint Environment Variables

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
w.api_client.do("PUT", f"/api/2.0/serving-endpoints/{name}/config", body={
    "served_entities": [{
        "entity_name": "catalog.schema.my_agent",
        "entity_version": str(version),
        "scale_to_zero_enabled": True,
        "environment_vars": {
            "MY_PATH": "/Volumes/catalog/schema/volume"
        }
    }]
})
```

## Monitoring Endpoint State

An endpoint can be `READY` (old version serving) while a new version deploys:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
endpoint = w.serving_endpoints.get(name="my-agent-endpoint")

# Check serving state
print(endpoint.state.ready)  # READY, NOT_READY

# Check if config update is in progress
print(endpoint.state.config_update)  # IN_PROGRESS, NOT_UPDATING
```

## Wait Loop Pattern

```python
import time

for i in range(40):
    endpoint = w.serving_endpoints.get(name="my-agent-endpoint")
    state = endpoint.state
    if state.ready == "READY" and state.config_update == "NOT_UPDATING":
        print(f"Endpoint ready after {(i+1)*30}s")
        break
    print(f"[{i+1}/40] ready={state.ready}, config_update={state.config_update}")
    time.sleep(30)
else:
    raise TimeoutError("Endpoint did not become ready in 20 minutes")
```

## UC Permissions for Model Serving

The deploying identity needs:
- `ALL_PRIVILEGES` on the schema containing the model
- `ALL_PRIVILEGES` on the model itself (if it already exists)

```bash
curl -X PATCH "$HOST/api/2.1/unity-catalog/permissions/schema/catalog.schema" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"changes": [{"principal": "account users", "add": ["ALL_PRIVILEGES"]}]}'
```

## Workspace API Reference

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/2.0/workspace/export` | GET | Use `--data-urlencode` for params |
| `/api/2.0/workspace/import` | POST | Content must be base64-encoded, set `overwrite: true` |
| `/api/2.0/fs/files/Volumes/...` | PUT | Upload files to UC Volumes via `--data-binary @file` |
| `/api/2.0/sql/statements` | POST | Requires `warehouse_id`, use `wait_timeout: "30s"` |
