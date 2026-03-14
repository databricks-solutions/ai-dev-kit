# Part IV: Databricks Platform

Databricks-specific best practices for building handoff-ready solutions. For comprehensive platform guidance, see [Databricks docs](https://docs.databricks.com/).

## 7.1 Notebooks

For detailed guidance on notebooks as entrypoints, project structure, and committing notebooks to git, see [**3-architecture.md §6.2 (Project Structure)**](3-architecture.md).

**Notebook Structure — keep them simple:**

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # Pipeline Name
# MAGIC Brief description of what this notebook does.

# COMMAND ----------
# MAGIC %pip install -r ../requirements.txt
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
# Config via widgets (job params override defaults)
dbutils.widgets.text("catalog", "dev_catalog")
dbutils.widgets.text("env", "dev")

catalog = dbutils.widgets.get("catalog")
env = dbutils.widgets.get("env")

# COMMAND ----------
from project.pipelines import customer_pipeline
from project.config import load_config

config = load_config(env)
result = customer_pipeline.run(spark, catalog, config)
```

## 7.2 Databricks Asset Bundles (DABs)

DABs are the **required** approach for managing Databricks infrastructure. They enable infrastructure as code, version-controlled deployments, and consistent dev/prod environments.

**Why DABs:**
- **Multi-environment:** Same code deploys to dev, staging, prod with variable substitution
- **Dev isolation:** `mode: development` prefixes resources with username, preventing conflicts
- **CI/CD integration:** Tag-based deployments to prod

**`databricks.yml`:**

```yaml
bundle:
  name: project-name

variables:
  catalog_name:
    description: "Unity Catalog name"
    default: "dev_catalog"

targets:
  dev:
    mode: development           # Prefixes resources with [dev username]
    default: true
    workspace:
      host: ${workspace.dev_host}
    variables:
      catalog_name: dev_catalog

  prod:
    mode: production
    workspace:
      host: ${workspace.prod_host}
    variables:
      catalog_name: prod_catalog
    run_as:
      service_principal_name: "project-sp"

include:
  - resources/**/*.yml
```

**Common Commands:**

```bash
databricks bundle validate -t dev     # Validate config
databricks bundle deploy -t dev       # Deploy resources
databricks bundle run job_name -t dev # Run a job
databricks bundle destroy -t dev      # Clean up dev resources
```

For DABs YAML reference (jobs, pipelines, dashboards, volumes), see **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)**.

## 7.3 Unity Catalog

**Naming Conventions:**

| Resource | Convention | Example |
|----------|-----------|---------|
| Catalog | `{env}_{domain}` | `dev_sales`, `prod_sales` |
| Schema | `{purpose}` | `bronze`, `silver`, `gold` |
| Table | `{descriptive_name}` | `customer_transactions` |
| Volume | `{purpose}` | `landing_zone`, `checkpoints` |

**Always use three-level namespace:**

```python
# GOOD - explicit
spark.table("prod_sales.gold.customer_transactions")

# BETTER - config-driven for environment flexibility
spark.table(f"{config.catalog}.{config.schema}.customers")

# BAD - relies on default catalog/schema
spark.table("customers")
```

For Unity Catalog operations and system tables queries, see **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)**.

## 7.4 Compute

**Development:**
- Start with the smallest viable cluster (or serverless)
- Set auto-terminate to 30–60 minutes
- Single-node clusters work for most development tasks
- Use your personal cluster, don't share during active development

**Production:**
- Use job clusters (ephemeral) rather than all-purpose clusters
- Right-size based on actual workload — profile before scaling up
- Enable autoscaling with sensible min/max bounds
- Prefer serverless for variable workloads to avoid idle costs

**When to use serverless:** Variable duration/frequency jobs, development and testing, when minimizing ops overhead.

**When to use dedicated clusters:** Predictable long-running workloads, specific library/config requirements, cost optimization for sustained high utilization.

---

## 8. Data Engineering Patterns

### 8.1 Idempotent Writes

Pipelines should produce the same result when run multiple times — critical for reliability and recovery.

```python
# BAD - append creates duplicates on re-run
df.write.mode("append").saveAsTable("catalog.schema.customers")

# GOOD - merge ensures idempotency
from delta.tables import DeltaTable
target = DeltaTable.forName(spark, "catalog.schema.customers")
target.alias("t").merge(
    source_df.alias("s"),
    "t.customer_id = s.customer_id"
).whenMatchedUpdateAll() \
 .whenNotMatchedInsertAll() \
 .execute()

# For full table refreshes - overwrite is also idempotent
df.write.mode("overwrite").saveAsTable("catalog.schema.daily_summary")
```

### 8.2 Medallion Architecture

```
Bronze (Raw) → Silver (Cleaned) → Gold (Business-Ready)
```

| Layer | Purpose | Typical Operations |
|-------|---------|-------------------|
| **Bronze** | Raw ingestion, preserve source fidelity | Append-only, minimal transformation |
| **Silver** | Cleaned, deduplicated, validated | Schema enforcement, deduplication, joins |
| **Gold** | Business-ready aggregations | Aggregations, business logic, feature tables |

This isn't the only valid pattern — use what fits the use case. Good default for data pipelines.

### 8.3 Data Quality

**For Lakeflow Declarative Pipelines:** Use [expectations](https://docs.databricks.com/en/delta-live-tables/expectations.html) for declarative data quality checks.

**For Spark jobs:** Validate at boundaries (ingestion, before writes):

```python
def validate_customers(df: DataFrame) -> DataFrame:
    """Validate and filter bad records."""
    valid_df = df.filter(
        col("customer_id").isNotNull() &
        col("email").isNotNull()
    )

    invalid_count = df.count() - valid_df.count()
    if invalid_count > 0:
        logger.warning(f"Filtered {invalid_count} invalid records")

    return valid_df.dropDuplicates(["customer_id"])
```

**Key principle:** Validate early, fail fast on critical issues, quarantine (don't drop) bad records when possible.

### 8.4 Incremental Processing

For large tables, process only changed data using Change Data Feed:

```python
# Enable CDF on the source table (one-time)
spark.sql("""
    ALTER TABLE catalog.schema.source_table
    SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
""")

# Read only changes since last run
changes = spark.read.format("delta") \
    .option("readChangeFeed", "true") \
    .option("startingVersion", last_processed_version) \
    .table("catalog.schema.source_table")
```

---

## 9. Resource Management

### 9.1 Resource Cleanup

**Weekly cleanup:**
- Delete test tables and volumes in dev catalogs
- Remove unused MLflow experiments and model versions
- Audit dev resources and delete anything not actively in use
- Run `databricks bundle destroy -t dev` for abandoned branches

**Before leaving for extended periods:**
- Terminate all interactive clusters
- Ensure no scheduled jobs are running unnecessarily in dev

### 9.2 Engagement Exit Checklist

- [ ] All personal dev resources deleted (`databricks bundle destroy`)
- [ ] Production resources documented in Reference Doc
- [ ] Ownership transferred to customer team
- [ ] Developer access removed or downgraded
- [ ] Service principal credentials rotated (if temporary dev access was granted)
- [ ] No orphaned resources (clusters, jobs, endpoints)
- [ ] Customer can deploy and operate independently

---

## 10. Security & Data Governance

### 10.1 Credentials Management

**Never hardcode credentials.** Use [Databricks Secrets](https://docs.databricks.com/aws/en/security/secrets/):

```bash
# Store a secret (CLI)
databricks secrets put-secret --scope project --key api_key
```

```python
# Access in code - value is redacted in logs
api_key = dbutils.secrets.get(scope="project", key="api_key")
```

Common credential types to manage: external API keys, service principal secrets, database connection strings, OAuth tokens.

### 10.2 Data Handling

- **Work in Databricks** — avoid downloading data to local machines
- **Follow customer data policies** — they may have stricter requirements than Databricks defaults
- **Mask PII in dev/test** — use tokenization, hashing, or synthetic data
- **Don't commit data** — no CSVs, JSONs, or sample data in git repos

### 10.3 Access Control

- **Principle of least privilege** — request only the access you need
- **Use service principals** for production jobs, not personal credentials
- **Document access grants** — track what access was granted and why
- **Remove access at engagement end** — don't leave orphaned permissions
