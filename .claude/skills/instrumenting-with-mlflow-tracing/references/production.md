# Production Configuration

This guide covers **configuration and optimization** for logging traces in production environments (environment variables, async logging, sampling).

For how to **construct traces** (instrumentation methods, what to trace, decorators, manual spans), refer to:
- `python.md` - Python instrumentation guide
- `typescript.md` - TypeScript instrumentation guide

---

## Contents
- Environment Variables
- Async Logging
- Sampling
---

## Environment Variables

Configure MLflow Tracing via environment variables for production deployments:

```bash
# Required: Tracking server URI
export MLFLOW_TRACKING_URI="http://mlflow-server:5000"

# Optional: Default experiment
export MLFLOW_EXPERIMENT_NAME="production-agent"

# Optional: Authentication
export MLFLOW_TRACKING_USERNAME="user"
export MLFLOW_TRACKING_PASSWORD="password"
# Or use token-based auth
export MLFLOW_TRACKING_TOKEN="your-token"
```

---

## Async Logging

For latency-sensitive applications, enable async logging to avoid blocking on trace uploads:

```python
import mlflow

mlflow.config.enable_async_logging(True)
```

Or via environment variable:

```bash
export MLFLOW_ENABLE_ASYNC_LOGGING=true
```

**Behavior**:
- Traces are queued and uploaded in a background thread
- Function returns immediately after local span creation
- Failed uploads are retried automatically

**Flush on shutdown**:

```python
import atexit
import mlflow

atexit.register(mlflow.flush_trace_async_logging)
```

---

## Sampling

Reduce tracing overhead by sampling a fraction of requests:

```bash
# Trace 10% of requests
export MLFLOW_TRACE_SAMPLING_RATIO=0.1
```

**Note**: Sampling is random per-trace. All spans within a sampled trace are captured.
