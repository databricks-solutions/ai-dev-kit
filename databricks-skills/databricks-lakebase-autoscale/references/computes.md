# Lakebase Autoscaling — Computes (deep dive)

Deep dive for Endpoints (computes). Basic CLI is in [SKILL.md](../SKILL.md).

## What an Endpoint Is

An endpoint is a Postgres server instance attached to one branch. Each branch has exactly one R/W endpoint (conventionally `ep-primary`) and may have additional read-only replicas. The endpoint owns the hostname clients connect to and the CU budget that determines concurrency and RAM.

## Compute Units

1 CU ≈ 2 GB RAM (vs ~16 GB/CU on Lakebase Provisioned — the autoscaling tier trades per-unit RAM for finer scaling granularity).

| CU | RAM | Max connections |
|----|-----|-----------------|
| 0.5 | ~1 GB | 104 |
| 1 | ~2 GB | 209 |
| 4 | ~8 GB | 839 |
| 8 | ~16 GB | 1,678 |
| 16 | ~32 GB | 3,357 |
| 32 | ~64 GB | 4,000 |
| 64 | ~128 GB | 4,000 |
| 112 | ~224 GB | 4,000 |

Max connections flattens at 4,000 above 32 CU — scale up past 32 CU for memory/CPU, not for connection headroom.

## Sizing Categories

| Category | Range | Behavior |
|----------|-------|----------|
| Autoscale | 0.5-32 CU | Dynamic scaling; `max − min ≤ 16 CU` |
| Large fixed | 36-112 CU | Fixed size, no autoscaling |

**Autoscaling window constraint.** The spread between `autoscaling_limit_min_cu` and `autoscaling_limit_max_cu` cannot exceed 16 CU:
- Valid: .5-4, 4-20, 8-32
- Invalid: 0.5-32 (31.5 CU spread), 1-24 (23 CU spread)

Set the minimum high enough to keep your working set in memory — traffic that lands after a scale-up pays a cache-warm penalty until hot pages are faulted back in.

## Scale-to-Zero

When enabled, an endpoint suspends after an inactivity window (min 60 s, default 5 min). Default state per branch:

| Branch | Default |
|--------|---------|
| `production` | Scale-to-zero **off** (always active) |
| Others | Scale-to-zero configurable |

### Wake-up

Incoming connections to a suspended endpoint trigger reactivation. Expected latency is ~100ms, but:
- First connection may see a timeout — applications must retry.
- Endpoint resumes at the **minimum** of its autoscaling range; expect cache-cold performance until load ramps up.
- All session-scoped state is lost: in-memory stats, temp tables, prepared statements, session GUCs, active transactions.

If your app keeps session state server-side (e.g., Postgres advisory locks, prepared statements you don't re-prepare), disable scale-to-zero.

## Advanced CLI

Create a read replica:

```bash
databricks postgres create-endpoint \
    projects/my-app/branches/production ep-readonly-1 \
    --json '{"spec": {"endpoint_type": "ENDPOINT_TYPE_READ_ONLY",
                      "autoscaling_limit_min_cu": 1.0,
                      "autoscaling_limit_max_cu": 4.0}}'
```

Change scale-to-zero timeout (durations are strings ending in `s`):

```bash
databricks postgres update-endpoint \
    projects/my-app/branches/development/endpoints/primary \
    spec.suspend_timeout_duration \
    --json '{"spec": {"suspend_timeout_duration": "1800s"}}'  # 30 min
```

Disable scale-to-zero on a non-default branch (`"0s"` = off):

```bash
databricks postgres update-endpoint \
    projects/my-app/branches/staging/endpoints/primary \
    spec.suspend_timeout_duration \
    --json '{"spec": {"suspend_timeout_duration": "0s"}}'
```

Convert from autoscale to a large fixed size (e.g., 64 CU):

```bash
databricks postgres update-endpoint \
    projects/my-app/branches/production/endpoints/primary \
    "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
    --json '{"spec": {"autoscaling_limit_min_cu": 64.0, "autoscaling_limit_max_cu": 64.0}}'
```

## High Availability

HA adds 1–3 read secondaries across availability zones with automatic failover (hot standby, automatic primary promotion on failure).

**Secondaries vs. read replicas:**
- **HA secondaries** share a `-ro` hostname suffix and floor at the primary's current CU. Use for failover with optional read offload.
- **Read replicas** are separate endpoints (`ENDPOINT_TYPE_READ_ONLY`) with independent sizing. Use for dedicated read scaling.

**HA constraints:**
- Scale-to-zero is **not supported** with HA enabled.
- Autoscaling spread limit (≤16 CU) still applies.
- Secondaries autoscale independently but won't drop below the primary's current minimum.
- Total compute instances per project: 2–4 (primary + 1–3 secondaries).

## Sizing Guidance

| Factor | Recommendation |
|--------|----------------|
| Query complexity | Complex analytical queries benefit from larger computes |
| Concurrent connections | Scale up until 32 CU; past that you're buying CPU/RAM, not connections |
| Working-set size | Min CU should hold your hot data in RAM |
| Latency-sensitive apps | Disable scale-to-zero or accept wake-up retries |

## SDK Equivalents

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import (
    Endpoint, EndpointSpec, EndpointType, FieldMask,
)

w = WorkspaceClient()

# Create R/W endpoint
w.postgres.create_endpoint(
    parent="projects/my-app/branches/production",
    endpoint=Endpoint(spec=EndpointSpec(
        endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
        autoscaling_limit_min_cu=0.5,
        autoscaling_limit_max_cu=4.0,
    )),
    endpoint_id="my-compute",
).wait()

# Resize
w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/my-compute",
        spec=EndpointSpec(autoscaling_limit_min_cu=2.0, autoscaling_limit_max_cu=8.0),
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu",
    ]),
).wait()

# Delete
w.postgres.delete_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute"
).wait()
```
