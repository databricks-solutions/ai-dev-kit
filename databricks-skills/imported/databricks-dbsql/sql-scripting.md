# SQL Scripting, Stored Procedures, Recursive CTEs, and Transactions

> Databricks SQL procedural extensions based on the SQL/PSM standard. Covers SQL scripting (compound statements, control flow, exception handling), stored procedures, recursive CTEs, and multi-statement transactions.

---

## Table of Contents

- [SQL Scripting](#sql-scripting)
  - [Compound Statements (BEGIN...END)](#compound-statements-beginend)
  - [Variable Declaration (DECLARE)](#variable-declaration-declare)
  - [Variable Assignment (SET)](#variable-assignment-set)
  - [Control Flow](#control-flow)
    - [IF / ELSEIF / ELSE](#if--elseif--else)
    - [CASE Statement](#case-statement)
    - [WHILE Loop](#while-loop)
    - [FOR Loop](#for-loop)
    - [LOOP Statement](#loop-statement)
    - [REPEAT Statement](#repeat-statement)
    - [LEAVE and ITERATE](#leave-and-iterate)
  - [Exception Handling](#exception-handling)
    - [Condition Declaration](#condition-declaration)
    - [Handler Declaration](#handler-declaration)
    - [SIGNAL and RESIGNAL](#signal-and-resignal)
  - [EXECUTE IMMEDIATE (Dynamic SQL)](#execute-immediate-dynamic-sql)
- [Stored Procedures](#stored-procedures)
  - [CREATE PROCEDURE](#create-procedure)
  - [CALL (Invoke a Procedure)](#call-invoke-a-procedure)
  - [DROP PROCEDURE](#drop-procedure)
  - [DESCRIBE PROCEDURE](#describe-procedure)
  - [SHOW PROCEDURES](#show-procedures)
- [Recursive CTEs](#recursive-ctes)
  - [WITH RECURSIVE Syntax](#with-recursive-syntax)
  - [Anchor and Recursive Members](#anchor-and-recursive-members)
  - [MAX RECURSION LEVEL](#max-recursion-level)
  - [Use Cases and Examples](#use-cases-and-examples)
  - [Limitations](#limitations)
- [Multi-Statement Transactions](#multi-statement-transactions)
  - [Overview and Current Status](#overview-and-current-status)
  - [SQL Scripting Atomic Blocks](#sql-scripting-atomic-blocks)
  - [Python Connector Transaction API](#python-connector-transaction-api)
  - [Isolation Levels](#isolation-levels)
  - [Write Conflicts and Concurrency](#write-conflicts-and-concurrency)
  - [Best Practices](#best-practices)

---

## SQL Scripting

**Availability**: Databricks Runtime 16.3+ and Databricks SQL

SQL scripting enables procedural logic using the SQL/PSM standard. Every SQL script starts with a compound statement block (`BEGIN...END`).

### Compound Statements (BEGIN...END)

A compound statement is the fundamental building block containing variable declarations, condition/handler declarations, and executable statements.

**Syntax**:

```sql
[ label : ] BEGIN
  [ { declare_variable | declare_condition } ; [...] ]
  [ declare_handler ; [...] ]
  [ SQL_statement ; [...] ]
END [ label ]
```

**Key rules**:

- Declarations must appear before executable statements
- Variable declarations come before condition declarations, which come before handler declarations
- Top-level compound statements cannot specify labels
- `NOT ATOMIC` is the default and only behavior (no automatic rollback on failure)
- In notebooks, the compound statement must be the sole statement in the cell

**Supported statement types in body**:

| Category | Statements |
|----------|-----------|
| DDL | ALTER, CREATE, DROP |
| DCL | GRANT, REVOKE |
| DML | INSERT, UPDATE, DELETE, MERGE |
| Query | SELECT |
| Assignment | SET |
| Dynamic SQL | EXECUTE IMMEDIATE |
| Control flow | IF, CASE, WHILE, FOR, LOOP, REPEAT, LEAVE, ITERATE |
| Nesting | Nested BEGIN...END blocks |

**Minimal example**:

```sql
BEGIN
  SELECT 'Hello, SQL Scripting!';
END;
```

### Variable Declaration (DECLARE)

**Syntax**:

```sql
DECLARE variable_name [, ...] data_type [ DEFAULT default_expr ];
```

- Variables initialize to `NULL` if no `DEFAULT` is specified
- Data type can be omitted when `DEFAULT` is provided (type inferred from expression)
- Multiple variable names in a single `DECLARE` supported in Runtime 17.2+
- Variables are scoped to their enclosing compound statement
- Variable names resolve from the innermost scope outward; use labels to disambiguate

**Examples**:

```sql
BEGIN
  DECLARE counter INT DEFAULT 0;
  DECLARE name STRING DEFAULT 'unknown';
  DECLARE x, y, z DOUBLE DEFAULT 0.0;        -- Runtime 17.2+
  DECLARE inferred DEFAULT current_date();    -- type inferred as DATE

  SET counter = counter + 1;
  VALUES (counter, name);
END;
```

### Variable Assignment (SET)

**Syntax**:

```sql
SET variable_name = expression;
SET VAR variable_name = expression;          -- explicit local variable
SET (var1, var2, ...) = (expr1, expr2, ...); -- multi-assignment
```

Use `SET VAR` to explicitly target a local variable when a session variable with the same name exists.

**Example**:

```sql
BEGIN
  DECLARE total INT DEFAULT 0;
  DECLARE label STRING;
  SET total = 100;
  SET label = 'final';
  VALUES (total, label);
END;
```

### Control Flow

#### IF / ELSEIF / ELSE

Executes statements based on the first condition evaluating to `TRUE`.

**Syntax**:

```sql
IF condition THEN
  { stmt ; } [...]
[ ELSEIF condition THEN
  { stmt ; } [...] ] [...]
[ ELSE
  { stmt ; } [...] ]
END IF;
```

**Example**:

```sql
BEGIN
  DECLARE score INT DEFAULT 85;
  DECLARE grade STRING;

  IF score >= 90 THEN
    SET grade = 'A';
  ELSEIF score >= 80 THEN
    SET grade = 'B';
  ELSEIF score >= 70 THEN
    SET grade = 'C';
  ELSE
    SET grade = 'F';
  END IF;

  VALUES (grade);  -- Returns 'B'
END;
```

#### CASE Statement

Two forms: **simple CASE** (compare expression) and **searched CASE** (evaluate boolean conditions).

**Simple CASE syntax**:

```sql
CASE expr
  WHEN opt1 THEN { stmt ; } [...]
  WHEN opt2 THEN { stmt ; } [...]
  [ ELSE { stmt ; } [...] ]
END CASE;
```

**Searched CASE syntax**:

```sql
CASE
  WHEN cond1 THEN { stmt ; } [...]
  WHEN cond2 THEN { stmt ; } [...]
  [ ELSE { stmt ; } [...] ]
END CASE;
```

Only the first matching branch executes.

**Example**:

```sql
BEGIN
  DECLARE status STRING DEFAULT 'active';

  CASE status
    WHEN 'active'   THEN VALUES ('Processing');
    WHEN 'paused'   THEN VALUES ('On hold');
    WHEN 'archived' THEN VALUES ('Read-only');
    ELSE VALUES ('Unknown status');
  END CASE;
END;
```

#### WHILE Loop

Repeats while a condition is `TRUE`.

**Syntax**:

```sql
[ label : ] WHILE condition DO
  { stmt ; } [...]
END WHILE [ label ];
```

**Example** -- sum odd numbers from 1 to 10:

```sql
BEGIN
  DECLARE total INT DEFAULT 0;
  DECLARE i INT DEFAULT 0;

  sum_odds: WHILE i < 10 DO
    SET i = i + 1;
    IF i % 2 = 0 THEN
      ITERATE sum_odds;   -- skip even numbers
    END IF;
    SET total = total + i;
  END WHILE sum_odds;

  VALUES (total);  -- Returns 25
END;
```

#### FOR Loop

Iterates over query result rows.

**Syntax**:

```sql
[ label : ] FOR [ variable_name AS ] query DO
  { stmt ; } [...]
END FOR [ label ];
```

- Use `variable_name` (not the label) to qualify column references from the cursor
- For Delta tables, modifying the source during iteration does not affect cursor results
- Loop may not fully execute the query if terminated early by `LEAVE` or an error

**Example** -- process each row from a query:

```sql
BEGIN
  DECLARE total_revenue DOUBLE DEFAULT 0.0;

  process_orders: FOR row AS
    SELECT order_id, amount FROM orders WHERE status = 'completed'
  DO
    SET total_revenue = total_revenue + row.amount;
    IF total_revenue > 1000000 THEN
      LEAVE process_orders;
    END IF;
  END FOR process_orders;

  VALUES (total_revenue);
END;
```

#### LOOP Statement

Unconditional loop; must use `LEAVE` to exit.

**Syntax**:

```sql
[ label : ] LOOP
  { stmt ; } [...]
END LOOP [ label ];
```

**Example**:

```sql
BEGIN
  DECLARE counter INT DEFAULT 0;

  count_up: LOOP
    SET counter = counter + 1;
    IF counter >= 5 THEN
      LEAVE count_up;
    END IF;
  END LOOP count_up;

  VALUES (counter);  -- Returns 5
END;
```

#### REPEAT Statement

Executes at least once, then repeats until condition is `TRUE`.

**Syntax**:

```sql
[ label : ] REPEAT
  { stmt ; } [...]
  UNTIL condition
END REPEAT [ label ];
```

**Example**:

```sql
BEGIN
  DECLARE total INT DEFAULT 0;
  DECLARE i INT DEFAULT 0;

  sum_loop: REPEAT
    SET i = i + 1;
    IF i % 2 != 0 THEN
      SET total = total + i;
    END IF;
    UNTIL i >= 10
  END REPEAT sum_loop;

  VALUES (total);  -- Returns 25
END;
```

#### LEAVE and ITERATE

| Statement | Purpose | Equivalent |
|-----------|---------|-----------|
| `LEAVE label` | Exit the labeled loop or compound block | `BREAK` in other languages |
| `ITERATE label` | Skip to the next iteration of the labeled loop | `CONTINUE` in other languages |

Both require a labeled loop to target.

### Exception Handling

#### Condition Declaration

Define named conditions for specific SQLSTATE codes.

**Syntax**:

```sql
DECLARE condition_name CONDITION [ FOR SQLSTATE [ VALUE ] sqlstate ];
```

- `sqlstate` is a 5-character alphanumeric string (A-Z, 0-9, case-insensitive)
- Cannot start with `'00'`, `'01'`, or `'XX'`
- Defaults to `'45000'` if not specified

**Example**:

```sql
BEGIN
  DECLARE divide_by_zero CONDITION FOR SQLSTATE '22012';
  -- Use in handler declarations below
END;
```

#### Handler Declaration

Catch and handle exceptions within compound statements.

**Syntax**:

```sql
DECLARE handler_type HANDLER FOR condition_value [, ...] handler_action;
```

| Parameter | Options | Description |
|-----------|---------|-------------|
| `handler_type` | `EXIT` | Exits the enclosing compound after handling |
| `condition_value` | `SQLSTATE 'xxxxx'`, `condition_name`, `SQLEXCEPTION`, `NOT FOUND` | What to catch |
| `handler_action` | Single statement or nested `BEGIN...END` | What to execute |

- `SQLEXCEPTION` catches all error states (SQLSTATE class not `'00'` or `'01'`)
- `NOT FOUND` catches `'02xxx'` states (no data found)
- A handler cannot apply to statements in its own body

**Example** -- catch division by zero:

```sql
BEGIN
  DECLARE result DOUBLE;
  DECLARE EXIT HANDLER FOR SQLSTATE '22012'
    BEGIN
      SET result = -1;
    END;

  SET result = 10 / 0;  -- triggers handler
  VALUES (result);       -- Returns -1
END;
```

**Example** -- generic exception handler:

```sql
BEGIN
  DECLARE error_msg STRING DEFAULT 'none';

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
      SET error_msg = 'An error occurred';
      INSERT INTO error_log (message, ts) VALUES (error_msg, current_timestamp());
    END;

  -- statements that might fail
  INSERT INTO target_table SELECT * FROM source_table;
END;
```

#### SIGNAL and RESIGNAL

Raise or re-raise exceptions.

**SIGNAL syntax**:

```sql
SIGNAL condition_name
  [ SET { MESSAGE_ARGUMENTS = argument_map | MESSAGE_TEXT = message_str } ];

SIGNAL SQLSTATE [ VALUE ] sqlstate
  [ SET MESSAGE_TEXT = message_str ];
```

**RESIGNAL syntax** (use in handlers to preserve diagnostic stack):

```sql
RESIGNAL [ condition_name | SQLSTATE [ VALUE ] sqlstate ]
  [ SET { MESSAGE_ARGUMENTS = argument_map | MESSAGE_TEXT = message_str } ];
```

- Prefer `RESIGNAL` over `SIGNAL` inside handlers -- `RESIGNAL` preserves the diagnostic stack while `SIGNAL` clears it
- `MESSAGE_ARGUMENTS` takes a `MAP<STRING, STRING>` literal

**Example** -- validate input and raise custom error:

```sql
BEGIN
  DECLARE input_value INT DEFAULT 150;

  IF input_value > 100 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Input value must be <= 100';
  END IF;

  VALUES (input_value);
END;
```

**Example** -- using named conditions with MESSAGE_ARGUMENTS:

```sql
BEGIN
  DECLARE input INT DEFAULT 5;
  DECLARE arg_map MAP<STRING, STRING>;

  IF input > 4 THEN
    SET arg_map = map('errorMessage', 'Input must be <= 4.');
    SIGNAL USER_RAISED_EXCEPTION
      SET MESSAGE_ARGUMENTS = arg_map;
  END IF;
END;
```

### EXECUTE IMMEDIATE (Dynamic SQL)

Execute SQL statements constructed as strings at runtime.

**Availability**: Runtime 14.3+; expression-based `sql_string` and nested execution from Runtime 17.3+.

**Syntax**:

```sql
EXECUTE IMMEDIATE sql_string
  [ INTO var_name [, ...] ]
  [ USING { arg_expr [ AS ] [ alias ] } [, ...] ];
```

- `sql_string`: a constant expression producing a well-formed SQL statement
- `INTO`: captures a single-row result into variables (returns `NULL` for zero rows; errors for multiple rows)
- `USING`: binds values to positional (`?`) or named (`:param`) parameter markers (cannot mix styles)

**Examples**:

```sql
-- Positional parameters
EXECUTE IMMEDIATE 'SELECT SUM(c1) FROM VALUES(?), (?) AS t(c1)' USING 5, 6;

-- Named parameters with INTO
BEGIN
  DECLARE total INT;
  EXECUTE IMMEDIATE 'SELECT SUM(c1) FROM VALUES(:a), (:b) AS t(c1)'
    INTO total USING (5 AS a, 6 AS b);
  VALUES (total);  -- Returns 11
END;

-- Dynamic table operations
BEGIN
  DECLARE table_name STRING DEFAULT 'my_catalog.my_schema.staging';
  EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || table_name;
  EXECUTE IMMEDIATE 'INSERT INTO ' || table_name || ' SELECT * FROM source';
END;
```

---

## Stored Procedures

**Availability**: Public Preview -- Databricks Runtime 17.0+

Stored procedures persist SQL scripts in Unity Catalog and are invoked with `CALL`.

### CREATE PROCEDURE

**Syntax**:

```sql
CREATE [ OR REPLACE ] PROCEDURE [ IF NOT EXISTS ]
    procedure_name ( [ parameter [, ...] ] )
    characteristic [...]
    AS compound_statement
```

**Parameter definition**:

```sql
[ IN | OUT | INOUT ] parameter_name data_type
  [ DEFAULT default_expression ]
  [ COMMENT parameter_comment ]
```

| Parameter mode | Behavior |
|---------------|----------|
| `IN` (default) | Input-only; value passed into the procedure |
| `OUT` | Output-only; initialized to `NULL`; final value returned on success |
| `INOUT` | Input and output; accepts a value and returns the modified value on success |

**Required characteristics**:

| Characteristic | Description |
|---------------|-------------|
| `LANGUAGE SQL` | Specifies the implementation language |
| `SQL SECURITY INVOKER` | Executes under the invoker's authority |

**Optional characteristics**:

| Characteristic | Description |
|---------------|-------------|
| `NOT DETERMINISTIC` | Procedure may return different results with identical inputs |
| `MODIFIES SQL DATA` | Procedure modifies SQL data |
| `COMMENT 'description'` | Human-readable description |
| `DEFAULT COLLATION UTF8_BINARY` | Required when schema uses non-UTF8_BINARY collation (Runtime 17.1+) |

**Rules**:

- `OR REPLACE` and `IF NOT EXISTS` cannot be combined
- Parameter names must be unique within the procedure
- `DEFAULT` is not supported for `OUT` parameters
- Once a parameter has a `DEFAULT`, all subsequent parameters must also have defaults
- Default expressions cannot reference other parameters or contain subqueries
- Body is validated syntactically at creation but semantically only at invocation

**Example** -- ETL procedure with output parameters:

```sql
CREATE OR REPLACE PROCEDURE run_daily_etl(
    IN source_schema STRING,
    IN target_schema STRING,
    OUT rows_processed INT,
    OUT status STRING DEFAULT 'pending'
)
LANGUAGE SQL
SQL SECURITY INVOKER
COMMENT 'Daily ETL pipeline for order processing'
AS BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
      SET status = 'failed';
      SET rows_processed = 0;
    END;

  -- Truncate and reload
  EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || target_schema || '.orders_daily';

  EXECUTE IMMEDIATE
    'INSERT INTO ' || target_schema || '.orders_daily '
    || 'SELECT * FROM ' || source_schema || '.orders '
    || 'WHERE order_date = current_date()';

  EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM ' || target_schema || '.orders_daily'
    INTO rows_processed;

  SET status = 'success';
END;
```

### CALL (Invoke a Procedure)

**Syntax**:

```sql
CALL procedure_name( [ argument [, ...] ] );
CALL procedure_name( [ named_param => argument ] [, ...] );
```

**Rules**:

- Supports up to 64 levels of nesting
- For `IN` parameters: any expression castable to the parameter type, or `DEFAULT`
- For `OUT`/`INOUT` parameters: must be a session variable or local variable
- Arguments must match the data type of the parameter (use typed literals, e.g., `DATE'2025-01-01'`)
- Fewer arguments allowed if remaining parameters have `DEFAULT` values
- Not supported via ODBC

**Example**:

```sql
-- Positional invocation
DECLARE rows_out INT;
DECLARE status_out STRING;
CALL run_daily_etl('raw', 'silver', rows_out, status_out);
SELECT rows_out, status_out;

-- Named parameter invocation
CALL run_daily_etl(
  target_schema => 'silver',
  source_schema => 'raw',
  rows_processed => rows_out,
  status => status_out
);
```

### DROP PROCEDURE

**Syntax**:

```sql
DROP PROCEDURE [ IF EXISTS ] procedure_name;
```

- Without `IF EXISTS`, dropping a non-existent procedure raises `ROUTINE_NOT_FOUND`
- Requires `MANAGE` privilege, ownership of the procedure, or ownership of the containing schema/catalog/metastore

**Example**:

```sql
DROP PROCEDURE IF EXISTS run_daily_etl;
```

### DESCRIBE PROCEDURE

**Syntax**:

```sql
{ DESC | DESCRIBE } PROCEDURE [ EXTENDED ] procedure_name;
```

- Basic: returns procedure name and parameter list
- `EXTENDED`: additionally returns owner, creation time, body, language, security type, determinism, data access, and configuration

**Example**:

```sql
DESCRIBE PROCEDURE EXTENDED run_daily_etl;
```

### SHOW PROCEDURES

**Syntax**:

```sql
SHOW PROCEDURES [ { FROM | IN } schema_name ];
```

Returns columns: `catalog`, `namespace`, `schema`, `procedure_name`.

**Example**:

```sql
SHOW PROCEDURES IN my_catalog.my_schema;
```

---

## Recursive CTEs

**Availability**: Databricks Runtime 17.0+ and DBSQL 2025.20+

Recursive CTEs enable self-referential queries for hierarchical data, graph traversal, and series generation.

### WITH RECURSIVE Syntax

```sql
WITH RECURSIVE cte_name [ ( column_name [, ...] ) ]
  [ MAX RECURSION LEVEL max_level ] AS (
    base_case_query
    UNION ALL
    recursive_query
  )
SELECT ... FROM cte_name;
```

### Anchor and Recursive Members

| Component | Description |
|-----------|-------------|
| **Anchor (base case)** | Initial query providing seed rows; must NOT reference the CTE name |
| **Recursive member** | References the CTE name; processes rows from the previous iteration |
| **UNION ALL** | Combines anchor and recursive results (required) |

The recursive member reads rows produced by the previous iteration and generates new rows. Recursion terminates when the recursive member produces zero rows.

### MAX RECURSION LEVEL

```sql
WITH RECURSIVE cte_name MAX RECURSION LEVEL 200 AS (...)
```

| Setting | Default | Description |
|---------|---------|-------------|
| Max recursion depth | 100 | Exceeding raises `RECURSION_LEVEL_LIMIT_EXCEEDED` |
| Max result rows | 1,000,000 | Exceeding raises an error |
| `LIMIT ALL` | N/A | Suspends the row limit (Runtime 17.2+) |

### Use Cases and Examples

**Generate a number series**:

```sql
WITH RECURSIVE numbers(n) AS (
  VALUES (1)
  UNION ALL
  SELECT n + 1 FROM numbers WHERE n < 100
)
SELECT * FROM numbers;
```

**Organizational hierarchy traversal**:

```sql
WITH RECURSIVE org_tree AS (
  -- Anchor: start from the CEO
  SELECT employee_id, name, manager_id, name AS root_name, 0 AS depth
  FROM employees
  WHERE manager_id IS NULL

  UNION ALL

  -- Recursive: find direct reports
  SELECT e.employee_id, e.name, e.manager_id, t.root_name, t.depth + 1
  FROM employees e
  JOIN org_tree t ON e.manager_id = t.employee_id
)
SELECT * FROM org_tree ORDER BY depth, name;
```

**Graph traversal with cycle detection**:

```sql
WITH RECURSIVE search_graph(f, t, label, path, cycle) AS (
  -- Anchor: all edges as starting paths
  SELECT *, array(struct(g.f, g.t)), false
  FROM graph g

  UNION ALL

  -- Recursive: extend paths, detect cycles
  SELECT g.f, g.t, g.label,
         sg.path || array(struct(g.f, g.t)),
         array_contains(sg.path, struct(g.f, g.t))
  FROM graph g
  JOIN search_graph sg ON g.f = sg.t
  WHERE NOT sg.cycle
)
SELECT * FROM search_graph WHERE NOT cycle;
```

**String accumulation**:

```sql
WITH RECURSIVE r(col) AS (
  SELECT 'a'
  UNION ALL
  SELECT col || char(ascii(substr(col, -1)) + 1)
  FROM r
  WHERE length(col) < 10
)
SELECT * FROM r;
-- a, ab, abc, abcd, ..., abcdefghij
```

**Bill of Materials (BOM) explosion**:

```sql
WITH RECURSIVE bom AS (
  -- Anchor: top-level product
  SELECT part_id, component_id, quantity, 1 AS level
  FROM bill_of_materials
  WHERE part_id = 'PROD-001'

  UNION ALL

  -- Recursive: sub-components
  SELECT b.part_id, b.component_id, b.quantity * bom.quantity, bom.level + 1
  FROM bill_of_materials b
  JOIN bom ON b.part_id = bom.component_id
)
SELECT component_id, SUM(quantity) AS total_quantity, MAX(level) AS max_depth
FROM bom
GROUP BY component_id
ORDER BY total_quantity DESC;
```

### Limitations

- Not supported in UPDATE, DELETE, or MERGE statements
- Step (recursive) queries cannot include correlated column references to the CTE name
- Random number generators may produce identical values across iterations
- Default row limit of 1,000,000 rows (use `LIMIT ALL` in Runtime 17.2+ to override)
- Default recursion depth of 100 (override with `MAX RECURSION LEVEL`)

---

## Multi-Statement Transactions

### Overview and Current Status

Multi-statement transactions (MST) allow grouping multiple SQL statements into atomic units that either succeed completely or fail completely.

| Feature | Status | Notes |
|---------|--------|-------|
| Single-table transactions | GA | Delta Lake default; every DML statement is atomic |
| Multi-statement transactions (SQL scripting) | Preview | `BEGIN ATOMIC...END` blocks |
| Multi-statement transactions (Python connector) | Preview | `connection.autocommit = False` pattern |
| Cross-table transactions | Preview | Atomic updates across multiple Delta tables |

### SQL Scripting Atomic Blocks

Use `BEGIN ATOMIC...END` to execute multiple statements as a single atomic unit:

```sql
BEGIN ATOMIC
  INSERT INTO customers (id, name) VALUES (1, 'Alice');
  INSERT INTO orders (id, customer_id, amount) VALUES (1, 1, 250.00);
  INSERT INTO audit_log (action, ts) VALUES ('new_customer_order', current_timestamp());
END;
```

If any statement fails, all changes are rolled back.

> **Note:** Tables used in `BEGIN ATOMIC` blocks must have the `catalogManaged` table feature enabled. Create tables with `TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported')`. Existing tables cannot be upgraded in place — they must be recreated with this property.

### Python Connector Transaction API

The Databricks SQL Connector for Python provides explicit transaction control:

```python
from databricks import sql

connection = sql.connect(
    server_hostname="...",
    http_path="...",
    access_token="..."
)

# Disable autocommit to start explicit transactions
connection.autocommit = False
cursor = connection.cursor()

try:
    cursor.execute("INSERT INTO customers VALUES (1, 'Alice')")
    cursor.execute("INSERT INTO orders VALUES (1, 1, 100.00)")
    cursor.execute("INSERT INTO shipments VALUES (1, 1, 'pending')")
    connection.commit()    # All three succeed atomically
except Exception:
    connection.rollback()  # All three discarded
finally:
    connection.autocommit = True
```

**Key API methods**:

| Method | Description |
|--------|-------------|
| `connection.autocommit = False` | Start explicit transaction mode |
| `connection.commit()` | Commit the current transaction |
| `connection.rollback()` | Discard all changes in the current transaction |
| `connection.get_transaction_isolation()` | Returns current isolation level |
| `connection.set_transaction_isolation(level)` | Sets isolation level |

**Error handling**:

- `sql.TransactionError` raised when committing without an active transaction
- Cannot change `autocommit` while a transaction is active
- `rollback()` is a safe no-op when no transaction is active

### Isolation Levels

Databricks uses **Snapshot Isolation** (mapped to `REPEATABLE_READ` in standard SQL terminology).

| Level | Description | Default |
|-------|-------------|---------|
| `WriteSerializable` | Only writes are serializable; concurrent writes may reorder | Yes (table default) |
| `Serializable` | Both reads and writes are serializable; strictest isolation | No |
| `REPEATABLE_READ` | Snapshot isolation for connector-level transactions | Connector default |

**Setting isolation at table level**:

```sql
ALTER TABLE my_table
SET TBLPROPERTIES ('delta.isolationLevel' = 'Serializable');
```

**Setting isolation in Python connector**:

```python
from databricks.sql import TRANSACTION_ISOLATION_LEVEL_REPEATABLE_READ

connection.set_transaction_isolation(TRANSACTION_ISOLATION_LEVEL_REPEATABLE_READ)
# Only REPEATABLE_READ is supported; others raise NotSupportedError
```

**Snapshot isolation behavior**:

- **Repeatable reads**: Data read within a transaction remains consistent
- **Atomic commits**: Changes are invisible to other connections until committed
- **Write conflicts**: Concurrent writes to the same table cause conflicts
- **Cross-table writes**: Concurrent writes to different tables can succeed

### Write Conflicts and Concurrency

**Row-level concurrency** (Runtime 14.2+) reduces conflicts for tables with deletion vectors or liquid clustering:

| Operation | WriteSerializable | Serializable |
|-----------|------------------|--------------|
| INSERT vs INSERT | No conflict | No conflict |
| UPDATE/DELETE/MERGE vs same | No conflict (different rows) | May conflict |
| OPTIMIZE vs concurrent DML | Conflict only with ZORDER BY | May conflict |

**Common conflict exceptions**:

| Exception | Cause |
|-----------|-------|
| `ConcurrentAppendException` | Concurrent append to the same partition |
| `ConcurrentDeleteReadException` | Concurrent delete of files being read |
| `MetadataChangedException` | Concurrent ALTER TABLE or schema change |
| `ProtocolChangedException` | Protocol version upgrade during write |

### Best Practices

1. **Keep transactions short** to minimize conflict windows
2. **Always wrap in try/except/finally** with rollback on errors
3. **Restore autocommit** in the `finally` block
4. **Use partition pruning** in MERGE conditions to reduce conflict scope
5. **Enable row-level concurrency** (deletion vectors + liquid clustering) for high-concurrency workloads
6. **Prefer single-statement MERGE** over multi-statement transactions when updating a single table
7. **Commit and restart** transactions to see changes made by other connections

---

## Runtime Version Reference

| Feature | Minimum Runtime | Status |
|---------|----------------|--------|
| SQL Scripting (compound statements, control flow) | 16.3 | GA |
| Stored Procedures (CREATE/CALL/DROP PROCEDURE) | 17.0 | Public Preview |
| Recursive CTEs (WITH RECURSIVE) | 17.0 / DBSQL 2025.20 | GA |
| Multi-variable DECLARE | 17.2 | GA |
| EXECUTE IMMEDIATE (basic) | 14.3 | GA |
| EXECUTE IMMEDIATE (expressions, nested) | 17.3 | GA |
| Recursive CTE LIMIT ALL | 17.2 | GA |
| Multi-statement Transactions | Varies | Preview |
| Row-level Concurrency | 14.2 | GA |

---

## Quick Reference Card

### SQL Scripting Skeleton

```sql
BEGIN
  -- 1. Declarations
  DECLARE var1 INT DEFAULT 0;
  DECLARE var2 STRING;
  DECLARE my_error CONDITION FOR SQLSTATE '45000';
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
      -- error handling logic
    END;

  -- 2. Logic
  IF var1 > 0 THEN
    SET var2 = 'positive';
  ELSE
    SET var2 = 'non-positive';
  END IF;

  -- 3. Output
  VALUES (var1, var2);
END;
```

### Stored Procedure Skeleton

```sql
CREATE OR REPLACE PROCEDURE my_schema.my_proc(
    IN  input_param STRING,
    OUT output_param INT
)
LANGUAGE SQL
SQL SECURITY INVOKER
COMMENT 'Description of what this procedure does'
AS BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    SET output_param = -1;

  -- procedure body
  SET output_param = (SELECT COUNT(*) FROM my_table WHERE col = input_param);
END;

-- Invoke
DECLARE result INT;
CALL my_schema.my_proc('value', result);
SELECT result;
```

### Recursive CTE Skeleton

```sql
WITH RECURSIVE cte_name (col1, col2) MAX RECURSION LEVEL 50 AS (
  -- Anchor
  SELECT seed_col1, seed_col2
  FROM base_table
  WHERE condition

  UNION ALL

  -- Recursive step
  SELECT derived_col1, derived_col2
  FROM source_table s
  JOIN cte_name c ON s.parent = c.col1
)
SELECT * FROM cte_name;
```
