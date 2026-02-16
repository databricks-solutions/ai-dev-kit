# Spark Python Data Source Skill

Build custom Python data sources for Apache Spark 4.0+ that read from and write to external systems.

## Overview

This skill guides you through building production-grade Spark Python data sources using the PySpark DataSource API, following the **SIMPLE over CLEVER** philosophy with flat, maintainable patterns.

## Structure

```
spark-python-data-source/
├── skill.md                          # Main skill specification
├── README.md                         # This file
└── references/                       # Detailed pattern documentation
    ├── partitioning-patterns.md      # Parallel reading strategies
    ├── authentication-patterns.md    # Multi-method authentication
    ├── type-conversion.md            # Bidirectional type mapping
    ├── streaming-patterns.md         # Offset management & exactly-once
    ├── error-handling.md             # Retries, circuit breakers, resilience
    ├── testing-patterns.md           # Unit & integration testing
    └── production-patterns.md        # Observability, security, validation
```

## Quick Start

The skill teaches you to build data sources with this pattern:

1. **DataSource** - Entry point returning readers/writers
2. **Base Reader/Writer** - Shared logic and options
3. **Batch classes** - Inherit base + `DataSourceReader`/`DataSourceWriter`
4. **Stream classes** - Inherit base + `DataSourceStreamReader`/`DataSourceStreamWriter`

## Core Principles

- ✅ **Flat single-level inheritance**
- ✅ **Direct implementations, no abstractions**
- ✅ **Standard library first, minimal dependencies**
- ❌ **No abstract base classes or factories**
- ❌ **No complex configuration frameworks**
- ❌ **No premature optimization**

## Key Topics Covered

### Partitioning Strategies
- Time-based partitioning with auto-subdivision
- Token-range partitioning for distributed databases
- ID-range partitioning for paginated APIs

### Authentication
- Unity Catalog service credentials
- Cloud default credentials (managed identity)
- Service principal, API key, username/password
- Multi-cloud support (Azure public/government/china)

### Streaming
- Offset management with exactly-once semantics
- Non-overlapping partition boundaries
- Watermarking and late data handling
- Idempotent writes

### Error Handling
- Exponential backoff with jitter
- Circuit breakers for cascading failures
- Graceful degradation and fallback strategies
- Dead letter queues for failed records

### Testing
- Unit tests with mocking
- Integration tests with testcontainers
- Performance testing
- Fixture organization

### Production
- Structured logging and metrics
- Secrets management
- Input validation and sanitization
- Resource cleanup and health checks

## Requirements

- **Python**: 3.10+
- **Spark**: 4.0.1+ (PySpark DataSource API)
- **Poetry**: For dependency management
- **pytest + pytest-spark**: For testing

## Reference Implementations

Study these real-world examples:

- [cyber-spark-data-connectors](https://github.com/alexott/cyber-spark-data-connectors) - Microsoft Sentinel, Splunk, REST API
- [spark-cassandra-data-source](https://github.com/alexott/spark-cassandra-data-source) - Cassandra with token-range partitioning
- [pyspark-hubspot](https://github.com/dgomez04/pyspark-hubspot) - REST API with pagination
- [pyspark-mqtt](https://github.com/alexott/dbx-python-data-sources/tree/main/mqtt) - Streaming with TLS

## Usage Examples

```bash
# Create a data source for MongoDB with sharding
"Build Spark data source for MongoDB with sharding support"

# Streaming connector with guarantees
"Create streaming connector for RabbitMQ with at-least-once delivery"

# Batch writer with optimization
"Implement batch writer for Snowflake with staged uploads"

# Complex authentication
"Write data source for REST API with OAuth2 and pagination"
```

## Related Skills

- **databricks-testing**: Test data sources on Databricks clusters
- **spark-declarative-pipelines**: Use custom sources in DLT pipelines
- **python-dev**: Python development best practices

## Documentation

- [Official Databricks Docs](https://docs.databricks.com/aws/en/pyspark/datasources)
- [Apache Spark Tutorial](https://spark.apache.org/docs/latest/api/python/tutorial/sql/python_data_source.html)
- [PySpark API Reference](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/datasource.html)

## License

Part of the Databricks AI Dev Kit skills library.
