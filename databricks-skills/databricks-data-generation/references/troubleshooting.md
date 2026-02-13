# Troubleshooting

Common issues when generating synthetic data with this skill.

## Dependency Errors

### `ModuleNotFoundError: mimesis`

This skill has no `pyproject.toml` — dependencies are supplied at runtime via `uv run --with`.

```bash
uv run --with polars --with mimesis scripts/my_script.py
```

### `ModuleNotFoundError: polars`

Same fix — add `--with polars`:

```bash
uv run --with polars --with mimesis scripts/my_script.py
```

### dbldatagen missing `jmespath` / `pyparsing`

dbldatagen declares `py4j`, `pyparsing`, and `jmespath` as pip dependencies. Normally these are satisfied automatically, but if you see import errors when using `uv run --with dbldatagen`, add the missing package explicitly:

```bash
uv run --with dbldatagen --with jmespath --with pyparsing scripts/my_script.py
```

This is a local dependency issue — dbldatagen works fine over Connect + serverless for Catalyst-safe features.

## Databricks Connect Issues

### `Serverless mode is not yet supported`

Pin `databricks-connect` to 16.x — version 18.x has serverless validation issues with classic workspaces:

```bash
uv run --with "databricks-connect>=16.4,<17.0" ...
```

See the [version matrix](databricks-connect-guide.md) for Python version compatibility.

### dbldatagen UDF-dependent features fail via Connect

Only UDF-dependent features fail over Connect + serverless — **standard Catalyst-safe features work fine**. Here's the breakdown:

| Works over Connect | Requires Tier 3 Notebook |
|---|---|
| `values=`, `weights=`, `random=True` | `text=mimesisText(...)` |
| `minValue`, `maxValue`, `step` | `distribution=Gamma/Beta/Normal` |
| `begin`, `end`, `interval` (timestamps) | `.withConstraint()` |
| `expr=`, `baseColumns=` | `template=` with UDF patterns |
| `percentNulls=`, `omit=True`, `.withIdOutput()` | |

If you only need Catalyst-safe features, use Tier 2 (dbldatagen + Connect). See [dbldatagen-connect-patterns.md](dbldatagen-connect-patterns.md) for validated patterns and [databricks-connect-guide.md](databricks-connect-guide.md) for the full compatibility matrix.

### `spark.read.parquet()` fails on local path

Spark sends file paths to the remote cluster, which can't access your local filesystem. Use Polars for local files:

```python
import polars as pl
df = pl.read_parquet("output/retail/customers.parquet")
```

## Delta / Unity Catalog Issues

### `DELTA_FAILED_TO_MERGE_FIELDS`

Schema mismatch when overwriting an existing table. Add the overwrite option:

```python
spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)
```

### `PERMISSION_DENIED: CREATE SCHEMA`

Check whether the schema already exists before creating:

```python
existing = [row.databaseName for row in spark.sql("SHOW SCHEMAS IN my_catalog").collect()]
if "retail" not in existing:
    spark.sql("CREATE SCHEMA my_catalog.retail")
```

### Catalog does not exist

Catalog creation requires **metastore admin** privileges and workspace-specific storage configuration. Create catalogs via the Databricks UI or ask a workspace admin. Always validate catalog existence — never try to create one programmatically.

## Data Quality Issues

### FK mismatch between tables

Child table foreign key ranges must match parent table primary key ranges. For example, if `customers` has IDs `1_000_000` to `1_100_000`, the `transactions` table's `customer_id` column must sample from the same range:

```python
customer_ids = list(range(1_000_000, 1_000_000 + num_customers))
# In transactions:
"customer_id": random.choices(customer_ids, k=num_transactions)
```

## Performance

### Polars generation slow at >5M rows

Polars list-comprehension generation is single-threaded. For >5M rows, switch to **Tier 3** (dbldatagen in a Databricks notebook) which parallelizes across Spark workers.
