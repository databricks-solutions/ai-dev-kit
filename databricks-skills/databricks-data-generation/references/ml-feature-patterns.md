# ML Feature Patterns

Patterns for generating synthetic data tailored to ML training, evaluation, and monitoring.

## Feature Arrays with numColumns/numFeatures

dbldatagen can generate multiple columns with the same spec using `numColumns` (or its alias `numFeatures`):

```python
import dbldatagen as dg

# Generate 10 feature columns: feature_0, feature_1, ..., feature_9
spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("feature", "float", minValue=0.0, maxValue=1.0,
                random=True, numColumns=10)
    .withColumn("label", "integer", values=[0, 1], weights=[90, 10])
    .build()
)
# Result has columns: id, feature_0, feature_1, ..., feature_9, label
```

### Array Column (Single Column with Array Type)
```python
from pyspark.sql.types import FloatType

# Combine into a single array column
spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("features", FloatType(), minValue=0.0, maxValue=1.0,
                random=True, numColumns=10, structType="array")
    .build()
)
# Result: single column "features" of type array<float> with 10 elements
```

### Variable-Length Feature Arrays
```python
from pyspark.sql.types import FloatType

# Random number of features between 3 and 8 per row (only works with structType="array")
spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("features", FloatType(), minValue=0.0, maxValue=1.0,
                random=True, numColumns=(3, 8), structType="array")
    .build()
)
```

**Naming convention**: When `structType` is not set, generated columns are named `{baseName}_{ix}` where ix starts at 0. When `structType="array"`, they are combined into a single array column using the base name.

## Label Imbalance

### Binary Classification
```python
import dbldatagen as dg

# 5% positive class (fraud detection)
spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("is_fraud", "boolean", expr="rand() < 0.05")
    .build()
)

# Weighted categorical labels
spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("churn", "string", values=["No", "Yes"], weights=[80, 20])
    .build()
)

# Heavily imbalanced with missing labels (simulates partial labeling)
spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("label", "string", values=["Negative", "Positive"],
                weights=[95, 5], percentNulls=0.3)
    .build()
)
```

### Multi-Class Imbalance
```python
import dbldatagen as dg

spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("category", "string",
                values=["Normal", "Warning", "Critical", "Unknown"],
                weights=[70, 15, 10, 5])
    .build()
)
```

## Data Drift Simulation

### Concept: Generating Drifted Batches
Generate multiple batches with shifting distributions to simulate model drift over time:

```python
import dbldatagen as dg
from datetime import datetime, timedelta
from functools import reduce
from pyspark.sql import DataFrame

def generate_drifted_batch(spark, batch_idx, rows=10_000, seed=42):
    """Generate a batch with gradually shifting distributions."""
    # Drift factor increases with each batch
    drift = batch_idx * 0.05  # 5% shift per batch

    return (
        dg.DataGenerator(spark, rows=rows, partitions=4, randomSeed=seed + batch_idx)
        .withColumn("id", "long", minValue=1, uniqueValues=rows)
        .withColumn("batch", "integer", values=[batch_idx])
        .withColumn("timestamp", "timestamp",
                    begin=(datetime.now() - timedelta(days=30 - batch_idx)).isoformat(),
                    end=(datetime.now() - timedelta(days=29 - batch_idx)).isoformat(),
                    random=True)
        # Feature 1: mean shifts over time
        .withColumn("feature_1", "double",
                    minValue=10 + drift * 20, maxValue=50 + drift * 20,
                    distribution="normal")
        # Feature 2: variance increases
        .withColumn("feature_2", "double",
                    minValue=0, maxValue=100 * (1 + drift),
                    random=True)
        # Label: class balance shifts
        .withColumn("prediction", "string", values=["No", "Yes"],
                    weights=[80 - int(drift * 100), 20 + int(drift * 100)])
        .build()
    )

# Generate 30 days of drifting data
batches = [generate_drifted_batch(spark, i) for i in range(30)]
drifted_df = reduce(DataFrame.unionAll, batches)
```

### Baseline vs. Inference Split

Separate baseline (no drift) from inference (with drift) for monitoring:

```python
import dbldatagen as dg

def generate_baseline(spark, rows=100_000, seed=42):
    """Baseline data with stable distributions."""
    return (
        dg.DataGenerator(spark, rows=rows, partitions=10, randomSeed=seed)
        .withColumn("id", "long", minValue=1, uniqueValues=rows)
        .withColumn("feature_1", "double", minValue=10, maxValue=50,
                    distribution="normal")
        .withColumn("feature_2", "double", minValue=0, maxValue=100,
                    random=True)
        .withColumn("feature_3", "double", minValue=0.0, maxValue=1.0,
                    distribution=dg.distributions.Beta(2, 5))
        .withColumn("prediction", "string", values=["No", "Yes"],
                    weights=[80, 20])
        .build()
    )

def generate_inference(spark, rows=100_000, seed=99, drift_factor=0.3):
    """Inference data with shifted distributions."""
    shift = drift_factor * 20
    return (
        dg.DataGenerator(spark, rows=rows, partitions=10, randomSeed=seed)
        .withColumn("id", "long", minValue=1, uniqueValues=rows)
        .withColumn("feature_1", "double", minValue=10 + shift, maxValue=50 + shift,
                    distribution="normal")
        .withColumn("feature_2", "double", minValue=0, maxValue=100 * (1 + drift_factor),
                    random=True)
        .withColumn("feature_3", "double", minValue=0.0, maxValue=1.0,
                    distribution=dg.distributions.Beta(5, 2))
        .withColumn("prediction", "string", values=["No", "Yes"],
                    weights=[60, 40])
        .build()
    )

baseline_df = generate_baseline(spark)
inference_df = generate_inference(spark)
```

### Drift Monitoring Integration

Use these datasets with Lakehouse Monitoring:

- Write `baseline_df` and `inference_df` to Delta tables
- Register with Lakehouse Monitoring as baseline and inference slices
- Monitor with JS divergence, chi-squared test, PSI
- Typical thresholds: JS distance > 0.19 or PSI > 0.2 indicates significant drift

## Distribution Selection for ML Features

### When to Use Each Distribution

| Distribution | Use Case | Parameters | Example |
|---|---|---|---|
| `"normal"` | Symmetric features, sensor readings | Scaled to `minValue`/`maxValue` | Age, temperature |
| `Beta(alpha, beta)` | Bounded [0,1] probabilities, scores | `alpha > 0, beta > 0` | Confidence scores, percentages |
| `Gamma(shape, scale)` | Right-skewed positive values | `shape > 0, scale > 0` | Transaction amounts, wait times |
| `"exponential"` | Long-tail, inter-arrival times | Scaled to `minValue`/`maxValue` | Purchase amounts, session duration |

All distributions produce values normalized to [0, 1] internally, then scaled to the column's `minValue`/`maxValue` range.

### Shape Guide
```python
import dbldatagen as dg

# Beta shapes — values bounded between minValue and maxValue
dg.distributions.Beta(2, 5)      # Left-skewed (most values low) — discount rates
dg.distributions.Beta(5, 2)      # Right-skewed (most values high) — quality scores
dg.distributions.Beta(2, 2)      # Symmetric bell in [0,1] — probabilities
dg.distributions.Beta(0.5, 0.5)  # U-shaped (values at extremes) — binary-like

# Gamma shapes — values normalized then scaled to column range
dg.distributions.Gamma(1.0, 2.0)  # Exponential-like (shape=1) — rare events
dg.distributions.Gamma(2.0, 2.0)  # Moderate right skew — transaction amounts
dg.distributions.Gamma(5.0, 1.0)  # More symmetric — response times
```

### Usage in Column Definitions
```python
import dbldatagen as dg

spec = (
    dg.DataGenerator(spark, rows=500_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=500_000)
    # Confidence score: mostly low values (left-skewed)
    .withColumn("confidence", "float", minValue=0.0, maxValue=1.0,
                distribution=dg.distributions.Beta(2, 5))
    # Transaction amount: right-skewed, most are small
    .withColumn("amount", "decimal(10,2)", minValue=1, maxValue=10_000,
                distribution=dg.distributions.Gamma(2.0, 2.0))
    # Sensor reading: symmetric around center
    .withColumn("temperature", "float", minValue=15.0, maxValue=35.0,
                distribution="normal")
    # Session duration: long-tail
    .withColumn("session_seconds", "integer", minValue=1, maxValue=7200,
                distribution="exponential")
    .build()
)
```

## Correlated Features via baseColumn

Use `baseColumn` to create feature dependencies, or use SQL expressions to derive correlated columns:

```python
import dbldatagen as dg

spec = (
    dg.DataGenerator(spark, rows=500_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=500_000)

    # Customer tenure drives loyalty tier probability
    .withColumn("tenure_months", "integer", minValue=0, maxValue=120, random=True)
    .withColumn("loyalty_tier", "string",
                values=["Bronze", "Silver", "Gold", "Platinum"],
                baseColumn="tenure_months")

    # Account balance influences risk rating via SQL expression
    .withColumn("balance", "decimal(12,2)", minValue=0, maxValue=1_000_000,
                distribution="exponential")
    .withColumn("risk_rating", "string",
                expr="""CASE
                    WHEN balance > 500000 THEN 'Low'
                    WHEN balance > 100000 THEN 'Medium'
                    ELSE 'High'
                END""")

    # Age correlates with income via expression
    .withColumn("age", "integer", minValue=18, maxValue=75, distribution="normal")
    .withColumn("income", "decimal(10,2)",
                expr="20000 + (age - 18) * 800 + rand() * 30000")
    .build()
)
```

### Multi-Column Correlation with baseColumn

When `baseColumn` is used, the derived column's value is deterministically mapped from the base column. This creates a functional dependency:

```python
import dbldatagen as dg

spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("department", "string",
                values=["Engineering", "Sales", "Marketing", "Support"])
    # Title distribution depends on department
    .withColumn("title", "string",
                values=["Junior", "Mid", "Senior", "Lead", "Director"],
                baseColumn="department")
    # Salary depends on both department and title
    .withColumn("salary", "decimal(10,2)", minValue=40_000, maxValue=200_000,
                baseColumn=["department", "title"])
    .build()
)
```

## Train/Test Split Generation

```python
import dbldatagen as dg

# Generate with a split column for reproducible train/test/validation splits
spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20, randomSeed=42)
    .withColumn("id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("split", "string", values=["train", "test", "validation"],
                weights=[70, 20, 10])
    .withColumn("feature_1", "float", minValue=0.0, maxValue=1.0, random=True)
    .withColumn("feature_2", "float", minValue=-1.0, maxValue=1.0,
                distribution="normal")
    .withColumn("label", "integer", values=[0, 1], weights=[85, 15])
    .build()
)

train_df = spec.filter("split = 'train'").drop("split")
test_df = spec.filter("split = 'test'").drop("split")
val_df = spec.filter("split = 'validation'").drop("split")
```

## Complete Example: Churn Prediction Dataset

Full end-to-end example generating a customer churn dataset with correlated demographics, service features, tenure-based churn probability, feature arrays, train/test split, and optional drift batches.

### Cell 1: Setup
```python
import dbldatagen as dg
from pyspark.sql.types import FloatType
from pyspark.sql import functions as F
```

### Cell 2: Generate Base Customer Dataset
```python
rows = 1_000_000
n_service_features = 6

churn_spec = (
    dg.DataGenerator(spark, rows=rows, partitions=20, randomSeed=42)
    .withColumn("customer_id", "long", minValue=100_000, uniqueValues=rows)

    # --- Demographics (correlated age/income) ---
    .withColumn("age", "integer", minValue=18, maxValue=75, distribution="normal")
    .withColumn("income", "decimal(10,2)",
                expr="20000 + (age - 18) * 800 + rand() * 30000")
    .withColumn("gender", "string", values=["M", "F", "Other"],
                weights=[48, 48, 4])
    .withColumn("region", "string",
                values=["Northeast", "Southeast", "Midwest", "West", "Southwest"],
                weights=[20, 25, 18, 22, 15])

    # --- Account features ---
    .withColumn("tenure_months", "integer", minValue=0, maxValue=72,
                distribution="exponential")
    .withColumn("contract_type", "string",
                values=["Month-to-Month", "One-Year", "Two-Year"],
                weights=[55, 25, 20])
    .withColumn("monthly_charges", "decimal(8,2)", minValue=19.99, maxValue=119.99,
                distribution=dg.distributions.Gamma(2.0, 2.0))

    # --- Service features as array (model input) ---
    .withColumn("service_score", FloatType(), minValue=0.0, maxValue=1.0,
                random=True, numColumns=n_service_features, structType="array")

    # --- Derived: total charges = tenure * monthly ---
    .withColumn("total_charges", "decimal(10,2)",
                expr="tenure_months * monthly_charges")

    # --- Churn label: probability depends on tenure and contract ---
    .withColumn("churn_prob", "double",
                expr="""CASE
                    WHEN contract_type = 'Two-Year' THEN 0.03
                    WHEN contract_type = 'One-Year' THEN 0.10
                    ELSE 0.35
                END
                - LEAST(tenure_months * 0.003, 0.20)
                + CASE WHEN monthly_charges > 80 THEN 0.10 ELSE 0.0 END""",
                omit=True)
    .withColumn("churned", "boolean", expr="rand() < ABS(churn_prob)")

    # --- Train/test split ---
    .withColumn("split", "string",
                values=["train", "test", "validation"],
                weights=[70, 20, 10])
)

churn_df = churn_spec.build()
```

### Cell 3: Inspect the Dataset
```python
# Check shape and schema
print(f"Total rows: {churn_df.count()}")
churn_df.printSchema()

# Verify class balance
churn_df.groupBy("churned").count().show()

# Verify split proportions
churn_df.groupBy("split").count().orderBy("split").show()

# Check feature array
churn_df.select("customer_id", "service_score").show(5, truncate=False)
```

### Cell 4: Split into Train/Test/Validation
```python
train_df = churn_df.filter("split = 'train'").drop("split")
test_df = churn_df.filter("split = 'test'").drop("split")
val_df = churn_df.filter("split = 'validation'").drop("split")

print(f"Train: {train_df.count()}, Test: {test_df.count()}, Val: {val_df.count()}")
```

### Cell 5: Write to Delta
```python
catalog = "my_catalog"
schema = "ml_datasets"

train_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.churn_train")
test_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.churn_test")
val_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.churn_validation")
```

### Cell 6: Generate Drift Batches (Optional)

Generate additional inference batches where feature distributions shift over time, for use with model monitoring:

```python
from datetime import datetime, timedelta
from functools import reduce
from pyspark.sql import DataFrame

def generate_churn_drift_batch(spark, batch_idx, rows=10_000, seed=42):
    """Generate a churn inference batch with gradual drift."""
    drift = batch_idx * 0.05

    return (
        dg.DataGenerator(spark, rows=rows, partitions=4,
                         randomSeed=seed + batch_idx)
        .withColumn("customer_id", "long", minValue=100_000, uniqueValues=rows)
        .withColumn("batch_id", "integer", values=[batch_idx])
        .withColumn("inference_time", "timestamp",
                    begin=(datetime(2025, 1, 1) + timedelta(days=batch_idx)).isoformat(),
                    end=(datetime(2025, 1, 1) + timedelta(days=batch_idx + 1)).isoformat(),
                    random=True)
        # Age distribution shifts younger over time
        .withColumn("age", "integer",
                    minValue=max(18, int(18 - drift * 5)),
                    maxValue=max(50, int(75 - drift * 30)),
                    distribution="normal")
        .withColumn("income", "decimal(10,2)",
                    expr="20000 + (age - 18) * 800 + rand() * 30000")
        .withColumn("tenure_months", "integer", minValue=0,
                    maxValue=max(12, int(72 - drift * 60)),
                    distribution="exponential")
        # Monthly charges increase with drift
        .withColumn("monthly_charges", "decimal(8,2)",
                    minValue=19.99 + drift * 20,
                    maxValue=119.99 + drift * 30,
                    distribution=dg.distributions.Gamma(2.0, 2.0))
        # Churn rate increases with drift
        .withColumn("churned", "boolean",
                    expr=f"rand() < {0.25 + drift * 0.5}")
        .build()
    )

# Generate 20 daily drift batches
drift_batches = [generate_churn_drift_batch(spark, i) for i in range(20)]
drift_df = reduce(DataFrame.unionAll, drift_batches)

print(f"Drift batches total rows: {drift_df.count()}")
drift_df.groupBy("batch_id", "churned").count().orderBy("batch_id").show(40)
```

## Resources

- [dbldatagen Documentation](https://databrickslabs.github.io/dbldatagen/)
- [dbldatagen Multi-Column / Feature Generation](https://databrickslabs.github.io/dbldatagen/public_docs/generating_column_data.html)
- [Lakehouse Monitoring](https://docs.databricks.com/en/lakehouse-monitoring/index.html)
