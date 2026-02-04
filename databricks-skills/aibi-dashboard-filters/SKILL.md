---
name: aibi-dashboard-filters
description: Implement context filters and cascading filters in Databricks AI/BI Dashboards. Use when migrating from other BI tools, designing dashboard interactions, or creating dependent filter behaviors like "only relevant values".
author: Artem Chebotko
source_url: https://www.databricksters.com/p/migrating-existing-dashboards-to
source_site: databricksters.com
---

# AI/BI Dashboard Filters: Context and Cascading

## Overview

When migrating from existing BI tools to Databricks AI/BI Dashboards, teams often need to replicate familiar filter patterns:

- **Context Filters**: Define a high-level data subset first, then apply other filters on top
- **Cascading Filters** ("Only Relevant Values"): Each filter's dropdown shows only values relevant to current selections

This skill covers both patterns using the TPCH sample dataset as a concrete example.

## Key Concepts

### Field Filters vs Parameter Filters

| Type | Behavior | Use Case |
|------|----------|----------|
| **Field Filter** | Applied on top of dataset results | Post-query filtering, cascading behavior |
| **Parameter Filter** | Substituted into dataset SQL | Context filtering, pre-join filtering |

### Filter Scopes

- **Global**: Applies across all dashboard pages
- **Page-level**: Applies to all visuals on a specific page
- **Widget-level**: Static filter on a single visualization

## Pattern 1: Context Filters with Parameters

Context filters define a base data subset first, with other filters applied on top.

### Step 1: Create Parameterized Dataset

```sql
-- Dataset: TPCH Sales (Context)
SELECT
  r.r_name AS region,
  n.n_name AS nation,
  c.c_custkey AS customer_id,
  c.c_name AS customer_name,
  o.o_orderkey AS order_id,
  o.o_orderdate AS order_date,
  l.l_extendedprice * (1 - l.l_discount) AS revenue
FROM samples.tpch.region AS r
JOIN samples.tpch.nation AS n ON n.n_regionkey = r.r_regionkey
JOIN samples.tpch.customer AS c ON c.c_nationkey = n.n_nationkey
JOIN samples.tpch.orders AS o ON o.o_custkey = c.c_custkey
JOIN samples.tpch.lineitem AS l ON l.l_orderkey = o.o_orderkey
WHERE r.r_name = :region_param  -- Context filter
```

### Step 2: Define the Parameter

In the dataset's **Parameters** panel:
- Name: `region_param`
- Type: String
- Default: `AMERICA` (optional)

### Step 3: Create Helper Dataset (Optional)

```sql
-- Dataset: TPCH Regions (Context)
SELECT DISTINCT r_name AS region
FROM samples.tpch.region
ORDER BY region
```

### Step 4: Configure Filter Widget

1. Add a **page-level filter widget** titled "Region"
2. Set filter type to **Single value**
3. Configure:
   - Fields: `TPCH Regions (Context).region`
   - Parameters: `TPCH Sales (Context).region_param`

### Effect

When viewer selects `Region: EUROPE`:
1. Widget writes "EUROPE" into `region_param`
2. Dataset reruns with `WHERE r.r_name = 'EUROPE'`
3. All visuals show European data as their base subset
4. Additional filters operate on this pre-filtered data

## Pattern 2: Cascading Filters with Field Filters

The simplest cascading behavior uses field filters on a shared dataset.

### Step 1: Create Base Dataset

```sql
-- Dataset: TPCH Sales (Cascading Pattern 1)
SELECT
  r.r_name AS region,
  n.n_name AS nation,
  c.c_custkey AS customer_id,
  c.c_name AS customer_name,
  o.o_orderkey AS order_id,
  o.o_orderdate AS order_date,
  l.l_extendedprice * (1 - l.l_discount) AS revenue
FROM samples.tpch.region AS r
JOIN samples.tpch.nation AS n ON n.n_regionkey = r.r_regionkey
JOIN samples.tpch.customer AS c ON c.c_nationkey = n.n_nationkey
JOIN samples.tpch.orders AS o ON o.o_custkey = c.c_custkey
JOIN samples.tpch.lineitem AS l ON l.l_orderkey = o.o_orderkey
-- No parameters - pure field filters
```

### Step 2: Add Field Filter Widgets

Add three **page-level field filters**:

| Filter | Field Connection |
|--------|-----------------|
| Region | `TPCH Sales (Cascading Pattern 1).region` |
| Nation | `TPCH Sales (Cascading Pattern 1).nation` |
| Customer | `TPCH Sales (Cascading Pattern 1).customer_id` |

### Effect

1. Select `Region: ASIA` → Dataset filters to Asia
2. Nation dropdown recomputes → Shows only Asian nations
3. Select `Nation: JAPAN` → Dataset filters further
4. Customer dropdown recomputes → Shows only Japanese customers

## Pattern 3: Cascading with Query-Based Parameters

For more control or multi-dataset scenarios, use query-based parameters.

### Step 1: Create Main Dataset with Parameters

```sql
-- Dataset: TPCH Sales (Cascading Pattern 2)
SELECT
  r.r_name AS region,
  n.n_name AS nation,
  c.c_custkey AS customer_id,
  c.c_name AS customer_name,
  o.o_orderkey AS order_id,
  o.o_orderdate AS order_date,
  l.l_extendedprice * (1 - l.l_discount) AS revenue
FROM samples.tpch.region AS r
JOIN samples.tpch.nation AS n ON n.n_regionkey = r.r_regionkey
JOIN samples.tpch.customer AS c ON c.c_nationkey = n.n_nationkey
JOIN samples.tpch.orders AS o ON o.o_custkey = c.c_custkey
JOIN samples.tpch.lineitem AS l ON l.l_orderkey = o.o_orderkey
WHERE (:region_param = 'All' OR r.r_name = :region_param)
  AND (:nation_param = 'All' OR n.n_name = :nation_param)
  AND (:customer_param = 0 OR c.c_custkey = :customer_param)
```

**Parameters**:
- `region_param`: String, default "All"
- `nation_param`: String, default "All"  
- `customer_param`: Numeric, default 0

### Step 2: Create Helper Datasets

```sql
-- Dataset: TPCH Regions (Pattern 2)
SELECT DISTINCT r_name AS region
FROM samples.tpch.region
ORDER BY region

-- Dataset: TPCH Nations by Region
SELECT DISTINCT n.n_name AS nation
FROM samples.tpch.nation AS n
JOIN samples.tpch.region AS r ON n.n_regionkey = r.r_regionkey
WHERE r.r_name = :region_param
ORDER BY nation

-- Dataset: TPCH Customers by Nation  
SELECT DISTINCT c.c_custkey AS customer_id
FROM samples.tpch.nation AS n
JOIN samples.tpch.customer AS c ON c.c_nationkey = n.n_nationkey
WHERE n.n_name = :nation_param
ORDER BY customer_id
```

### Step 3: Wire Filter Widgets

**Region Filter**:
- Type: Single value
- Fields: `TPCH Regions (Pattern 2).region`
- Parameters: `TPCH Sales (Pattern 2).region_param`, `TPCH Nations by Region.region_param`
- Default: "All"

**Nation Filter**:
- Type: Single value  
- Fields: `TPCH Nations by Region.nation`
- Parameters: `TPCH Sales (Pattern 2).nation_param`, `TPCH Customers by Nation.nation_param`
- Default: "All"

**Customer Filter**:
- Type: Single value
- Fields: `TPCH Customers by Nation.customer_id`
- Parameters: `TPCH Sales (Pattern 2).customer_param`
- Default: 0

## Examples

### Example: Complete Dashboard Setup

```sql
-- 1. Create datasets
-- Main dataset with parameter
CREATE TABLE IF NOT EXISTS samples.tpch.sales_view AS
SELECT
  r.r_name AS region,
  n.n_name AS nation,
  c.c_custkey AS customer_id,
  c.c_name AS customer_name,
  l.l_extendedprice * (1 - l.l_discount) AS revenue
FROM samples.tpch.region AS r
JOIN samples.tpch.nation AS n ON n.n_regionkey = r.r_regionkey
JOIN samples.tpch.customer AS c ON c.c_nationkey = n.n_nationkey
JOIN samples.tpch.orders AS o ON o.o_custkey = c.c_custkey
JOIN samples.tpch.lineitem AS l ON l.l_orderkey = o.o_orderkey;

-- 2. In AI/BI Dashboard:
--    - Create dataset from above query
--    - Define parameters in Data tab
--    - Add filter widgets with proper field/parameter mappings
--    - Create visualizations using the filtered dataset
```

## Edge Cases & Troubleshooting

### Issue: Filters Not Cascading

**Symptoms**: Nation dropdown shows all values regardless of Region selection.

**Solutions**:
1. Ensure all filters connect to the **same dataset**
2. Check that field filter (not parameter filter) is used for cascading
3. Verify dataset is not using "Direct table reference" (must use SQL query)

### Issue: Parameter Not Applying

**Symptoms**: Dashboard shows all data despite filter selection.

**Diagnostics**:
1. Check parameter syntax in SQL: `:param_name` (not `{param_name}`)
2. Verify parameter is defined in dataset's Parameters panel
3. Confirm filter widget maps to correct parameter

### Issue: Slow Filter Performance

**Symptoms**: Dropdowns take too long to populate.

**Solutions**:
1. Add LIMIT to helper dataset queries
2. Enable caching on datasets
3. Use smaller helper datasets (avoid joining large tables)

### Issue: "All" Option Not Working

**Symptoms**: Selecting "All" shows no data.

**Fix**: Check your SQL WHERE clause logic:

```sql
-- CORRECT: Parentheses around OR conditions
WHERE (:region_param = 'All' OR r.r_name = :region_param)

-- INCORRECT: Without proper grouping
WHERE :region_param = 'All' OR r.r_name = :region_param  -- Logic error!
```

## Best Practices

1. **Use field filters for simple cascading** - Easiest to set up and maintain
2. **Use parameter filters for context filtering** - Better performance for large datasets
3. **Create helper datasets for dropdowns** - Keeps dropdown queries lightweight
4. **Set sensible defaults** - Prevents "empty dashboard" on load
5. **Test with real data volumes** - Cascading behavior can slow down with large datasets

## Attribution

This skill is based on content by **Artem Chebotko** from the Databricksters blog post:
[Migrating Existing Dashboards to Databricks AI/BI, Part 1: Context and Cascading Filters](https://www.databricksters.com/p/migrating-existing-dashboards-to)

Companion dashboard available at: [GitHub Repository](https://github.com/ArtemChebotko/Migrating-Existing-Dashboards-to-Databricks-AI-BI)

## Related Resources

- [AI/BI Dashboards Filters Documentation](https://docs.databricks.com/aws/en/dashboards/filters)
- [Parameters in AI/BI Dashboards](https://docs.databricks.com/aws/en/dashboards/parameters)
- [Caching and Data Freshness](https://docs.databricks.com/aws/en/dashboards/caching)
