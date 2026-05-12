# Protobuf Schema Generation

Generate `.proto` schemas from Unity Catalog table definitions, compile language bindings, and understand Delta-to-Protobuf type mappings.

---

## Why Protobuf?

| Aspect | JSON | Protobuf |
|--------|------|----------|
| **Type safety** | None (runtime errors on mismatch) | Compile-time type checking |
| **Schema evolution** | Manual; easy to break silently | Forward-compatible by design |
| **Performance** | Text parsing overhead | Binary encoding, smaller payloads |
| **Recommended for** | Prototyping, simple schemas | Production, complex schemas |

**Recommendation:** Use Protobuf for any production workload. Use JSON only for quick prototyping or when the schema is trivial.

---

## Generate .proto from a UC Table

### Python

```bash
python -m zerobus.tools.generate_proto \
    --uc-endpoint "https://dbc-a1b2c3d4-e5f6.cloud.databricks.com" \
    --client-id "$DATABRICKS_CLIENT_ID" \
    --client-secret "$DATABRICKS_CLIENT_SECRET" \
    --table "catalog.schema.table_name" \
    --output record.proto
```

### Java

```bash
java -jar zerobus-ingest-sdk-0.1.0-jar-with-dependencies.jar \
    --uc-endpoint "https://dbc-a1b2c3d4-e5f6.cloud.databricks.com" \
    --client-id "$DATABRICKS_CLIENT_ID" \
    --client-secret "$DATABRICKS_CLIENT_SECRET" \
    --table "catalog.schema.table_name" \
    --output record.proto
```

The generated `.proto` file will contain a message definition matching the table schema, for example:

```protobuf
syntax = "proto3";

message AirQuality {
    string device_name = 1;
    int32 temp = 2;
    int64 humidity = 3;
}
```

---

## Compile Language Bindings

### Python

```bash
pip install grpcio-tools

python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    record.proto
```

This generates `record_pb2.py`. Import and use it:

```python
import record_pb2

record = record_pb2.AirQuality(
    device_name="sensor-1",
    temp=22,
    humidity=55,
)
```

### Java

```bash
protoc --java_out=src/main/java record.proto
```

Generates Java classes under `src/main/java/`. Usage:

```java
import com.example.proto.Record.AirQuality;

AirQuality record = AirQuality.newBuilder()
    .setDeviceName("sensor-1")
    .setTemp(22)
    .setHumidity(55)
    .build();
```

### Go

```bash
protoc --go_out=. record.proto
```

### Rust

Use `prost` in `build.rs`:

```rust
// build.rs
fn main() {
    prost_build::compile_protos(&["record.proto"], &["."]).unwrap();
}
```

---

## Delta-to-Protobuf Type Mappings

| Delta / Spark Type | Protobuf Type | Notes |
|--------------------|---------------|-------|
| `STRING` | `string` | |
| `INT` / `INTEGER` | `int32` | |
| `LONG` / `BIGINT` | `int64` | |
| `FLOAT` | `float` | |
| `DOUBLE` | `double` | |
| `BOOLEAN` | `bool` | |
| `BINARY` | `bytes` | |
| `ARRAY<T>` | `repeated T` | Element type maps recursively |
| `MAP<K,V>` | `map<K,V>` | Key must be string or integer type |
| `STRUCT` | Nested `message` | Fields map recursively |
| `DATE` | `int32` | Epoch days (days since 1970-01-01) |
| `TIMESTAMP` | `int64` | Epoch microseconds |
| `DECIMAL(p,s)` | `bytes` or `string` | Check generated .proto for exact mapping |
| `VARIANT` | `string` | JSON-encoded string |

**Important:** The Protobuf schema must match the Delta table schema exactly (1:1 field mapping). If the table schema changes, regenerate the `.proto` and recompile.

---

## Maximum Schema Size

- Maximum **2000 columns** per proto schema
- Maximum **10 MB** per individual message (10,485,760 bytes)

---

## Schema Evolution Workflow

When your table schema changes:

1. Alter the table in Unity Catalog (add columns, etc.)
2. Regenerate the `.proto` file using the generation command
3. Recompile language bindings
4. Update your producer code to populate new fields
5. Redeploy

**Note:** Zerobus does not support automatic schema evolution. You must manage this process explicitly.

---

## Using the Descriptor in Code

### Python

```python
from zerobus.sdk.shared import TableProperties, RecordType
import record_pb2

# Pass the DESCRIPTOR from the compiled module
table_props = TableProperties(
    "catalog.schema.table_name",
    record_pb2.AirQuality.DESCRIPTOR,
)
```

### Java

```java
// Pass a default instance to extract the descriptor
TableProperties<AirQuality> tableProperties = new TableProperties<>(
    "catalog.schema.table_name",
    AirQuality.getDefaultInstance()
);
```

### Go / Rust

Pass the raw descriptor bytes when constructing `TableProperties`.
