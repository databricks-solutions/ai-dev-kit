# Streaming Patterns

Offset management and streaming implementation patterns for exactly-once semantics.

## Basic Offset Implementation

Simple JSON-serializable offset:

```python
class SimpleOffset:
    """Basic offset with single timestamp field."""

    def __init__(self, timestamp):
        self.timestamp = timestamp

    def json(self):
        """Serialize to JSON string."""
        import json
        return json.dumps({"timestamp": self.timestamp})

    @staticmethod
    def from_json(json_str):
        """Deserialize from JSON string."""
        import json
        data = json.loads(json_str)
        return SimpleOffset(data["timestamp"])
```

## Multi-Field Offset

Complex offset with multiple fields:

```python
class MultiFieldOffset:
    """Offset with timestamp, sequence ID, and partition."""

    def __init__(self, timestamp, sequence_id, partition_id):
        self.timestamp = timestamp
        self.sequence_id = sequence_id
        self.partition_id = partition_id

    def json(self):
        import json
        return json.dumps({
            "timestamp": self.timestamp,
            "sequence_id": self.sequence_id,
            "partition_id": self.partition_id
        })

    @staticmethod
    def from_json(json_str):
        import json
        data = json.loads(json_str)
        return MultiFieldOffset(
            timestamp=data["timestamp"],
            sequence_id=data["sequence_id"],
            partition_id=data["partition_id"]
        )

    def __lt__(self, other):
        """Enable offset comparison for ordering."""
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        if self.sequence_id != other.sequence_id:
            return self.sequence_id < other.sequence_id
        return self.partition_id < other.partition_id
```

## Stream Reader Implementation

Complete streaming reader with offset management:

```python
from pyspark.sql.datasource import DataSourceStreamReader

class YourStreamReader(DataSourceStreamReader):
    def __init__(self, options, schema):
        super().__init__(options, schema)

        # Parse start time option
        start_time = options.get("start_time", "latest")

        if start_time == "latest":
            from datetime import datetime, timezone
            self.start_time = datetime.now(timezone.utc).isoformat()

        elif start_time == "earliest":
            # Query for earliest timestamp (one-time cost)
            self.start_time = self._get_earliest_timestamp()

        else:
            # Validate ISO 8601 format
            from datetime import datetime
            datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            self.start_time = start_time

        # Partition duration (e.g., 1 hour)
        self.partition_duration = int(options.get("partition_duration", "3600"))

    def _get_earliest_timestamp(self):
        """Find earliest data timestamp for 'earliest' option."""
        from datetime import datetime, timezone

        timestamp_column = self.options.get("timestamp_column", "timestamp")
        query = f"{self.query} | summarize earliest=min({timestamp_column})"

        response = self._execute_query(query, timespan=None)

        if response.tables and response.tables[0].rows:
            earliest_value = response.tables[0].rows[0][0]
            if earliest_value:
                if isinstance(earliest_value, datetime):
                    return earliest_value.isoformat()
                return str(earliest_value)

        # Fallback to current time
        return datetime.now(timezone.utc).isoformat()

    def initialOffset(self):
        """
        Return initial offset (start time minus 1 microsecond).

        Subtract 1µs to compensate for +1µs in partitions() method,
        preventing overlap between batches.
        """
        from datetime import datetime, timedelta

        start_dt = datetime.fromisoformat(self.start_time.replace("Z", "+00:00"))
        adjusted = start_dt - timedelta(microseconds=1)
        return SimpleOffset(adjusted.isoformat()).json()

    def latestOffset(self):
        """Return latest offset (current time)."""
        from datetime import datetime, timezone

        current_time = datetime.now(timezone.utc).isoformat()
        return SimpleOffset(current_time).json()

    def partitions(self, start, end):
        """
        Create non-overlapping partitions for offset range.

        Adds 1µs to start to prevent overlap with previous batch.
        """
        from datetime import datetime, timedelta

        start_offset = SimpleOffset.from_json(start)
        end_offset = SimpleOffset.from_json(end)

        start_time = datetime.fromisoformat(start_offset.timestamp.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end_offset.timestamp.replace("Z", "+00:00"))

        # Add 1µs to prevent overlap with previous batch
        # This works with -1µs in initialOffset() to ensure:
        # - Initial batch: (start - 1µs) + 1µs = start (correct)
        # - Subsequent batches: previous_end + 1µs (no overlap)
        start_time = start_time + timedelta(microseconds=1)

        # Create fixed-duration partitions
        partitions = []
        current = start_time
        delta = timedelta(seconds=self.partition_duration)

        while current < end_time:
            next_time = min(current + delta, end_time)
            partitions.append(TimeRangePartition(current, next_time))
            current = next_time + timedelta(microseconds=1)  # No overlap

        return partitions if partitions else [TimeRangePartition(start_time, end_time)]

    def commit(self, end):
        """Called when batch is successfully processed."""
        # Spark handles checkpointing - usually no action needed
        pass

    def read(self, partition):
        """Read data for partition time range."""
        response = self._query_api(
            start=partition.start_time,
            end=partition.end_time
        )

        for item in response:
            yield self._convert_to_row(item)
```

## Watermarking Support

Support for event-time watermarking:

```python
class WatermarkedStreamReader(DataSourceStreamReader):
    def __init__(self, options, schema):
        super().__init__(options, schema)

        # Watermark configuration
        self.watermark_column = options.get("watermark_column")
        self.watermark_delay = options.get("watermark_delay", "10 minutes")

    def read(self, partition):
        """Read with event-time watermarking."""
        from datetime import datetime

        response = self._query_api(
            start=partition.start_time,
            end=partition.end_time
        )

        for item in response:
            row = self._convert_to_row(item)

            # Validate watermark column exists
            if self.watermark_column:
                if not hasattr(row, self.watermark_column):
                    raise ValueError(
                        f"Watermark column '{self.watermark_column}' not found in row"
                    )

                # Ensure watermark column is timestamp
                watermark_value = getattr(row, self.watermark_column)
                if not isinstance(watermark_value, datetime):
                    raise ValueError(
                        f"Watermark column must be timestamp, got {type(watermark_value)}"
                    )

            yield row
```

## Stateful Streaming

Track state across batches:

```python
class StatefulStreamReader(DataSourceStreamReader):
    def __init__(self, options, schema):
        super().__init__(options, schema)

        # State management
        self.checkpoint_location = options.get("checkpoint_location")
        self._state = {}

    def _load_state(self):
        """Load state from checkpoint location."""
        import json
        import os

        if not self.checkpoint_location:
            return {}

        state_file = os.path.join(self.checkpoint_location, "reader_state.json")

        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                return json.load(f)

        return {}

    def _save_state(self):
        """Save state to checkpoint location."""
        import json
        import os

        if not self.checkpoint_location:
            return

        os.makedirs(self.checkpoint_location, exist_ok=True)
        state_file = os.path.join(self.checkpoint_location, "reader_state.json")

        with open(state_file, 'w') as f:
            json.dump(self._state, f)

    def initialOffset(self):
        """Load state and return initial offset."""
        self._state = self._load_state()

        # Check if we have previous state
        if "last_offset" in self._state:
            return self._state["last_offset"]

        # First run - use configured start time
        return self._create_initial_offset()

    def commit(self, end):
        """Save state after successful batch."""
        self._state["last_offset"] = end
        self._state["last_commit_time"] = datetime.now().isoformat()
        self._save_state()
```

## Exactly-Once Semantics

Ensure exactly-once delivery with idempotent writes:

```python
class ExactlyOnceWriter(DataSourceStreamWriter):
    def __init__(self, options, schema):
        super().__init__(options, schema)
        self.enable_idempotency = options.get("enable_idempotency", "true").lower() == "true"

    def write(self, iterator):
        """Write with idempotency key."""
        import hashlib
        from pyspark import TaskContext

        context = TaskContext.get()
        partition_id = context.partitionId()
        batch_id = getattr(context, 'batchId', lambda: 0)()

        for row in iterator:
            # Generate idempotency key from batch_id + partition_id + row content
            row_dict = row.asDict()

            if self.enable_idempotency:
                idempotency_key = self._generate_idempotency_key(
                    batch_id,
                    partition_id,
                    row_dict
                )
                row_dict["_idempotency_key"] = idempotency_key

            # Write with idempotency check
            self._write_with_idempotency_check(row_dict)

    def _generate_idempotency_key(self, batch_id, partition_id, row_dict):
        """Generate deterministic idempotency key."""
        import hashlib
        import json

        key_data = {
            "batch_id": batch_id,
            "partition_id": partition_id,
            "row": row_dict
        }

        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _write_with_idempotency_check(self, row_dict):
        """Write only if idempotency key not seen before."""
        idempotency_key = row_dict.get("_idempotency_key")

        if idempotency_key:
            # Check if already written (implementation depends on target system)
            if self._is_already_written(idempotency_key):
                return  # Skip duplicate

        # Write data
        self._write_data(row_dict)

    def commit(self, messages, batchId):
        """Commit batch after all writes succeed."""
        # Log successful batch
        print(f"Batch {batchId} committed successfully")

    def abort(self, messages, batchId):
        """Handle failed batch."""
        # Log failed batch
        print(f"Batch {batchId} aborted")
```

## Monitoring and Progress

Track streaming progress:

```python
class MonitoredStreamReader(DataSourceStreamReader):
    def read(self, partition):
        """Read with progress tracking."""
        from datetime import datetime

        start_time = datetime.now()
        row_count = 0

        for row in self._read_partition(partition):
            row_count += 1
            yield row

        duration = (datetime.now() - start_time).total_seconds()

        # Log metrics
        self._log_partition_metrics(
            partition_id=partition.partition_id,
            row_count=row_count,
            duration=duration
        )

    def _log_partition_metrics(self, partition_id, row_count, duration):
        """Log partition processing metrics."""
        print(f"Partition {partition_id}: {row_count} rows in {duration:.2f}s")
```

## Best Practices

1. **Non-Overlapping Partitions**: Use microsecond adjustments to prevent duplicates
2. **Idempotency**: Generate deterministic keys for exactly-once semantics
3. **State Management**: Store offsets in Spark checkpoints
4. **Watermarking**: Support event-time processing for late data
5. **Monitoring**: Track batch progress and lag metrics
6. **Error Handling**: Implement retry logic for transient failures
7. **Backpressure**: Respect rate limits with appropriate partition sizing
