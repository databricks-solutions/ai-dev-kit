# Governance & Metadata

Tags, comments, quality monitors, and naming conventions.

## Tags

Tags classify and categorize Unity Catalog objects for governance.

### About Tags

Tags are created implicitly when first applied to an object. Governed tags (with allowed values and enforced rules) are managed via Catalog Explorer UI or API, not SQL.

### Apply Tags to Objects

**SQL (ALTER ... SET TAGS):**
```sql
-- Tag a table (key-value format required)
ALTER TABLE analytics.gold.customers
SET TAGS ('pii' = '', 'gdpr' = '');

-- Tag with key-value
ALTER TABLE analytics.gold.customers
SET TAGS ('data_classification' = 'confidential', 'owner' = 'data_team');

-- Tag specific columns
ALTER TABLE analytics.gold.customers
ALTER COLUMN email SET TAGS ('pii' = 'email');

ALTER TABLE analytics.gold.customers
ALTER COLUMN ssn SET TAGS ('pii' = 'ssn', 'confidential' = '');

ALTER TABLE analytics.gold.customers
ALTER COLUMN phone SET TAGS ('pii' = 'phone_number');

-- Tag schema
ALTER SCHEMA analytics.gold
SET TAGS ('data_quality' = 'curated');

-- Tag catalog
ALTER CATALOG analytics
SET TAGS ('environment' = 'production');
```

**SQL (SET TAG ON ... — Databricks Runtime 16.1+):**
```sql
-- Alternative syntax supporting key-only tags
SET TAG ON TABLE analytics.gold.customers pii;
SET TAG ON TABLE analytics.gold.customers data_classification = 'confidential';
SET TAG ON COLUMN analytics.gold.customers.ssn pii;
```

### Query Tags

**SQL:**
```sql
-- Find all PII tables
SELECT
    table_catalog,
    table_schema,
    table_name
FROM system.information_schema.table_tags
WHERE tag_name = 'pii';

-- Find all PII columns
SELECT
    table_catalog,
    table_schema,
    table_name,
    column_name
FROM system.information_schema.column_tags
WHERE tag_name = 'pii';

-- Find tables by classification
SELECT *
FROM system.information_schema.table_tags
WHERE tag_name = 'data_classification'
  AND tag_value = 'confidential';
```

### Remove Tags

**SQL (ALTER ... UNSET TAGS):**
```sql
-- Remove tag from table
ALTER TABLE analytics.gold.customers
UNSET TAGS ('pii');

-- Remove tag from column
ALTER TABLE analytics.gold.customers
ALTER COLUMN email UNSET TAGS ('pii');
```

**SQL (UNSET TAG ON ... — Databricks Runtime 16.1+):**
```sql
UNSET TAG ON TABLE analytics.gold.customers pii;
UNSET TAG ON COLUMN analytics.gold.customers.email pii;
```

---

## Comments

Comments document objects for discoverability and understanding.

### Add Comments

**SQL:**
```sql
-- Table comment (at creation)
CREATE TABLE analytics.gold.customer_360 (
    customer_id BIGINT COMMENT 'Unique customer identifier',
    email STRING COMMENT 'Primary contact email',
    ltv DECIMAL(18,2) COMMENT 'Lifetime value in USD',
    segment STRING COMMENT 'Customer segment (premium/standard/basic)'
)
COMMENT 'Unified customer view combining orders, interactions, and profile data. Updated daily at 6 AM UTC.';

-- Add/update table comment (use COMMENT ON, not ALTER TABLE SET COMMENT)
COMMENT ON TABLE analytics.gold.customer_360
IS 'Unified customer view v2. Now includes churn prediction score.';

-- Column comments (ALTER COLUMN ... COMMENT is valid)
ALTER TABLE analytics.gold.customer_360
ALTER COLUMN ltv COMMENT 'Lifetime value = sum(orders) - sum(returns) - sum(discounts)';

-- Schema comment
COMMENT ON SCHEMA analytics.gold
IS 'Business-ready aggregates for reporting and ML. SLA: 99.9% availability.';

-- Catalog comment
COMMENT ON CATALOG analytics
IS 'Production analytics platform. Contact: data-team@company.com';
```

### Query Comments

**SQL:**
```sql
-- Get table comment
SELECT comment FROM system.information_schema.tables
WHERE table_catalog = 'analytics'
  AND table_schema = 'gold'
  AND table_name = 'customer_360';

-- Get all column comments
SELECT
    column_name,
    comment
FROM system.information_schema.columns
WHERE table_catalog = 'analytics'
  AND table_schema = 'gold'
  AND table_name = 'customer_360';

-- Search for tables by comment
SELECT table_catalog, table_schema, table_name, comment
FROM system.information_schema.tables
WHERE comment LIKE '%customer%';
```

---

## Quality Monitors

Monitor data quality with automated profiling and anomaly detection.

### Create Quality Monitor

> Quality monitors (Lakehouse Monitors) are created via SDK, CLI, or UI (not SQL).

**Python SDK:**
```python
from databricks.sdk.service.catalog import MonitorCronSchedule

# Create quality monitor
monitor = w.quality_monitors.create(
    table_name="analytics.gold.orders",
    schedule=MonitorCronSchedule(
        quartz_cron_expression="0 0 * * * ?",
        timezone_id="UTC"
    ),
    output_schema_name="analytics.monitoring",
    assets_dir="/Shared/monitors/orders"
)

# Get monitor status
monitor = w.quality_monitors.get("analytics.gold.orders")
print(f"Status: {monitor.status}")

# Trigger refresh manually
w.quality_monitors.run_refresh("analytics.gold.orders")

# List refresh history
refreshes = w.quality_monitors.list_refreshes("analytics.gold.orders")
for r in refreshes:
    print(f"{r.refresh_id}: {r.state}")
```

**CLI:**
```bash
# Create monitor
databricks quality-monitors create analytics.gold.orders --json '{
    "schedule": {
        "quartz_cron_expression": "0 0 * * * ?",
        "timezone_id": "UTC"
    },
    "output_schema_name": "analytics.monitoring"
}'

# Get monitor
databricks quality-monitors get analytics.gold.orders

# Run refresh
databricks quality-monitors run-refresh analytics.gold.orders

# List refreshes
databricks quality-monitors list-refreshes analytics.gold.orders
```

### Query Monitor Results

```sql
-- Profile metrics
SELECT *
FROM analytics.monitoring.orders_profile_metrics
WHERE window_end >= current_date() - 7;

-- Drift metrics
SELECT *
FROM analytics.monitoring.orders_drift_metrics
WHERE window_end >= current_date() - 7
  AND drift_score > 0.1;

-- Anomaly detection
SELECT *
FROM analytics.monitoring.orders_profile_metrics
WHERE is_anomaly = true
ORDER BY window_end DESC;
```

### Delete Quality Monitor

**Python SDK:**
```python
w.quality_monitors.delete("analytics.gold.orders")
```

**CLI:**
```bash
databricks quality-monitors delete analytics.gold.orders
```

---

## Artifact Allowlists

Control which libraries and init scripts can be used on shared clusters.

### Manage Allowlists

> Artifact allowlists are managed via SDK or CLI (not SQL).

**Python SDK:**
```python
# Get current allowlist
allowlist = w.artifact_allowlists.get("LIBRARY_JAR")
for artifact in allowlist.artifact_matchers:
    print(f"{artifact.artifact}: {artifact.match_type}")

# Update allowlist
from databricks.sdk.service.catalog import ArtifactMatcher, MatchType

w.artifact_allowlists.update(
    artifact_type="LIBRARY_JAR",
    artifact_matchers=[
        ArtifactMatcher(
            artifact="com.databricks:*",
            match_type=MatchType.PREFIX_MATCH
        ),
        ArtifactMatcher(
            artifact="org.apache.spark:*",
            match_type=MatchType.PREFIX_MATCH
        )
    ]
)
```

**CLI:**
```bash
# Get allowlist
databricks artifact-allowlists get LIBRARY_JAR

# Update allowlist
databricks artifact-allowlists update LIBRARY_JAR --json '{
    "artifact_matchers": [
        {"artifact": "com.databricks:*", "match_type": "PREFIX_MATCH"},
        {"artifact": "org.apache.spark:*", "match_type": "PREFIX_MATCH"}
    ]
}'
```

---

## Naming Conventions

### Recommended Patterns

| Object | Pattern | Examples |
|--------|---------|----------|
| Catalog | `{domain}_{environment}` | `analytics_prod`, `ml_dev` |
| Schema | `{layer}` or `{domain}` | `bronze`, `silver`, `gold`, `marketing`, `finance` |
| Table | `{entity}_{descriptor}` | `orders_raw`, `customers_enriched`, `daily_sales` |
| View | `v_{entity}_{purpose}` | `v_orders_summary`, `v_customer_360` |
| Volume | `{content_type}_{source}` | `raw_files_s3`, `images_uploads` |
| Function | `{action}_{target}` | `mask_email`, `validate_phone`, `calculate_ltv` |

### Environment Patterns

```
# Catalog-per-environment (recommended for isolation)
analytics_dev
analytics_staging
analytics_prod

# Schema-per-environment (simpler, less isolation)
analytics.dev_bronze
analytics.staging_bronze
analytics.prod_bronze
```

### Medallion Architecture

```
# Standard layers
{catalog}.bronze    # Raw data, minimal transformation
{catalog}.silver    # Cleaned, validated, enriched
{catalog}.gold      # Business aggregates, ML features

# Additional layers (optional)
{catalog}.platinum  # Highly curated, published datasets
{catalog}.quarantine # Data that failed validation
```

---

## Best Practices

### Tags
1. **Define a taxonomy** - Standardize tag names across the organization
2. **Use allowed values** - Constrain tags to prevent typos
3. **Tag at creation** - Add tags when creating objects, not after
4. **Automate tagging** - Use policies to auto-tag based on rules
5. **Regular audits** - Query system tables to find untagged objects

### Comments
1. **Be specific** - Include update frequency, SLAs, owners
2. **Keep current** - Update comments when tables change
3. **Include contact** - Who to reach for questions
4. **Document lineage** - What sources feed this table

### Quality Monitors
1. **Start with critical tables** - Focus on business-critical data
2. **Use baselines** - Compare against known-good data
3. **Alert on anomalies** - Integrate with notification systems
4. **Review regularly** - Tune thresholds based on findings

### Naming
1. **Consistent casing** - Use snake_case everywhere
2. **Avoid abbreviations** - `customer` not `cust`
3. **Be descriptive** - `order_line_items` not `oli`
4. **Version carefully** - `customers_v2` only when necessary
