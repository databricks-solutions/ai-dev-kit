# Report Analysis & Output Paths (Steps 14–15)

Steps 14 and 15 of the migration workflow: analyze sample reports and choose between PBI reconnection or Databricks-native output.

---

## Step 14: Sample Report Analysis

If `input/` contains `.docx`, `.pdf`, `.png`, `.jpg`, `.xlsx`, or `.pptx` files, analyze them to extract KPI names, formatting, chart types, narrative templates, and disclaimers. Produce `reference/report_analysis.md`.

### What to Extract

- **KPI names and values** visible in the report
- **Column formatting** (currency symbols, decimal places, date formats)
- **Chart types** (bar, line, pie, table, scorecard)
- **Narrative templates** (dynamic text patterns like "Sales increased by X% compared to...")
- **Disclaimers and footnotes**
- **Branding** (colors, logos, headers/footers)
- **Filter/slicer positions** and default values

### Output: reference/report_analysis.md

```markdown
## Report Analysis: <filename>

### KPIs Identified
| KPI | Value (as shown) | Likely Measure | Format |
|-----|------------------|----------------|--------|
| Total Revenue | $1.2M | SUM(revenue) | Currency, 1 decimal |
| Order Count | 4,521 | COUNT(1) | Integer |

### Visuals
| # | Type | Title | Dimensions | Measures |
|---|------|-------|------------|----------|
| 1 | Scorecard | Key Metrics | — | Total Revenue, Order Count |
| 2 | Line Chart | Monthly Trend | Month | Total Revenue |
| 3 | Table | Top Products | Product | Revenue, Units |

### Narrative Templates
- "Revenue for {period} was {Total Revenue}, a {YoY Change}% change from the prior year."

### Disclaimers
- "Data as of {last_refresh_date}. Excludes returns processed after close."
```

---

## Step 15: Output Path

After report analysis, choose the output path:

---

### Path A: Power BI Reconnection

Update Power Query M formulas to use `Databricks.Catalogs()`. Use DirectQuery for facts, Dual for dimensions. Parameterize `ServerHostName`/`HTTPPath`.

**Power Query M formula pattern:**

```m
let
    Source = Databricks.Catalogs(ServerHostName, HTTPPath,
             [Catalog=null, Database=null, EnableAutomaticProxyDiscovery=null]),
    catalog = Source{[Name=CatalogName, Kind="Database"]}[Data],
    schema = catalog{[Name="gold", Kind="Schema"]}[Data],
    metric_view = schema{[Name="sales_metrics", Kind="Table"]}[Data]
in
    metric_view
```

**Connection parameterization steps:**
1. Create `ServerHostName`, `HTTPPath`, and `CatalogName` parameters in Power Query (Type must be **Text**)
2. Replace hardcoded values in M queries with parameter references for dynamic environments (Dev vs. Prod)
3. Update parameters via Power BI Service UI or REST API for CI/CD pipelines

**Performance settings:**
- Set DirectQuery for fact tables, Dual for dimension tables
- Enable "Assume Referential Integrity" on relationships where PK/FK constraints are declared with `RELY`
- Configure query parallelization settings (MaxParallelismPerQuery, max connections per data source)
- Use the same SQL Warehouse for datasets querying the same data to maximize caching

**Simplify Power BI after reconnection:**
- Remove redundant calculated columns and measures now handled by metric views
- "Move left" transformations: prefer SQL views and metric views over Power Query transformations and DAX
- Set "Assume Referential Integrity" on relationships when PK/FK constraints are declared with `RELY`

---

### Path B: Databricks-Native Report

Read the `databricks-aibi-dashboards` skill. Build a report specification and email template in `planreport/`.

```bash
bash scripts/init_project.sh --report
```

**Report specification template:**

```markdown
## Report: <Report Name>

### Page 1: Executive Summary
- **Visual 1**: KPI scorecard (Total Sales, Avg Order Value, Customer Count)
- **Visual 2**: Monthly trend line (Total Sales by Month)
- **Visual 3**: Top 10 table (Products by Revenue)
- **Filters**: Date range, Region, Product Category

### Page 2: Detail View
- **Visual 1**: Table with drill-through (Order details)
- **Filters**: All from Page 1 + Customer Segment
```

**Email distribution template:**

```markdown
## Email Distribution

- **Recipients**: [list of email addresses or groups]
- **Schedule**: Weekly, Monday 8:00 AM UTC
- **Subject**: "{Report Name} - Week of {date}"
- **Body**: See narrative template from report_spec.md
- **Attachments**: PDF export of dashboard
- **Format**: HTML with inline charts
```

**Deployment configuration:**

```yaml
report_name: "Sales Weekly Report"
warehouse_id: "<sql_warehouse_id>"
schedule:
  quartz_cron: "0 0 8 ? * MON"
  timezone: "UTC"
notifications:
  on_success:
    - email: "team@company.com"
  on_failure:
    - email: "admin@company.com"
```

**planreport/ folder structure:**

```
planreport/
├── report_spec.md          # Visual layout, chart specs, narrative blocks
├── email_template.md       # Recipients, schedule, subject, body template
└── deployment_config.yml   # Job schedule, warehouse, notification targets
```

Use the `databricks-jobs` skill to schedule delivery.

---

## Validation After Migration (both paths)

### Functional Validation
- Validate that Power BI visuals return identical results as before (Path A), or that Databricks dashboards match original report values (Path B)
- Compare DAX vs. metric view outputs side-by-side for consistency
- Test edge cases: null handling, division by zero, date boundary conditions

### Performance Validation
- Monitor query performance using Databricks **Query Profile** tools
- Use Power BI **Performance Analyzer** to identify bottleneck visuals (Path A)
- Adjust caching, aggregation strategies, or SQL Warehouse sizing as needed

### Common Pitfalls

| Issue | What to Verify |
|-------|----------------|
| Column name casing | Databricks is case-insensitive but Power BI may expect specific casing |
| Data type mismatches | Integers from some sources become decimals in Power BI |
| Relationship loss | PK/FK auto-detection may delete manually created relationships |
| Large result sets | Visuals pulling 1000s of rows indicate inefficient DAX or missing aggregations |
