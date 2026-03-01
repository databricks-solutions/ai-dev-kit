# Deployment Checklist (Step 16)

Step 16 of the migration workflow: generate the ordered deployment checklist from local artifacts to a running, scheduled report.

Output: `reference/deployment_checklist.md`

---

## Checklist Template

```markdown
## Deployment Checklist: <Project Name>

**Project**: <description>
**Date**: <YYYY-MM-DD>
**Path**: A (PBI Reconnection) | B (Databricks-Native Report)

### Pre-Deployment
- [ ] Validate catalog access:
  ```sql
  SELECT 1 FROM <catalog>.<schema>.<table> LIMIT 1;
  ```
- [ ] Verify all source tables exist and are accessible
- [ ] Confirm SQL warehouse is running and sized appropriately
- [ ] Verify user/group has SELECT on all required tables and metric views

### Metric View Deployment
- [ ] Deploy metric views: run each SQL file in models/metric_views/
- [ ] Verify metric views:
  ```sql
  SELECT MEASURE(`<measure_name>`) FROM <catalog>.<schema>.<view_name> LIMIT 10;
  ```
- [ ] Grant SELECT to required users/groups:
  ```sql
  GRANT SELECT ON VIEW <catalog>.<schema>.<view_name> TO `<group>`;
  ```

### Path A: Power BI Reconnection
- [ ] Create parameters: `ServerHostName`, `HTTPPath`, `CatalogName` (Type: Text)
- [ ] Update Power Query M formulas to use `Databricks.Catalogs()` connector
- [ ] Set DirectQuery for fact tables, Dual for dimension tables
- [ ] Enable "Assume Referential Integrity" on all relationships with RELY constraints
- [ ] Test: verify key KPI values match original report
- [ ] Publish to Power BI Service
- [ ] Update stored credentials in Power BI Service

### Path B: Databricks-Native Report
- [ ] Create AI/BI dashboard from planreport/report_spec.md
  (read `databricks-aibi-dashboards` skill)
- [ ] Configure job schedule from planreport/deployment_config.yml
  (read `databricks-jobs` skill)
- [ ] Set up email distribution from planreport/email_template.md
- [ ] Test dashboard rendering and data accuracy

### Post-Deployment
- [ ] Run validation queries against metric views
- [ ] Compare output values with original PBI report (5+ key KPIs)
- [ ] Monitor query performance for 1 week
- [ ] Document any known gaps or deferred items in reference/validation_notes.md
- [ ] Share deployment summary with stakeholders
```

---

## Example: Completed Checklist (Path A)

```markdown
## Deployment Checklist: Sales Analytics Migration

**Project**: Sales PBI to Databricks
**Date**: 2026-03-03
**Path**: A (PBI Reconnection)

### Pre-Deployment
- [ ] Validate catalog access:
  ```sql
  SELECT 1 FROM analytics_catalog.gold.sales_fact LIMIT 1;
  SELECT 1 FROM analytics_catalog.gold.customer_dim LIMIT 1;
  SELECT 1 FROM analytics_catalog.gold.date_dim LIMIT 1;
  ```
- [ ] Verify SQL warehouse `analytics-wh` is running
- [ ] Confirm user has SELECT on `analytics_catalog.gold`

### Metric View Deployment
- [ ] Run `models/metric_views/sales_metrics.sql`
- [ ] Run `models/metric_views/customer_metrics.sql`
- [ ] Verify:
  ```sql
  SELECT MEASURE(`Total Sales`) FROM analytics_catalog.gold.sales_metrics LIMIT 10;
  SELECT MEASURE(`Customer Count`) FROM analytics_catalog.gold.customer_metrics LIMIT 10;
  ```
- [ ] Grant SELECT to `analysts` group:
  ```sql
  GRANT SELECT ON VIEW analytics_catalog.gold.sales_metrics TO `analysts`;
  ```

### Power BI Reconnection
- [ ] Create parameters: `ServerHostName`, `HTTPPath`, `CatalogName`
- [ ] Update M queries to use `Databricks.Catalogs()` connector
- [ ] Set SalesFact to DirectQuery, CustomerDim/DateDim to Dual
- [ ] Enable "Assume Referential Integrity" on all relationships
- [ ] Test: verify Total Sales matches original report value
- [ ] Publish to Power BI Service
- [ ] Update stored credentials in Power BI Service

### Post-Deployment
- [ ] Compare 5 key KPI values between old and new reports
- [ ] Monitor query performance for 1 week
- [ ] Document any discrepancies in reference/validation_notes.md
- [ ] Share deployment summary with stakeholders
```

---

## Governance and Automation

### Governance
- Manage metric versioning and ownership through **Unity Catalog** and audit logs
- Use tags and comments on metric views for discoverability
- Implement row-level security through Unity Catalog grants (replacing Power BI RLS where appropriate)

### Automation
- Automate metric view deployments with **CI/CD pipelines** using Databricks REST APIs, CLI, or **Databricks Asset Bundles** (read `databricks-asset-bundles` skill)
- Schedule Delta table maintenance (OPTIMIZE, VACUUM) via Databricks Jobs or predictive optimization

### Data Contracts
- Establish a data contract process: new metrics or schema changes must go through metric view updates, not ad-hoc Power BI model edits
- Document metric definitions, owners, and SLAs in the Unity Catalog metadata
