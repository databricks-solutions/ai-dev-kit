# Feature Engineering (Feature Store)

## Why use Feature Engineering?

**The problem it solves — training-serving skew.** When your training pipeline computes features one way and your serving pipeline computes them differently, models degrade silently in production. Feature Engineering enforces one canonical definition per feature: the same `FeatureLookup` that builds your training dataset also resolves features at `score_batch()` and inside serving endpoints — guaranteed to be identical.

**Additional value:**
- **Feature reuse** — compute a feature once, share it across teams and models without re-implementing logic
- **Feature lineage** — Unity Catalog tracks every registered model's feature table dependencies; catch upstream data changes before they silently impact model quality
- **Point-in-time correctness** — rolling/window features automatically reflect only information available at label time, preventing data leakage without writing time-join logic

**Use Feature Engineering instead of plain `mlflow.autolog` when you need** feature reuse across models, point-in-time correctness, lineage in the registered model, or real-time feature lookups. For simple one-off models with no sharing requirement, the plain autolog path in [SKILL.md](SKILL.md) is sufficient.

Canonical flow — adds a managed feature layer between silver tables and training:

```
silver_tables
  → fe.create_table() / fe.write_table()  → UC feature table (Delta)
  → FeatureLookup + fe.create_training_set()
  → fe.log_model(training_set=...)        → UC registry (with feature lineage)
  → fe.score_batch(@prod, df=keys_only)   → gold_predictions
     OR  publish_table() → online store   → real-time endpoint (<1ms lookup)
```

---

## Setup

```python
%pip install mlflow==2.22.0 databricks-feature-engineering==0.13.0
dbutils.library.restartPython()
```

```python
from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup
from mlflow.tracking import MlflowClient
import mlflow

fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")
mlflow.set_registry_uri("databricks-uc")

# --- Replace with your own values ---
CATALOG  = "my_catalog"
SCHEMA   = "my_schema"
MODEL    = "my_model"
PROJECT  = "my_project"   # used for online store and endpoint names
# ------------------------------------
FULL_NAME = f"{CATALOG}.{SCHEMA}.{MODEL}"
```

---

## 1. Create and populate feature tables

**Option A — Create from a DataFrame** (new computed feature table):

```python
# Aggregate entity-level features from your silver source table
# Replace silver_events, entity_id, and column names with your own
entity_features_df = spark.sql(f"""
    SELECT entity_id,
           COUNT(*)                                   AS total_interactions,
           SUM(CAST(action_flag AS INT))              AS total_actions,
           AVG(value)                                 AS avg_value,
           SUM(CAST(converted AS INT))
             / NULLIF(SUM(CAST(action_flag AS INT)), 0) AS conversion_rate
    FROM {CATALOG}.{SCHEMA}.silver_events
    GROUP BY entity_id
""")

fe.create_table(
    name=f"{CATALOG}.{SCHEMA}.entity_features",
    primary_keys=["entity_id"],      # required; must be unique; cannot be added after creation
    df=entity_features_df,
    description="Entity-level aggregated features",
    # tags={"team": "data_science"}
)
```

For **rolling/window features that require point-in-time lookups**, include a timestamp key:

```python
fe.create_table(
    name=f"{CATALOG}.{SCHEMA}.user_features",
    primary_keys=["user_id", "ts"],
    timestamp_keys="ts",                 # tells FeatureLookup to filter by feature.ts <= label.ts
    schema=user_features_df.schema,      # create schema-only first, then write separately
    description="User rolling behavior features with timestamp key"
)
fe.write_table(
    name=f"{CATALOG}.{SCHEMA}.user_features",
    df=user_features_df,
    # mode="merge"      # default — upsert on primary key(s)
    # mode="overwrite"  # full replace; use when recomputing all rows
)
```

**Option B — Promote an existing UC table** (no `create_table` needed — just add a PK constraint):

```python
# Example: promoting a static attributes table (demographics, metadata, etc.)
# Replace entity_attributes and entity_id with your table and key column
spark.sql(f"ALTER TABLE {CATALOG}.{SCHEMA}.entity_attributes ALTER COLUMN entity_id SET NOT NULL")
try:
    spark.sql(f"ALTER TABLE {CATALOG}.{SCHEMA}.entity_attributes ADD CONSTRAINT entity_attributes_pk PRIMARY KEY(entity_id)")
except Exception:
    pass  # already exists — safe to ignore
# Table now appears in UC Explorer's Features tab and supports FeatureLookup
```

---

## 2. Build a training set with FeatureLookup

### Simple lookup (no point-in-time)

```python
# Start from your labels/transactions table — only need keys + label column
# Replace silver_events, entity_id, item_id, and label column with your own
id_and_label = spark.table(f"{CATALOG}.{SCHEMA}.silver_events") \
    .select("record_id", "label", "entity_id", "item_id")

training_set = fe.create_training_set(
    df=id_and_label,
    feature_lookups=[
        FeatureLookup(
            table_name=f"{CATALOG}.{SCHEMA}.entity_features",
            lookup_key="entity_id",       # must match a column in id_and_label
            # feature_names=["avg_value", "conversion_rate"]  # omit to include all columns
        ),
        FeatureLookup(
            table_name=f"{CATALOG}.{SCHEMA}.entity_attributes",
            lookup_key="entity_id",
            feature_names=["attr_a", "attr_b", "attr_c"],   # specify subset if table is wide
        ),
    ],
    label="label",
    exclude_columns=["record_id", "entity_id", "item_id"],  # drop keys and metadata
)
training_pd = training_set.load_df().toPandas()
```

### Point-in-time lookup (rolling/window features)

Add `timestamp_lookup_key` so the engine only joins feature values that existed **at or before the label's timestamp** — prevents future data from leaking into training.

```python
# Split by time — train on historical data, test on most recent
# Replace the date cutoff and column names with your own
ground_truth = spark.table(f"{CATALOG}.{SCHEMA}.silver_events") \
    .select("user_id", "item_id", "label", "ts")
training_labels = ground_truth.where("ts < '2024-01-01'")   # your cutoff date
test_labels     = ground_truth.where("ts >= '2024-01-01'")

training_set = fe.create_training_set(
    df=training_labels,
    feature_lookups=[
        FeatureLookup(
            table_name=f"{CATALOG}.{SCHEMA}.user_features",
            lookup_key="user_id",
            feature_names=["rolling_7d_avg", "rolling_30d_sum", "tenure_days"],
            timestamp_lookup_key="ts",   # only features where feature.ts <= label.ts
        ),
        FeatureLookup(
            table_name=f"{CATALOG}.{SCHEMA}.entity_features",
            lookup_key="item_id",
            timestamp_lookup_key="ts",
        ),
    ],
    label="label",
    exclude_columns=["ts", "user_id", "item_id"],
)
training_pd = training_set.load_df().toPandas()
```

---

## 3. Train and register with feature lineage

**The only change from plain MLflow training: replace `mlflow.log_model()` with `fe.log_model(training_set=...)`.**  
This binds feature lineage to the registered model so `score_batch()` can auto-join features at inference.

```python
mlflow.sklearn.autolog(log_input_examples=True, silent=True)
mlflow.set_experiment(f"/Shared/{PROJECT}/experiments")

with mlflow.start_run(run_name="feature_store_model"):
    model.fit(X_train, y_train)

    fe.log_model(
        model=model,
        artifact_path="model",
        flavor=mlflow.sklearn,
        training_set=training_set,          # ← captures feature lineage; required for score_batch
        registered_model_name=FULL_NAME,
    )

# Promote to @production — same alias pattern as SKILL.md
mlflow_client = MlflowClient(registry_uri="databricks-uc")
latest = max(mlflow_client.search_model_versions(f"name='{FULL_NAME}'"),
             key=lambda v: int(v.version))
mlflow_client.set_registered_model_alias(FULL_NAME, "production", version=latest.version)
```

---

## 4. Batch scoring with score_batch()

Pass **only the primary key columns** (plus `ts` for point-in-time models). Feature Engineering auto-joins all feature values via the lineage stored in the model.

```python
# Keys only — no need to pre-join feature values
# Replace silver_events and key columns with your scoring dataset
id_to_score = spark.table(f"{CATALOG}.{SCHEMA}.silver_events") \
    .select("record_id", "user_id", "item_id")
# Point-in-time models: also include "ts"

scored_df = fe.score_batch(
    model_uri=f"models:/{FULL_NAME}@production",
    df=id_to_score,
    result_type="boolean",  # "boolean" | "double" (probability) | "int"
)

scored_df.select("record_id", "prediction") \
    .write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.gold_predictions")
```

---

## 5. Online store (real-time feature serving)

Use when a serving endpoint needs sub-millisecond feature lookups. Backed by Databricks Lakebase.

**Prerequisites** (both must be true before `publish_table` will succeed):

```sql
-- Replace user_features and user_id with your feature table and primary key
ALTER TABLE user_features SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE user_features ALTER COLUMN user_id SET NOT NULL;
```

**Create online store and publish:**

```python
ONLINE_STORE = f"{PROJECT}-online-store"   # name your store per project

# Create the Lakebase-backed store (~5 min first time; CU_1 = ~16GB RAM)
try:
    online_store = fe.get_online_store(name=ONLINE_STORE)
except Exception:
    fe.create_online_store(name=ONLINE_STORE, capacity="CU_1")
    import time; time.sleep(300)
    online_store = fe.get_online_store(name=ONLINE_STORE)

# Publish: CONTINUOUS = live sync on every Delta commit
fe.publish_table(
    online_store=online_store,
    source_table_name=f"{CATALOG}.{SCHEMA}.user_features",
    online_table_name=f"{CATALOG}.{SCHEMA}.user_features_online",
    publish_mode="CONTINUOUS",
)
```

**Two serving patterns once tables are online:**

| Pattern | Use when | How |
|---|---|---|
| **Feature Serving Endpoint** | Scoring model lives outside Databricks; app needs raw features via REST | `fe.create_feature_spec()` → `fe.create_feature_serving_endpoint()` → `client.predict(inputs={"dataframe_records": [{"entity_id": 1}]})` |
| **Model Serving Endpoint** | Model deployed in Databricks; endpoint auto-looks up features | `client.create_endpoint(entity_name=FULL_NAME, ...)` → `client.predict(inputs={"dataframe_records": [{"entity_id": 1}]})` — no feature join code needed in the caller |

For full endpoint creation code, see [SKILL.md](SKILL.md#consume-real-time-serving-endpoint-only-when-required).  
For the Feature Serving Endpoint API details, see [4-declarative-features.md](4-declarative-features.md#feature-serving-endpoint).

---

## Gotchas

| Trap | Fix |
|---|---|
| `FeatureStoreClient` used | Deprecated — use `FeatureEngineeringClient` from `databricks.feature_engineering` |
| `mlflow.log_model()` instead of `fe.log_model()` | No `training_set=` → no lineage → `score_batch()` fails at inference |
| `primary_keys=` missing at `create_table` | Required and cannot be added after creation |
| `score_batch()` called with full feature columns | Pass lookup key columns only (+ `ts` for point-in-time); features are auto-joined |
| `timestamp_lookup_key` omitted on rolling features | Future values leak into training labels — AUC looks inflated in training, collapses in prod |
| `publish_table` fails silently or with permission error | Confirm CDF enabled (`delta.enableChangeDataFeed = true`) **and** primary key column is `NOT NULL` |
| `write_table` wipes rows unexpectedly | Default mode is `"merge"` (upsert); you explicitly opted in to `"overwrite"` |
| Model serving endpoint missing from UI | UI defaults to "Owned by me" — switch to "All", or `databricks serving-endpoints list` |
