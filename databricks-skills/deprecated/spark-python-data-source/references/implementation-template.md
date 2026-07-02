# Implementation Template

Full skeleton for a Python data source covering all four modes: batch read, batch write, stream read, stream write. Adapt to your needs — most connectors only implement a subset.

```python
from pyspark.sql.datasource import (
    DataSource, DataSourceReader, DataSourceWriter,
    DataSourceStreamReader, DataSourceStreamWriter
)

# 1. DataSource class — entry point that returns readers/writers
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

# 2. Base Writer — shared logic for batch and stream writing
#    Plain class (not a DataSourceWriter yet) so batch/stream
#    subclasses can mix it in with the right PySpark base.
class YourWriter:
    def __init__(self, options, schema=None):
        self.url = options.get("url")
        assert self.url, "url is required"
        self.batch_size = int(options.get("batch_size", "50"))
        self.schema = schema

    def write(self, iterator):
        # Import here — this runs on executors, not the driver.
        # Executor processes don't share the driver's module state.
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

# 3. Batch Writer — inherits shared logic + PySpark interface
class YourBatchWriter(YourWriter, DataSourceWriter):
    pass

# 4. Stream Writer — adds commit/abort for micro-batch semantics
class YourStreamWriter(YourWriter, DataSourceStreamWriter):
    def commit(self, messages, batchId):
        pass

    def abort(self, messages, batchId):
        pass

# 5. Base Reader — shared logic for batch and stream reading
class YourReader:
    def __init__(self, options, schema):
        self.url = options.get("url")
        assert self.url, "url is required"
        self.schema = schema

    def partitions(self):
        return [YourPartition(0, start, end)]

    def read(self, partition):
        # Import here — runs on executors
        import requests

        response = requests.get(f"{self.url}?start={partition.start}")
        for item in response.json():
            yield tuple(item.values())

# 6. Batch Reader
class YourBatchReader(YourReader, DataSourceReader):
    pass

# 7. Stream Reader — adds offset tracking for incremental reads
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

## Registration and Usage

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
