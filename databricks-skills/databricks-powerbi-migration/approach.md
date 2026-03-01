# PowerBI Semantic Model to Databricks Metric Views: High-Level Approach

This document outlines the methodology for converting Power BI semantic models into Databricks metric views, enabling governed, reusable analytics on the Databricks Lakehouse platform.

---

## 1. Assess and Document the Existing Semantic Model

Start by analyzing your Power BI dataset to identify the critical semantic assets:

### Tables and Relationships

- List all fact and dimension tables, their cardinalities, and relationship types.
- Document join keys, cross-filter directions, and any inactive relationships.
- Note whether relationships are one-to-one, one-to-many, or many-to-many.

### Measures and KPIs

- Document all DAX measures, aggregations, and calculated columns, noting their purpose and logic.
- Categorize measures by business domain (e.g., Revenue, Operations, Customer).
- Identify complex measures (e.g., time-intelligence, CALCULATE with filters, iterator functions) that require careful SQL translation.

### Hierarchies, Metadata, and Security Roles

- Capture any row-level security (RLS) filters and their definitions.
- Document display folders, field formatting, sort-by columns, and default summarization.
- Record any hierarchies (e.g., Geography: Country > State > City).

This inventory becomes your **translation map** to Databricks metric views.

---

## 2. Migrate Data Foundations to Delta Tables

Databricks metric views rely on Delta tables as the core storage layer. Follow these steps:

### Ingest and Convert

- Convert or sync your existing data sources (from SQL Server, Synapse, Redshift, etc.) into Delta format using **Auto Loader** or **Spark Declarative Pipelines (Lakeflow)**.
- Use the **medallion architecture**: land raw data in Bronze, cleanse in Silver, and serve business-ready aggregates from Gold.

### Optimize for Performance

- Apply **Liquid Clustering** (preferred) or Z-Ordering on columns frequently used in filters and joins.
- Consider partitioning for tables exceeding 1 TB.
- Enable **predictive optimization** or schedule regular `VACUUM` and `OPTIMIZE` operations.
- Enable **schema evolution** to handle upstream changes gracefully.

### Maintain Semantic Consistency

- Column naming, data types, and business keys should match those used in Power BI to minimize transformation complexity.
- Declare **primary and foreign key constraints** in Unity Catalog with `RELY` to enable Power BI auto-relationship detection and Databricks query optimization.
- Avoid wide data types and high-cardinality columns to reduce Power BI semantic model size.

### Example

If Power BI used a `SalesFact` table joined to `CustomerDim` and `DateDim`, ensure equivalent tables exist as optimized Delta tables in your Databricks Lakehouse:

```sql
-- Gold layer fact table with PK/FK constraints
CREATE TABLE gold.sales_fact (
  sale_id BIGINT NOT NULL,
  customer_id BIGINT NOT NULL,
  date_key INT NOT NULL,
  quantity INT,
  unit_price DECIMAL(18,2),
  total_amount DECIMAL(18,2)
)
USING DELTA
CLUSTER BY (date_key, customer_id);

ALTER TABLE gold.sales_fact ADD CONSTRAINT pk_sales PRIMARY KEY (sale_id) RELY;
ALTER TABLE gold.sales_fact ADD CONSTRAINT fk_customer
  FOREIGN KEY (customer_id) REFERENCES gold.customer_dim(customer_id) RELY;
ALTER TABLE gold.sales_fact ADD CONSTRAINT fk_date
  FOREIGN KEY (date_key) REFERENCES gold.date_dim(date_key) RELY;
```

---

## 3. Translate Measures and Logic into Metric Definitions

Power BI measures (DAX) must be reimplemented as SQL metrics using Databricks metric views:

### Reimplement DAX as SQL

- Create SQL-based logic for each core DAX measure using Databricks' metric view YAML syntax.
- Map DAX aggregation functions to SQL equivalents:

| DAX Function | SQL Equivalent |
|---|---|
| `SUM(Sales[Amount])` | `SUM(total_amount)` |
| `COUNTROWS(Orders)` | `COUNT(1)` |
| `DISTINCTCOUNT(Customer[ID])` | `COUNT(DISTINCT customer_id)` |
| `DIVIDE(SUM(...), SUM(...))` | `SUM(...) / NULLIF(SUM(...), 0)` |
| `CALCULATE(SUM(...), Filter)` | Use metric view `filter` or filtered measure expressions |

### Centralize and Organize

- Store metric definitions in Unity Catalog metric views for discoverability and reuse.
- When applicable, use parameterized queries to enable dynamic filtering within connected BI tools.

**Best practice:** Group related metrics (e.g., revenue, margin, quantity) into a single metric view per business domain to simplify governance.

---

## 4. Define Metric Views in Databricks SQL

Leverage Databricks' metric view functionality to expose reusable, governed aggregates:

### Build the Metric View

- Reference the underlying Delta tables directly in the metric view definition.
- Include measure definitions, column metadata (comments), default filters, and optional groupings.
- For star/snowflake schemas, declare joins within the metric view YAML.

### Register in Unity Catalog

- Register the metric view in Unity Catalog.
- Assign business-friendly names, tags, and ownership to maintain discoverability and lineage.
- Grant `SELECT` privileges to appropriate users and groups.

### Example: Translating a Power BI "Total Sales" Measure

**Power BI DAX:**
```dax
Total Sales = SUM(SalesFact[TotalAmount])
Avg Order Value = DIVIDE([Total Sales], COUNTROWS(SalesFact))
Sales YoY Growth = DIVIDE([Total Sales] - CALCULATE([Total Sales], SAMEPERIODLASTYEAR(DateDim[Date])), CALCULATE([Total Sales], SAMEPERIODLASTYEAR(DateDim[Date])))
```

**Databricks Metric View (YAML):**
```sql
CREATE OR REPLACE VIEW gold.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Sales KPIs translated from Power BI semantic model"
  source: gold.sales_fact

  dimensions:
    - name: Order Date
      expr: date_key
      comment: "Date key for time-based analysis"
    - name: Customer Segment
      expr: customer_segment
      comment: "Customer classification"
    - name: Product Category
      expr: product_category
      comment: "Product grouping"

  measures:
    - name: Total Sales
      expr: SUM(total_amount)
      comment: "Equivalent to Power BI DAX: SUM(SalesFact[TotalAmount])"
    - name: Order Count
      expr: COUNT(1)
      comment: "Total number of sales transactions"
    - name: Avg Order Value
      expr: SUM(total_amount) / NULLIF(COUNT(1), 0)
      comment: "Equivalent to Power BI DAX: DIVIDE([Total Sales], COUNTROWS(SalesFact))"
    - name: Distinct Customers
      expr: COUNT(DISTINCT customer_id)
      comment: "Unique customers with purchases"

  joins:
    - name: customer_dim
      source: gold.customer_dim
      on: sales_fact.customer_id = customer_dim.customer_id
    - name: date_dim
      source: gold.date_dim
      on: sales_fact.date_key = date_dim.date_key
$$;
```

**Querying the metric view:**
```sql
SELECT
  `Order Date`,
  `Customer Segment`,
  MEASURE(`Total Sales`) AS total_sales,
  MEASURE(`Avg Order Value`) AS avg_order_value,
  MEASURE(`Distinct Customers`) AS unique_customers
FROM gold.sales_metrics
GROUP BY ALL
ORDER BY ALL;
```

The result acts like a Power BI semantic model layer -- computationally defined and reusable across analytics tools.

---

## 5. Connect Power BI to Databricks SQL Warehouse

Using guidance from the [Power BI on Databricks Best Practices Cheatsheet](https://www.databricks.com/sites/default/files/2025-04/2025-04-power-bi-on-databricks-best-practices-cheat-sheet.pdf):

### Connection Setup

- Connect Power BI via **DirectQuery** mode to your Databricks SQL Warehouse.
- Use **DirectQuery for fact tables** and **Dual mode for dimension tables** to balance performance and freshness.
- Use the Databricks connector in Power BI with `Databricks.Catalogs()` function.

### Parameterize Connections

- Create `ServerHostName` and `HTTPPath` parameters in Power Query (Type must be **Text**).
- Replace hardcoded values in M queries with parameter references for dynamic environments (Dev vs. Prod).
- Update parameters via Power BI Service UI or REST API for CI/CD pipelines.

**Power Query M formula pattern:**
```
let
    Source = Databricks.Catalogs(ServerHostName, HTTPPath,
             [Catalog=null, Database=null, EnableAutomaticProxyDiscovery=null]),
    catalog = Source{[Name=CatalogName, Kind="Database"]}[Data],
    schema = catalog{[Name="gold", Kind="Schema"]}[Data],
    metric_view = schema{[Name="sales_metrics", Kind="Table"]}[Data]
in
    metric_view
```

### Performance Settings

- Configure query parallelization settings (MaxParallelismPerQuery, max connections per data source).
- Set appropriate cache and query timeout values.
- Use the same SQL Warehouse for datasets querying the same data to maximize caching.

### Simplify Power BI

- Remove redundant calculated columns and measures now handled by metric views.
- "Move left" transformations: prefer SQL views and metric views over Power Query transformations and DAX formulas.
- Set "Assume Referential Integrity" on relationships when PK/FK constraints are declared with `RELY`.

---

## 6. Validate and Refine

### Functional Validation

- Validate that Power BI visuals return identical results as before.
- Compare DAX vs. metric view outputs side-by-side for consistency.
- Test edge cases: null handling, division by zero, date boundary conditions.

### Performance Validation

- Monitor query performance using Databricks **Query Profile** tools.
- Use Power BI **Performance Analyzer** to identify bottleneck visuals.
- Adjust caching, aggregation strategies, or SQL Warehouse sizing as needed.

### Common Pitfalls to Check

| Issue | What to Verify |
|---|---|
| Column name casing | Databricks is case-insensitive but Power BI may expect specific casing |
| Data type mismatches | Integers from some sources become decimals in Power BI |
| Relationship loss | PK/FK auto-detection may delete manually created relationships |
| Large result sets | Visuals pulling 1000s of rows indicate inefficient DAX or missing aggregations |

---

## 7. Govern and Automate

### Governance

- Manage metric versioning and ownership through **Unity Catalog** and audit logs.
- Use tags and comments on metric views for discoverability.
- Implement row-level security through Unity Catalog grants (replacing Power BI RLS where appropriate).

### Automation

- Automate metric view deployments with **CI/CD pipelines** using Databricks REST APIs, CLI, or **Databricks Asset Bundles**.
- Schedule Delta table maintenance (OPTIMIZE, VACUUM) via Databricks Jobs or predictive optimization.

### Data Contracts

- Establish a data contract process: new metrics or schema changes must go through metric view updates, not ad-hoc Power BI model edits.
- Document metric definitions, owners, and SLAs in the Unity Catalog metadata.

---

## Example Flow Summary

```
1. Extract semantic layer details from Power BI
       |
       v
2. Recreate the data model with Delta tables in Databricks
       |
       v
3. Implement equivalent metrics as SQL metric definitions
       |
       v
4. Register and expose them through metric views in Unity Catalog
       |
       v
5. Connect Power BI in DirectQuery mode to Databricks
       |
       v
6. Validate and tune
       |
       v
7. Govern, automate, and iterate
```

---

## Reference Articles

- [Adopting Power BI semantic models on Databricks SQL](https://medium.com/dbsql-sme-engineering/adopting-power-bi-semantic-models-on-databricks-sql-6efb4b0f78c9) -- Migration walkthrough with M formula examples for Snowflake, Synapse, and Hive Metastore sources.
- [Parameterizing your Databricks SQL Connections in Power BI](https://medium.com/@kyle.hale/parameterizing-your-databricks-sql-connections-in-power-bi-fd7aae20863e) -- Step-by-step guide for parameterizing ServerHostName and HTTPPath in Power Query.
- [Power BI on Databricks Best Practices Cheat Sheet](https://medium.com/dbsql-sme-engineering/introducing-the-power-bi-on-databricks-best-practices-cheatsheet-a55e0aed9575) -- One-pager covering Data Preparation, SQL Serving, Power BI Integration, and Report Design best practices.
- [Cheat Sheet PDF](https://www.databricks.com/sites/default/files/2025-04/2025-04-power-bi-on-databricks-best-practices-cheat-sheet.pdf) -- Downloadable best practices reference.
- [Unity Catalog Metric Views Documentation](https://docs.databricks.com/en/metric-views/) -- YAML syntax, joins, materialization, and MEASURE() function reference.
