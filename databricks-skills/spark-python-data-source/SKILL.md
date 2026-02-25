---
name: spark-python-data-source
description: Use when building custom Spark data source connectors for external systems (databases, APIs, message queues), implementing batch/streaming readers/writers, or creating data source plugins for systems without native Spark support. Triggers - "build Spark data source", "create Spark connector", "implement Spark reader/writer", "connect Spark to [system]", "streaming data source"
---

# spark-python-data-source

Build custom Python data sources for Apache Spark 4.0+ to read from and write to external systems in batch and streaming modes.

## When to use

Use when building Spark connectors for external systems that lack native support:
- External databases, APIs, message queues
- Custom file formats or protocols
- Real-time streaming data sources
- Systems requiring specialized authentication or protocols

Triggers: "build Spark data source", "create Spark connector", "implement Spark reader/writer", "connect Spark to [system]", "streaming data source"

## Instructions

You are an experienced Spark developer building custom Python data sources following the PySpark DataSource API. Follow these principles and patterns:

### Core Architecture

Each data source follows a flat, single-level inheritance structure:

1. **DataSource class** - Entry point returning readers/writers
2. **Base Reader/Writer classes** - Shared logic for options and data processing
3. **Batch classes** - Inherit from base + `DataSourceReader`/`DataSourceWriter`
4. **Stream classes** - Inherit from base + `DataSourceStreamReader`/`DataSourceStreamWriter`

### Critical Design Principles

**SIMPLE over CLEVER** - These are non-negotiable:

✅ REQUIRED:
- Flat single-level inheritance only
- Direct implementations, no abstractions
- Explicit imports, explicit control flow
- Standard library first, minimal dependencies
- Simple classes with single responsibilities

❌ FORBIDDEN:
- Abstract base classes or complex inheritance
- Factory patterns or dependency injection
- Decorators for cross-cutting concerns
- Complex configuration classes
- Async/await (unless absolutely necessary)
- Connection pooling or caching (unless critical)
- Generic "framework" code
- Premature optimization

### Implementation Pattern

```python
from pyspark.sql.datasource import (
    DataSource, DataSourceReader, DataSourceWriter,
    DataSourceStreamReader, DataSourceStreamWriter
)

# 1. DataSource class
class YourDataSource(DataSource):
    @classmethod
    def name(cls):
        return "your-format"

    def __init__(self, options):
        self.options = options

    def schema(self):
        return self._infer_or_return_schema()

    def reader(self, schema):
        return YourBatchReader(self.options, schema)

    def streamReader(self, schema):
        return YourStreamReader(self.options, schema)

    def writer(self, schema, overwrite):
        return YourBatchWriter(self.options, schema)

    def streamWriter(self, schema, overwrite):
        return YourStreamWriter(self.options, schema)

# 2. Base Writer with shared logic
class YourWriter:
    def __init__(self, options, schema=None):
        # Validate required options
        self.url = options.get("url")
        assert self.url, "url is required"
        self.batch_size = int(options.get("batch_size", "50"))
        self.schema = schema

    def write(self, iterator):
        # Import libraries here for partition execution
        import requests
        from pyspark import TaskContext

        context = TaskContext.get()
        partition_id = context.partitionId()

        msgs = []
        cnt = 0

        for row in iterator:
            cnt += 1
            msgs.append(row.asDict())

            if len(msgs) >= self.batch_size:
                self._send_batch(msgs)
                msgs = []

        if msgs:
            self._send_batch(msgs)

        return SimpleCommitMessage(partition_id=partition_id, count=cnt)

    def _send_batch(self, msgs):
        # Implement send logic
        pass

# 3. Batch Writer
class YourBatchWriter(YourWriter, DataSourceWriter):
    pass

# 4. Stream Writer
class YourStreamWriter(YourWriter, DataSourceStreamWriter):
    def commit(self, messages, batchId):
        pass

    def abort(self, messages, batchId):
        pass

# 5. Base Reader with partitioning
class YourReader:
    def __init__(self, options, schema):
        self.url = options.get("url")
        assert self.url, "url is required"
        self.schema = schema

    def partitions(self):
        # Return list of partitions for parallel reading
        return [YourPartition(0, start, end)]

    def read(self, partition):
        # Import here for executor execution
        import requests

        response = requests.get(f"{self.url}?start={partition.start}")
        for item in response.json():
            yield tuple(item.values())

# 6. Batch Reader
class YourBatchReader(YourReader, DataSourceReader):
    pass

# 7. Stream Reader
class YourStreamReader(YourReader, DataSourceStreamReader):
    def initialOffset(self):
        return {"offset": "0"}

    def latestOffset(self):
        return {"offset": str(self._get_latest())}

    def partitions(self, start, end):
        return [YourPartition(0, start["offset"], end["offset"])]

    def commit(self, end):
        pass
```

### Project Setup

```bash
# Create project
poetry new your-datasource
cd your-datasource
poetry add pyspark pytest pytest-spark

# Development commands - CRITICAL: Always use 'poetry run'
poetry run pytest                    # Run tests
poetry run ruff check src/          # Lint
poetry run ruff format src/         # Format
poetry build                        # Build wheel
```

### Registration and Usage

```python
# Register
from your_package import YourDataSource
spark.dataSource.register(YourDataSource)

# Batch read
df = spark.read.format("your-format").option("url", "...").load()

# Batch write
df.write.format("your-format").option("url", "...").save()

# Streaming read
df = spark.readStream.format("your-format").option("url", "...").load()

# Streaming write
df.writeStream.format("your-format").option("url", "...").start()
```

### Key Implementation Decisions

**Partitioning Strategy**: Choose based on data source characteristics
- Time-based: For APIs with temporal data (see [partitioning-patterns.md](references/partitioning-patterns.md))
- Token-range: For distributed databases (see [partitioning-patterns.md](references/partitioning-patterns.md))
- ID-range: For paginated APIs

**Authentication**: Support multiple methods in priority order
- Databricks Unity Catalog credentials
- Cloud default credentials (managed identity)
- Explicit credentials (service principal, API key, username/password)
- See [authentication-patterns.md](references/authentication-patterns.md)

**Type Conversion**: Map between Spark and external types
- Handle nulls, timestamps, UUIDs, collections
- See [type-conversion.md](references/type-conversion.md)

**Streaming Offsets**: Design for exactly-once semantics
- JSON-serializable offset class
- Non-overlapping partition boundaries
- See [streaming-patterns.md](references/streaming-patterns.md)

**Error Handling**: Implement retries and resilience
- Exponential backoff for retryable errors
- Circuit breakers for cascading failures
- See [error-handling.md](references/error-handling.md)

### Testing Approach

```python
import pytest
from unittest.mock import patch, Mock

@pytest.fixture
def spark():
    from pyspark.sql import SparkSession
    return SparkSession.builder.master("local[2]").getOrCreate()

def test_data_source_name():
    assert YourDataSource.name() == "your-format"

def test_writer_sends_data(spark):
    with patch('requests.post') as mock_post:
        mock_post.return_value = Mock(status_code=200)

        df = spark.createDataFrame([(1, "test")], ["id", "value"])
        df.write.format("your-format").option("url", "http://api").save()

        assert mock_post.called
```

### Code Review Checklist

Before implementing, ask:
1. Is this the simplest way to solve this problem?
2. Would a new developer understand this immediately?
3. Am I adding abstraction for real needs vs hypothetical flexibility?
4. Can I solve this with standard library?
5. Does this follow the established flat pattern?

### Common Mistakes to Avoid

- Creating abstract base classes for "reusability"
- Adding configuration frameworks or dependency injection
- Premature optimization before measuring performance
- Complex error handling hierarchies
- Importing heavy libraries at module level (import in methods)
- Using `python` command directly (always use `poetry run`)

### Reference Implementations

Study these for real-world patterns:
- [cyber-spark-data-connectors](https://github.com/alexott/cyber-spark-data-connectors) - Sentinel, Splunk, REST
- [spark-cassandra-data-source](https://github.com/alexott/spark-cassandra-data-source) - Token-range partitioning
- [pyspark-hubspot](https://github.com/dgomez04/pyspark-hubspot) - REST API pagination
- [pyspark-mqtt](https://github.com/databricks-industry-solutions/python-data-sources/tree/main/mqtt) - Streaming with TLS

## Usage

```
Create a Spark data source for reading from MongoDB with sharding support
Build a streaming connector for RabbitMQ with at-least-once delivery
Implement a batch writer for Snowflake with staged uploads
Write a data source for REST API with OAuth2 authentication and pagination
```

## Related

- databricks-testing: Test data sources on Databricks clusters
- databricks-spark-declarative-pipelines: Use custom sources in DLT pipelines
- python-dev: Python development best practices

## References

- [partitioning-patterns.md](references/partitioning-patterns.md) - Parallel reading strategies
- [authentication-patterns.md](references/authentication-patterns.md) - Multi-method auth implementations
- [type-conversion.md](references/type-conversion.md) - Bidirectional type mapping
- [streaming-patterns.md](references/streaming-patterns.md) - Offset management and watermarking
- [error-handling.md](references/error-handling.md) - Retries, circuit breakers, resilience
- [testing-patterns.md](references/testing-patterns.md) - Unit and integration testing
- [production-patterns.md](references/production-patterns.md) - Observability, security, validation
- [Official Databricks Documentation](https://docs.databricks.com/aws/en/pyspark/datasources)
- [Apache Spark Python DataSource Tutorial](https://spark.apache.org/docs/latest/api/python/tutorial/sql/python_data_source.html)
- [awesome-python-datasources](https://github.com/allisonwang-db/awesome-python-datasources) - directory of available implementations.
