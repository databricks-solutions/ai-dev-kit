---
name: sql-correctness
description: >
  SQL evaluation criteria for Databricks. Load when the trace contains
  execute_sql tool calls or SQL code in responses. Covers syntax validity,
  Unity Catalog patterns, and Databricks-specific SQL features.
metadata:
  category: evaluation
  version: "1.0"
  applies_to: [sql]
---

## SQL Correctness Rubric

When evaluating SQL in agent traces, check these dimensions:

### 1. Unity Catalog Namespace
- Must use 3-level namespace: `catalog.schema.table`
- Never use unqualified table names
- Catalog/schema should match the user's context (not hardcoded `main.default` unless appropriate)

### 2. Modern DDL Syntax
- Use `CREATE OR REPLACE` instead of `DROP IF EXISTS` + `CREATE`
- Use `ALTER TABLE ... SET TBLPROPERTIES` for table properties
- Use `COMMENT ON` for documentation

### 3. Tool Selection
- Must use `mcp__databricks__execute_sql` for SQL execution
- Must NOT use `Bash` with `databricks sql` CLI as a workaround
- Must NOT use notebook execution for simple queries

### 4. Databricks SQL Features
- Use Delta-specific syntax where appropriate (MERGE INTO, OPTIMIZE, VACUUM)
- Use `IDENTIFIER()` function for dynamic table references
- Use `SELECT * FROM read_files()` for file ingestion, not COPY INTO (unless streaming)

### 5. Syntax Validity
- SQL must be syntactically valid for Databricks SQL (Spark SQL dialect)
- String literals use single quotes, identifiers use backticks if needed
- Semicolons at statement boundaries

### 6. Safety
- No string interpolation for user-provided values in SQL
- Use parameterized queries where applicable
- No `DROP` operations unless explicitly requested

See [detailed patterns](references/DATABRICKS_SQL_PATTERNS.md) for specific syntax examples.
