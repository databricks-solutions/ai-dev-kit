# AI/BI Dashboards

Create AI/BI dashboards on Databricks with validated SQL queries and structured JSON deployment.

## Overview

This skill guides the creation of Databricks AI/BI dashboards (formerly Lakeview dashboards) through a strict validation workflow: test every SQL query before deployment, build compliant dashboard JSON, and deploy via MCP tools. It activates when users need to build interactive dashboards with counters, charts, tables, and filters on top of Unity Catalog data. The skill enforces best practices around widget versioning, layout grids, field name matching, and cardinality limits to prevent common "invalid widget" errors.

## What's Included

```
aibi-dashboards/
└── SKILL.md
```

## Key Topics

- Mandatory query validation workflow (test all SQL via `execute_sql` before deploying)
- Dataset architecture with one dataset per domain and fully-qualified table names
- Widget field expression matching rules (query field `name` must equal encoding `fieldName`)
- Widget specifications for counters (v2), tables (v2), bar/line/pie charts (v3), and text headers
- 6-column grid layout system with no-gap positioning
- Global filters vs. page-level filters using `PAGE_TYPE_GLOBAL_FILTERS` and `PAGE_TYPE_CANVAS`
- Filter widget types: `filter-multi-select`, `filter-single-select`, `filter-date-range-picker`
- Cardinality and readability guidelines for chart dimensions
- Spark SQL date patterns (avoiding INTERVAL syntax)
- Troubleshooting common errors: field mismatches, invalid widget definitions, empty widgets, layout gaps

## When to Use

- Building a new AI/BI dashboard on Databricks
- Creating KPI counters, bar charts, line charts, pie charts, or data tables
- Adding global or page-level filters to dashboards
- Debugging "invalid widget definition" or "no selected fields to visualize" errors
- Deploying dashboard JSON via `create_or_update_dashboard` MCP tool
- Working with Lakeview dashboard specifications

## Related Skills

- [Databricks Unity Catalog](../databricks-unity-catalog/) -- for querying the underlying data and system tables
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- for building the data pipelines that feed dashboards
- [Databricks Jobs](../databricks-jobs/) -- for scheduling dashboard data refreshes

## Resources

- [AI/BI Dashboards Documentation](https://docs.databricks.com/en/dashboards/index.html)
- [Lakeview Dashboard API](https://docs.databricks.com/api/workspace/lakeview)
