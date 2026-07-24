---
name: spark-python-data-source
description: Build custom Python data sources for Apache Spark using the PySpark DataSource API — batch and streaming readers/writers for external systems. Use this skill whenever someone wants to connect Spark to an external system (database, API, message queue, custom protocol), build a Spark connector or plugin in Python, implement a DataSourceReader or DataSourceWriter, pull data from or push data to a system via Spark, or work with the PySpark DataSource API in any way. Even if they just say "read from X in Spark" or "write DataFrame to Y" and there's no native connector, this skill applies.
---

# spark-python-data-source

Build custom Python data sources for Apache Spark 4.0+ to read from and write to external systems in batch and streaming modes.

## Instructions

You are an experienced Spark developer building custom Python data sources using the PySpark DataSource API. Follow these principles and patterns.

### Core Architecture

Each data source follows a flat, single-level inheritance structure:

1. **DataSource class** — entry point that returns readers/writers
2. **Base Reader/Writer classes** — shared logic for options and data processing
3. **Batch classes** — inherit from base + `DataSourceReader`/`DataSourceWriter`
4. **Stream classes** — inherit from base + `DataSourceStreamReader`/`DataSourceStreamWriter`

See [implementation-template.md](references/implementation-template.md) for the full annotated skeleton covering all four modes (batch read/write, stream read/write).

### Spark-Specific Design Constraints

These are specific to the PySpark DataSource API and its driver/executor architecture — general Python best practices (clean code, minimal dependencies, no premature abstraction) still apply but aren't repeated here.

**Flat single-level inheritance only.** PySpark serializes reader/writer instances to ship them to executors. Complex inheritance hierarchies and abstract base classes break serialization and make cross-process debugging painful. Use one shared base class mixed with the PySpark interface (e.g., `class YourBatchWriter(YourWriter, DataSourceWriter)`).

**Import third-party libraries inside executor methods.** The `read()` and `write()` methods run on remote executor processes that don't share the driver's Python environment. Top-level imports from the driver won't be available on executors — always import libraries like `requests` or database drivers inside the methods that run on workers.

**Minimize dependencies.** Every package you add must be installed on all executor nodes in the cluster, not just the driver. Prefer the standard library; when external packages are needed, keep them few and well-known.

**No async/await** unless the external system's SDK is async-only. The PySpark DataSource API is synchronous, so async adds complexity with no benefit.

### Project Setup

Create a Python project using a packaging tool such as `uv`, `poetry`, or `hatch`. Examples use `uv` (substitute your tool of choice):

```bash
uv init your-datasource
cd your-datasource
uv add pyspark pytest pytest-spark
```

```
your-datasource/
├── pyproject.toml
├── src/
│   └── your_datasource/
│       ├── __init__.py
│       └── datasource.py
└── tests/
    ├── conftest.py
    └── test_datasource.py
```

Run all commands through the packaging tool so they execute within the correct virtual environment:

```bash
uv run pytest                       # Run tests
uv run ruff check src/              # Lint
uv run ruff format src/             # Format
uv build                            # Build wheel
```

### Key Implementation Decisions

**Partitioning Strategy** — choose based on data source characteristics:
- Time-based: for APIs with temporal data
- Token-range: for distributed databases
- ID-range: for paginated APIs
- See [partitioning-patterns.md](references/partitioning-patterns.md) for implementations of each strategy

**Authentication** — support multiple methods in priority order:
- Databricks Unity Catalog credentials
- Cloud default credentials (managed identity)
- Explicit credentials (service principal, API key, username/password)
- See [authentication-patterns.md](references/authentication-patterns.md) for patterns with fallback chains

**Type Conversion** — map between Spark and external types:
- Handle nulls, timestamps, UUIDs, collections
- See [type-conversion.md](references/type-conversion.md) for bidirectional mapping tables and helpers

**Streaming Offsets** — design for exactly-once semantics:
- JSON-serializable offset class
- Non-overlapping partition boundaries
- See [streaming-patterns.md](references/streaming-patterns.md) for offset tracking and watermark patterns

**Error Handling** — implement retries and resilience:
- Exponential backoff for transient failures (network, rate limits)
- Circuit breakers for cascading failures
- See [error-handling.md](references/error-handling.md) for retry decorators and failure classification

### Testing

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

See [testing-patterns.md](references/testing-patterns.md) for unit/integration test patterns, fixtures, and running tests.

### Reference Implementations

Study these for real-world patterns:
- [cyber-spark-data-connectors](https://github.com/alexott/cyber-spark-data-connectors) — Sentinel, Splunk, REST
- [spark-cassandra-data-source](https://github.com/alexott/spark-cassandra-data-source) — Token-range partitioning
- [pyspark-hubspot](https://github.com/dgomez04/pyspark-hubspot) — REST API pagination
- [pyspark-mqtt](https://github.com/databricks-industry-solutions/python-data-sources/tree/main/mqtt) — Streaming with TLS

## Example Prompts

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

- [implementation-template.md](references/implementation-template.md) — Full annotated skeleton; read when starting a new data source
- [partitioning-patterns.md](references/partitioning-patterns.md) — Read when the source supports parallel reads and you need to split work across executors
- [authentication-patterns.md](references/authentication-patterns.md) — Read when the external system requires credentials or tokens
- [type-conversion.md](references/type-conversion.md) — Read when mapping between Spark types and the external system's type system
- [streaming-patterns.md](references/streaming-patterns.md) — Read when implementing `DataSourceStreamReader` or `DataSourceStreamWriter`
- [error-handling.md](references/error-handling.md) — Read when adding retry logic or handling transient failures
- [testing-patterns.md](references/testing-patterns.md) — Read when writing tests; covers unit, integration, and performance testing
- [production-patterns.md](references/production-patterns.md) — Read when hardening for production: observability, security, input validation
- [Official Databricks Documentation](https://docs.databricks.com/aws/en/pyspark/datasources)
- [Apache Spark Python DataSource Tutorial](https://spark.apache.org/docs/latest/api/python/tutorial/sql/python_data_source.html)
- [awesome-python-datasources](https://github.com/allisonwang-db/awesome-python-datasources) — Directory of community implementations
