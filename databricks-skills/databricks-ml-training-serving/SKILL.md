---
name: databricks-ml-training-serving
description: "Classical ML and custom-agent model training, registration, and inference on Databricks. Use when: user ask to train models on Databricks, with MLflow tracking or autolog (sklearn, XGBoost, LightGBM, PyTorch, custom pyfunc etc); registering models to Unity Catalog; MLOPS, promoting versions with `@prod` / `@challenger` aliases; loading a registered model for batch scoring via `mlflow.pyfunc.spark_udf`; creating, updating, querying, or version-swapping a Databricks Model Serving endpoint; calling Foundation Model API endpoints (Claude / GPT / Llama / Gemini / embeddings); writing a custom MLflow `ResponsesAgent` (LangGraph, OpenAI-compatible chat) with UC Function or Vector Search tools. NOT for: no-code Knowledge Assistants or Supervisor Agents (use databricks-agent-bricks); MLflow evaluation / scorers (use databricks-mlflow-evaluation)."
---

# ML Training & Serving on Databricks

Train with MLflow → register to Unity Catalog → consume the **same artifact** as either a batch Spark UDF over Delta or a real-time REST endpoint (~5–15 min cold start, quota-bound — only when the user asks for per-request low-latency scoring).

> **Always train on Databricks** (serverless job or notebook), never in the local Python process the agent is running in. Local training has no access to the silver tables, no MLflow tracking server, no UC registry path, and dies if the chat session drops — submit `databricks jobs submit --no-wait` (see "Train + deploy as a serverless job" below). Only fall back to local execution if the user explicitly asks for it.

| Consumption | When | How |
|---|---|---|
| **Batch UDF** | Dashboards, daily/hourly scores, precomputed ~daily predictions, read by Genie/Dashboards, or app (typically synched to a lakebase table) | `mlflow.pyfunc.spark_udf(...)` → `INSERT INTO gold_predictions` |
| **Real-time endpoint** | Score on a user action (fraud at authorization, rec at page load) — sub-100ms | `mlflow.deployments.get_deploy_client()` (classical) / `agents.deploy()` (agents) |

## Canonical flow

```
silver_<features>  +  silver_<labels>
        ▼
   notebook (as a serverless job):
   ├── train with mlflow.autolog (XGBoost / sklearn / etc.)
   ├── mlflow.register_model → UC: {catalog}.{schema}.{model}
   ├── set_registered_model_alias(name, "prod", version)
   └── spark_udf(@prod) over latest features → MERGE into gold_predictions
        ▼
gold_<entity>_predictions   ◄── dashboards, apps, Genie read this
```

One notebook, one artifact. Re-running = retraining. Gold is where truth lives — read paths never call the model directly. Keep label-window logic (`failure occurred within 7 days`) in the notebook during dev; once stable, promote to a silver materialized view in SDP.

---

## Train and register (the 90% case)

`mlflow.autolog()` captures params, metrics, code, and the model artifact for every run; `registered_model_name=...` auto-registers the best run to UC (auto-incremented version). Wrap training with **Optuna** so each trial is a child run and the best one is what gets registered.

**Always `mlflow.set_registry_uri("databricks-uc")`** — without it, models land in the deprecated workspace registry. **The experiment's parent folder must exist** — `set_experiment` does NOT auto-create it (fails with `NOT_FOUND: Parent directory does not exist`). Pre-create it once with `databricks workspace mkdirs` before the job runs.

```bash
# Once per project — create the parent folder for the MLflow experiment.
databricks workspace mkdirs /Users/me@example.com/turbine_project
```

```python
import mlflow, mlflow.xgboost, optuna
from mlflow.tracking import MlflowClient
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/me@example.com/turbine_project/mlflow_experiment")

CATALOG, SCHEMA, NAME = "ai_demo_gen", "wind_farm", "turbine_failure"
FULL_NAME = f"{CATALOG}.{SCHEMA}.{NAME}"

mlflow.xgboost.autolog(log_input_examples=True, registered_model_name=FULL_NAME)

# For imbalanced labels: stratify the split, set scale_pos_weight = neg/pos.
def objective(trial):
    params = {
        "n_estimators":  trial.suggest_int("n_estimators", 100, 400),
        "max_depth":     trial.suggest_int("max_depth", 3, 10),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
    }
    with mlflow.start_run(nested=True):
        m = XGBClassifier(**params).fit(X_train, y_train)
        return roc_auc_score(y_test, m.predict_proba(X_test)[:, 1])

with mlflow.start_run(run_name="hpo"):
    optuna.create_study(direction="maximize").optimize(objective, n_trials=20)

# Move @prod alias to the just-registered version. Stages are deprecated — aliases only.
client = MlflowClient(registry_uri="databricks-uc")
latest = max(client.search_model_versions(f"name='{FULL_NAME}'"),
             key=lambda v: int(v.version))
client.set_registered_model_alias(FULL_NAME, "prod", latest.version)
```

**Framework autolog**: `mlflow.{sklearn,xgboost,lightgbm,pytorch,tensorflow,spark}.autolog()`.

**Aliases, not stages**: UC dropped `Staging`/`Production`. Use movable `@prod`/`@challenger`; load with `models:/{full_name}@prod`. Promoting a new version is one `set_registered_model_alias` call.

---

## Consume: batch scoring over Delta

The cheap, default path. Load the registered model as a Spark UDF and score a Delta table; write predictions to a gold table that downstream consumers read.

```python
import mlflow

# env_manager rules:
#   "local"     → same runtime as training (same notebook/job). Fastest for the demo, keep that.
#   "virtualenv"→ different runtime than training; rebuilds the model's env.
#   "uv"        → same as virtualenv but faster (MLflow ≥ 2.22).
predict = mlflow.pyfunc.spark_udf(
    spark,
    model_uri=f"models:/{FULL_NAME}@prod",
    env_manager="local",
)

features = spark.table(f"{CATALOG}.{SCHEMA}.silver_turbine_features_latest")
scored = features.withColumn("risk_score", predict(*[features[c] for c in feature_cols]))

# Overwrite-per-run pattern for "latest score per entity":
scored.select("turbine_id", "risk_score", F.current_timestamp().alias("scored_at")) \
    .write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.gold_turbine_predictions")
```

For incremental scoring with history, MERGE into the predictions table instead of overwrite.

---

## Consume: real-time serving endpoint (only when required)

Use the MLflow Deployments client. `workload_size: "Small"` + `scale_to_zero_enabled: true` is the default for demos and dev. First deploy can take ~5 min for classical ML

```python
from mlflow.deployments import get_deploy_client

client = get_deploy_client("databricks")
client.create_endpoint(
    name="turbine-risk-endpoint",
    config={
        "served_entities": [{
            "entity_name": FULL_NAME,
            "entity_version": latest.version,
            "workload_size": "Small",
            "scale_to_zero_enabled": True, # Always
        }],
        # served_model_name = "<model>-<version>"; the API auto-derives it but
        # you reference this exact string in traffic_config.
        "traffic_config": {"routes": [
            {"served_model_name": f"{NAME}-{latest.version}", "traffic_percentage": 100}
        ]},
    },
    # Tags are TOP-LEVEL — NOT inside `config`. Same {key, value} shape used
    # by `serving-endpoints patch --add-tags`. Tag every demo resource for cleanup.
    tags=[{"key": "aidevkit_project", "value": "ai-dev-kit"}],
)
```

**Zero-downtime version swap.** Repoint the alias *and* call `update_endpoint`:

```python
client.set_registered_model_alias(FULL_NAME, "prod", new_version)
client.update_endpoint(endpoint="turbine-risk-endpoint", config={
    "served_entities": [{"entity_name": FULL_NAME, "entity_version": new_version,
                        "workload_size": "Small", "scale_to_zero_enabled": True}],
    "traffic_config": {"routes": [
        {"served_model_name": f"{NAME}-{new_version}", "traffic_percentage": 100}
    ]},
})
```

### Endpoint management (CLI)

```bash
databricks serving-endpoints list
databricks serving-endpoints get turbine-risk-endpoint
databricks serving-endpoints delete turbine-risk-endpoint

# Query a classical ML endpoint
databricks serving-endpoints query turbine-risk-endpoint --json '{
  "dataframe_records": [{"vibration": 0.42, "rpm": 18.3, "temp_c": 71.2}]
}'

# Query a chat/agent endpoint
databricks serving-endpoints query my-agent-endpoint --json '{
  "messages": [{"role":"user","content":"Hello"}], "max_tokens": 500
}'

# Tag for project tracking
databricks serving-endpoints patch turbine-risk-endpoint --json '{
  "add_tags": [{"key": "aidevkit_project", "value": "ai-dev-kit"}]
}'
```

### Readiness has TWO state fields

`databricks serving-endpoints get` returns both:

- `state.ready` — `READY` once the endpoint has any working config (first deploy).
- `state.config_update` — `NOT_UPDATING` once the *current* config update finishes; `IN_PROGRESS` during a version swap.

A loop watching only `state.ready` will say "ready" mid version-swap while the old version is still serving. Poll **both**:

```bash
databricks serving-endpoints get turbine-risk-endpoint \
  | jq '{ready: .state.ready, config_update: .state.config_update}'
```

---

## Train + deploy as a serverless job

Training notebooks run a few minutes (Optuna + UC register; endpoint warmup adds 5–15 min if you also deploy). Submit as a serverless one-time run so the CLI doesn't block. The notebook ends with `dbutils.notebook.exit(json.dumps({...}))` so the structured result (`model_version`, `val_auc`, `endpoint_name`) reaches `.notebook_output.result`.

```bash
# 1. Upload the training notebook
databricks workspace import /Workspace/Users/me@example.com/turbine_project/train \
  --file ./train_notebook.py --format SOURCE --language PYTHON --overwrite

# 2. Submit as serverless one-time run (returns {"run_id": N} immediately with --no-wait)
RUN_ID=$(databricks jobs submit --no-wait --json '{
  "run_name": "turbine-train-and-deploy",
  "tasks": [{
    "task_key": "train",
    "notebook_task": {"notebook_path": "/Workspace/Users/me@example.com/turbine_project/train"},
    "environment_key": "ml_env"
  }],
  "environments": [{
    "environment_key": "ml_env",
    "spec": {
      "client": "4",
      "dependencies": ["mlflow==2.22.0", "xgboost==2.1.3", "optuna==4.1.0", "scikit-learn==1.5.2"]
    }
  }]
}' | jq -r .run_id)

# 3. Poll until a terminal life_cycle_state.
for _ in $(seq 60); do
  STATE=$(databricks jobs get-run "$RUN_ID" | jq -r '.state.life_cycle_state // "UNKNOWN"')
  echo "$(date +%H:%M:%S) $STATE"
  [[ "$STATE" =~ ^(TERMINATED|SKIPPED|INTERNAL_ERROR)$ ]] && break
  sleep 30
done
[[ "$STATE" =~ ^(TERMINATED|SKIPPED|INTERNAL_ERROR)$ ]] || { databricks jobs cancel-run "$RUN_ID"; exit 1; }

# life_cycle_state TERMINATED only means "the run ended" — check result_state
# (SUCCESS / FAILED / TIMEDOUT / CANCELED / SUCCESS_WITH_FAILURES / …) for outcome.
RESULT=$(databricks jobs get-run "$RUN_ID" | jq -r '.state.result_state // "UNKNOWN"')
echo "result_state=$RESULT"
[[ "$RESULT" == "SUCCESS" ]] || { echo "Run did not succeed"; exit 1; }

# 4. Pull structured output via the TASK run_id (NOT the submit run_id).
TASK_RUN_ID=$(databricks jobs get-run "$RUN_ID" | jq -r '.tasks[0].run_id')
databricks jobs get-run-output "$TASK_RUN_ID" | jq '.notebook_output.result'
# → '{"model_version":"3","val_auc":0.91,"rows_scored":124,"endpoint":"turbine-risk-endpoint"}'
```

**Serving UI hides SP-owned endpoints by default.** If the deploy ran as a service principal, the Serving page won't show the new endpoint until you switch from "Owned by me" to "All". Or just `databricks serving-endpoints list`.

For the four `jobs submit` traps (`spec.client: "4"` requirement, TASK-vs-submit run_id, `print()` unreliable, tags rejected) and full debugging flow, see **[databricks-jobs](../databricks-jobs/SKILL.md#one-time-runs-jobs-submit--async-pattern-for-notebooks)**.

---

## Custom pyfunc

When sklearn/XGBoost autolog isn't enough — custom preprocessing, multiple sub-models, external API calls, ensemble logic. See **[1-custom-pyfunc.md](1-custom-pyfunc.md)** for a full worked example. Two non-obvious things:

- **`python_model="path/to/file.py"`** (file path, not class instance) + `mlflow.models.set_model(MyModel())` at the end of that file. This is the "Models from Code" pattern — the file is logged verbatim, no pickling of the class.
- **`mlflow.models.predict(model_uri=..., input_data=..., env_manager="uv")`** before deploying. Catches missing deps before the endpoint does.

---

## Foundation Model API endpoints

Pay-per-token, pre-provisioned in every workspace. New models land regularly and a static skill list goes stale fast — **always list at runtime instead of hard-coding names**. Filter by the `databricks-` name prefix AND by the served entity being in `system.ai.*` (other endpoints like `databricks-app-template-serving` share the prefix but aren't FM API endpoints).

```bash
# Foundation Model API endpoints in this workspace, grouped by task (chat / embeddings / etc.)
databricks serving-endpoints list \
  | jq -r '.[]
      | select(.name | startswith("databricks-"))
      | select((.config.served_entities[0].entity_name // "") | startswith("system.ai."))
      | "\(.task)\t\(.name)"' \
  | sort
```

**Defaults when the user doesn't specify**: pick the highest-numbered Claude Sonnet for agents, the highest-numbered `-codex-max` for code, `databricks-gte-large-en` for embeddings — resolve actual names from the live list above.

---

## Gotchas (the ones that cost time)

| Trap | Fix |
|---|---|
| Model lands in workspace registry, not UC | `mlflow.set_registry_uri("databricks-uc")` *before* logging |
| Endpoint returns PERMISSION_DENIED at first query | Pass `resources=[...]` to `log_model` (covers UC functions, VS indexes, other endpoints, Lakebase) — see [2-genai-agents.md](2-genai-agents.md#resources-that-need-passthrough-auth) for the full list |
| Used `transition_model_version_stage` | Stages are deprecated in UC. Use `client.set_registered_model_alias(name, "prod", version)` |
| `spark_udf` rebuilds a virtualenv on every call | Pass `env_manager="local"` when training+scoring share a runtime |
| Endpoint version swap says "ready" but old version still serving | Poll **both** `state.ready` AND `state.config_update` — see "Readiness has TWO state fields" |
| `pip_requirements` mismatch crashes endpoint at load | Pin exact versions; or pull live with `f"mlflow=={get_distribution('mlflow').version}"` |
| `agents.deploy()` produced a weirdly-named endpoint | Pass `endpoint_name=...` explicitly. Auto-derived name is `agents_<catalog>-<schema>-<model>` |
| Endpoint missing from Serving UI | UI filter defaults to "Owned by me"; deploy jobs run as SP. Switch to "All" or use `serving-endpoints list` |

---

## Reference files

| File | Contents |
|---|---|
| [1-custom-pyfunc.md](1-custom-pyfunc.md) | Single end-to-end custom pyfunc example: artifacts, signature, code_paths, log → register → deploy → query. |
| [2-genai-agents.md](2-genai-agents.md) | Edge case: deploying a LangGraph `ResponsesAgent` with UC Function + Vector Search tools. For supervised multi-agent tiles, use **databricks-agent-bricks** instead. |

## Related skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — no-code Knowledge Assistants and Supervisor Agents. Prefer this over hand-rolling agents.
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** — evaluate model/agent quality before promoting `@prod`.
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** — vector indexes used as retrieval tools in agents.
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — async deploy pattern (`--no-wait`, TASK run_id trap).
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — UC governs the registered model: permissions, lineage, audit.
