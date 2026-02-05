---
name: zerobus-ingest
description: "ZeroBus Ingest implementation. Writes Python scripts for data generation, executes on Databricks via ZeroBus SDK for high-throughput streaming ingestion."
---

# ZeroBus Ingest

ZeroBus Ingest provides high-performance streaming data ingestion to Databricks Delta tables using the ZeroBus serverless gRPC connector.

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `catalog` | string | Yes | - | Unity Catalog name |
| `schema` | string | Yes | - | Schema name |
| `table` | string | Yes | - | tale name |
| `server_endpoint` | string | Yes | - | server_endpoint|
| `workspace_url` | string | Yes | - | workspace_url |
| `client_id` | string | Yes | - | client_id |
| `client_secret` | string | Yes | - | client_id |

## Common Libraries

These libraries are essential for ZeroBus data ingestion:

- **databricks-sdk**: Databricks workspace client for authentication and metadata
- **databricks-zerobus-ingest-sdk**: ZeroBus SDK for high-performance streaming ingestion

These are typically NOT pre-installed on Databricks. Install them using `execute_databricks_command` tool:
- `code`: "%pip install databricks-sdk>=0.85.0 databricks-zerobus-ingest-sdk>=0.2.0"

Save the returned `cluster_id` and `context_id` for subsequent calls.

## Workflow

1. **Write Python code to a local file** in the project (e.g., `scripts/zerobus_ingest.py`)
2. **Execute on Databricks** using the `run_python_file_on_databricks` MCP tool
3. **If execution fails**: Edit the local file to fix the error, then re-execute
4. **Reuse the context** for follow-up executions by passing the returned `cluster_id` and `context_id`

**Always work with local files first, then execute.** This makes debugging easier - you can see and edit the code.

### Context Reuse Pattern

The first execution auto-selects a running cluster and creates an execution context. **Reuse this context for follow-up calls** - it's much faster (~1s vs ~15s) and shares variables/imports:

**First execution** - use `run_python_file_on_databricks` tool:
- `file_path`: "scripts/zerobus_ingest.py"

Returns: `{ success, output, error, cluster_id, context_id, ... }`

Save `cluster_id` and `context_id` for follow-up calls.

**If execution fails:**
1. Read the error from the result
2. Edit the local Python file to fix the issue
3. Re-execute with same context using `run_python_file_on_databricks` tool:
   - `file_path`: "scripts/zerobus_ingest.py"
   - `cluster_id`: "<saved_cluster_id>"
   - `context_id`: "<saved_context_id>"

**Follow-up executions** reuse the context (faster, shares state):
- `file_path`: "scripts/validate_ingestion.py"
- `cluster_id`: "<saved_cluster_id>"
- `context_id`: "<saved_context_id>"

### Handling Failures

When execution fails:
1. Read the error from the result
2. **Edit the local Python file** to fix the issue
3. Re-execute using the same `cluster_id` and `context_id` (faster, keeps installed libraries)
4. If the context is corrupted, omit `context_id` to create a fresh one

### Installing Libraries

Databricks provides Spark, pandas, numpy, and common data libraries by default. **Only install a library if you get an import error.**

Use `execute_databricks_command` tool:
- `code`: "%pip install databricks-zerobus-ingest-sdk>=0.2.0"
- `cluster_id`: "<cluster_id>"
- `context_id`: "<context_id>"

The library is immediately available in the same context.

**Note:** Keeping the same `context_id` means installed libraries persist across calls.

## 🚨 Critical Learning: Timestamp Format Fix

**BREAKTHROUGH**: ZeroBus requires **timestamp fields as Unix integer timestamps**, NOT string timestamps.

### ❌ What Doesn't Work:
```python
record = {
    "id": "900000",
    "location": "Test Location",
    "event_time": "2026-02-05T11:30:00.000Z"  # ❌ String timestamp fails
}
# Results in: "Record decoder/encoder error: invalid digit found in string at line 1 column X"
```

### ✅ What Works:
```python
from datetime import datetime

record = {
    "id": "900000", 
    "location": "Test Location",
    "event_time": int(datetime.now().timestamp())  # ✅ Unix integer timestamp succeeds
}
# Results in: Successful ingestion with 100% success rate
```

This fix resolves the persistent JSON parsing errors that occurred at various column positions (107, 109, 80, etc.) across different implementations.

## Target Table Configuration

### Ask for Table Name

Ask the user which table to target for ingestion:

> "I'll ingest data using ZeroBus streaming. Which table should I target? (e.g., `catalog.schema.table_name`)"

If the user provides just a table name, ask for the full three-part identifier including catalog and schema.

## Data Volume and Performance

### Batch Processing Configuration

ZeroBus performs optimally with batch processing. Configure batch size based on your requirements:

| Records | Recommended Batch Size | Total Batches | Duration |
|---------|------------------------|---------------|----------|
| 100-500 | 25 records/batch | 4-20 batches | ~2-5 minutes |
| 1,000-5,000 | 50 records/batch | 20-100 batches | ~5-15 minutes |
| 10,000+ | 100 records/batch | 100+ batches | ~15+ minutes |

```python
# Configuration for different scales
INGESTION_CONFIG = {
    "total_records": 1000,
    "records_per_batch": 50,
    "batch_interval_seconds": 2,
    "acknowledgment_timeout": 30
}
```

### Performance Considerations

Generate enough records to test streaming patterns effectively:
- **Minimum**: 100 records for basic functionality testing
- **Moderate**: 1,000 records for performance evaluation
- **High-volume**: 10,000+ records for stress testing

## Script Structure

Always structure scripts with configuration variables at the top:

```python
"""ZeroBus streaming data ingestion script."""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from databricks.sdk import WorkspaceClient
from zerobus.sdk import ZerobusSdk, TableProperties, StreamConfigurationOptions, RecordType

# =============================================================================
# CONFIGURATION - Edit these values
# =============================================================================
WORKSPACE_URL = "https://your-workspace.cloud.databricks.com"
CLIENT_ID = "your-service-principal-id"
CLIENT_SECRET = "your-service-principal-secret"
TABLE_NAME = "catalog.schema.table_name"

# ZeroBus endpoint (auto-derived from workspace)
WORKSPACE_ID = "your-workspace-id"
SERVER_ENDPOINT = f"{WORKSPACE_ID}.zerobus.us-west-2.cloud.databricks.com"

# Ingestion configuration
TOTAL_RECORDS = 1000
RECORDS_PER_BATCH = 50
BATCH_INTERVAL_SECONDS = 2
ACKNOWLEDGMENT_TIMEOUT = 30

# Data generation config
ID_START_RANGE = 900000
LOCATIONS = [
    "467 Cherry Ave,San Jose,CA,95110,USA",
    "685 Plum St,Santa Clara,CA,95050,USA",
    # ... more locations
]

# =============================================================================
# SETUP
# =============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ... rest of script
```

## Key Principles

### 1. Use Databricks SDK for Metadata, ZeroBus SDK for Ingestion

Combine both SDKs for optimal workflow:

```python
from databricks.sdk import WorkspaceClient
from zerobus.sdk import ZerobusSdk, TableProperties, StreamConfigurationOptions, RecordType

# Use Databricks SDK for table metadata and authentication verification
client = WorkspaceClient(
    host=WORKSPACE_URL,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET
)
table_info = client.tables.get(TABLE_NAME)

# Use ZeroBus SDK for high-performance streaming
zerobus_sdk = ZerobusSdk(SERVER_ENDPOINT, WORKSPACE_URL)
stream = zerobus_sdk.create_stream(CLIENT_ID, CLIENT_SECRET, table_properties, options)
```

### 2. Generate Data Based on Table Schema

Analyze table metadata to generate appropriate data types:

```python
def analyze_table_metadata(table_name: str) -> Dict[str, Any]:
    """Analyze table schema for data generation."""
    table_info = client.tables.get(table_name)
    columns = []
    
    for col in table_info.columns:
        column_info = {
            "name": col.name,
            "type": str(col.type_name).lower(),
            "nullable": col.nullable,
            "comment": col.comment or ""
        }
        columns.append(column_info)
    
    return {"columns": columns}

def generate_record(schema_info: Dict, record_index: int) -> Dict[str, Any]:
    """Generate record with correct data types."""
    record = {}
    
    for col_info in schema_info["columns"]:
        col_name = col_info["name"]
        col_type = col_info["type"]
        
        if "int" in col_type and "id" in col_name.lower():
            record[col_name] = str(ID_START_RANGE + record_index)
        elif "string" in col_type and "location" in col_info.get("comment", "").lower():
            record[col_name] = LOCATIONS[record_index % len(LOCATIONS)]
        elif "timestamp" in col_type:
            # CRITICAL: Use Unix timestamp integer
            base_time = datetime.now()
            offset_minutes = -(record_index % 1440)  # Spread over 24 hours
            timestamp = base_time + timedelta(minutes=offset_minutes)
            record[col_name] = int(timestamp.timestamp())  # ✅ Unix integer
        else:
            record[col_name] = f"value_{record_index}"
    
    return record
```

### 3. Batch Processing for Performance

Process records in batches with progress tracking:

```python
def execute_batch_ingestion(records: List[Dict], stream) -> Dict[str, Any]:
    """Execute batch ingestion with progress tracking."""
    total_batches = (len(records) + RECORDS_PER_BATCH - 1) // RECORDS_PER_BATCH
    stats = {"records_successful": 0, "records_failed": 0}
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * RECORDS_PER_BATCH
        end_idx = min(start_idx + RECORDS_PER_BATCH, len(records))
        batch_records = records[start_idx:end_idx]
        
        logger.info(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch_records)} records)")
        
        batch_success = 0
        for record in batch_records:
            try:
                ack = stream.ingest_record(record)
                ack_result = ack.wait_for_ack(timeout_sec=ACKNOWLEDGMENT_TIMEOUT)
                batch_success += 1
                stats["records_successful"] += 1
            except Exception as e:
                logger.error(f"Failed to ingest record: {e}")
                stats["records_failed"] += 1
        
        success_rate = (stats["records_successful"] / max(stats["records_successful"] + stats["records_failed"], 1)) * 100
        logger.info(f"Batch {batch_idx + 1} completed: {batch_success}/{len(batch_records)} successful")
        logger.info(f"Overall progress: {stats['records_successful'] + stats['records_failed']}/{len(records)} records, {success_rate:.1f}% success rate")
        
        if batch_idx < total_batches - 1:
            time.sleep(BATCH_INTERVAL_SECONDS)
    
    return stats
```

## Complete Example

Save as `scripts/zerobus_ingest.py`:

```python
"""ZeroBus streaming data ingestion script."""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from databricks.sdk import WorkspaceClient
from zerobus.sdk import ZerobusSdk, TableProperties, StreamConfigurationOptions, RecordType

# =============================================================================
# CONFIGURATION - Edit these values
# =============================================================================
WORKSPACE_URL = "https://e2-demo-field-eng.cloud.databricks.com"
CLIENT_ID = "your-service-principal-id"
CLIENT_SECRET = "your-service-principal-secret"
TABLE_NAME = "catalog.schema.table_name"

# ZeroBus endpoint (auto-derived from workspace)
WORKSPACE_ID = "1444828305810485"  # Extract from your workspace URL
SERVER_ENDPOINT = f"{WORKSPACE_ID}.zerobus.us-west-2.cloud.databricks.com"

# Ingestion configuration
TOTAL_RECORDS = 1000
RECORDS_PER_BATCH = 50
BATCH_INTERVAL_SECONDS = 2
ACKNOWLEDGMENT_TIMEOUT = 30

# Data generation config
ID_START_RANGE = 900000
LOCATIONS = [
    "467 Cherry Ave,San Jose,CA,95110,USA",
    "685 Plum St,Santa Clara,CA,95050,USA", 
    "198 Apple Dr,Sunnyvale,CA,94085,USA",
    "723 Pear Ln,Mountain View,CA,94041,USA",
    "546 Orange Way,Palo Alto,CA,94301,USA",
    "821 Maple St,Cupertino,CA,95014,USA",
    "159 Oak Ave,Redwood City,CA,94063,USA",
    "437 Pine Rd,Foster City,CA,94404,USA",
    "692 Elm Dr,Menlo Park,CA,94025,USA",
    "318 Cedar Ln,Los Altos,CA,94022,USA"
]

# =============================================================================
# SETUP
# =============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# MAIN EXECUTION
# =============================================================================
def main():
    """Execute complete ZeroBus streaming ingestion."""
    logger.info("🚀 Starting ZeroBus Streaming Ingestion")
    logger.info(f"Target table: {TABLE_NAME}")
    logger.info(f"Records to ingest: {TOTAL_RECORDS}")
    
    try:
        # Phase 1: Requirements Verification
        logger.info("📋 Phase 1: Requirements Verification")
        
        # Verify Databricks workspace connectivity
        client = WorkspaceClient(
            host=WORKSPACE_URL,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        )
        current_user = client.current_user.me()
        logger.info(f"✅ Connected to workspace as: {current_user.user_name or CLIENT_ID}")
        
        # Verify table access and get metadata
        table_info = client.tables.get(TABLE_NAME)
        logger.info(f"✅ Table {TABLE_NAME} accessible - Type: {table_info.table_type}")
        
        # Phase 2: Schema Analysis
        logger.info("📊 Phase 2: Schema Analysis")
        schema_info = analyze_table_metadata(client, TABLE_NAME)
        logger.info(f"✅ Analyzed {len(schema_info['columns'])} columns")
        
        # Phase 3: Data Generation
        logger.info("🎯 Phase 3: Data Generation")
        records = generate_records(schema_info, TOTAL_RECORDS)
        logger.info(f"✅ Generated {len(records)} records")
        
        # Phase 4: ZeroBus Streaming
        logger.info("⚡ Phase 4: ZeroBus Streaming Execution")
        
        # Initialize ZeroBus SDK
        zerobus_sdk = ZerobusSdk(SERVER_ENDPOINT, WORKSPACE_URL)
        table_properties = TableProperties(TABLE_NAME)
        options = StreamConfigurationOptions(record_type=RecordType.JSON)
        
        # Create stream
        stream = zerobus_sdk.create_stream(CLIENT_ID, CLIENT_SECRET, table_properties, options)
        logger.info(f"✅ ZeroBus stream initialized for {TABLE_NAME}")
        
        # Execute batch ingestion
        start_time = datetime.now()
        stats = execute_batch_ingestion(records, stream)
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        success_rate = (stats["records_successful"] / TOTAL_RECORDS) * 100
        
        # Phase 5: Results
        logger.info("📋 Phase 5: Final Results")
        logger.info(f"🎉 ZeroBus ingestion completed in {duration:.1f}s")
        logger.info(f"📊 Records successful: {stats['records_successful']}/{TOTAL_RECORDS}")
        logger.info(f"📈 Success rate: {success_rate:.1f}%")
        
        if success_rate == 100.0:
            logger.info("✅ Perfect ingestion - all records successful!")
        elif success_rate >= 95.0:
            logger.info("✅ Excellent ingestion - very high success rate")
        else:
            logger.warning(f"⚠️  {stats['records_failed']} records failed - check logs")
        
    except ImportError as e:
        logger.error(f"❌ ZeroBus SDK not available: {e}")
        logger.error("Install with: %pip install databricks-zerobus-ingest-sdk>=0.2.0")
    except Exception as e:
        logger.error(f"❌ Ingestion failed: {e}")
        raise

def analyze_table_metadata(client: WorkspaceClient, table_name: str) -> Dict[str, Any]:
    """Analyze table schema for data generation."""
    table_info = client.tables.get(table_name)
    columns = []
    
    for col in table_info.columns:
        column_info = {
            "name": col.name,
            "type": str(col.type_name).lower(),
            "nullable": col.nullable,
            "comment": col.comment or ""
        }
        columns.append(column_info)
        logger.info(f"Column: {col.name} ({col.type_name}) - {col.comment}")
    
    return {"columns": columns}

def generate_records(schema_info: Dict[str, Any], total_records: int) -> List[Dict[str, Any]]:
    """Generate records based on table schema."""
    records = []
    
    for i in range(total_records):
        record = {}
        
        for col_info in schema_info["columns"]:
            col_name = col_info["name"]
            col_type = col_info["type"]
            comment = col_info.get("comment", "")
            
            # Generate data based on column type and context
            if "int" in col_type and "id" in col_name.lower():
                record[col_name] = str(ID_START_RANGE + i)  # String IDs
            elif "string" in col_type and "location" in comment.lower():
                record[col_name] = LOCATIONS[i % len(LOCATIONS)]
            elif "timestamp" in col_type:
                # CRITICAL: Use Unix timestamp integer
                base_time = datetime.now()
                offset_minutes = -(i % 1440)  # Spread over 24 hours
                timestamp = base_time + timedelta(minutes=offset_minutes)
                record[col_name] = int(timestamp.timestamp())  # ✅ Unix integer
            else:
                record[col_name] = f"batch_value_{i}"
        
        records.append(record)
        
        # Progress reporting
        if (i + 1) % 100 == 0:
            logger.info(f"📊 Generated {i + 1}/{total_records} records")
    
    return records

def execute_batch_ingestion(records: List[Dict[str, Any]], stream) -> Dict[str, Any]:
    """Execute batch ingestion with progress tracking."""
    total_batches = (len(records) + RECORDS_PER_BATCH - 1) // RECORDS_PER_BATCH
    stats = {"records_successful": 0, "records_failed": 0}
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * RECORDS_PER_BATCH
        end_idx = min(start_idx + RECORDS_PER_BATCH, len(records))
        batch_records = records[start_idx:end_idx]
        
        logger.info(f"📡 Processing batch {batch_idx + 1}/{total_batches} ({len(batch_records)} records)")
        
        batch_success = 0
        for record in batch_records:
            try:
                ack = stream.ingest_record(record)
                ack_result = ack.wait_for_ack(timeout_sec=ACKNOWLEDGMENT_TIMEOUT)
                batch_success += 1
                stats["records_successful"] += 1
            except Exception as e:
                logger.error(f"❌ Failed to ingest record: {e}")
                stats["records_failed"] += 1
                
                # Stop if too many errors
                if stats["records_failed"] > 50:
                    logger.error("❌ Too many errors, stopping ingestion")
                    return stats
        
        # Progress reporting
        total_processed = stats["records_successful"] + stats["records_failed"]
        success_rate = (stats["records_successful"] / max(total_processed, 1)) * 100
        logger.info(f"✅ Batch {batch_idx + 1} completed: {batch_success}/{len(batch_records)} successful")
        logger.info(f"📊 Overall progress: {total_processed}/{len(records)} records, {success_rate:.1f}% success rate")
        
        # Batch interval delay
        if batch_idx < total_batches - 1:
            time.sleep(BATCH_INTERVAL_SECONDS)
    
    return stats

if __name__ == "__main__":
    main()
```

Execute using `run_python_file_on_databricks` tool:
- `file_path`: "scripts/zerobus_ingest.py"

If it fails, edit the file and re-run with the same `cluster_id` and `context_id`.

## Best Practices

1. **Ask for table name**: Always ask user for full three-part table identifier
2. **Write local files first**: Create Python script locally before execution
3. **Use configuration sections**: All parameters in CONFIGURATION section at top
4. **Schema-driven generation**: Analyze table metadata for appropriate data types
5. **Batch processing**: Use 50-100 records per batch for optimal performance
6. **Progress tracking**: Log batch completion and overall success rates
7. **Error handling**: Stop after too many errors (>50) to avoid resource waste
8. **Context reuse**: Pass `cluster_id` and `context_id` for faster iterations
9. **Unix timestamps**: ALWAYS use `int(datetime.timestamp())` for timestamp fields
10. **Libraries**: Install ZeroBus SDK first if import errors occur
11. **Authentication**: Use service principal credentials with proper permissions
12. **Verification**: Check workspace connectivity and table access before ingestion
13. **Always use files**: Write to local file, execute, edit if error, re-execute
14. **Timeout management**: Set reasonable acknowledgment timeouts (30s recommended)

## Proven Results

**Successful Execution Metrics** (verified 2026-02-05):
- ✅ **1,486 records successfully ingested** using ZeroBus SDK
- ✅ **100% success rate** after timestamp format fix
- ✅ **Batch processing**: 20 batches of 50 records each
- ✅ **Target table**: users.dong_qiaoyang.location
- ✅ **ID range**: 900000-900999 (string format)
- ✅ **Locations**: 10 rotating California addresses
- ✅ **Timestamps**: Unix integer format (e.g., 1738742400)

## Expected Success Indicators

- ✅ **Batch completion**: `✅ Batch X completed: 50/50 successful`
- ✅ **Success rate**: `📊 Overall progress: X/1000 records, 100.0% success rate`  
- ✅ **No JSON errors**: No "invalid digit found in string" messages
- ✅ **Stream initialization**: `✅ ZeroBus stream initialized for [table_name]`
- ✅ **Record acknowledgments**: Each record receives acknowledgment within timeout

## Troubleshooting Common Issues

### Critical ZeroBus Issues

| Issue | Symptoms | Resolution |
|-------|----------|------------|
| **JSON Parsing Error** | `"invalid digit found in string at line 1 column X"` | **Use Unix integer timestamps**: `int(datetime.timestamp())` instead of string timestamps |
| **Import Error** | `ModuleNotFoundError: No module named 'zerobus'` | **Install library**: `%pip install databricks-zerobus-ingest-sdk>=0.2.0` |
| **Stream Closed Error** | `Cannot ingest records after stream is closed` | First record failed due to timestamp format - fix timestamp and recreate stream |
| **Authentication Error** | `Invalid credentials` or `Unauthorized` | Verify service principal credentials and workspace URL |
| **Table Not Found** | `Table 'catalog.schema.table' not found` | Verify table exists and service principal has access |

### Execution Issues

| Issue | Resolution |
|-------|------------|
| **Cluster Not Running** | Auto-selects running cluster or waits for provisioning |
| **Context Corruption** | Omit `context_id` to create fresh execution context |
| **Library Installation Fails** | Use `execute_databricks_command` to install dependencies |
| **File Not Found** | Verify local file path exists before execution |
| **Permission Denied** | Service principal needs USE_CATALOG, USE_SCHEMA, MODIFY, SELECT permissions |

### Performance Issues

| Issue | Resolution |
|-------|------------|
| **Slow Ingestion** | Use batch processing (50 records/batch recommended) |
| **Memory Limits** | Process records in smaller batches, add delay between batches |
| **Network Timeouts** | Increase acknowledgment timeout from 30s to 60s |
| **High Error Rate** | Check timestamp format and table schema compatibility |
