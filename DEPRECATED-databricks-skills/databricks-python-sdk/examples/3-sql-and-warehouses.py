"""
Databricks SDK - SQL Warehouses and Statement Execution Examples

Warehouses API: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html
Statement Execution: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html
"""

from datetime import timedelta
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import (
    StatementState,
    Disposition,
    Format,
    StatementParameterListItem,
)

w = WorkspaceClient()

# =============================================================================
# SQL WAREHOUSES
# =============================================================================

# List all warehouses
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html
for warehouse in w.warehouses.list():
    print(f"{warehouse.name}: {warehouse.state} (id: {warehouse.id})")


# Get warehouse details
warehouse = w.warehouses.get(id="abc123def456")
print(f"Warehouse: {warehouse.name}")
print(f"Size: {warehouse.cluster_size}")
print(f"State: {warehouse.state}")


# Create a serverless SQL warehouse
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html
created = w.warehouses.create_and_wait(
    name="my-warehouse",
    cluster_size="Small",
    max_num_clusters=1,
    auto_stop_mins=15,
    enable_serverless_compute=True,
    timeout=timedelta(minutes=20)
)
print(f"Created warehouse: {created.id}")


# Start a stopped warehouse
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html
w.warehouses.start(id="abc123").result()  # Blocks until RUNNING


# Stop a warehouse
w.warehouses.stop(id="abc123").result()


# Edit warehouse configuration
w.warehouses.edit(
    id="abc123",
    name="my-warehouse-renamed",
    cluster_size="Medium",
    max_num_clusters=2,
    auto_stop_mins=30
)


# Delete warehouse
w.warehouses.delete(id="abc123")


# =============================================================================
# STATEMENT EXECUTION (Running SQL Queries)
# =============================================================================

# Execute a simple SQL query
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html
response = w.statement_execution.execute_statement(
    warehouse_id="abc123",
    statement="SELECT * FROM main.default.my_table LIMIT 10",
    wait_timeout="30s"  # Wait up to 30 seconds for results
)

# Check if query succeeded
if response.status.state == StatementState.SUCCEEDED:
    # Get column names
    columns = [col.name for col in response.manifest.schema.columns]
    print(f"Columns: {columns}")

    # Get data rows
    for row in response.result.data_array:
        print(row)
else:
    print(f"Query failed: {response.status.error}")


# Execute with parameterized query (prevents SQL injection)
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html
response = w.statement_execution.execute_statement(
    warehouse_id="abc123",
    statement="SELECT * FROM main.default.users WHERE age > :min_age AND name = :name",
    parameters=[
        StatementParameterListItem(name="min_age", value="21", type="INT"),
        StatementParameterListItem(name="name", value="Alice", type="STRING"),
    ],
    wait_timeout="30s"
)


# Execute with specific catalog and schema context
response = w.statement_execution.execute_statement(
    warehouse_id="abc123",
    catalog="main",
    schema="analytics",
    statement="SELECT COUNT(*) FROM events",
    wait_timeout="30s"
)


# Execute query with external links (for large results > 25MB)
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html
response = w.statement_execution.execute_statement(
    warehouse_id="abc123",
    statement="SELECT * FROM large_table",
    disposition=Disposition.EXTERNAL_LINKS,  # Results stored externally
    format=Format.ARROW_STREAM,  # Arrow format for efficiency
    wait_timeout="0s"  # Don't wait, poll separately
)

# Poll for completion
statement_id = response.statement_id
while True:
    status = w.statement_execution.get_statement(statement_id)
    if status.status.state in [StatementState.SUCCEEDED, StatementState.FAILED]:
        break
    import time
    time.sleep(1)


# Fetch result chunks for large results
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html
if response.manifest and response.manifest.total_chunk_count > 1:
    for chunk_index in range(response.manifest.total_chunk_count):
        chunk = w.statement_execution.get_statement_result_chunk_n(
            statement_id=response.statement_id,
            chunk_index=chunk_index
        )
        for row in chunk.data_array:
            print(row)


# Cancel a running statement
w.statement_execution.cancel_execution(statement_id="stmt-xxx")


# =============================================================================
# PRACTICAL PATTERN: Query to DataFrame
# =============================================================================

def query_to_dataframe(warehouse_id: str, sql: str):
    """Execute SQL and return results as a pandas DataFrame."""
    import pandas as pd

    response = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        wait_timeout="300s"
    )

    if response.status.state != StatementState.SUCCEEDED:
        raise Exception(f"Query failed: {response.status.error}")

    columns = [col.name for col in response.manifest.schema.columns]
    data = response.result.data_array

    return pd.DataFrame(data, columns=columns)

# Usage:
# df = query_to_dataframe("abc123", "SELECT * FROM my_table")
