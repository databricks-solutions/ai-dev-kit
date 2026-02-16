# Multi-Language Clients

Zerobus Ingest SDK examples for Java, Go, TypeScript/Node.js, and Rust. All languages follow the same core pattern: **SDK init -> create stream -> ingest records -> ACK -> flush -> close**.

---

## Java (8+)

### Installation

Maven:
```xml
<dependency>
    <groupId>com.databricks</groupId>
    <artifactId>zerobus-ingest-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

### Protobuf Flow (Recommended)

Java uses Protobuf by default. Generate and compile your `.proto` first (see [4-protobuf-schema.md](4-protobuf-schema.md)).

```java
import com.databricks.zerobus.*;
import com.example.proto.Record.AirQuality;

public class ZerobusProducer {
    public static void main(String[] args) throws Exception {
        String serverEndpoint = System.getenv("ZEROBUS_SERVER_ENDPOINT");
        String workspaceUrl = System.getenv("DATABRICKS_WORKSPACE_URL");
        String tableName = System.getenv("ZEROBUS_TABLE_NAME");
        String clientId = System.getenv("DATABRICKS_CLIENT_ID");
        String clientSecret = System.getenv("DATABRICKS_CLIENT_SECRET");

        ZerobusSdk sdk = new ZerobusSdk(serverEndpoint, workspaceUrl);

        TableProperties<AirQuality> tableProperties = new TableProperties<>(
            tableName,
            AirQuality.getDefaultInstance()
        );

        ZerobusStream<AirQuality> stream = sdk.createStream(
            tableProperties, clientId, clientSecret
        ).join();

        try {
            for (int i = 0; i < 100; i++) {
                AirQuality record = AirQuality.newBuilder()
                    .setDeviceName("sensor-" + i)
                    .setTemp(22)
                    .setHumidity(55)
                    .build();
                stream.ingestRecord(record).join();
            }
        } finally {
            stream.close();
        }
    }
}
```

### Proto Generation for Java

```bash
java -jar zerobus-ingest-sdk-0.1.0-jar-with-dependencies.jar \
    --uc-endpoint "https://dbc-a1b2c3d4-e5f6.cloud.databricks.com" \
    --client-id "$DATABRICKS_CLIENT_ID" \
    --client-secret "$DATABRICKS_CLIENT_SECRET" \
    --table "catalog.schema.table_name" \
    --output "record.proto"

# Compile to Java
protoc --java_out=src/main/java record.proto
```

---

## Go (1.21+)

### Installation

```bash
go get github.com/databricks/zerobus-sdk-go
```

### JSON Flow

```go
package main

import (
    "fmt"
    "log"
    "os"

    zerobus "github.com/databricks/zerobus-go-sdk/sdk"
)

func main() {
    serverEndpoint := os.Getenv("ZEROBUS_SERVER_ENDPOINT")
    workspaceURL := os.Getenv("DATABRICKS_WORKSPACE_URL")
    tableName := os.Getenv("ZEROBUS_TABLE_NAME")
    clientID := os.Getenv("DATABRICKS_CLIENT_ID")
    clientSecret := os.Getenv("DATABRICKS_CLIENT_SECRET")

    sdk, err := zerobus.NewZerobusSdk(serverEndpoint, workspaceURL)
    if err != nil {
        log.Fatal(err)
    }
    defer sdk.Free()

    options := zerobus.DefaultStreamConfigurationOptions()
    options.RecordType = zerobus.RecordTypeJson

    stream, err := sdk.CreateStream(
        zerobus.TableProperties{TableName: tableName},
        clientID, clientSecret, options,
    )
    if err != nil {
        log.Fatal(err)
    }
    defer stream.Close()

    for i := 0; i < 100; i++ {
        record := fmt.Sprintf(
            `{"device_name": "sensor-%d", "temp": 22, "humidity": 55}`, i,
        )
        ack, err := stream.IngestRecord(record)
        if err != nil {
            log.Printf("Ingest failed for record %d: %v", i, err)
            continue
        }
        ack.Await()
    }

    stream.Flush()
}
```

### Protobuf Flow

```go
options := zerobus.DefaultStreamConfigurationOptions()
options.RecordType = zerobus.RecordTypeProto

// Load compiled proto descriptor
tableProps := zerobus.TableProperties{
    TableName:       tableName,
    DescriptorProto: descriptorBytes, // compiled .proto descriptor
}

stream, err := sdk.CreateStream(tableProps, clientID, clientSecret, options)
// ... ingest protobuf-serialized bytes ...
```

---

## TypeScript / Node.js (16+)

### Installation

```bash
npm install @databricks/zerobus-ingest-sdk
```

### JSON Flow

```typescript
import { ZerobusSdk, RecordType } from "@databricks/zerobus-ingest-sdk";

const serverEndpoint = process.env.ZEROBUS_SERVER_ENDPOINT!;
const workspaceUrl = process.env.DATABRICKS_WORKSPACE_URL!;
const tableName = process.env.ZEROBUS_TABLE_NAME!;
const clientId = process.env.DATABRICKS_CLIENT_ID!;
const clientSecret = process.env.DATABRICKS_CLIENT_SECRET!;

const sdk = new ZerobusSdk(serverEndpoint, workspaceUrl);

const stream = await sdk.createStream(
  { tableName },
  clientId,
  clientSecret,
  { recordType: RecordType.Json }
);

try {
  for (let i = 0; i < 100; i++) {
    const record = { device_name: `sensor-${i}`, temp: 22, humidity: 55 };
    await stream.ingestRecord(record);
  }
  await stream.flush();
} finally {
  await stream.close();
}
```

### With Error Handling

```typescript
import { ZerobusSdk, RecordType } from "@databricks/zerobus-ingest-sdk";

async function ingestWithRetry(
  stream: any,
  record: Record<string, unknown>,
  maxRetries = 3
): Promise<boolean> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      await stream.ingestRecord(record);
      return true;
    } catch (error) {
      console.warn(`Attempt ${attempt + 1}/${maxRetries} failed:`, error);
      if (attempt < maxRetries - 1) {
        await new Promise((r) => setTimeout(r, 2 ** attempt * 1000));
      }
    }
  }
  return false;
}
```

---

## Rust (1.70+)

### Installation

```bash
cargo add databricks-zerobus-ingest-sdk
cargo add tokio --features macros,rt-multi-thread
```

### JSON Flow

```rust
use databricks_zerobus_ingest_sdk::{
    RecordType, StreamConfigurationOptions, TableProperties, ZerobusSdk,
};
use std::env;
use std::error::Error;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let server_endpoint = env::var("ZEROBUS_SERVER_ENDPOINT")?;
    let workspace_url = env::var("DATABRICKS_WORKSPACE_URL")?;
    let table_name = env::var("ZEROBUS_TABLE_NAME")?;
    let client_id = env::var("DATABRICKS_CLIENT_ID")?;
    let client_secret = env::var("DATABRICKS_CLIENT_SECRET")?;

    let table_properties = TableProperties {
        table_name,
        descriptor_proto: None,
    };

    let options = StreamConfigurationOptions {
        record_type: RecordType::Json,
        ..Default::default()
    };

    let sdk = ZerobusSdk::new(server_endpoint, workspace_url)?;
    let mut stream = sdk
        .create_stream(table_properties, client_id, client_secret, Some(options))
        .await?;

    for i in 0..100 {
        let record = format!(
            r#"{{"device_name": "sensor-{}", "temp": 22, "humidity": 55}}"#,
            i
        );
        let ack = stream.ingest_record(record.into_bytes()).await?;
        ack.await?;
    }

    stream.close().await?;
    Ok(())
}
```

### Protobuf Flow

```rust
let table_properties = TableProperties {
    table_name: table_name.clone(),
    descriptor_proto: Some(proto_descriptor_bytes),
};

let options = StreamConfigurationOptions {
    record_type: RecordType::Proto,
    ..Default::default()
};

let mut stream = sdk
    .create_stream(table_properties, client_id, client_secret, Some(options))
    .await?;

// Ingest serialized protobuf bytes
let record_bytes = my_proto_message.encode_to_vec();
let ack = stream.ingest_record(record_bytes).await?;
ack.await?;
```

---

## Language Comparison

| Feature | Python | Java | Go | TypeScript | Rust |
|---------|--------|------|----|------------|------|
| Min version | 3.9+ | 8+ | 1.21+ | Node 16+ | 1.70+ |
| Package | `databricks-zerobus-ingest-sdk` | `com.databricks:zerobus-ingest-sdk` | `github.com/databricks/zerobus-sdk-go` | `@databricks/zerobus-ingest-sdk` | `databricks-zerobus-ingest-sdk` |
| Default serialization | JSON | Protobuf | JSON | JSON | JSON |
| Async API | Yes (separate module) | CompletableFuture | Goroutines | Native async/await | Tokio async/await |
| ACK pattern | `ack.wait_for_ack()` or callback | `.join()` | `ack.Await()` | Implicit in `await` | `ack.await?` |
| Proto generation | `python -m zerobus.tools.generate_proto` | JAR CLI tool | External `protoc` | External `protoc` | External `protoc` |
