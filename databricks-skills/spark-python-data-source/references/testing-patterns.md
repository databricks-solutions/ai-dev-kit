# Testing Patterns

Unit and integration testing strategies for Spark data sources.

## Basic Unit Tests

Test data source registration and initialization:

```python
import pytest
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark():
    """Create Spark session for tests."""
    return SparkSession.builder \
        .master("local[2]") \
        .appName("test") \
        .config("spark.sql.shuffle.partitions", "2") \
        .getOrCreate()

def test_data_source_name():
    """Test data source name registration."""
    assert YourDataSource.name() == "your-format"

def test_data_source_initialization():
    """Test data source can be initialized."""
    options = {"url": "http://api.example.com"}
    ds = YourDataSource(options)
    assert ds.options == options

def test_missing_required_option():
    """Test error on missing required option."""
    options = {}  # Missing required 'url'

    with pytest.raises(AssertionError, match="url is required"):
        YourDataSource(options)
```

## Mocking HTTP Requests

Test writers without external dependencies:

```python
from unittest.mock import patch, Mock
import pytest

@pytest.fixture
def basic_options():
    """Common options for tests."""
    return {
        "url": "http://api.example.com",
        "batch_size": "10"
    }

@pytest.fixture
def sample_schema():
    """Sample schema for tests."""
    from pyspark.sql.types import StructType, StructField, IntegerType, StringType
    return StructType([
        StructField("id", IntegerType(), False),
        StructField("name", StringType(), True)
    ])

def test_writer_sends_batch(spark, basic_options, sample_schema):
    """Test writer sends data in batches."""
    with patch('requests.post') as mock_post:
        mock_post.return_value = Mock(status_code=200)

        # Create test data
        df = spark.createDataFrame([
            (1, "Alice"),
            (2, "Bob"),
            (3, "Charlie")
        ], ["id", "name"])

        # Write using data source
        df.write.format("your-format").options(**basic_options).save()

        # Verify API was called
        assert mock_post.called
        assert mock_post.call_count > 0

def test_writer_respects_batch_size(spark, basic_options, sample_schema):
    """Test writer respects configured batch size."""
    with patch('requests.post') as mock_post:
        mock_post.return_value = Mock(status_code=200)

        # Create 25 rows with batch_size=10
        rows = [(i, f"name_{i}") for i in range(25)]
        df = spark.createDataFrame(rows, ["id", "name"])

        df.write.format("your-format").options(**basic_options).save()

        # Should make 3 calls: 10 + 10 + 5
        assert mock_post.call_count == 3
```

## Testing Readers

Mock external API responses:

```python
def test_reader_fetches_data(spark, basic_options):
    """Test reader fetches and converts data."""
    with patch('requests.get') as mock_get:
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]
        mock_get.return_value = mock_response

        # Read using data source
        df = spark.read.format("your-format").options(**basic_options).load()

        # Verify data
        rows = df.collect()
        assert len(rows) == 2
        assert rows[0]["id"] == 1
        assert rows[0]["name"] == "Alice"

def test_reader_handles_empty_response(spark, basic_options):
    """Test reader handles empty response."""
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        df = spark.read.format("your-format").options(**basic_options).load()

        assert df.count() == 0
```

## Testing Partitioning

Test partition creation logic:

```python
def test_partitions_created(basic_options, sample_schema):
    """Test correct number of partitions created."""
    options = {**basic_options, "num_partitions": "4"}

    reader = YourBatchReader(options, sample_schema)
    partitions = reader.partitions()

    assert len(partitions) == 4

def test_partition_ranges_non_overlapping():
    """Test partitions have non-overlapping ranges."""
    from datetime import datetime, timedelta

    reader = TimeBasedReader(options, schema)
    partitions = reader.partitions()

    # Check no gaps or overlaps
    for i in range(len(partitions) - 1):
        current_end = partitions[i].end_time
        next_start = partitions[i + 1].start_time

        # Next partition should start right after current ends
        assert next_start >= current_end
```

## Testing Streaming

Test offset management and streaming logic:

```python
def test_initial_offset():
    """Test initial offset is correct."""
    from datetime import datetime

    reader = YourStreamReader(options, schema)
    initial = reader.initialOffset()

    # Should be valid JSON
    import json
    offset_dict = json.loads(initial)

    assert "timestamp" in offset_dict

def test_latest_offset_advances():
    """Test latest offset advances over time."""
    reader = YourStreamReader(options, schema)

    offset1 = reader.latestOffset()
    import time
    time.sleep(0.1)
    offset2 = reader.latestOffset()

    # Offset should advance
    assert offset2 > offset1 or offset2 != offset1

def test_partitions_non_overlapping(basic_options, sample_schema):
    """Test streaming partitions don't overlap."""
    reader = YourStreamReader(basic_options, sample_schema)

    start = reader.initialOffset()
    end = reader.latestOffset()

    partitions = reader.partitions(start, end)

    # Verify no overlaps
    for i in range(len(partitions) - 1):
        assert partitions[i].end_time < partitions[i + 1].start_time
```

## Testing Type Conversion

Test type mapping and conversion:

```python
def test_convert_timestamp():
    """Test timestamp conversion."""
    from datetime import datetime
    from pyspark.sql.types import TimestampType

    dt = datetime(2024, 1, 1, 12, 0, 0)
    result = convert_external_to_spark(dt, TimestampType())

    assert isinstance(result, datetime)
    assert result == dt

def test_convert_null_values():
    """Test null value handling."""
    from pyspark.sql.types import StringType

    result = convert_external_to_spark(None, StringType())
    assert result is None

def test_convert_invalid_type():
    """Test error on invalid type conversion."""
    from pyspark.sql.types import IntegerType

    with pytest.raises(ValueError, match="Cannot convert"):
        convert_external_to_spark("not_a_number", IntegerType())
```

## Integration Tests with Testcontainers

Run end-to-end tests against real systems:

```python
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for integration tests."""
    with PostgresContainer("postgres:15") as container:
        yield container

@pytest.fixture
def postgres_connection(postgres_container):
    """Create connection to test database."""
    import psycopg2

    conn = psycopg2.connect(postgres_container.get_connection_url())
    cursor = conn.cursor()

    # Create test table
    cursor.execute("""
        CREATE TABLE test_data (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            value INTEGER
        )
    """)
    conn.commit()

    yield conn

    conn.close()

def test_write_integration(spark, postgres_container, postgres_connection):
    """Integration test for writing to PostgreSQL."""
    # Create test data
    df = spark.createDataFrame([
        (1, "Alice", 100),
        (2, "Bob", 200)
    ], ["id", "name", "value"])

    # Write using data source
    df.write.format("your-format") \
        .option("url", postgres_container.get_connection_url()) \
        .option("table", "test_data") \
        .save()

    # Verify data written
    cursor = postgres_connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM test_data")
    count = cursor.fetchone()[0]

    assert count == 2

def test_read_integration(spark, postgres_container, postgres_connection):
    """Integration test for reading from PostgreSQL."""
    # Insert test data
    cursor = postgres_connection.cursor()
    cursor.execute("INSERT INTO test_data (name, value) VALUES ('Alice', 100)")
    cursor.execute("INSERT INTO test_data (name, value) VALUES ('Bob', 200)")
    postgres_connection.commit()

    # Read using data source
    df = spark.read.format("your-format") \
        .option("url", postgres_container.get_connection_url()) \
        .option("table", "test_data") \
        .load()

    # Verify data
    assert df.count() == 2
    names = [row["name"] for row in df.collect()]
    assert "Alice" in names
    assert "Bob" in names
```

## Performance Tests

Test performance characteristics:

```python
import time

def test_write_performance(spark, basic_options):
    """Test write performance meets requirements."""
    # Create large dataset
    rows = [(i, f"name_{i}") for i in range(10000)]
    df = spark.createDataFrame(rows, ["id", "name"])

    start = time.time()
    df.write.format("your-format").options(**basic_options).save()
    duration = time.time() - start

    # Should complete in reasonable time
    assert duration < 30.0  # 30 seconds

    # Calculate throughput
    throughput = len(rows) / duration
    print(f"Write throughput: {throughput:.0f} rows/second")

def test_partition_read_parallelism(spark, basic_options):
    """Test reads execute in parallel."""
    options = {**basic_options, "num_partitions": "4"}

    df = spark.read.format("your-format").options(**options).load()

    # Check partition count
    assert df.rdd.getNumPartitions() == 4
```

## Test Fixtures and Utilities

Reusable test fixtures:

```python
import pytest
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark():
    """Shared Spark session."""
    return SparkSession.builder \
        .master("local[2]") \
        .appName("test") \
        .config("spark.sql.shuffle.partitions", "2") \
        .getOrCreate()

@pytest.fixture
def sample_dataframe(spark):
    """Sample DataFrame for testing."""
    return spark.createDataFrame([
        (1, "Alice", 25),
        (2, "Bob", 30),
        (3, "Charlie", 35)
    ], ["id", "name", "age"])

@pytest.fixture
def temp_output_path(tmp_path):
    """Temporary output path."""
    return str(tmp_path / "output")

def assert_dataframes_equal(df1, df2):
    """Assert two DataFrames are equal."""
    assert df1.schema == df2.schema
    assert df1.count() == df2.count()

    rows1 = sorted(df1.collect())
    rows2 = sorted(df2.collect())

    assert rows1 == rows2
```

## Test Organization

Structure tests by functionality:

```
tests/
├── unit/
│   ├── test_datasource.py       # DataSource class tests
│   ├── test_reader.py            # Reader tests
│   ├── test_writer.py            # Writer tests
│   ├── test_partitioning.py      # Partitioning logic
│   └── test_type_conversion.py   # Type conversion
├── integration/
│   ├── test_read_integration.py  # End-to-end read tests
│   ├── test_write_integration.py # End-to-end write tests
│   └── test_streaming.py         # Streaming tests
├── performance/
│   └── test_performance.py       # Performance tests
└── conftest.py                   # Shared fixtures
```

## Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/unit/test_writer.py

# Run specific test
poetry run pytest tests/unit/test_writer.py::test_writer_sends_batch

# Run with coverage
poetry run pytest --cov=your_package --cov-report=html

# Run only unit tests
poetry run pytest tests/unit/

# Run with verbose output
poetry run pytest -v

# Run with print statements
poetry run pytest -s
```
