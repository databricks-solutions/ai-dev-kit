# Lakebase Computes and Scaling

## Compute Sizing

Each Compute Unit (CU) allocates ~2 GB of RAM. Lakebase Provisioned used ~16 GB per CU.

| Category | Range | Notes |
|----------|-------|-------|
| **Autoscale** | 0.5–32 CU | Dynamic scaling (max − min <= 16 CU) |
| **Fixed-size** | 36–112 CU | No autoscaling |

| CU | RAM | Max Connections |
|----|-----|-----------------|
| 0.5 | ~1 GB | 104 |
| 1 | ~2 GB | 209 |
| 4 | ~8 GB | 839 |
| 8 | ~16 GB | 1,678 |
| 16 | ~32 GB | 3,357 |
| 32+ | ~64 GB+ | 4,000 (cap) |

## Endpoint Operations

Each branch can have only one read-write endpoint. Run `databricks postgres <subcommand> -h` to discover exact flags.

```bash
# Create endpoint with autoscaling
databricks postgres create-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID> <ENDPOINT_ID> \
  --json '{"spec": {"endpoint_type": "ENDPOINT_TYPE_READ_WRITE", "autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 4.0}}' \
  --profile <PROFILE>

# Get endpoint details (host, state, CU range)
databricks postgres get-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>

# List endpoints on a branch
databricks postgres list-endpoints projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>

# Resize (update_mask specifies which fields to change)
databricks postgres update-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
  --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}' \
  --profile <PROFILE>

# Delete endpoint
databricks postgres delete-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>
```

## SDK equivalents

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType, FieldMask

w = WorkspaceClient()

# Create a read-write compute endpoint
w.postgres.create_endpoint(
    parent="projects/my-app/branches/production",
    endpoint=Endpoint(
        spec=EndpointSpec(
            endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
            autoscaling_limit_min_cu=0.5,
            autoscaling_limit_max_cu=4.0,
        )
    ),
    endpoint_id="my-compute",
).wait()

# Resize (update_mask lists which fields change)
w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/my-compute",
        spec=EndpointSpec(
            autoscaling_limit_min_cu=2.0,
            autoscaling_limit_max_cu=8.0,
        ),
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu",
    ]),
).wait()
```

## Autoscaling Configuration

- **Range:** 0.5–32 CU. **Constraint:** Max − Min <= 16 CU.
- **Valid:** 4–20 CU, 8–16 CU, 16–32 CU. **Invalid:** 0.5–32 CU (spread of 31.5).
- Set minimum CU large enough to cache your working set in memory.
- Connection limits are based on the maximum CU in the autoscaling range.

## Scale-to-Zero

Automatically suspends compute after inactivity. Default timeout: 5 minutes. Minimum: 60 seconds.

| Branch | Default |
|--------|---------|
| `production` | Scale-to-zero **disabled** (always active) |
| Other branches | Configurable |

**Wake-up:** Compute restarts automatically in ~100ms when a connection arrives. Restarts at minimum CU. Applications should implement retry logic for the brief reactivation period.

**Session context is reset on reactivation:**
- Temporary tables and prepared statements are lost
- Session settings and in-memory cache are cleared
- Connection pools and active transactions are terminated
- Advisory locks released, NOTIFY/LISTEN subscriptions lost

## High Availability

1 primary + 1–3 secondary compute instances across availability zones. GA on AWS and Azure.

**How it works:**
- Secondaries are hot standbys promoted automatically if primary fails
- All instances share the same storage layer
- Total: 2–4 compute instances per HA endpoint

**Connection strings:**

| String | Format | Routes To |
|--------|--------|-----------|
| Primary | `{endpoint-id}.database.{region}.databricks.com` | Current primary (auto-routes after failover) |
| Read-only | `{endpoint-id}-ro.database.{region}.databricks.com` | Readable secondaries |

**Enabling HA:** Configured at the endpoint level. Run `databricks postgres create-endpoint -h` and `databricks postgres update-endpoint -h` for spec fields. Each secondary can be Read-only (serves reads) or Disabled (failover standby only).

**Failover behavior:**
- All committed transactions are preserved
- Active connections are terminated — applications must reconnect
- Primary connection string routes to promoted secondary transparently
- With only one readable secondary, read traffic is interrupted during failover

**HA secondaries vs read replicas:**

| Feature | HA Secondaries | Read Replicas |
|---------|---------------|---------------|
| Purpose | Failover + optional reads | Read offload only |
| Failover | Yes, auto-promoted | No |
| Connection | Shared `-ro` string | Separate endpoint |
| Sizing | Floor at primary CU, can scale above | Independent |
| Scale-to-zero | Not supported | Configurable |

**Constraints:**
- Scale-to-zero not supported with HA
- Max autoscaling spread remains 16 CU
- Secondaries autoscale independently but will not scale below the primary's current CU size
- Minimum 2, maximum 4 compute instances

## Sizing Guidance

- Use `EXPLAIN ANALYZE` to understand query plans — **rows examined** is the most actionable metric
- Create covering indexes for frequent queries (include filter + sort columns)
- Paginate queries that can return unbounded result sets
- Keep transactions short and deterministic to avoid lock contention
- Follow consistent table access order within transactions to prevent deadlocks
