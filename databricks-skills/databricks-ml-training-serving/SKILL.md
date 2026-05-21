---
name: databricks-ml-training-serving
description: "ML training + Unity Catalog model registry + batch and real-time serving. Use when training classical ML (sklearn/XGBoost/LightGBM/PyTorch) with MLflow tracking, registering to UC, batch-scoring over Delta via spark_udf, or deploying real-time serving endpoints. For GenAI agents see [3-genai-agents.md](3-genai-agents.md); for pre-built no-code agents see databricks-agent-bricks."
---

# ML Training & Serving on Databricks

End-to-end ML lifecycle: train with MLflow tracking → register to Unity Catalog → consume either as **cheap batch inference** over Delta or as a **real-time REST endpoint**. Same artifact, two consumption patterns. Pick batch by default; switch to a serving endpoint only when the app needs per-request latency.

## Decision: batch vs serving

| Consumption | When | How |
|---|---|---|
| **Batch UDF over Delta** | Dashboards, daily/hourly scores, precomputed predictions table read by apps/Genie | `mlflow.pyfunc.spark_udf(...)` → `MERGE INTO gold_predictions` |
| **Real-time serving endpoint** | App needs to score on a user action (fraud at authorization, recommendation at page load) — sub-100ms | `agents.deploy()` or `mlflow.deployments.get_deploy_client()` |

Serving endpoints take ~5–15 min to come online for the first deploy and consume quota. **Don't deploy one for batch use cases.**

## Canonical flow

```
silver_<features>  +  silver_<labels>
        ▼
   nightly serverless job:
   ├── train with mlflow.autolog (XGBoost / sklearn / etc.)
   ├── mlflow.register_model → UC: {catalog}.{schema}.{model}
   ├── set_registered_model_alias(name, "prod", version)
   └── spark_udf(@prod) over latest features → MERGE into gold_predictions
        ▼
gold_<entity>_predictions   ◄── dashboards, apps, Genie read this
```

One notebook, one artifact. Re-running = retraining. Gold is where truth lives — read paths never call the model directly. See **[1-batch-scoring-pattern.md](1-batch-scoring-pattern.md)** for the full notebook.

---

## Train and register (the 90% case)

`mlflow.autolog()` captures params, metrics, code, and the model artifact for every run; `registered_model_name=...` auto-registers the best run to UC. Auto-incremented version. **Always `mlflow.set_registry_uri("databricks-uc")`** — without it, models land in the deprecated workspace registry.

```python
import mlflow
import mlflow.xgboost
from mlflow.tracking import MlflowClient
from xgboost import XGBClassifier

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/me@example.com/turbine_failure")

CATALOG, SCHEMA, NAME = "ai_demo_gen", "wind_farm", "turbine_failure"
FULL_NAME = f"{CATALOG}.{SCHEMA}.{NAME}"

mlflow.xgboost.autolog(log_input_examples=True, registered_model_name=FULL_NAME)

with mlflow.start_run() as run:
    model = XGBClassifier(n_estimators=200, max_depth=6).fit(X_train, y_train)
    auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    mlflow.log_metric("test_auc", auc)

# Move @prod alias to this version — stages are deprecated, aliases only.
client = MlflowClient(registry_uri="databricks-uc")
latest = client.get_model_version_by_alias(FULL_NAME, "latest") if False else \
         max(client.search_model_versions(f"name='{FULL_NAME}'"), key=lambda v: int(v.version))
client.set_registered_model_alias(FULL_NAME, "prod", latest.version)
```

**Framework autolog table**: `mlflow.{sklearn,xgboost,lightgbm,pytorch,tensorflow,spark}.autolog()`.

**HPO**: wrap with Optuna; pass `mlflow.xgboost.autolog()` and each trial becomes a child run. The best trial's model is the one auto-registered.

**Aliases, not stages**: UC dropped `Staging`/`Production` stages. Use movable aliases: `@prod`, `@challenger`. Load with `models:/{full_name}@prod` — promoting a new version is one `set_registered_model_alias` call.

---

## Consume: batch scoring over Delta

The cheap, default path. Load the registered model as a Spark UDF and score a Delta table; write predictions to a gold table that downstream consumers read.

```python
import mlflow

# env_manager rules:
#   "local"     → same runtime as training (same notebook/job). Fastest.
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

## Consume: real-time serving endpoint

Use the MLflow Deployments client. `workload_size: "Small"` + `scale_to_zero_enabled: true` is the default for demos and dev. First deploy takes ~5 min for classical ML, ~15 min for agents.

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
            "scale_to_zero_enabled": True,
        }],
        # served_model_name = "<model>-<version>"; the API auto-derives it but
        # you reference this exact string in traffic_config.
        "traffic_config": {"routes": [
            {"served_model_name": f"{NAME}-{latest.version}", "traffic_percentage": 100}
        ]},
    },
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
# Done when ready=READY AND config_update=NOT_UPDATING
```

---

## Deploy as an async job (long-running deploys)

Classical ML deploys are usually fast enough to wait for inline. Agents and large models take 10–15 min — run from a serverless job so the CLI doesn't block on you.

The full pattern (`--no-wait`, polling, `get-run-output`, and the **TASK run_id vs submit run_id** trap) is in **[databricks-jobs](../databricks-jobs/SKILL.md)**. Three specifics for model deploys:

- **`spec.client: "4"`** is required for the `environments[].spec.dependencies` list to actually install. `"1"` silently ignores it.
- **`print()` is unreliable on serverless**; end the notebook with `dbutils.notebook.exit(json.dumps({...}))` so the structured result (model version, endpoint name, AUC) shows up in `.notebook_output.result`.
- The `databricks serving-endpoints` UI page defaults to **Owned by me** — if the deploy job ran as a service principal, switch to **All** to see the endpoint, or list via `databricks serving-endpoints list`.

---

## Custom pyfunc

When sklearn/XGBoost autolog isn't enough — custom preprocessing, multiple sub-models, external API calls, ensemble logic. See **[2-custom-pyfunc.md](2-custom-pyfunc.md)** for a full worked example. Two non-obvious things:

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

**Naming conventions to recognize** (so you can pick a sensible default without listing every time):
- `databricks-claude-{opus,sonnet,haiku}-N-M` — Anthropic; opus = most capable, haiku = fastest/cheapest.
- `databricks-gpt-N(-mini|-nano|-codex-max|-codex-mini)` — OpenAI; `-mini`/`-nano` cheaper, `-codex-*` code-specialized.
- `databricks-gemini-N-M(-pro|-flash|-flash-lite)` — Google; `-pro` most capable, `-flash` fast.
- `databricks-meta-llama-N-M-...-instruct` — Meta open-weight.
- `databricks-gpt-oss-{20b,120b}`, `databricks-qwen*`, `databricks-gemma-*` — open-weight.
- `databricks-{gte,bge,qwen3}-...-en` / `databricks-*-embedding-*` — embedding models (task `llm/v1/embeddings`).

**Defaults when the user doesn't specify**: pick the highest-numbered Sonnet for agents (e.g. `databricks-claude-sonnet-4-6`), highest-numbered codex-max for code, `databricks-gte-large-en` for embeddings. Resolve the actual name from the live list above.

---

## Gotchas (the ones that cost time)

| Trap | Fix |
|---|---|
| Model lands in workspace registry, not UC | `mlflow.set_registry_uri("databricks-uc")` *before* logging |
| Endpoint returns PERMISSION_DENIED at first query | Pass `resources=[DatabricksServingEndpoint(...), DatabricksFunction(...), DatabricksVectorSearchIndex(...), DatabricksLakebase(...)]` to `log_model` — without it, the endpoint has no creds for its dependencies |
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
| [1-batch-scoring-pattern.md](1-batch-scoring-pattern.md) | Full nightly train + spark_udf + MERGE-to-gold notebook example. The canonical demo flow. |
| [2-custom-pyfunc.md](2-custom-pyfunc.md) | Single end-to-end custom pyfunc example: artifacts, signature, code_paths, log → register → deploy → query. |
| [3-genai-agents.md](3-genai-agents.md) | Edge case: deploying a LangGraph `ResponsesAgent` with UC Function + Vector Search tools. For supervised multi-agent tiles, use **databricks-agent-bricks** instead. |

## Related skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — no-code Knowledge Assistants and Supervisor Agents. Prefer this over hand-rolling agents.
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** — evaluate model/agent quality before promoting `@prod`.
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** — vector indexes used as retrieval tools in agents.
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — async deploy pattern (`--no-wait`, TASK run_id trap).
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — UC governs the registered model: permissions, lineage, audit.
