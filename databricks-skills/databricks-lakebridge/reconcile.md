# Reconcile

The Reconcile capability verifies data consistency between source and target systems after migration. It supports schema validation, row-level comparison, and column-level data reconciliation.

Documentation: https://databrickslabs.github.io/lakebridge/reconcile

## Report Types

| Type | Description |
|------|-------------|
| `schema` | Validate datatype compatibility between source and target |
| `row` | Row-level hash-based reconciliation |
| `data` | Row and column-level reconciliation using join columns |
| `all` | Combined data + schema validation |

## Supported Source Systems

Source systems are frequently updated. Always check the official documentation:
https://databrickslabs.github.io/lakebridge/reconcile

## CLI Commands

### configure-reconcile

Interactive wizard to generate reconcile configuration:

```bash
databricks labs lakebridge configure-reconcile
```

### reconcile

Run data reconciliation:

```bash
databricks labs lakebridge reconcile
```

### aggregates-reconcile

Run aggregate-level reconciliation (SUM, AVG, COUNT, MIN, MAX, etc.):

```bash
databricks labs lakebridge aggregates-reconcile
```

## Configuration

Reconcile uses a JSON configuration file. Key configuration elements:

### Table Configuration

| Field | Description |
|-------|-------------|
| `source_name` | Fully qualified source table name (required) |
| `target_name` | Fully qualified target table name (required) |
| `join_columns` | Primary key columns for matching rows |
| `select_columns` | Columns to include (default: all) |
| `drop_columns` | Columns to exclude |
| `column_mapping` | Source-to-target column name mapping |
| `transformations` | SQL expressions for data normalization before comparison |
| `filters` | WHERE conditions for source and/or target |

### Thresholds

| Field | Description |
|-------|-------------|
| `column_thresholds` | Per-column variance tolerance (percentile, boundary, or date type) |
| `table_thresholds` | Overall mismatch tolerance for the table |

### Aggregates

Supported aggregate functions: `SUM`, `AVG`, `COUNT`, `MIN`, `MAX`, `MODE`, `STDDEV`, `VARIANCE`, `MEDIAN`

### JDBC Reader Options

For large tables, configure parallel reads:

| Field | Description |
|-------|-------------|
| `number_partitions` | Number of parallel partitions |
| `column` | Partition column |
| `lower_bound` / `upper_bound` | Partition range |

## Secret Scope Configuration

Database credentials are stored in Databricks secret scopes:

| Source System | Default Scope |
|---------------|---------------|
| General | `lakebridge_data_source` |
| Snowflake | `lakebridge_snowflake` |
| Oracle | `lakebridge_oracle` |
| MS SQL Server | `lakebridge_mssql` |
| Synapse | `lakebridge_synapse` |
| Databricks | `lakebridge_databricks` |

## Output Metrics Tables

Reconciliation results are written to Delta tables:

| Table | Description |
|-------|-------------|
| `schema_comparison` | Schema-level comparison results |
| `schema_difference` | Schema differences between source and target |
| `missing_in_src` | Rows present in target but missing in source |
| `missing_in_tgt` | Rows present in source but missing in target |
| `mismatch_data` | Row-level data mismatches |
| `threshold_mismatch` | Mismatches exceeding defined thresholds |
| `mismatch_columns` | Column-level mismatch summary |

For full configuration reference and examples, see:
https://databrickslabs.github.io/lakebridge/reconcile/reconcile_configuration
