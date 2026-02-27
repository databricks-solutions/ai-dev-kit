# Lakebase Autoscaling Computes

## Overview

A compute is a virtualized service that runs Postgres for a branch. Each branch has one primary read-write compute and can have optional read replicas. Computes support autoscaling, scale-to-zero, and granular sizing from 0.5 to 112 CU.

## Compute Sizing

Each Compute Unit (CU) allocates approximately 2 GB of RAM.

### Available Sizes

| Category | Range | Notes |
|----------|-------|-------|
| **Autoscale computes** | 0.5-32 CU | Dynamic scaling within range (max-min <= 8 CU) |
| **Large fixed-size** | 36-112 CU | Fixed size, no autoscaling |

### Representative Sizes

| Compute Units | RAM | Max Connections |
|--------------|-----|-----------------|
| 0.5 CU | ~1 GB | 104 |
| 1 CU | ~2 GB | 209 |
| 4 CU | ~8 GB | 839 |
| 8 CU | ~16 GB | 1,678 |
| 16 CU | ~32 GB | 3,357 |
| 32 CU | ~64 GB | 4,000 |
| 64 CU | ~128 GB | 4,000 |
| 112 CU | ~224 GB | 4,000 |

**Note:** Lakebase Provisioned used ~16 GB per CU. Autoscaling uses ~2 GB per CU for more granular scaling.

## Creating a Compute

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType

w = WorkspaceClient()

# Create a read-write compute endpoint
result = w.postgres.create_endpoint(
    parent="projects/my-app/branches/production",
    endpoint=Endpoint(
        spec=EndpointSpec(
            endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
            autoscaling_limit_min_cu=0.5,
            autoscaling_limit_max_cu=4.0
        )
    ),
    endpoint_id="my-compute"
).wait()

print(f"Endpoint created: {result.name}")
print(f"Host: {result.status.hosts.host}")
```

### CLI

```bash
databricks postgres create-endpoint \
    projects/my-app/branches/production my-compute \
    --json '{
        "spec": {
            "endpoint_type": "ENDPOINT_TYPE_READ_WRITE",
            "autoscaling_limit_min_cu": 0.5,
            "autoscaling_limit_max_cu": 4.0
        }
    }'
```

**Important:** Each branch can have only one read-write compute.

## Getting Compute Details

```python
endpoint = w.postgres.get_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute"
)

print(f"Endpoint: {endpoint.name}")
print(f"Type: {endpoint.status.endpoint_type}")
print(f"State: {endpoint.status.current_state}")
print(f"Host: {endpoint.status.hosts.host}")
print(f"Min CU: {endpoint.status.autoscaling_limit_min_cu}")
print(f"Max CU: {endpoint.status.autoscaling_limit_max_cu}")
```

## Listing Computes

```python
endpoints = list(w.postgres.list_endpoints(
    parent="projects/my-app/branches/production"
))

for ep in endpoints:
    print(f"Endpoint: {ep.name}")
    print(f"  Type: {ep.status.endpoint_type}")
    print(f"  CU Range: {ep.status.autoscaling_limit_min_cu}-{ep.status.autoscaling_limit_max_cu}")
```

## Resizing a Compute

Use `update_mask` to specify which fields to update:

```python
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, FieldMask

# Update min and max CU
w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/my-compute",
        spec=EndpointSpec(
            autoscaling_limit_min_cu=2.0,
            autoscaling_limit_max_cu=8.0
        )
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu"
    ])
).wait()
```

### CLI

```bash
# Update single field
databricks postgres update-endpoint \
    projects/my-app/branches/production/endpoints/my-compute \
    spec.autoscaling_limit_max_cu \
    --json '{"spec": {"autoscaling_limit_max_cu": 8.0}}'

# Update multiple fields
databricks postgres update-endpoint \
    projects/my-app/branches/production/endpoints/my-compute \
    "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
    --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}'
```

## Deleting a Compute

```python
w.postgres.delete_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute"
).wait()
```

## Autoscaling

Autoscaling dynamically adjusts compute resources based on workload demand.

### Configuration

- **Range:** 0.5-32 CU
- **Constraint:** Max - Min cannot exceed 8 CU
- **Valid examples:** 4-8 CU, 8-16 CU, 16-24 CU
- **Invalid example:** 0.5-32 CU (range of 31.5 CU)

### Best Practices

- Set minimum CU large enough to cache your working set in memory
- Performance may be degraded until compute scales up and caches data
- Connection limits are based on the maximum CU in the range

## Scale-to-Zero

Automatically suspends compute after a period of inactivity.

| Setting | Description |
|---------|-------------|
| **Enabled** | Compute suspends after inactivity timeout (saves cost) |
| **Disabled** | Always-active compute (eliminates wake-up latency) |

**Default behavior:**
- `production` branch: Scale-to-zero **disabled** (always active)
- Other branches: Scale-to-zero can be configured

**Default inactivity timeout:** 5 minutes
**Minimum inactivity timeout:** 60 seconds

### Wake-up Behavior

When a connection arrives on a suspended compute:
1. Compute starts automatically (reactivation takes a few hundred milliseconds)
2. The connection request is handled transparently once active
3. Compute restarts at minimum autoscaling size (if autoscaling enabled)
4. Applications should implement connection retry logic for the brief reactivation period

### Session Context After Reactivation

When a compute suspends and reactivates, session context is **reset**:
- In-memory statistics and cache contents are cleared
- Temporary tables and prepared statements are lost
- Session-specific configuration settings reset
- Connection pools and active transactions are terminated

If your application requires persistent session data, consider disabling scale-to-zero.

## Sizing Guidance

| Factor | Recommendation |
|--------|---------------|
| Query complexity | Complex analytical queries benefit from larger computes |
| Concurrent connections | More connections need more CPU and memory |
| Data volume | Larger datasets may need more memory for performance |
| Response time | Critical apps may require larger computes |
