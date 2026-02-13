# Schema Introspection Patterns

DataAnalyzer for reverse-engineering production schemas into dbldatagen specs.

## DataAnalyzer API

```python
from dbldatagen import DataAnalyzer
# or: from dbldatagen.data_analyzer import DataAnalyzer
```

Constructor:

```python
DataAnalyzer(df=spark_dataframe, sparkSession=spark, debug=False, verbose=False)
```

- `df` is REQUIRED (raises `ValueError` if not supplied)
- `sparkSession` is optional (auto-detected via `SparkSingleton`)

### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `summarizeToDF()` | `DataFrame` | Summary with measures: schema, count, null_probability, distinct_count, min, max, mean, stddev, print_len_min, print_len_max |
| `summarize(suppressOutput=False)` | `str` | Human-readable summary string (prints by default) |
| `scriptDataGeneratorFromData(suppressOutput=False, name=None)` | `str` | Generates dbldatagen code from actual data statistics |
| `scriptDataGeneratorFromSchema(schema, suppressOutput=False, name=None)` | `str` | **Classmethod.** Generates code from `StructType` schema only (no data analysis) |

All code generation methods are experimental -- treat output as a starting point to refine.

## Introspect, Analyze, Generate

The core workflow: read a table, analyze it, generate a dbldatagen spec, then refine.

```python
import dbldatagen as dg
from dbldatagen import DataAnalyzer

# 1. Read production table
df = spark.table("prod_catalog.sales.customers")

# 2. Analyze
analyzer = DataAnalyzer(df=df)
summary_df = analyzer.summarizeToDF()
display(summary_df)  # inspect schema, nulls, cardinality, min/max, stddev

# 3. Generate code from data statistics
generated_code = analyzer.scriptDataGeneratorFromData(
    suppressOutput=True,
    name="customer_synth"
)
print(generated_code)

# 4. Copy the printed code, paste into your editor, and refine
```

The generated code includes `import dbldatagen as dg` and a full `DataGenerator` spec with `.withColumn()` calls derived from the source data's min/max/null statistics.

## Schema-First Generation

When you only need the schema (no data scan), use the classmethod:

```python
from dbldatagen import DataAnalyzer
from pyspark.sql.types import StructType

schema = spark.table("prod_catalog.sales.customers").schema

code = DataAnalyzer.scriptDataGeneratorFromSchema(
    schema,
    suppressOutput=True,
    name="customer_synth"
)
print(code)
```

This is faster since it skips the full-table aggregation. Column specs use default value ranges rather than actual data statistics.

## Unity Catalog Integration

Read a production table schema, generate synthetic data, and write to a dev catalog:

```python
import dbldatagen as dg
from dbldatagen import DataAnalyzer
from utils.mimesis_text import mimesisText

# Analyze prod
prod_df = spark.table("prod_catalog.sales.customers")
analyzer = DataAnalyzer(df=prod_df)
display(analyzer.summarizeToDF())

# Use generated code as a starting point, then refine:
spec = (
    dg.DataGenerator(spark, name="customer_synth", rows=500_000, random=True)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=500_000)
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("signup_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
    .withColumn("lifetime_spend", "decimal(12,2)", minValue=0, maxValue=50000, random=True)
)

synth_df = spec.build()

# Write to dev catalog
synth_df.write.mode("overwrite").saveAsTable("dev_catalog.sales.customers")
```

## Handling Complex Types

DataAnalyzer maps Spark SQL types to dbldatagen column parameters:

| Spark Type | Generated Parameters | Defaults (no data) |
|------------|---------------------|---------------------|
| `StringType` | `template=r'\\w'` | Single word template |
| `IntegerType`, `LongType` | `minValue, maxValue` | 0, 1000000 |
| `ByteType` | `minValue, maxValue` | 0, 127 |
| `ShortType` | `minValue, maxValue` | 0, 32767 |
| `BooleanType` | `expr='id % 2 = 1'` | Alternating true/false |
| `DateType` | `expr='current_date()'` | Current date |
| `DecimalType` | `minValue, maxValue` | 0, 1000000.0 |
| `FloatType`, `DoubleType` | `minValue, maxValue, step` | 0.0, 1000000.0, 0.1 |
| `TimestampType` | `begin, end, interval` | 2020-01-01 to 2020-12-31, 1 minute |
| `BinaryType` | `expr="cast('...' as binary)"` | Static binary string |
| `ArrayType` | `structType='array', numFeatures=(2,6)` | Element type inferred |

When `scriptDataGeneratorFromData()` detects `null_probability > 0` for a column, it appends `percentNulls=<value>` to that column's spec.

With data-driven generation (`scriptDataGeneratorFromData`), `minValue` and `maxValue` come from the actual column statistics rather than defaults.

## Refining Generated Code

The auto-generated spec is a scaffold. Improve it by:

**Replace generic templates with mimesisText for PII columns:**
```python
# Generated: .withColumn('first_name', 'string', template=r'\\w')
# Refined:
.withColumn("first_name", "string", text=mimesisText("person.first_name"))
.withColumn("email", "string", text=mimesisText("person.email"))
```

**Add distributions based on data shape:**
```python
# Generated: .withColumn('order_amount', 'decimal(10,2)', minValue=5.0, maxValue=9500.0)
# Refined — use exponential for right-skewed spend data:
.withColumn("order_amount", "decimal(10,2)", minValue=5, maxValue=9500,
            distribution=dg.distributions.Exponential(rate=0.1), random=True)
```

**Add FK relationships that DataAnalyzer cannot detect:**
```python
# DataAnalyzer treats every column independently — add FK alignment manually:
.withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_099_999)
```

**Add constraints for business rules:**
```python
from dbldatagen.constraints import SqlExpr
# Ensure end_date >= start_date
spec = spec.withConstraint(SqlExpr("end_date >= start_date"))
```

## Complete Example

```python
# --- Cell 1: Analyze existing table ---
from dbldatagen import DataAnalyzer

source_df = spark.table("prod.sales.customers")
analyzer = DataAnalyzer(df=source_df)
display(analyzer.summarizeToDF())

# --- Cell 2: Generate initial code ---
generated_code = analyzer.scriptDataGeneratorFromData(
    suppressOutput=True,
    name="customer_synth"
)
print(generated_code)

# --- Cell 3: Refine and run (paste generated code, then modify) ---
import dbldatagen as dg
from utils.mimesis_text import mimesisText

spec = (
    dg.DataGenerator(sparkSession=spark, name="customer_synth", rows=100_000, random=True)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("phone", "string", text=mimesisText("person.telephone"))
    .withColumn("city", "string", text=mimesisText("address.city"))
    .withColumn("state", "string", values=["CA", "NY", "TX", "FL", "IL"],
                weights=[25, 20, 18, 15, 10], random=True)
    .withColumn("signup_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
    .withColumn("lifetime_spend", "decimal(12,2)", minValue=0, maxValue=50000,
                distribution=dg.distributions.Exponential(rate=0.1), random=True)
    .withColumn("is_active", "boolean", values=[True, False], weights=[85, 15], random=True)
)

synth_df = spec.build()
display(synth_df)

# --- Cell 4: Write to dev catalog ---
synth_df.write.mode("overwrite").saveAsTable("dev.sales.customers")
```
