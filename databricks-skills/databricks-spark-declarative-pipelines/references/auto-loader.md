# Auto Loader (`cloudFiles`)

Auto Loader incrementally processes new files arriving in cloud object storage. It tracks
processed files in a checkpoint, infers and evolves schemas, and exposes either a streaming
DataFrame (`spark.readStream.format("cloudFiles")`) or a SQL streaming source
(`STREAM read_files(...)`).

In SDP pipelines, the schema location and checkpoint live inside the pipeline storage area —
declared implicitly. Outside SDP (raw Structured Streaming), you set both explicitly. This
page covers Auto Loader fundamentals from both angles. SDP-specific wrappers around these
patterns (the `@dp.table` shape, fan-out into bronze/quarantine/silver) live in
[python/2-ingestion.md](python/2-ingestion.md).

**Official documentation:**
- [Auto Loader options](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/options)
- [File detection modes](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/file-detection-modes)
- [Schema inference and evolution](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/schema)

---

## When to Use

| Use case | Tool |
|---|---|
| Incremental ingestion of files arriving over time | **Auto Loader** (this page) |
| One-time idempotent batch load of an existing folder | `COPY INTO` |
| One-shot SQL read with no state tracking | `read_files()` (batch TVF) |
| Declarative bronze table inside a managed pipeline | SDP streaming table — uses Auto Loader under the hood |

Pick Auto Loader whenever new files keep arriving and you want each file processed exactly
once without re-reading the full directory.

---

## Quick Start: SDP (Default)

Inside SDP, the schema location and checkpoint are managed by the pipeline. You declare the
source path and the Auto Loader options; the pipeline takes care of the rest.

### Python (`@dp.table`)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(name="bronze_orders", cluster_by=["order_date"])
def bronze_orders():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("cloudFiles.rescuedDataColumn", "_rescued_data")
        .load("/Volumes/catalog/schema/raw/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )
```

### SQL (`STREAM read_files`)

```sql
CREATE OR REFRESH STREAMING TABLE catalog.schema.bronze_orders
AS SELECT *,
       _metadata.file_path AS _source_file,
       current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/catalog/schema/raw/orders/',
  format => 'json',
  schemaEvolutionMode => 'addNewColumns'
);
```

`STREAM read_files()` is the SQL frontend for Auto Loader — used by SDP, materialized
views, and DBSQL streaming tables.

---

## Quick Start: Raw Structured Streaming

Outside SDP, set `cloudFiles.schemaLocation` and `checkpointLocation` to distinct,
persistent paths. UC Volumes are recommended.

```python
df = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", "/Volumes/catalog/schema/_schemas/orders/")
    .option("cloudFiles.inferColumnTypes", "true")
    .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
    .option("cloudFiles.rescuedDataColumn", "_rescued_data")
    .load("/Volumes/catalog/schema/raw/orders/")
)

(df.writeStream
    .option("checkpointLocation", "/Volumes/catalog/schema/_checkpoints/orders/")
    .trigger(availableNow=True)
    .toTable("catalog.schema.bronze_orders"))
```

Schema location and checkpoint must be **distinct, persistent paths**. Don't put them
under the source data path. Each stream needs its own pair.

---

## Core Concepts

| Concept | Purpose |
|---|---|
| **Source path** | Cloud directory to watch (S3, ADLS, GCS, or UC Volume path) |
| **Schema location** | Where Auto Loader persists the inferred schema and its evolution history (managed by SDP; explicit outside SDP) |
| **Checkpoint location** | Where the streaming query records which files have been processed (managed by SDP; explicit outside SDP) |
| **Discovery mode** | How Auto Loader finds new files: directory listing (default) or file notifications |
| **Format** | `json`, `csv`, `parquet`, `avro`, `orc`, `text`, `binaryFile` |

---

## Discovery Modes

Auto Loader has two ways to discover new files. Pick one based on directory size, file
arrival rate, and operational complexity tolerance.

| Signal | Directory listing | File notification |
|---|---|---|
| Files in source directory | Up to ~1M | Any size |
| File arrival rate | Low to moderate | High |
| Cloud setup required | None | IAM + SNS/SQS / Event Grid / Pub/Sub |
| Listing cost | Scales with files | Constant |
| Latency from arrival to processing | Seconds to minutes | Seconds |
| Default | ✓ | — |

Start with directory listing. Switch to notification mode when listing time becomes a
bottleneck or directory size is projected to exceed 1M files.

### Directory Listing (Default)

Auto Loader lists the source directory at every micro-batch and compares against the
checkpoint to find new files. No additional options required.

Listing performance is best when files use date-partitioned subdirectories
(`/raw/orders/year=2026/month=04/day=26/`).

**Incremental listing** kicks in automatically when filenames sort lexicographically with
a date or timestamp prefix:

- `2026-04-26T10-15-00_orders.json` ✓
- `events_20260426_101500.parquet` ✓
- Random UUIDs, sequential integers without zero-padding, or unsynchronized writers fall
  back to full listing.

### File Notification

Auto Loader subscribes to a cloud event stream (S3 → SNS/SQS, ADLS → Event Grid, GCS →
Pub/Sub) and processes one event per new file without scanning the directory.

```python
.option("cloudFiles.useNotifications", "true")
```

For managed setup (Databricks creates the queue/topic and IAM resources):

```python
.option("cloudFiles.useManagedFileEvents", "true")
```

Managed file events automate the full cloud setup but require the workspace to have the
required cloud permissions and the source path to be under a UC External Location.

### Switching Modes

You can switch between listing and notifications on the same checkpoint:

1. Stop the streaming query.
2. Set up the cloud event source (or enable managed file events).
3. Add or remove `cloudFiles.useNotifications`.
4. Restart the query — it picks up where the checkpoint left off.

The reverse switch also works.

### When to Reconsider

Switch from listing to notifications when any of these is true:

- Source directory exceeds 100k files and grows daily
- Listing time per micro-batch exceeds 30 seconds
- Files arrive at a rate where you need sub-minute latency
- The job runs in `processingTime` mode (continuous), not `availableNow`

Stay on listing when the source is small, partitioning is clean, the job runs hourly or
less with `availableNow=True`, or operational simplicity beats latency.

---

## Schema Management

Three strategies, picked by source stability:

| Strategy | Use when | How |
|---|---|---|
| **Provided schema** | Source is well-known, stable, contract-enforced | `.schema(StructType(...))` |
| **Inferred + hints** | Source is mostly stable, a few fields need fixing | `cloudFiles.inferColumnTypes=true` + `cloudFiles.schemaHints="field TYPE, ..."` |
| **Inferred + evolve** | Source is exploratory or actively changing | `cloudFiles.inferColumnTypes=true` + `cloudFiles.schemaEvolutionMode=addNewColumns` |

Inferred and inferred+hints both require a persistent schema location — managed
automatically inside SDP, explicit outside.

### Provided Schema

Most stable. New fields in source files are dropped. Type mismatches go to `_rescued_data`
if `rescuedDataColumn` is set; otherwise the query fails.

```python
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, DoubleType

orders_schema = StructType([
    StructField("order_id", StringType(), nullable=False),
    StructField("customer_id", StringType(), nullable=False),
    StructField("amount", DoubleType()),
    StructField("ordered_at", TimestampType()),
])

spark.readStream.format("cloudFiles") \
    .option("cloudFiles.format", "json") \
    .schema(orders_schema) \
    .load(source_path)
```

### Schema Inference

```python
.option("cloudFiles.format", "json")
.option("cloudFiles.inferColumnTypes", "true")
```

Without `inferColumnTypes`, all fields infer as `STRING` (safer default for JSON/CSV).
With it, Auto Loader samples up to 50 files (configurable via
`cloudFiles.schemaInferenceSampleSize`) and infers types.

Each schema version is persisted under the schema location — inspect `_schemas/` to see
history.

### Schema Hints

Hints override inference for specific fields. Useful when inference picks the wrong type
(a TIMESTAMP read as STRING, an INT read as DOUBLE because of nulls).

```python
.option("cloudFiles.schemaHints",
    "order_id STRING NOT NULL, "
    "amount DECIMAL(18, 2), "
    "metadata MAP<STRING, STRING>")
```

Syntax matches Spark SQL DDL. Apply hints sparingly — once you're hinting most fields,
switch to a provided schema.

### Schema Evolution Modes

Set via `cloudFiles.schemaEvolutionMode`:

| Mode | Behavior on new column |
|---|---|
| `addNewColumns` | Stop the stream, update schema, restart automatically. **Most common production choice.** |
| `rescue` | Stream continues; new columns land in `_rescued_data` as JSON; never modifies the table schema |
| `failOnNewColumns` | Stream fails; manual intervention |
| `none` | Ignore new columns silently. Avoid — silent data loss |

`addNewColumns` requires the target table to support schema evolution (Delta does by
default). The first batch after a new column appears triggers a restart. Wrap in a job
with retries so the restart is automatic.

### Rescued Data

Captures values that don't match the schema (type mismatch, malformed JSON, columns
dropped because they aren't in the provided schema):

```python
.option("cloudFiles.rescuedDataColumn", "_rescued_data")
```

`_rescued_data` is `NULL` for clean records and a JSON STRING for records with
type, parse, or missing-field issues. Filter downstream:

```python
quarantine = bronze.filter("_rescued_data IS NOT NULL")
clean      = bronze.filter("_rescued_data IS NULL")
```

Always set `rescuedDataColumn` in production. The cost is one nullable column; the
benefit is never losing a record silently.

### Format-Specific Options

| Option | Format | Effect |
|---|---|---|
| `cloudFiles.inferColumnTypes` | JSON, CSV | Infer types beyond STRING |
| `cloudFiles.schemaInferenceSampleSize` | JSON, CSV | Files to sample (default 50) |
| `multiLine` | JSON | Multi-line JSON objects per file |
| `header` | CSV | First line is header |
| `delimiter` | CSV | Field delimiter (default `,`) |
| `mergeSchema` | Parquet | Merge schemas across files (slow, use sparingly) |

---

## Cloud Event Setup (File Notification Mode)

Notification mode requires a cloud event source on the storage bucket. Pick managed file
events for the simplest path; fall back to manual setup when the workspace lacks the
required cloud permissions.

### Managed File Events (Recommended)

```python
.option("cloudFiles.useNotifications", "true")
.option("cloudFiles.useManagedFileEvents", "true")
```

Requirements:

- Source path is a UC External Location or UC Volume backed by an external location
- The workspace has cloud manager permissions to provision event resources
- Path is registered in Unity Catalog (not raw `s3://`)

When managed events aren't available, fall back to the cloud-specific setups below.

### AWS — S3 + SNS + SQS

Resources to provision:

1. **SNS topic** receives `s3:ObjectCreated:*` events from the bucket
2. **SQS queue** subscribed to the SNS topic; Auto Loader reads from this queue
3. **S3 event notification** routes the bucket → SNS topic for `ObjectCreated` events
4. **IAM** — workspace credential needs SQS read + delete; SNS subscribe is one-time

```python
.option("cloudFiles.useNotifications", "true")
.option("cloudFiles.region", "us-east-1")
.option("cloudFiles.queueUrl", "https://sqs.us-east-1.amazonaws.com/123/my-queue")
```

Required IAM (workspace credential):

```json
{
  "Effect": "Allow",
  "Action": [
    "sqs:ReceiveMessage",
    "sqs:DeleteMessage",
    "sqs:GetQueueAttributes"
  ],
  "Resource": "arn:aws:sqs:us-east-1:123:my-queue"
}
```

If you let Auto Loader create the topic/queue, the credential additionally needs
`sqs:CreateQueue`, `sns:CreateTopic`, `s3:GetBucketNotification`,
`s3:PutBucketNotification`.

### Azure — ADLS Gen2 + Event Grid + Queue Storage

Resources:

1. **Storage Queue** — Auto Loader reads events here
2. **Event Grid system topic** on the storage account routes
   `Microsoft.Storage.BlobCreated` events
3. **Event Subscription** delivers events from the system topic to the storage queue
4. **RBAC** — workspace identity needs `Storage Queue Data Contributor` on the queue
   and `Storage Account Contributor` on the source storage account (only when Auto
   Loader self-provisions)

```python
.option("cloudFiles.useNotifications", "true")
.option("cloudFiles.subscriptionId", "<subscription-id>")
.option("cloudFiles.tenantId", "<tenant-id>")
.option("cloudFiles.clientId", "<client-id>")
.option("cloudFiles.clientSecret", dbutils.secrets.get("scope", "azure-client-secret"))
.option("cloudFiles.resourceGroup", "<resource-group>")
.option("cloudFiles.queueName", "my-queue")
```

For source and queue in different resource groups:

```python
.option("cloudFiles.resourceGroup", "<source-storage-rg>")
.option("cloudFiles.queueResourceGroup", "<queue-storage-rg>")
```

### GCP — GCS + Pub/Sub

Resources:

1. **Pub/Sub topic** receives bucket notifications
2. **Pub/Sub subscription** — Auto Loader reads from this subscription
3. **Bucket notification** — `gsutil notification create -t <topic> -f json gs://<bucket>`
4. **Service account** needs `roles/pubsub.subscriber` on the subscription and (if
   self-provisioning) `roles/pubsub.editor` + `roles/storage.admin`

```python
.option("cloudFiles.useNotifications", "true")
.option("cloudFiles.subscription", "projects/<project>/subscriptions/<sub>")
```

### Existing Files at First Run

By default Auto Loader processes all existing files on first run:

```python
.option("cloudFiles.includeExistingFiles", "true")  # default
```

For very large existing directories, set to `false` and seed historical data with a
one-shot batch (`COPY INTO` or `read_files()`). Then start Auto Loader for new arrivals
only.

### Backfill Behavior

Notification mode only sees events delivered after the subscription was created. Use
`cloudFiles.backfillInterval` to periodically reconcile via directory listing:

```python
.option("cloudFiles.backfillInterval", "1 day")
```

This runs a directory listing every N hours/days and picks up files whose events were
lost — at the cost of one full listing per interval. **Set this in production**
notification mode; it's cheap insurance against missed events.

### Verifying Events Flow

After setup, verify events flow before pointing Auto Loader at the queue:

| Cloud | Verification command |
|---|---|
| AWS | `aws sqs receive-message --queue-url <url> --max-number-of-messages 1` |
| Azure | `az storage message peek --queue-name <queue> --account-name <account>` |
| GCP | `gcloud pubsub subscriptions pull <sub> --limit=1` |

If you don't see messages within a minute of writing a test file to the bucket, the event
source isn't wired correctly — fix that before involving Auto Loader.

### Cost Notes

| Cloud | Per million events |
|---|---|
| AWS SNS + SQS | ~$0.40 |
| Azure Event Grid + Queue Storage | ~$0.60 |
| GCP Pub/Sub | ~$0.40 |

For 100M files/month, expect $40–$60 in cloud event costs — typically less than the
equivalent listing cost on a 10M-file directory.

---

## Triggers and Cost

Most file-ingestion workloads are cheaper as scheduled batch jobs (`availableNow=True`)
than as continuous streams. Pick by latency SLA, not by streaming-vs-batch ideology.

| Latency SLA | Trigger | Why |
|---|---|---|
| Hourly or longer | `availableNow=True` + cron | Pay only during job runs |
| 5–60 minutes | `availableNow=True` + frequent cron | Same model, more frequent runs |
| < 5 minutes | `processingTime="N seconds"` | Continuous stream, fixed-size cluster always on |
| Sub-second | Real-Time Mode (separate) | Different runtime; rarely needed for file ingestion |

For 90% of file-ingestion workloads, `availableNow=True` is the right answer.

### `availableNow=True` (Scheduled Batch)

```python
(df.writeStream
    .option("checkpointLocation", checkpoint_path)
    .trigger(availableNow=True)
    .toTable("catalog.schema.bronze_orders"))
```

Behavior: query starts, discovers all files since the last checkpoint, processes them in
micro-batches (memory pressure stays bounded), stops cleanly when caught up. Wrap in a
Databricks Job with cron.

In SDP, the scheduling lives at the pipeline level (triggered runs); `availableNow` is
the implicit semantics. You don't write `.trigger(availableNow=True)` inside `@dp.table`.

### `processingTime` (Continuous)

```python
.trigger(processingTime="30 seconds")
```

Use when you need consistent sub-5-minute latency. Cluster stays on; query never stops;
new micro-batch every N seconds.

Caveats:

- No autoscaling on streaming workloads — fixed-size cluster
- Cluster cost runs 24×7
- Idle periods (no new files) still cost compute
- Recovery on failure depends on the job retry policy — set max retries high with backoff

For continuous streams, prefer notification mode and avoid `processingTime` below
~5 seconds (Spark overhead dominates).

### Continuous Trigger (Deprecated)

```python
.trigger(continuous="1 second")  # Don't use
```

Predates `processingTime` and has limited operator support. Avoid.

### Cost Levers

For `availableNow=True` scheduled jobs, total cost is dominated by cluster startup
overhead, discovery cost, and read+write throughput. Levers:

| Action | Effect |
|---|---|
| Increase trigger interval (hourly vs every 5 min) | Fewer startups; same throughput |
| Switch to notification mode for large dirs | Lower discovery cost |
| Use serverless compute | Lower startup overhead |
| Right-size the cluster | Idle CPU is wasted spend |
| Enable autoscaling on the *job cluster* | Allowed only with `availableNow` (not `processingTime`) |

For `processingTime` continuous streams: increase trigger interval, use notification
mode, smallest cluster that meets throughput.

### File Trigger Tuning

`maxFilesPerTrigger` and `maxBytesPerTrigger` cap how much each micro-batch processes.
Defaults are fine for `availableNow=True`. For `processingTime`, tune when each
micro-batch is doing too much (high latency) or too little (overhead dominates):

```python
.option("cloudFiles.maxFilesPerTrigger", "10000")
.option("cloudFiles.maxBytesPerTrigger", "10g")
```

### Concurrency

Multiple Auto Loader streams can read from the same source path as long as each has its
own schema location, checkpoint, and target table. Standard pattern when fan-out is
needed (e.g., bronze copy + a real-time alerting stream off the same files). For cost
efficiency, fan out *after* a single bronze ingestion.

---

## Error Handling

Auto Loader fails in three broad ways: bad records (parseable but wrong), schema
surprises (new columns or type changes), and infrastructure (checkpoint corruption,
missing files). Plan for each.

### Quarantine Pattern

Route bad records to a separate table for inspection without polluting the bronze layer.
The bronze table keeps everything (audit trail). Quarantine and silver split downstream
by `_rescued_data IS NULL`:

```python
from pyspark import pipelines as dp

@dp.table(name="bronze_events")
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.rescuedDataColumn", "_rescued_data")
        .load(source_path)
    )

@dp.table(name="bronze_quarantine")
def bronze_quarantine():
    return spark.readStream.table("bronze_events").filter("_rescued_data IS NOT NULL")

@dp.table(name="silver_events")
def silver_events():
    return (
        spark.readStream.table("bronze_events")
            .filter("_rescued_data IS NULL")
            .drop("_rescued_data")
    )
```

### Schema Evolution Failures

`UnknownFieldException` fires when a new column appears and `schemaEvolutionMode` is
`failOnNewColumns`. Auto Loader stops the stream with a non-retryable error.

| Mode | Behavior | Restart needed |
|---|---|---|
| `addNewColumns` | Stream stops, schema updated, restart auto-recovers | Yes (one time) |
| `rescue` | New columns silently land in `_rescued_data` | No |
| `failOnNewColumns` | Stream stops permanently | Manual schema update |
| `none` | New columns are silently dropped | No |

Set Databricks Job retries to a low positive number (e.g. 3) with exponential backoff so
`addNewColumns` restarts pick up automatically. Don't use `unlimited` retries — that
hides real failures.

### Notification Mode Failures

| Symptom | Cause | Fix |
|---|---|---|
| No new files processed despite arrivals | Subscription disconnected; events delivered to dead-letter | Check queue depth; enable `cloudFiles.backfillInterval` |
| Burst processing after a quiet period | Subscription was paused; events queued | Verify queue isn't backed up; consider increasing batch size |
| Events for files that no longer exist | File deleted between event delivery and Auto Loader read | Set `cloudFiles.allowOverwrites=true` if files are intentionally rewritten |

### Checkpoint and Schema Location Failures

| Symptom | Cause | Fix |
|---|---|---|
| Files re-processed on every run | Checkpoint deleted or pointing to a new path | Restore checkpoint from backup; if not possible, accept duplicates and dedup downstream |
| Stream fails to start: "schema location does not exist" | Path mistyped or removed | Verify `cloudFiles.schemaLocation` exists; create directory if needed |
| Stream fails: "schema mismatch" | Schema location reused across incompatible streams | Each stream needs its own schema location |

UC Volumes are the recommended location for both — persistent and versioned, no DBFS
deprecation risk.

### File Format Failures

CSV with quoted fields containing newlines:

```python
.option("multiLine", "true")
.option("escape", "\"")
```

JSON with single objects spanning multiple lines:

```python
.option("multiLine", "true")
```

Parquet/Avro/ORC with schema variation across files:

```python
.option("mergeSchema", "true")  # Slow — use with caution
```

`mergeSchema=true` lists every file's footer at startup. Avoid on directories with
millions of files; use a provided schema or hints instead.

### Glob Filtering and Path Selection

Auto Loader processes everything under the source path matching `cloudFiles.format`. Use
`pathGlobFilter` or `cloudFiles.pathFilter` to narrow:

```python
.option("pathGlobFilter", "*.json")                     # Standard glob
.option("cloudFiles.pathFilter", "{2026,2027}/*.json")  # Brace expansion
```

If files of multiple formats land in the same directory (mixed JSON and CSV), process
each format with a separate Auto Loader stream.

### Recovery Patterns

**Replay a specific file** (after a code fix):

1. Read the file as a one-off batch (`spark.read.format("json").load("path/to/file")`)
2. Write to a recovery target table
3. Merge into the production table by primary key

Don't try to manipulate the checkpoint — that's brittle and risks corruption.

**Reset a stream** (when schema or logic changes incompatibly):

1. Pause the source so no new files arrive
2. Drop the target table
3. Delete the checkpoint and schema location
4. Recreate the table with the new logic
5. Run with `cloudFiles.includeExistingFiles=true` to backfill from scratch

This is destructive — only do it when you control the source pause and downstream impact.

---

## Troubleshooting

### Files Not Picked Up

Stream is running, no errors, but new files aren't being processed. Diagnostic order:

1. **Verify path:** `databricks fs ls dbfs:/Volumes/catalog/schema/raw/`
2. **Verify format:** `cloudFiles.format` matches actual file extension/content
3. **Check glob filters:** `pathGlobFilter` may be too narrow
4. **In notification mode:** verify events flow per the cloud-setup verification table above
5. **Check the checkpoint:** `checkpointLocation/sources/0/` for the last seen offset

If listing mode is used and files arrive but aren't seen, confirm the file naming
pattern allows incremental listing or accept a full listing per micro-batch.

### Schema Mismatch / `UnknownFieldException`

A new column appeared in source files. Action depends on `schemaEvolutionMode`:

| Current mode | Action |
|---|---|
| `addNewColumns` | Job retry recovers automatically |
| `failOnNewColumns` | Either change to `addNewColumns` or update your provided schema |
| Provided schema (no inference) | Add the new field to your schema; restart |

If you don't want the new column, set `schemaEvolutionMode=rescue` so it lands in
`_rescued_data` instead of failing the stream.

### `Schema Location Must Be Set`

You're inferring schema (`cloudFiles.inferColumnTypes=true` or relying on default
JSON/CSV inference) without `cloudFiles.schemaLocation`. Add a schema location pointing
at a UC Volume:

```python
.option("cloudFiles.schemaLocation", "/Volumes/catalog/schema/_schemas/my_stream/")
```

Each stream needs a unique schema location — don't share between streams. (In SDP this
is managed automatically.)

### Files Processed Twice

After a restart, every file is reprocessed. Likely causes:

1. Checkpoint location changed
2. Checkpoint deleted
3. Stream started with `cloudFiles.includeExistingFiles=true` against an existing target

Recovery:

- Dedup downstream if the target has primary keys
- Restore the checkpoint from backup if duplicates aren't acceptable
- Don't try to "skip" files by editing the checkpoint — unsupported and brittle

### Listing Time Grows Unbounded

Source directory has too many files for directory listing. Options:

- Switch to notification mode
- Restructure the source to use date-partitioned subdirectories
  (`/raw/year=2026/month=04/`)
- Periodically archive processed files to a separate prefix

Auto Loader doesn't archive or move processed files — that's the producer's
responsibility.

### Memory Pressure During First Run

`includeExistingFiles=true` on a directory with millions of files causes Auto Loader to
enumerate everything before starting. Mitigations:

```python
.option("cloudFiles.includeExistingFiles", "false")
.option("cloudFiles.maxFilesPerTrigger", "10000")
```

For very large historical loads, do a one-time `COPY INTO` of historical data to populate
the target, then start Auto Loader with `includeExistingFiles=false` for new arrivals
only.

### Notification Subscription Fails

| Cloud | Diagnostic |
|---|---|
| AWS | `aws sqs get-queue-attributes --queue-url <url>` — verify queue exists and credential has `sqs:ReceiveMessage` |
| Azure | `az storage message peek --queue-name <queue>` — verify queue and RBAC roles |
| GCP | `gcloud pubsub subscriptions describe <sub>` — verify subscription and IAM |

If queue exists but Auto Loader can't read, the workspace credential is missing the read
permission. See the cloud-setup section above.

### Stream Stops Without Error

Query exits cleanly with no exception; status is `FINISHED`. This is `availableNow=True`
working correctly — it stops when there are no more files to process. Restart the job on
the next schedule and Auto Loader resumes from the checkpoint.

If you're using `processingTime` and the stream still stops, check job logs for shutdown
signals or cluster termination events.

### High Cost Despite Low File Volume

| Cause | Fix |
|---|---|
| `processingTime` continuous stream with idle periods | Switch to `availableNow=True` + cron |
| Cluster sized for peak, runs 24×7 | Use serverless or smaller cluster + autoscale on `availableNow` |
| `mergeSchema=true` on Parquet | Provide schema instead |
| Notification mode with backfill at 1-second intervals | Increase backfill interval to 1 hour or longer |

### Delta Sink Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| Target table fails to write — schema mismatch | Source schema evolved, target hasn't | Set `mergeSchema=true` on the writer or pre-evolve the table |
| `Concurrent write` error | Multiple writers on same table | Each Auto Loader stream → own table; merge downstream |
| Liquid clustering not applying | Table missing `CLUSTER BY` | `ALTER TABLE ... CLUSTER BY (...)` and run `OPTIMIZE` |

### Diagnosing With `lastProgress`

```python
for stream in spark.streams.active:
    progress = stream.lastProgress
    if progress:
        print(f"Files seen: {progress.get('numInputRows', 0)}")
        print(f"Trigger duration: {progress.get('durationMs', {}).get('triggerExecution', 0)} ms")
        for source in progress.get("sources", []):
            print(f"Source desc: {source.get('description')}")
            print(f"Latest offset: {source.get('latestOffset')}")
```

`lastProgress` is the fastest way to see what Auto Loader is doing without combing
through driver logs.

### When to Open a Support Ticket

Most issues resolve via the diagnostics above. Open a ticket when:

- Checkpoint corruption is suspected (errors mentioning `_metadata` or version files in
  the checkpoint dir)
- Schema location version files are inconsistent with table schema
- Notification mode delivers events but Auto Loader claims it doesn't see them
- Same source + same code processes files in one workspace but not another

Include the streaming query ID, checkpoint path, and the last 200 lines of driver logs.

---

## Migration

### From `COPY INTO`

`COPY INTO` is idempotent and tracks loaded files in a metadata table. Works for one-shot
or infrequent batch loads but doesn't scale to high file volumes or low-latency arrivals.

| `COPY INTO` | Auto Loader |
|---|---|
| `COPY INTO bronze FROM 's3://bucket/raw/' FILEFORMAT = JSON` | `spark.readStream.format("cloudFiles")` |
| Idempotency via metadata table | Idempotency via checkpoint |
| Re-reads directory listing each run | Listing or notifications |
| No schema evolution | Full schema evolution support |

Migration:

1. **Bootstrap historical data** with `COPY INTO` one final time, or accept that Auto
   Loader will re-list and re-process the existing directory on first run.
2. **Stop scheduling `COPY INTO`** runs.
3. **Start Auto Loader** with the same source, a new schema location, a new checkpoint,
   and `includeExistingFiles=false` (history is already in the target):

```python
spark.readStream.format("cloudFiles") \
    .option("cloudFiles.format", "json") \
    .option("cloudFiles.schemaLocation", schema_location) \
    .option("cloudFiles.includeExistingFiles", "false") \
    .load(source_path) \
    .writeStream \
    .option("checkpointLocation", checkpoint_path) \
    .trigger(availableNow=True) \
    .toTable("catalog.schema.bronze")
```

4. **Verify duplicate-free** with a `COUNT DISTINCT` on the primary key for the cutover
   window.

### From Full-Directory Batch Reads

Pattern being replaced:

```python
df = spark.read.format("json").load("/Volumes/.../raw/")
df.write.mode("overwrite").saveAsTable("catalog.schema.bronze")
```

Problems: full re-read of entire directory every run; no incremental tracking;
`overwrite` is destructive while `append` produces duplicates.

Migration:

1. Replace `spark.read` with `spark.readStream.format("cloudFiles")`.
2. Add a schema location and a checkpoint (managed automatically inside SDP).
3. Pick `availableNow=True` for scheduled jobs; `processingTime` for continuous.
4. Replace `saveAsTable("...", mode="overwrite")` with `.toTable("...")`.

If the original job did transformations and `overwrite` semantics were intentional (e.g.,
daily snapshot of dimension data), Auto Loader is the wrong tool — keep the batch read.

### From Generic Structured Streaming

Pattern being replaced:

```python
spark.readStream.format("json").load(source_path)
```

Generic file streams don't have a checkpoint of which files were processed — they replay
the directory on every restart. Equivalent Auto Loader call:

```python
spark.readStream.format("cloudFiles") \
    .option("cloudFiles.format", "json") \
    .option("cloudFiles.schemaLocation", schema_location) \
    .load(source_path)
```

Auto Loader checkpoints processed files individually; schema inference and evolution are
opt-in and persisted; file notification mode is supported.

Migration:

1. Stop the existing stream cleanly.
2. Replace `format("json")` with `format("cloudFiles")` + `cloudFiles.format=json`.
3. Add `cloudFiles.schemaLocation` (or move into SDP, where it's managed for you).
4. Use a **new** checkpoint location — the old format's checkpoint isn't compatible.
5. Set `cloudFiles.includeExistingFiles=false` if the data is already loaded.

### Cutover Checklist

- [ ] Source path is unchanged or migrated cleanly
- [ ] Target table accepts append-only writes (Delta + matching schema)
- [ ] New checkpoint location chosen (not reused from prior tool)
- [ ] New schema location chosen (UC Volume) — or moved into SDP
- [ ] `includeExistingFiles` decision made (true to backfill, false if history is
      loaded)
- [ ] First run validated against expected counts
- [ ] Old job decommissioned only after cutover is verified
- [ ] Monitoring alerts updated to point at the new query / job

---

## Production Checklist

Outside SDP:

- [ ] Schema location and checkpoint on UC Volumes (not source path, not DBFS)
- [ ] Distinct checkpoint per pipeline / target table
- [ ] `cloudFiles.format` set explicitly
- [ ] Schema strategy chosen (provided / hints / infer + evolve)
- [ ] Discovery mode chosen and IAM configured if using notifications
- [ ] Metadata columns added (`_ingested_at`, `_source_file`)
- [ ] `rescuedDataColumn` configured for evolving sources
- [ ] Trigger matches workload — `availableNow=True` for scheduled jobs
- [ ] Job retry policy set (max 3 retries with exponential backoff)

Inside SDP, schema location, checkpoint, and trigger are managed by the pipeline. Focus
on the format, schema strategy, discovery mode, and quarantine wiring.

---

## Related

- [`python/2-ingestion.md`](python/2-ingestion.md) — SDP-specific wrappers (`@dp.table`
  shape, fan-out into bronze/quarantine/silver)
- `databricks-spark-structured-streaming` — checkpointing, triggers, and joins outside
  SDP
- `databricks-unity-catalog` — Volumes (the recommended source/target for Auto Loader
  paths)
- `databricks-jobs` — scheduling `availableNow` workloads
- `databricks-dbsql` — `read_files()` (batch) and `STREAM read_files()` (streaming) SQL
  TVFs
