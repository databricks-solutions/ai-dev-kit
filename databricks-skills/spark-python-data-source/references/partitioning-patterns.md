# Partitioning Patterns

Strategies for distributing reads across Spark executors for parallel processing.

## Time-Based Partitioning

For APIs with temporal data or streaming sources.

### Fixed Duration Partitions

```python
from pyspark.sql.datasource import InputPartition
from datetime import datetime, timedelta

class TimeRangePartition(InputPartition):
    def __init__(self, start_time, end_time):
        self.start_time = start_time
        self.end_time = end_time

class TimeBasedReader:
    def __init__(self, options, schema):
        self.partition_duration = int(options.get("partition_duration", "3600"))  # seconds
        # Parse start/end time from options

    def partitions(self):
        """Split time range into fixed-duration partitions."""
        partitions = []
        current = self.start_time
        delta = timedelta(seconds=self.partition_duration)

        while current < self.end_time:
            next_time = min(current + delta, self.end_time)
            partitions.append(TimeRangePartition(current, next_time))
            current = next_time

        return partitions

    def read(self, partition):
        """Query data for specific time range."""
        response = self._query_api(
            start=partition.start_time,
            end=partition.end_time
        )
        for item in response:
            yield self._convert_to_row(item)
```

### Auto-Subdividing for Large Results

Handle APIs with result size limits by automatically subdividing large partitions:

```python
class AutoSubdivideReader:
    def __init__(self, options, schema):
        self.min_partition_seconds = int(options.get("min_partition_seconds", "60"))
        self.max_retries = int(options.get("max_retries", "5"))

    def read(self, partition):
        """Read with automatic subdivision on size limit errors."""
        try:
            response = self._execute_query(partition.start_time, partition.end_time)

            # Check if response is partial due to size limits
            if self._is_size_limit_error(response):
                yield from self._read_with_subdivision(partition)
                return

            yield from self._process_response(response)

        except Exception as e:
            raise

    def _read_with_subdivision(self, partition):
        """Recursively subdivide large partitions."""
        duration = (partition.end_time - partition.start_time).total_seconds()

        if duration <= self.min_partition_seconds:
            raise Exception(
                f"Cannot subdivide further. Duration {duration}s at minimum. "
                f"Consider more selective query or increase min_partition_seconds."
            )

        # Split in half
        midpoint = partition.start_time + timedelta(seconds=duration / 2)

        first_half = TimeRangePartition(partition.start_time, midpoint)
        second_half = TimeRangePartition(midpoint, partition.end_time)

        yield from self.read(first_half)
        yield from self.read(second_half)

    def _is_size_limit_error(self, response):
        """Detect result size limit errors."""
        size_limit_codes = [
            "QueryExecutionResultSizeLimitExceeded",
            "ResponsePayloadTooLarge",
            "E_QUERY_RESULT_SET_TOO_LARGE",
        ]

        if hasattr(response, "error") and response.error:
            if response.error.code in size_limit_codes:
                return True

            error_str = str(response.error).lower()
            return any(p in error_str for p in ["size limit", "too large", "exceed"])

        return False
```

## Token-Range Partitioning

For distributed databases using consistent hashing (Cassandra, ScyllaDB).

### Cassandra Token-Range Pattern

```python
from collections import namedtuple

class TokenRangePartition(InputPartition):
    def __init__(self, partition_id, start_token, end_token, pk_columns,
                 is_wrap_around=False, min_token=None):
        self.partition_id = partition_id
        self.start_token = start_token  # None = unbounded
        self.end_token = end_token      # None = unbounded
        self.pk_columns = pk_columns
        self.is_wrap_around = is_wrap_around
        self.min_token = min_token

class TokenRangeReader:
    def _get_token_ranges(self, token_map):
        """Compute token ranges from cluster token ring."""
        if not token_map or not token_map.ring:
            return []

        TokenRange = namedtuple('TokenRange', ['start', 'end'])
        ranges = []
        ring = sorted(token_map.ring)

        for i in range(len(ring)):
            start = ring[i]
            end = ring[(i + 1) % len(ring)]  # Wrap around
            ranges.append(TokenRange(start=start, end=end))

        return ranges

    def partitions(self):
        """Create partitions following TokenRangesScan.java logic."""
        if not self.token_ranges:
            return []

        partitions = []
        sorted_ranges = sorted(self.token_ranges)
        partition_id = 0

        min_token_obj = sorted_ranges[0].start
        min_token = min_token_obj.value if hasattr(min_token_obj, 'value') else str(min_token_obj)

        for i, token_range in enumerate(sorted_ranges):
            start_value = token_range.start.value if hasattr(token_range.start, 'value') else str(token_range.start)
            end_value = token_range.end.value if hasattr(token_range.end, 'value') else str(token_range.end)

            if start_value == end_value:
                # Case 1: Single-node cluster (entire ring)
                partition = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=min_token,
                    end_token=None,  # Unbounded
                    pk_columns=self.pk_columns,
                    is_wrap_around=True,
                    min_token=min_token
                )
                partitions.append(partition)
                partition_id += 1

            elif i == 0:
                # Case 2: First range - split into TWO partitions
                # Partition 1: token <= minToken (wrap-around)
                partition1 = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=None,
                    end_token=min_token,
                    pk_columns=self.pk_columns,
                    is_wrap_around=True,
                    min_token=min_token
                )
                partitions.append(partition1)
                partition_id += 1

                # Partition 2: token > start AND token <= end
                partition2 = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=start_value,
                    end_token=end_value,
                    pk_columns=self.pk_columns,
                    is_wrap_around=False,
                    min_token=min_token
                )
                partitions.append(partition2)
                partition_id += 1

            elif end_value == min_token:
                # Case 3: Range ending at minToken - no upper bound
                partition = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=start_value,
                    end_token=None,
                    pk_columns=self.pk_columns,
                    is_wrap_around=False,
                    min_token=min_token
                )
                partitions.append(partition)
                partition_id += 1

            else:
                # Case 4: Normal range - both bounds
                partition = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=start_value,
                    end_token=end_value,
                    pk_columns=self.pk_columns,
                    is_wrap_around=False,
                    min_token=min_token
                )
                partitions.append(partition)
                partition_id += 1

        return partitions

    def read(self, partition):
        """Build query with token range predicates."""
        pk_cols_str = ", ".join(partition.pk_columns)

        # Build WHERE clause based on bounds
        if partition.start_token is None:
            where_clause = f"token({pk_cols_str}) <= {partition.end_token}"
        elif partition.end_token is None:
            where_clause = f"token({pk_cols_str}) > {partition.start_token}"
        else:
            where_clause = (
                f"token({pk_cols_str}) > {partition.start_token} AND "
                f"token({pk_cols_str}) <= {partition.end_token}"
            )

        query = f"SELECT {columns} FROM {table} WHERE {where_clause}"

        # Execute and yield results
        for row in self._execute_query(query):
            yield row
```

## ID-Range Partitioning

For APIs with pagination or sequential IDs.

```python
class IdRangePartition(InputPartition):
    def __init__(self, partition_id, start_id, end_id):
        self.partition_id = partition_id
        self.start_id = start_id
        self.end_id = end_id

class IdRangeReader:
    def __init__(self, options, schema):
        self.num_partitions = int(options.get("num_partitions", "4"))
        self.page_size = int(options.get("page_size", "1000"))

    def partitions(self):
        """Split by ID ranges."""
        # Get total count from API
        total = self._get_total_count()
        partition_size = total // self.num_partitions

        partitions = []
        for i in range(self.num_partitions):
            start_id = i * partition_size
            end_id = (i + 1) * partition_size if i < self.num_partitions - 1 else total
            partitions.append(IdRangePartition(i, start_id, end_id))

        return partitions

    def read(self, partition):
        """Paginate through ID range."""
        current_id = partition.start_id

        while current_id < partition.end_id:
            response = self._query_api(
                start_id=current_id,
                limit=self.page_size
            )

            for item in response.items:
                yield self._convert_to_row(item)

            current_id += self.page_size
```

## Partition Count Guidelines

**For Batch Reads:**
- Start with 2-4x number of executor cores
- Adjust based on data volume and partition size
- Consider external system load limits

**For Streaming Reads:**
- Use fixed-duration partitions (e.g., 1 hour)
- Let Spark handle parallelism across micro-batches
- Balance latency vs throughput

**For Token-Range:**
- One partition per token range (determined by cluster)
- Naturally distributes based on data distribution
- May split first range into two partitions

## Performance Considerations

1. **Partition Size**: Aim for 128MB - 1GB per partition
2. **API Rate Limits**: Respect rate limits with concurrency controls
3. **Network Overhead**: Larger partitions reduce round-trips
4. **Skew Handling**: Monitor for data skew, repartition if needed
