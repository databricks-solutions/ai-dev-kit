# Python Client

Python SDK patterns for Zerobus Ingest: synchronous and asynchronous APIs, JSON and Protobuf flows, and a reusable client class.

---

## SDK Imports

```python
# Synchronous API
from zerobus.sdk.sync import ZerobusSdk

# Asynchronous API (equivalent capabilities)
from zerobus.sdk.asyncio import ZerobusSdk as AsyncZerobusSdk

# Shared types (used by both sync and async)
from zerobus.sdk.shared import (
    RecordType,
    IngestRecordResponse,
    StreamConfigurationOptions,
    TableProperties,
)
```

---

<!-- ## JSON Ingestion (Quick Start)

JSON is the simplest path. Pass Python dicts whose keys match the target table column names.

```python
import os
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties

server_endpoint = os.environ["ZEROBUS_SERVER_ENDPOINT"]
workspace_url = os.environ["DATABRICKS_WORKSPACE_URL"]
table_name = os.environ["ZEROBUS_TABLE_NAME"]
client_id = os.environ["DATABRICKS_CLIENT_ID"]
client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]

sdk = ZerobusSdk(server_endpoint, workspace_url)

options = StreamConfigurationOptions(record_type=RecordType.JSON)
table_props = TableProperties(table_name)

stream = sdk.create_stream(client_id, client_secret, table_props, options)

try:
    for i in range(100):
        record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
        ack = stream.ingest_record(record)
        ack.wait_for_ack()  # Block until durably written
finally:
    stream.close()
``` -->

---

## Protobuf Ingestion

You must always use Protobuf
For type-safe production workloads, use Protobuf. First generate and compile your `.proto` (see [4-protobuf-schema.md](4-protobuf-schema.md)), then:

```python
import os
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties

# Import your compiled protobuf module
import record_pb2

server_endpoint = os.environ["ZEROBUS_SERVER_ENDPOINT"]
workspace_url = os.environ["DATABRICKS_WORKSPACE_URL"]
table_name = os.environ["ZEROBUS_TABLE_NAME"]
client_id = os.environ["DATABRICKS_CLIENT_ID"]
client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]

sdk = ZerobusSdk(server_endpoint, workspace_url)

options = StreamConfigurationOptions(record_type=RecordType.PROTO)
table_props = TableProperties(table_name, record_pb2.AirQuality.DESCRIPTOR)

stream = sdk.create_stream(client_id, client_secret, table_props, options)

try:
    for i in range(100):
        record = record_pb2.AirQuality(
            device_name=f"sensor-{i}",
            temp=22,
            humidity=55,
        )
        ack = stream.ingest_record(record)
        ack.wait_for_ack()
finally:
    stream.close()
```

---

## ACK Callback (Asynchronous Acknowledgment)

Instead of blocking on each ACK, register a callback for background durability confirmation:

```python
from zerobus.sdk.shared import IngestRecordResponse, StreamConfigurationOptions, RecordType

def on_ack(response: IngestRecordResponse) -> None:
    print(f"Durable up to offset: {response.durability_ack_up_to_offset}")

options = StreamConfigurationOptions(
    record_type=RecordType.JSON,
    ack_callback=on_ack,
)

# Create stream with callback
stream = sdk.create_stream(client_id, client_secret, table_props, options)

try:
    for i in range(1000):
        record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
        stream.ingest_record(record)  # Non-blocking, ACKs arrive via callback
    stream.flush()  # Ensure all buffered records are sent
finally:
    stream.close()
```

---

## Reusable Client Class

A production-ready wrapper with retry logic, reconnection, and both JSON and Protobuf support:

```python
import os
import time
import logging
from typing import Optional, Callable

from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import (
    RecordType,
    IngestRecordResponse,
    StreamConfigurationOptions,
    TableProperties,
)

logger = logging.getLogger(__name__)


class ZerobusClient:
    """Reusable Zerobus Ingest client with retry and reconnection."""

    def __init__(
        self,
        server_endpoint: str,
        workspace_url: str,
        table_name: str,
        client_id: str,
        client_secret: str,
        record_type: RecordType = RecordType.JSON,
        ack_callback: Optional[Callable[[IngestRecordResponse], None]] = None,
        proto_descriptor=None,
    ):
        self.server_endpoint = server_endpoint
        self.workspace_url = workspace_url
        self.table_name = table_name
        self.client_id = client_id
        self.client_secret = client_secret
        self.record_type = record_type
        self.ack_callback = ack_callback
        self.proto_descriptor = proto_descriptor

        self.sdk = ZerobusSdk(self.server_endpoint, self.workspace_url)
        self.stream = None

    def init_stream(self) -> None:
        """Open a new stream to the target table."""
        options = StreamConfigurationOptions(
            record_type=self.record_type,
            ack_callback=self.ack_callback,
        )
        if self.record_type == RecordType.PROTO and self.proto_descriptor:
            table_props = TableProperties(self.table_name, self.proto_descriptor)
        else:
            table_props = TableProperties(self.table_name)

        self.stream = self.sdk.create_stream(
            self.client_id, self.client_secret, table_props, options
        )
        logger.info("Zerobus stream initialized for %s", self.table_name)

    def ingest(self, payload, max_retries: int = 3) -> bool:
        """Ingest a single record (dict for JSON, protobuf message for PROTO).

        Returns True on success, False after exhausting retries.
        """
        for attempt in range(max_retries):
            try:
                if self.stream is None:
                    self.init_stream()
                ack = self.stream.ingest_record(payload)
                ack.wait_for_ack()
                return True
            except Exception as e:
                err = str(e).lower()
                logger.warning(
                    "Ingest attempt %d/%d failed: %s", attempt + 1, max_retries, e
                )
                if "closed" in err or "connection" in err:
                    self.close()
                    self.init_stream()
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff: 1s, 2s, 4s
        return False

    def flush(self) -> None:
        """Flush buffered writes."""
        if self.stream:
            self.stream.flush()

    def close(self) -> None:
        """Close the stream and release resources."""
        if self.stream:
            self.stream.close()
            self.stream = None

    def __enter__(self):
        self.init_stream()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()
        self.close()
        return False
```

### Using the Client Class

```python
# JSON flow with context manager
with ZerobusClient(
    server_endpoint=os.environ["ZEROBUS_SERVER_ENDPOINT"],
    workspace_url=os.environ["DATABRICKS_WORKSPACE_URL"],
    table_name=os.environ["ZEROBUS_TABLE_NAME"],
    client_id=os.environ["DATABRICKS_CLIENT_ID"],
    client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    record_type=RecordType.JSON,
) as client:
    for i in range(100):
        client.ingest({"device_name": f"sensor-{i}", "temp": 22, "humidity": 55})

# Protobuf flow
import record_pb2

with ZerobusClient(
    server_endpoint=os.environ["ZEROBUS_SERVER_ENDPOINT"],
    workspace_url=os.environ["DATABRICKS_WORKSPACE_URL"],
    table_name=os.environ["ZEROBUS_TABLE_NAME"],
    client_id=os.environ["DATABRICKS_CLIENT_ID"],
    client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    record_type=RecordType.PROTO,
    proto_descriptor=record_pb2.AirQuality.DESCRIPTOR,
) as client:
    for i in range(100):
        record = record_pb2.AirQuality(device_name=f"sensor-{i}", temp=22, humidity=55)
        client.ingest(record)
```

---

## Async Python API

The SDK provides an equivalent async API for use with `asyncio`:

```python
import asyncio
from zerobus.sdk.asyncio import ZerobusSdk as AsyncZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties


async def ingest_async():
    sdk = AsyncZerobusSdk(server_endpoint, workspace_url)
    options = StreamConfigurationOptions(record_type=RecordType.JSON)
    table_props = TableProperties(table_name)

    stream = await sdk.create_stream(client_id, client_secret, table_props, options)

    try:
        for i in range(100):
            record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
            ack = await stream.ingest_record(record)
            await ack.wait_for_ack()
    finally:
        await stream.close()


asyncio.run(ingest_async())
```

**Tip:** The sync and async APIs have equivalent capabilities. Choose based on your application architecture (FastAPI/aiohttp -> async; scripts/batch jobs -> sync).

---

## Batch Pattern

For higher throughput, send records without blocking on each ACK and flush at the end:

```python
with ZerobusClient(
    server_endpoint=os.environ["ZEROBUS_SERVER_ENDPOINT"],
    workspace_url=os.environ["DATABRICKS_WORKSPACE_URL"],
    table_name=os.environ["ZEROBUS_TABLE_NAME"],
    client_id=os.environ["DATABRICKS_CLIENT_ID"],
    client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    record_type=RecordType.JSON,
    ack_callback=lambda resp: None,  # Discard individual ACKs
) as client:
    for i in range(10_000):
        record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
        client.stream.ingest_record(record)  # Non-blocking
    # flush() and close() called automatically by context manager
```
