---
name: salesforce-batch-writer
description: Write data from Databricks to Salesforce using the Python Data Source API and Bulk API v2. Use for reverse-ETL scenarios, Salesforce data synchronization, or parent-child object upserts.
author: Neil Wilson
source_url: https://www.databricksters.com/p/bulking-up-high-performance-batch
source_site: databricksters.com
---

# Salesforce Batch Writer with PySpark

## Overview

This skill implements a custom PySpark data source for writing data to Salesforce using the Bulk API v2.0. It enables high-performance batch writes with automatic parallelization, parent-child relationship handling, and robust error tracking.

**Key Capabilities**:
- Bulk API v2.0 support (150MB per job limit)
- Automatic parallelization via Spark partitioning
- Parent-child object upserts
- Configurable batch sizes and error handling

## Prerequisites

### Required Libraries

```python
# Install simple-salesforce
%pip install simple-salesforce
```

### Salesforce Credentials

Store credentials securely using Databricks secrets:

```bash
# Create secret scope (one-time setup)
databricks secrets create-scope --scope salesforce

# Store credentials
databricks secrets put --scope salesforce --key username
databricks secrets put --scope salesforce --key password
databricks secrets put --scope salesforce --key token
databricks secrets put --scope salesforce --key domain  # "test" for sandbox
```

## Quick Start

### Step 1: Register the Data Source

```python
# Copy SalesforceBatchDataSource class to your project
# Then register it
spark.dataSource.register(SalesforceBatchDataSource)
```

### Step 2: Load Credentials

```python
import dbutils

sf_creds = {
    "username": dbutils.secrets.get(scope="salesforce", key="username"),
    "password": dbutils.secrets.get(scope="salesforce", key="password"),
    "security_token": dbutils.secrets.get(scope="salesforce", key="token"),
    "instance_url": "https://yourcompany.my.salesforce.com",
    "domain": dbutils.secrets.get(scope="salesforce", key="domain")  # "test" or "login"
}
```

### Step 3: Write Data

```python
# Repartition to control batch size (max 150MB per partition)
df_to_write = df.repartition(32)

# Write to Salesforce
(df_to_write.write
    .format("salesforce-batch")
    .mode("append")
    .options(**sf_creds)
    .option("sobject", "Contact")
    .option("api_version", "2")
    .save()
)
```

## Core Implementation

### Data Source Class Structure

```python
from pyspark.sql.datasource import DataSource, DataSourceWriter
from pyspark.sql.types import StructType
from typing import Iterator, Dict, Any

class SalesforceBatchDataSource(DataSource):
    """Custom data source for Salesforce Bulk API writes."""
    
    @classmethod
    def name(cls) -> str:
        return "salesforce-batch"
    
    def schema(self) -> str:
        # Schema is inferred from input DataFrame
        return "*"
    
    def writer(self, schema: StructType, overwrite: bool):
        return SalesforceBatchWriter(self.options, schema)

class SalesforceBatchWriter(DataSourceWriter):
    """Handles batch writes to Salesforce."""
    
    def __init__(self, options: Dict[str, str], schema: StructType):
        self.options = options
        self.schema = schema
    
    def write(self, rows: Iterator[Row]) -> Dict[str, Any]:
        # Implementation details below
        pass
```

### Write Method Implementation

```python
def write(self, rows: Iterator[Row]) -> Dict[str, Any]:
    from simple_salesforce import Salesforce
    from pyspark import TaskContext
    
    ctx = TaskContext.get()
    partition_id = ctx.partitionId()
    
    # Extract options
    username = self.options.get("username")
    password = self.options.get("password")
    security_token = self.options.get("security_token")
    sobject = self.options.get("sobject")
    instance_url = self.options.get("instance_url")
    domain = self.options.get("domain", "login")
    api_version = self.options.get("api_version", "2")
    operation = self.options.get("operation", "insert")
    
    # Collect rows to list (materializes partition in memory)
    data_to_upload = [row.asDict() for row in rows]
    
    if not data_to_upload:
        return {"partition_id": partition_id, "records_written": 0}
    
    # Authenticate
    sf = Salesforce(
        username=username,
        password=password,
        security_token=security_token,
        instance_url=instance_url,
        domain=domain
    )
    
    # Perform bulk operation
    if api_version == "2":
        result = self._bulk2_operation(sf, sobject, operation, data_to_upload)
    else:
        result = self._bulk1_operation(sf, sobject, operation, data_to_upload)
    
    return {
        "partition_id": partition_id,
        "records_written": result["success_count"],
        "errors": result["error_count"]
    }
```

## Examples

### Example 1: Basic Insert

```python
# Prepare DataFrame with matching schema
df_contacts = spark.createDataFrame([
    {"FirstName": "John", "LastName": "Doe", "Email": "john.doe@example.com"},
    {"FirstName": "Jane", "LastName": "Smith", "Email": "jane.smith@example.com"}
])

# Write to Salesforce
(df_contacts.write
    .format("salesforce-batch")
    .mode("append")
    .options(**sf_creds)
    .option("sobject", "Contact")
    .option("api_version", "2")
    .option("operation", "insert")
    .save()
)
```

### Example 2: Upsert with External ID

```python
# Upsert based on Email field
df_contacts = spark.createDataFrame([
    {"FirstName": "John", "LastName": "Doe", "Email": "john.doe@example.com", "Phone": "555-0123"}
])

(df_contacts.write
    .format("salesforce-batch")
    .mode("append")
    .options(**sf_creds)
    .option("sobject", "Contact")
    .option("api_version", "2")
    .option("operation", "upsert")
    .option("upsertField", "Email")  # External ID field
    .save()
)
```

### Example 3: Parent-Child Relationship Upsert

```python
# Step 1: Upsert Accounts with External ID
df_accounts = spark.createDataFrame([
    {"Name": "Acme Corp", "Oracle_Id__c": "ORA-1001"},  # External ID
    {"Name": "Tech Inc", "Oracle_Id__c": "ORA-1002"}
])

(df_accounts.write
    .format("salesforce-batch")
    .mode("append")
    .options(**sf_creds)
    .option("sobject", "Account")
    .option("api_version", "2")
    .option("operation", "upsert")
    .option("upsertField", "Oracle_Id__c")
    .save()
)

# Step 2: Upsert Contacts linked to Accounts
from pyspark.sql.functions import col

df_contacts = spark.createDataFrame([
    {"FirstName": "John", "LastName": "Doe", "Email": "john@acme.com", "AccountExtId": "ORA-1001"},
    {"FirstName": "Jane", "LastName": "Smith", "Email": "jane@tech.com", "AccountExtId": "ORA-1002"}
])

# Map AccountExtId to Account relationship field
df_contacts_ready = df_contacts.select(
    "FirstName",
    "LastName",
    "Email",
    col("AccountExtId").alias("Account.Oracle_Id__c")  # Link to Account
)

(df_contacts_ready.write
    .format("salesforce-batch")
    .mode("append")
    .options(**sf_creds)
    .option("sobject", "Contact")
    .option("api_version", "2")
    .option("operation", "upsert")
    .option("upsertField", "Email")
    .option("ignoreNullValues", "true")  # Don't overwrite nulls
    .save()
)
```

### Example 4: Performance Optimization

```python
# Optimize for 300k records
# Tested: 1 partition = 372 seconds, 32 partitions = 31 seconds

TOTAL_RECORDS = 300000
NUM_PARTITIONS = 32  # Match cluster cores

# Repartition for parallel processing
df_perf = df_large.repartition(NUM_PARTITIONS)

print(f"Writing {TOTAL_RECORDS:,} records via {NUM_PARTITIONS} partitions...")

(df_perf.write
    .format("salesforce-batch")
    .mode("append")
    .options(**sf_creds)
    .option("sobject", "Contact")
    .option("api_version", "2")
    .save()
)
```

## Configuration Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `username` | Yes | - | Salesforce username |
| `password` | Yes | - | Salesforce password |
| `security_token` | Yes | - | Salesforce security token |
| `sobject` | Yes | - | Salesforce object name |
| `instance_url` | No | Auto | Full Salesforce URL |
| `domain` | No | `login` | `login` (prod) or `test` (sandbox) |
| `api_version` | No | `2` | Bulk API version: `1` or `2` |
| `operation` | No | `insert` | `insert`, `upsert`, `update`, `delete` |
| `upsertField` | Conditional | - | External ID field for upserts |
| `ignoreNullValues` | No | `false` | Skip nulls instead of overwriting |
| `batchSize` | No | `10000` | Records per batch |

## Edge Cases & Troubleshooting

### Issue: Out of Memory Errors

**Cause**: Partitions too large, materializing entire partition in memory.

**Solution**: Increase partition count:

```python
# Reduce partition size (aim for < 150MB per partition)
df = df.repartition(64)  # More partitions = smaller chunks
```

### Issue: Salesforce API Limits

**Cause**: Too many parallel jobs exceeding daily API limits.

**Solution**: Balance parallelism with API limits:

```python
# Calculate optimal partitions based on API limits
daily_api_limit = 100000  # Your Salesforce limit
records_per_run = 500000
safety_margin = 0.8

optimal_partitions = int((daily_api_limit * safety_margin) / (records_per_run / 10))
df = df.repartition(min(optimal_partitions, 32))
```

### Issue: Failed Records Not Clear

**Solution**: Implement detailed error logging:

```python
def write(self, rows):
    # ... existing code ...
    
    if result["error_count"] > 0:
        failed_records = sf.bulk2.__getattr__(sobject).get_failed_records(job_id)
        print(f"Failed records: {failed_records[:2000]}")  # First 2KB
    
    return result
```

### Issue: Schema Mismatch

**Cause**: DataFrame columns don't match Salesforce object fields.

**Solution**: Align schemas explicitly:

```python
# Map DataFrame to Salesforce schema
df_mapped = df.select(
    col("first_name").alias("FirstName"),
    col("last_name").alias("LastName"),
    col("email_address").alias("Email")
)

# Verify before write
df_mapped.printSchema()
```

## Best Practices

1. **Repartition carefully**: Match partition count to cluster cores and API limits
2. **Use Bulk API v2**: Better performance and automatic batching
3. **Enable ignoreNullValues**: Prevent accidental data clearing
4. **Monitor API usage**: Track against Salesforce daily limits
5. **Test with small batches**: Validate before full data loads
6. **Use External IDs**: For reliable parent-child relationships

## Attribution

This skill is based on content by **Neil Wilson** from the Databricksters blog post:
[Bulking Up: High-Performance Batch Salesforce Writes with PySpark](https://www.databricksters.com/p/bulking-up-high-performance-batch)

Reference implementation: [GitHub Repository](https://github.com/neil-wilson-data/python-data-sources/blob/main/salesforce/salesforce_batch_writer.py)

## Related Resources

- [Salesforce Bulk API 2.0 Documentation](https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/bulk_api_2_0.htm)
- [simple-salesforce Library](https://github.com/simple-salesforce/simple-salesforce)
- [Spark Python Data Source API](https://spark.apache.org/docs/latest/api/python/tutorial/sql/python_data_source.html)
