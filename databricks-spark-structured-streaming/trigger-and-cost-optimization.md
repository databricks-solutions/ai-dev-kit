---
name: trigger-and-cost-optimization
description: Select and tune triggers for Spark Structured Streaming to balance latency and cost. Use when choosing between processingTime, availableNow, and Real-Time Mode (RTM), calculating optimal trigger intervals, optimizing costs through cluster right-sizing, scheduled streaming, multi-stream clusters, or managing latency vs cost trade-offs.
---

# Trigger and Cost Optimization

Select and tune triggers to balance latency requirements with cost. Optimize streaming job costs through trigger tuning, cluster right-sizing, multi-stream clusters, storage optimization, and scheduled execution patterns.

## Quick Start

```python
# Cost-optimized: Scheduled streaming instead of continuous
df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/stream") \
    .trigger(availableNow=True) \  # Process all, then stop
    .start("/delta/target")

# Schedule via Databricks Jobs: Every 15 minutes
# Cost: ~$20/day for 100 tables on 8-core cluster
```

## Trigger Types

### ProcessingTime Trigger

Process at fixed intervals:

```python
# Process every 30 seconds
.trigger(processingTime="30 seconds")

# Process every 5 minutes
.trigger(processingTime="5 minutes")

# Latency: Trigger interval + processing time
# Cost: Continuous cluster running
```

### AvailableNow Trigger

Process all available data, then stop:

```python
# Process all available data, then stop
.trigger(availableNow=True)

# Schedule via Databricks Jobs:
# - Every 15 minutes: Near real-time
# - Every 4 hours: Batch-style

# Latency: Schedule interval + processing time
# Cost: Cluster runs only during processing
```

### Real-Time Mode (RTM)

Sub-second latency with Photon:

```python
# Real-Time Mode (Databricks 13.3+)
.trigger(realTime=True)

# Requirements:
# - Photon enabled
# - Fixed-size cluster (no autoscaling)
# - Latency: < 800ms

# Cost: Continuous cluster with Photon
```

## Trigger Selection Guide

| Latency Requirement | Trigger | Cost | Use Case |
|---------------------|---------|------|----------|
| < 800ms | RTM | $$$ | Real-time analytics, alerts |
| 1-30 seconds | processingTime | $$ | Near real-time dashboards |
| 15-60 minutes | availableNow (scheduled) | $ | Batch-style SLA |
| > 1 hour | availableNow (scheduled) | $ | ETL pipelines |

## Trigger Interval Calculation

### Rule of Thumb: SLA / 3

```python
# Calculate trigger interval from SLA
business_sla_minutes = 60  # 1 hour SLA
trigger_interval_minutes = business_sla_minutes / 3  # 20 minutes

.trigger(processingTime=f"{trigger_interval_minutes} minutes")

# Why /3?
# - Processing time buffer
# - Recovery time buffer
# - Safety margin
```

### Example Calculations

```python
# Example 1: 1 hour SLA
sla = 60  # minutes
trigger = sla / 3  # 20 minutes
.trigger(processingTime="20 minutes")

# Example 2: 15 minute SLA
sla = 15  # minutes
trigger = sla / 3  # 5 minutes
.trigger(processingTime="5 minutes")

# Example 3: Real-time requirement
.trigger(realTime=True)  # < 800ms
```

## Cost Optimization Strategies

### Strategy 1: Trigger Interval Tuning

Balance latency and cost:

```python
# Shorter interval = higher cost
.trigger(processingTime="5 seconds")   # Expensive - continuous processing

# Longer interval = lower cost
.trigger(processingTime="5 minutes")   # Cheaper - less frequent processing

# Use availableNow for batch-style (cheapest)
.trigger(availableNow=True)            # Process backlog, then stop

# Rule of thumb: SLA / 3
# Example: 1 hour SLA → 20 minute trigger
```

### Strategy 2: Scheduled vs Continuous

Choose execution pattern based on SLA:

| Pattern | Cost | Latency | Use Case |
|---------|------|---------|----------|
| Continuous | $$$ | < 1 minute | Real-time requirements |
| 15-min schedule | $$ | 15-30 minutes | Near real-time |
| 4-hour schedule | $ | 4-5 hours | Batch-style SLA |

```python
# Continuous (expensive)
.trigger(processingTime="30 seconds")

# Scheduled (cost-effective)
.trigger(availableNow=True)  # Schedule via Jobs: Every 15 minutes

# Batch-style (cheapest)
.trigger(availableNow=True)  # Schedule via Jobs: Every 4 hours
```

### Strategy 3: Cluster Right-Sizing

Right-size clusters based on workload:

```python
# Don't oversize:
# - Monitor CPU utilization (target 60-80%)
# - Check for idle time
# - Use fixed-size clusters (no autoscaling for streaming)

# Scale test approach:
# 1. Start small
# 2. Monitor lag (max offsets behind latest)
# 3. Scale up if falling behind
# 4. Right-size based on steady state
```

### Strategy 4: Multi-Stream Clusters

Run multiple streams on one cluster:

```python
# Run multiple streams on one cluster
# Tested: 100 streams on 8-core single-node cluster
# Cost: ~$20/day for 100 tables

# Example: Multiple streams on same cluster
stream1.writeStream.option("checkpointLocation", "/checkpoints/stream1").start()
stream2.writeStream.option("checkpointLocation", "/checkpoints/stream2").start()
stream3.writeStream.option("checkpointLocation", "/checkpoints/stream3").start()
# ... up to 100+ streams

# Monitor: CPU/memory per stream
# Scale cluster if aggregate utilization > 80%
```

### Strategy 5: Storage Optimization

Reduce storage costs:

```sql
-- VACUUM old files
VACUUM table RETAIN 24 HOURS;

-- Enable auto-optimize to reduce small files
ALTER TABLE table SET TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = true,
    'delta.autoOptimize.autoCompact' = true
);

-- Archive old data to cheaper storage
-- Use data retention policies
```

## Cost Formula

```
Daily Cost = 
    (Cluster DBU/hour × Hours running) +
    (Storage GB × Storage rate) +
    (Network egress if applicable)

Optimization levers:
- Reduce hours running (scheduled triggers)
- Reduce cluster size (right-sizing)
- Reduce storage (VACUUM, compression)
- Reduce network egress (co-locate compute and storage)
```

## Common Patterns

### Pattern 1: Cost-Optimized Scheduled Streaming

Convert continuous to scheduled:

```python
# Before: Continuous (expensive)
df.writeStream \
    .trigger(processingTime="30 seconds") \
    .start()

# After: Scheduled (cost-effective)
df.writeStream \
    .trigger(availableNow=True) \  # Process all, then stop
    .start()

# Schedule via Databricks Jobs:
# - Every 15 minutes: Near real-time
# - Every 4 hours: Batch-style
# Same code, different schedule
```

### Pattern 2: Multi-Stream Cluster

Optimize cluster utilization:

```python
# Run multiple streams on one cluster
def start_all_streams():
    streams = []
    
    # Start multiple streams
    for i in range(100):
        stream = (spark
            .readStream
            .table(f"source_{i}")
            .writeStream
            .format("delta")
            .option("checkpointLocation", f"/checkpoints/stream_{i}")
            .trigger(availableNow=True)
            .start(f"/delta/target_{i}")
        )
        streams.append(stream)
    
    return streams

# Monitor aggregate CPU/memory
# Scale cluster if needed
```

### Pattern 3: RTM for Sub-Second Latency

Use RTM for real-time requirements:

```python
# Real-Time Mode for sub-second latency
df.writeStream \
    .format("kafka")
    .option("topic", "output")
    .trigger(realTime=True) \
    .start()

# Required configurations:
spark.conf.set("spark.databricks.photon.enabled", "true")
spark.conf.set("spark.sql.streaming.stateStore.providerClass", 
               "com.databricks.sql.streaming.state.RocksDBStateProvider")

# Latency: < 800ms
# Cost: Continuous cluster with Photon
```

## Real-Time Mode (RTM) Configuration

### Enable RTM

```python
# Enable Real-Time Mode
.trigger(realTime=True)

# Required configurations:
spark.conf.set("spark.databricks.photon.enabled", "true")
spark.conf.set("spark.sql.streaming.stateStore.providerClass", 
               "com.databricks.sql.streaming.state.RocksDBStateProvider")

# Cluster requirements:
# - Fixed-size cluster (no autoscaling)
# - Photon enabled
# - Driver: Minimum 4 cores
```

### RTM Use Cases

```python
# Good for RTM:
# - Sub-second latency requirements
# - Simple transformations
# - Stateless operations
# - Kafka-to-Kafka pipelines

# Not recommended for RTM:
# - Stateful operations (aggregations, joins)
# - Complex transformations
# - Large batch sizes
```

## Performance Considerations

### Batch Duration vs Trigger Interval

```python
# Batch duration should be < trigger interval
# Example:
trigger_interval = 30  # seconds
batch_duration = 10  # seconds

# Healthy: batch_duration < trigger_interval
# Unhealthy: batch_duration >= trigger_interval

# Monitor in Spark UI:
# - Batch duration
# - Trigger interval
# - Alert if batch duration >= trigger interval
```

### Trigger Interval Tuning

```python
# Start conservative, optimize based on monitoring
# Step 1: Start with SLA / 3
trigger_interval = business_sla / 3

# Step 2: Monitor batch duration
# If batch duration < trigger_interval / 2: Can increase trigger
# If batch duration >= trigger_interval: Decrease trigger

# Step 3: Optimize for cost vs latency
# Increase trigger interval to reduce cost
# Decrease trigger interval to reduce latency
```

## Cost Monitoring

### Track Per-Stream Costs

```python
# Tag jobs with stream name
job_tags = {
    "stream_name": "orders_stream",
    "environment": "prod",
    "cost_center": "analytics"
}

# Use DBU consumption metrics
# Monitor by workspace/cluster
# Track cost per stream over time
```

### Monitor Cluster Utilization

```python
# Check CPU utilization
# Target: 60-80% utilization
# Below 60%: Consider downsizing
# Above 80%: Consider upsizing

# Check memory utilization
# Monitor for OOM errors
# Adjust cluster size accordingly
```

## Latency vs Cost Trade-offs

### Continuous Processing

```python
# High cost, low latency
.trigger(processingTime="30 seconds")

# Cost: Continuous cluster running
# Latency: 30 seconds + processing time
# Use when: Real-time requirements
```

### Scheduled Processing

```python
# Lower cost, higher latency
.trigger(availableNow=True)  # Schedule: Every 15 minutes

# Cost: Cluster runs only during processing
# Latency: Schedule interval + processing time
# Use when: Batch-style SLA acceptable
```

### Real-Time Mode

```python
# Highest cost, lowest latency
.trigger(realTime=True)

# Cost: Continuous cluster with Photon
# Latency: < 800ms
# Use when: Sub-second latency required
```

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **High latency** | Trigger interval too long | Decrease trigger interval or use RTM |
| **High cost** | Continuous processing | Use scheduled (availableNow) |
| **Batch duration > trigger** | Processing too slow | Optimize processing or increase trigger |
| **RTM not working** | Photon not enabled | Enable Photon and configure cluster |

## Quick Wins

1. **Change from continuous to 15-minute schedule** - Significant cost reduction
2. **Run multiple streams per cluster** - Better cluster utilization
3. **Enable auto-optimize** - Reduce storage costs
4. **Use Spot instances** - For non-critical streams (with caution)
5. **Archive old data** - Move to cheaper storage tiers

## Trade-offs

| Cost Reduction | Impact | Mitigation |
|----------------|--------|------------|
| Longer trigger | Higher latency | Acceptable if SLA allows |
| Smaller cluster | May fall behind | Monitor lag; scale if needed |
| Aggressive VACUUM | Less time travel | Balance retention vs cost |
| Spot instances | Possible interruptions | Use for non-critical streams |
| Scheduled vs continuous | Higher latency | Match to business SLA |

## Production Best Practices

### Match Trigger to SLA

```python
# Calculate trigger from business SLA
def calculate_trigger_interval(sla_minutes):
    """Calculate optimal trigger interval"""
    return max(30, sla_minutes / 3)  # Minimum 30 seconds

trigger_interval = calculate_trigger_interval(business_sla_minutes)
.trigger(processingTime=f"{trigger_interval} seconds")
```

### Cluster Configuration

```python
# Fixed-size cluster (no autoscaling for streaming)
cluster_config = {
    "num_workers": 4,
    "node_type_id": "i3.xlarge",
    "autotermination_minutes": 60,  # Terminate if idle
    "enable_elastic_disk": True  # Reduce storage costs
}
```

### Storage Management

```sql
-- Enable auto-optimize
ALTER TABLE table SET TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = true,
    'delta.autoOptimize.autoCompact' = true
);

-- Periodic VACUUM
VACUUM table RETAIN 7 DAYS;  -- Balance retention vs cost

-- Archive old partitions
-- Move to cheaper storage tier
```

## Production Checklist

- [ ] Trigger type selected based on latency requirements
- [ ] Trigger interval calculated from SLA (SLA / 3)
- [ ] Batch duration monitored (< trigger interval)
- [ ] Cluster right-sized (60-80% utilization)
- [ ] Multiple streams per cluster (if applicable)
- [ ] Scheduled execution (if SLA allows)
- [ ] RTM configured if sub-second latency required
- [ ] Auto-optimize enabled
- [ ] Storage costs monitored
- [ ] Cost per stream tracked

## Related Skills

- `kafka-streaming` - RTM configuration for Kafka pipelines
- `checkpoint-best-practices` - Checkpoint management
