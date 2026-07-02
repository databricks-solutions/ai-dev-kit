# Serverless Job Execution

**Use when:** Running intensive Python code remotely (ML training, heavy processing) that doesn't need Spark, or when code shouldn't depend on local machine staying connected.

## When to Choose Serverless Job

- ML model training (runs independently of local machine)
- Heavy non-Spark Python processing
- Code that takes > 5 minutes (local connection can drop)
- Production/scheduled runs

## Trade-offs

| Pro | Con |
|-----|-----|
| No cluster to manage | ~25-50s cold start each invocation |
| Up to 30 min timeout | No state preserved between calls |
| Independent execution | print() unreliable—use `dbutils.notebook.exit()` |

## Executing code
### Prefer running from a Local File (edit the local file then run it)

```python
execute_code(
    file_path="/local/path/to/train_model.py",
    compute_type="serverless"
)
```

## Jobs with Custom Dependencies

Use `job_extra_params` to install pip packages:

```python
execute_code(
    file_path="/path/to/train.py",
    job_extra_params={
        "environments": [{
            "environment_key": "ml_env",
            "spec": {"client": "4", "dependencies": ["scikit-learn", "pandas", "mlflow"]}
        }]
    }
)
```

**CRITICAL:** Use `"client": "4"` in the spec. `"client": "1"` won't install dependencies.

## Output Handling

```python
# ❌ BAD - print() may not be captured
print("Training complete!")

# ✅ GOOD - Use dbutils.notebook.exit()
import json
results = {"accuracy": 0.95, "model_path": "/Volumes/..."}
dbutils.notebook.exit(json.dumps(results))
```

## Common Issues

| Issue | Solution |
|-------|----------|
| print() output missing | Use `dbutils.notebook.exit()` |
| `ModuleNotFoundError` | Add to environments spec with `"client": "4"` |
| Job times out | Max is 1800s; split into smaller tasks |

## When NOT to Use

Switch to **[Databricks Connect](1-databricks-connect.md)** when:
- Iterating on Spark code and want instant feedback
- Need local debugging with breakpoints

Switch to **[Interactive Cluster](3-interactive-cluster.md)** when:
- Need state across multiple MCP tool calls
- Need Scala or R support
