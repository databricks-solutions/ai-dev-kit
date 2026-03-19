# Databricks SQL Patterns Reference

## Correct Patterns

### Table creation
```sql
CREATE OR REPLACE TABLE catalog.schema.my_table (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  name STRING NOT NULL,
  created_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
```

### Merge (upsert)
```sql
MERGE INTO catalog.schema.target AS t
USING catalog.schema.source AS s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

### Dynamic table references
```sql
SELECT * FROM IDENTIFIER(:table_name)
WHERE date_col >= :start_date;
```

### File ingestion
```sql
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/path/',
  format => 'csv',
  header => 'true'
);
```

## Anti-Patterns

### Wrong: Unqualified table name
```sql
-- BAD: missing catalog.schema
SELECT * FROM my_table;
```

### Wrong: DROP + CREATE instead of CREATE OR REPLACE
```sql
-- BAD: not atomic, loses table history
DROP TABLE IF EXISTS catalog.schema.my_table;
CREATE TABLE catalog.schema.my_table (...);
```

### Wrong: String interpolation
```sql
-- BAD: SQL injection risk
SELECT * FROM catalog.schema.orders WHERE id = '{user_input}';
```

### Wrong: Using Bash for SQL
The agent should use `mcp__databricks__execute_sql`, not:
```bash
# BAD: shell workaround
databricks sql -e "SELECT * FROM catalog.schema.my_table"
```
