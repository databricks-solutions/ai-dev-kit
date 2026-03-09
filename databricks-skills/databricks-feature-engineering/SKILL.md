---
name: databricks-feature-engineering
description: "Build and manage ML feature tables on Databricks. Covers feature table creation with primary keys, feature computation patterns, point lookups for serving, online tables, and Feature Engineering in Unity Catalog. Use when building ML features, feature stores, or real-time feature serving."
---

# Databricks Feature Engineering

Create, manage, and serve ML features using Unity Catalog feature tables, online tables, and the Feature Engineering SDK.

## When to Use

- Creating feature tables for ML model training
- Computing and storing features from raw data
- Setting up real-time feature serving for inference
- Building feature pipelines with scheduled updates
- Migrating from legacy Feature Store to Unity Catalog

## Quick Start

### Create a Feature Table

```sql
CREATE TABLE catalog.schema.customer_features (
    customer_id BIGINT NOT NULL,
    total_purchases INT,
    avg_order_value DOUBLE,
    last_purchase_date DATE,
    customer_segment STRING,
    CONSTRAINT pk PRIMARY KEY (customer_id)
) CLUSTER BY (customer_id);
```

The `PRIMARY KEY` constraint is required for feature tables — it defines the lookup key for feature serving.

### Write Features with the SDK

```python
from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()

# Write features from a DataFrame
fe.write_table(
    name="catalog.schema.customer_features",
    df=features_df,
    mode="merge"  # "merge" upserts by PK, "overwrite" replaces
)
```

## Common Patterns

### Pattern 1: Feature Table with Primary Key

Feature tables are Delta tables with a primary key constraint:

```sql
CREATE TABLE catalog.schema.user_features (
    user_id BIGINT NOT NULL,
    signup_days_ago INT,
    total_sessions INT,
    avg_session_duration DOUBLE,
    preferred_category STRING,
    is_premium BOOLEAN,
    CONSTRAINT user_pk PRIMARY KEY (user_id)
);
```

Composite primary keys for multi-key lookups:

```sql
CREATE TABLE catalog.schema.user_product_features (
    user_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    view_count INT,
    purchase_count INT,
    last_interaction TIMESTAMP,
    CONSTRAINT user_product_pk PRIMARY KEY (user_id, product_id)
);
```

### Pattern 2: Feature Computation

Compute features using SQL window functions and aggregations:

```sql
CREATE OR REPLACE TABLE catalog.schema.customer_features AS
SELECT
    customer_id,
    COUNT(*) as total_orders,
    AVG(order_total) as avg_order_value,
    MAX(order_date) as last_order_date,
    DATEDIFF(current_date(), MAX(order_date)) as days_since_last_order,
    PERCENT_RANK() OVER (ORDER BY COUNT(*)) as order_frequency_percentile,
    NTILE(4) OVER (ORDER BY AVG(order_total)) as value_quartile,
    CASE
        WHEN COUNT(*) >= 50 THEN 'platinum'
        WHEN COUNT(*) >= 20 THEN 'gold'
        WHEN COUNT(*) >= 5 THEN 'silver'
        ELSE 'bronze'
    END as customer_segment
FROM catalog.schema.orders
GROUP BY customer_id;

-- Add PK constraint after creation
ALTER TABLE catalog.schema.customer_features
ADD CONSTRAINT pk PRIMARY KEY (customer_id);
```

### Pattern 3: Feature Lookup for Training

Use the Feature Engineering SDK to create training sets with automatic feature lookup:

```python
from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup

fe = FeatureEngineeringClient()

# Define feature lookups
feature_lookups = [
    FeatureLookup(
        table_name="catalog.schema.customer_features",
        feature_names=["total_orders", "avg_order_value", "customer_segment"],
        lookup_key="customer_id"
    ),
    FeatureLookup(
        table_name="catalog.schema.product_features",
        feature_names=["category", "avg_rating"],
        lookup_key="product_id"
    )
]

# Create training set (joins features automatically)
training_set = fe.create_training_set(
    df=labels_df,  # DataFrame with customer_id, product_id, label
    feature_lookups=feature_lookups,
    label="label"
)

training_df = training_set.load_df()
```

### Pattern 4: Log Model with Feature Metadata

```python
from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()

# Log model with feature lineage
fe.log_model(
    model=trained_model,
    artifact_path="model",
    flavor=mlflow.sklearn,
    training_set=training_set,
    registered_model_name="catalog.schema.my_model"
)
```

When this model is deployed to serving, it automatically looks up features by primary key at inference time.

### Pattern 5: Online Tables for Real-Time Serving

Online tables provide low-latency feature lookups for model serving:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create an online table from a feature table
w.online_tables.create(
    name="catalog.schema.customer_features_online",
    spec={
        "source_table_full_name": "catalog.schema.customer_features",
        "primary_key_columns": ["customer_id"],
        "run_triggered": {}  # or "run_continuously": {} for streaming
    }
)
```

**Sync modes:**
- `run_triggered` — manual or scheduled sync from source table
- `run_continuously` — streaming sync (near real-time)

### Pattern 6: Point Lookup (Feature Serving)

Query features by primary key for real-time inference:

```sql
SELECT * FROM catalog.schema.customer_features
WHERE customer_id = 1003;
```

Via the SDK (for serving endpoints):

```python
from databricks.feature_engineering.online_store_spec import OnlineStoreSpec

features = fe.score_batch(
    model_uri="models:/catalog.schema.my_model/1",
    df=request_df  # DataFrame with lookup keys
)
```

## Scheduled Feature Updates

### SQL Job for Feature Refresh

```sql
-- Run as a scheduled Databricks Job
INSERT INTO catalog.schema.customer_features
SELECT
    customer_id,
    COUNT(*) as total_orders,
    AVG(order_total) as avg_order_value,
    MAX(order_date) as last_order_date,
    -- ... more features
FROM catalog.schema.orders
WHERE order_date >= current_date() - INTERVAL 1 DAY
GROUP BY customer_id
ON CONFLICT (customer_id) DO UPDATE SET *;
```

### Python SDK Feature Pipeline

```python
from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()

# Compute fresh features
features_df = spark.sql("""
    SELECT customer_id, COUNT(*) as total_orders, ...
    FROM catalog.schema.orders
    GROUP BY customer_id
""")

# Upsert into feature table
fe.write_table(
    name="catalog.schema.customer_features",
    df=features_df,
    mode="merge"
)
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **Missing primary key** | Feature tables require `CONSTRAINT pk PRIMARY KEY (col)` |
| **`write_table` fails with schema mismatch** | Ensure DataFrame columns match table schema exactly |
| **Online table sync stuck** | Check source table for schema changes; recreate online table if needed |
| **Feature lookup returns NULL** | Verify lookup key values exist in the feature table |
| **`FeatureEngineeringClient` not found** | Install: `pip install databricks-feature-engineering` |
| **Can't add PK to existing table** | Use `ALTER TABLE ... ADD CONSTRAINT pk PRIMARY KEY (col)` |
