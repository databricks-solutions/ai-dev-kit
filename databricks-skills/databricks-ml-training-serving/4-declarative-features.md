# Declarative Feature Engineering

## Why use the Declarative API?

**The problem it solves — rolling feature boilerplate.** Writing Spark window functions for temporal features is verbose and brittle:

```python
# What you'd write manually — once per feature, per entity, per time window:
F.avg("value").over(
    W.partitionBy("user_id").orderBy(F.col("ts").cast("long")).rangeBetween(-7*86400, 0)
)
```

Across 5 features × 3 time windows × 2 entity types = 30 near-identical blocks to maintain, test, and keep synchronized between your training and serving pipelines.

**The declarative approach:** declare *what* you want — "7-day rolling average of `purchase_value` per `customer_id`" — and Databricks handles backfill scheduling, incremental refresh, materialization to Delta tables, and publishing to the online store.

**Use the Declarative API when you have:**
- Multiple rolling/window aggregations (≥3 features, ≥2 time windows) on the same source table
- Features that must stay fresh offline (training) AND online (serving) from the same definition
- Teams that prefer declarative feature definitions over maintaining Spark window code

**Don't use yet when you need:**
- Non-aggregation transformations (ratio features, cross-entity joins, string parsing) — current BETA limitation; static columns work via `ColumnSelection`
- Serverless compute — Classic cluster (DBR 17.0 LTS ML+) required
- Kafka-sourced streaming features → a separate Private Preview ("Streaming Declarative Features", MSK only) exists; not covered here

**Status:** Public Preview, requires `databricks-feature-engineering>=0.15.0` and DBR 17.0 LTS ML+ on a Classic cluster.

Uses the same `FeatureEngineeringClient` and the same `fe.log_model(training_set=...)` → `fe.score_batch()` path as the standard API in [3-feature-store.md](3-feature-store.md).

---

## Setup

```python
%pip install databricks-feature-engineering>=0.15.0
dbutils.library.restartPython()
```

```python
from databricks.feature_engineering import FeatureEngineeringClient, CronSchedule
from databricks.feature_engineering.entities import (
    DeltaTableSource,
    Sum, Avg, Count, ColumnSelection,              # aggregation functions
    SlidingWindow, TumblingWindow, RollingWindow,  # window types
    OfflineStoreConfig, OnlineStoreConfig,
    MaterializedFeaturePipelineScheduleState,
    TableTrigger,
)
from datetime import timedelta

fe = FeatureEngineeringClient()

# --- Replace with your own values ---
catalog  = "my_catalog"
schema   = "my_schema"
PROJECT  = "my_project"   # used for online store and endpoint names
# ------------------------------------
```

### Aggregation functions

| Function | Notes |
|---|---|
| `Sum(input="col")` | Sum over the window |
| `Avg(input="col")` | Average over the window |
| `Count(input="col")` | Row count |
| `ColumnSelection(column_name)` | Raw column passthrough — **no aggregation, no time window** |

### Window types

| Type | Behaviour |
|---|---|
| `SlidingWindow(window_duration, slide_duration)` | Overlapping rolling windows — e.g. 7-day avg recalculated daily |
| `TumblingWindow(window_duration)` | Non-overlapping fixed intervals — e.g. weekly totals |
| `RollingWindow(window_duration, delay=None)` | Continuous lookback ending at evaluation time — point-in-time snapshots |

---

## 1. Define feature sources

In `>=0.15.0`, **`entity` and `timeseries_column` belong on the Feature, not on the source**. `DeltaTableSource` only carries the table reference.

```python
# Preprocess: cast booleans/strings to numeric before using in aggregations
# Replace silver_events with your source table name
from pyspark.sql import functions as F
(
    spark.table(f"{catalog}.{schema}.silver_events")
         .withColumn("action_int", F.col("action_flag").cast("int"))  # boolean → int
         .withColumn("impression",  F.lit(1))                          # row count proxy
         .write.format("delta").mode("overwrite")
         .saveAsTable(f"{catalog}.{schema}.silver_events_clean")
)

# One source per entity type — same underlying table, different entity columns
user_source = DeltaTableSource(
    catalog_name=catalog,
    schema_name=schema,
    table_name="silver_events_clean",
    # filter_condition="value > 0"   # optional SQL filter
)

item_source = DeltaTableSource(
    catalog_name=catalog,
    schema_name=schema,
    table_name="silver_events_clean",
)
```

---

## 2. Declare features with `create_feature()`

Each feature declares its own `entity` and `timeseries_column`, enabling different aggregation levels from the same source table.

```python
# Replace user_id, item_id, ts, action_int, value with your column names
user_features = [
    # 7-day rolling average of value per user
    fe.create_feature(
        source=user_source,
        entity=["user_id"],
        timeseries_column="ts",
        function=Avg(input="value"),
        time_window=SlidingWindow(window_duration=timedelta(days=7), slide_duration=timedelta(days=1)),
        catalog_name=catalog, schema_name=schema,
        name="user_avg_value_7d",    # omit to auto-generate from inputs+function+window
    ),
    # 7-day total actions per user (tumbling = non-overlapping weekly buckets)
    fe.create_feature(
        source=user_source,
        entity=["user_id"],
        timeseries_column="ts",
        function=Sum(input="action_int"),
        time_window=TumblingWindow(window_duration=timedelta(days=7)),
        catalog_name=catalog, schema_name=schema,
    ),
    # Static attribute passthrough from a separate table — no aggregation, no time window
    fe.create_feature(
        source=DeltaTableSource(catalog_name=catalog, schema_name=schema, table_name="entity_attributes"),
        entity=["user_id"],
        function=ColumnSelection(column_name="loyalty_tier"),
        catalog_name=catalog, schema_name=schema,
    ),
]

item_features = [
    # 7-day total impressions per item (different entity, same source table)
    fe.create_feature(
        source=item_source,
        entity=["item_id"],          # different aggregation level from user_source
        timeseries_column="ts",
        function=Sum(input="impression"),
        time_window=SlidingWindow(window_duration=timedelta(days=7), slide_duration=timedelta(days=1)),
        catalog_name=catalog, schema_name=schema,
        name="item_impressions_7d",
    ),
]

# Preview computed values — debugging only; does not persist or track lineage
fe.compute_features(features=user_features).display()
```

If you construct `Feature` objects manually (e.g., from a config file) instead of using `create_feature()`, persist them to UC with:

```python
fe.register_feature(feature=my_feature_obj, catalog_name=catalog, schema_name=schema)
```

---

## 3. Training set (automatically point-in-time correct)

The declarative `create_training_set()` has a **different signature** from the standard API — takes `features=` (list of Feature objects) not `feature_lookups=`, and requires `name=`, `catalog_name=`, `schema_name=`.

```python
# Replace silver_events, key columns, and label with your own
id_and_label = spark.table(f"{catalog}.{schema}.silver_events") \
    .select("record_id", "label", "user_id", "item_id", "ts")

training_set = fe.create_training_set(
    name=f"{PROJECT}_training_set",
    catalog_name=catalog,
    schema_name=schema,
    df=id_and_label,
    features=user_features + item_features,
    label="label",
    exclude_columns=["user_id", "item_id", "ts"],
)
training_df = training_set.load_df()
```

Train and log the same way as the standard API — `fe.log_model(training_set=training_set, ...)`.

---

## 4. Materialize features with `materialize_features()`

Replaces `create_pipeline()` from `<0.15.0`. Persists features to offline Delta tables, online Lakebase store, or both from a single call.

```python
TABLE_PREFIX = f"{PROJECT}_features"   # prefix for materialized Delta table names

# Offline only (batch training / score_batch)
fe.materialize_features(
    features=user_features + item_features,
    offline_config=OfflineStoreConfig(
        catalog_name=catalog, schema_name=schema, table_name_prefix=TABLE_PREFIX
    ),
    trigger=CronSchedule(
        quartz_cron_expression="0 0 * * * ?",  # daily at 00:00 UTC
        timezone_id="UTC",
        pipeline_schedule_state=MaterializedFeaturePipelineScheduleState.ACTIVE,
    ),
)

# Online only (real-time serving — Lakebase instance must exist first)
ONLINE_STORE = f"{PROJECT}-online-store"
fe.materialize_features(
    features=user_features + item_features,
    online_config=OnlineStoreConfig(
        catalog_name=catalog, schema_name=schema,
        table_name_prefix=TABLE_PREFIX,
        online_store_name=ONLINE_STORE,
    ),
    trigger=CronSchedule(quartz_cron_expression="0 * * * * ?", timezone_id="UTC"),  # hourly
)
```

**`TableTrigger`** — fires on every Delta commit, valid for `ColumnSelection` features only (not windowed aggregations):

```python
fe.materialize_features(
    features=[loyalty_tier_feature],   # ColumnSelection only
    offline_config=OfflineStoreConfig(...),
    trigger=TableTrigger(),
)
```

---

## Feature Serving Endpoint

Exposes raw feature values as a REST API — use when the scoring model lives outside Databricks and only needs the features, not a prediction.

```python
from databricks.feature_engineering.entities.feature_serving_endpoint import (
    ServedEntity, EndpointCoreConfig,
)

ENDPOINT_NAME    = f"{PROJECT}-feature-endpoint"
FEATURE_SPEC     = f"{catalog}.{schema}.{PROJECT}_feature_spec"

fe.create_feature_spec(
    name=FEATURE_SPEC,
    features=[
        FeatureLookup(table_name=f"{catalog}.{schema}.user_features", lookup_key="user_id"),
        FeatureLookup(table_name=f"{catalog}.{schema}.item_features",  lookup_key="item_id"),
    ],
)

fe.create_feature_serving_endpoint(
    name=ENDPOINT_NAME,
    config=EndpointCoreConfig(
        served_entities=ServedEntity(
            feature_spec_name=FEATURE_SPEC,
            workload_size="Small",
            scale_to_zero_enabled=True,
        )
    ),
)

# Query: pass lookup keys → get back feature values
import mlflow.deployments
client = mlflow.deployments.get_deploy_client("databricks")
response = client.predict(
    endpoint=ENDPOINT_NAME,
    inputs={"dataframe_records": [{"user_id": 42, "item_id": 7}]},
)
```

---

## Gotchas

| Trap | Fix |
|---|---|
| `entity` / `timeseries_column` placed on `DeltaTableSource` | In `>=0.15.0` they moved to `Feature` / `create_feature()` level; `DeltaTableSource` only takes location + optional `filter_condition` |
| `ContinuousWindow` import fails | Renamed to `RollingWindow` in `>=0.15.0` |
| `create_pipeline()` not found | Replaced by `materialize_features()` in `>=0.15.0` |
| Declarative `create_training_set()` signature mismatch | Takes `features=list[Feature]`, not `feature_lookups=list[FeatureLookup]`; also requires `name=`, `catalog_name=`, `schema_name=` |
| Entity column is DATE or TIMESTAMP type | Declarative API does not support DATE/TIMESTAMP as entity columns — use a string or numeric key |
| Label column name exists in the feature source table | The label column cannot appear in any feature source — drop or rename it before defining features |
| `ColumnSelection` feature passed to `CronSchedule` | Use `TableTrigger` for `ColumnSelection` features — they cannot be cron-scheduled |
