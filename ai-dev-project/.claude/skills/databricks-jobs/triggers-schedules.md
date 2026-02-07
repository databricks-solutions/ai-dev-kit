# Triggers and Schedules Reference

## Contents
- [Cron Schedule](#cron-schedule)
- [Periodic Trigger](#periodic-trigger)
- [File Arrival Trigger](#file-arrival-trigger)
- [Table Update Trigger](#table-update-trigger)
- [Continuous Jobs](#continuous-jobs)
- [Manual Runs](#manual-runs)

---

## Cron Schedule

Run jobs on a cron-based schedule.

### DABs YAML

```yaml
resources:
  jobs:
    daily_etl:
      name: "Daily ETL"
      schedule:
        quartz_cron_expression: "0 0 8 * * ?"  # Daily at 8 AM
        timezone_id: "America/New_York"
        pause_status: UNPAUSED
      tasks:
        - task_key: etl
          notebook_task:
            notebook_path: ../src/etl.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import CronSchedule, PauseStatus

w = WorkspaceClient()

job = w.jobs.create(
    name="Daily ETL",
    schedule=CronSchedule(
        quartz_cron_expression="0 0 8 * * ?",
        timezone_id="America/New_York",
        pause_status=PauseStatus.UNPAUSED
    ),
    tasks=[...]
)
```

### CLI JSON

```json
{
  "name": "Daily ETL",
  "schedule": {
    "quartz_cron_expression": "0 0 8 * * ?",
    "timezone_id": "America/New_York",
    "pause_status": "UNPAUSED"
  },
  "tasks": [...]
}
```

### Cron Expression Reference

Format: `seconds minutes hours day-of-month month day-of-week`

| Expression | Description |
|------------|-------------|
| `0 0 8 * * ?` | Daily at 8:00 AM |
| `0 0 8 * * MON-FRI` | Weekdays at 8:00 AM |
| `0 0 */2 * * ?` | Every 2 hours |
| `0 30 9 * * ?` | Daily at 9:30 AM |
| `0 0 0 1 * ?` | First day of month at midnight |
| `0 0 6 ? * MON` | Every Monday at 6:00 AM |
| `0 0 8 15 * ?` | 15th of each month at 8:00 AM |
| `0 0 8 L * ?` | Last day of month at 8:00 AM |

### Common Timezones

| Timezone ID | Description |
|-------------|-------------|
| `UTC` | Coordinated Universal Time |
| `America/New_York` | Eastern Time (US) |
| `America/Chicago` | Central Time (US) |
| `America/Denver` | Mountain Time (US) |
| `America/Los_Angeles` | Pacific Time (US) |
| `Europe/London` | British Time |
| `Europe/Paris` | Central European Time |
| `Asia/Tokyo` | Japan Standard Time |

---

## Periodic Trigger

Run jobs at fixed intervals (simpler than cron).

### DABs YAML

```yaml
resources:
  jobs:
    hourly_sync:
      name: "Hourly Sync"
      trigger:
        pause_status: UNPAUSED
        periodic:
          interval: 1
          unit: HOURS
      tasks:
        - task_key: sync
          notebook_task:
            notebook_path: ../src/sync.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import TriggerSettings, Periodic, PeriodicTriggerConfigurationTimeUnit, PauseStatus

w = WorkspaceClient()

job = w.jobs.create(
    name="Hourly Sync",
    trigger=TriggerSettings(
        pause_status=PauseStatus.UNPAUSED,
        periodic=Periodic(
            interval=1,
            unit=PeriodicTriggerConfigurationTimeUnit.HOURS
        )
    ),
    tasks=[...]
)
```

### Interval Units

| Unit | Description |
|------|-------------|
| `HOURS` | Run every N hours |
| `DAYS` | Run every N days |
| `WEEKS` | Run every N weeks |

### Examples

```yaml
# Every 30 minutes (not supported - use cron)
# Minimum periodic interval is 1 hour

# Every 4 hours
trigger:
  periodic:
    interval: 4
    unit: HOURS

# Every 2 days
trigger:
  periodic:
    interval: 2
    unit: DAYS

# Weekly
trigger:
  periodic:
    interval: 1
    unit: WEEKS
```

---

## File Arrival Trigger

Run jobs when new files arrive in cloud storage.

### DABs YAML

```yaml
resources:
  jobs:
    process_uploads:
      name: "Process Uploads"
      trigger:
        pause_status: UNPAUSED
        file_arrival:
          url: "s3://my-bucket/uploads/"
          min_time_between_triggers_seconds: 60
          wait_after_last_change_seconds: 30
      tasks:
        - task_key: process
          notebook_task:
            notebook_path: ../src/process_files.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import TriggerSettings, FileArrivalTriggerConfiguration, PauseStatus

w = WorkspaceClient()

job = w.jobs.create(
    name="Process Uploads",
    trigger=TriggerSettings(
        pause_status=PauseStatus.UNPAUSED,
        file_arrival=FileArrivalTriggerConfiguration(
            url="s3://my-bucket/uploads/",
            min_time_between_triggers_seconds=60,
            wait_after_last_change_seconds=30
        )
    ),
    tasks=[...]
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | Yes | Cloud storage URL to monitor |
| `min_time_between_triggers_seconds` | No | Minimum wait between triggers (default: 0) |
| `wait_after_last_change_seconds` | No | Wait time after last file change (default: 0) |

### Supported URL Formats

| Cloud | Format | Example |
|-------|--------|---------|
| AWS S3 | `s3://bucket/path/` | `s3://my-bucket/data/uploads/` |
| Azure ADLS | `abfss://container@account.dfs.core.windows.net/path/` | `abfss://data@myaccount.dfs.core.windows.net/uploads/` |
| GCS | `gs://bucket/path/` | `gs://my-bucket/uploads/` |
| Unity Catalog Volume | `/Volumes/catalog/schema/volume/path/` | `/Volumes/main/data/uploads/` |

### Access File Information in Notebook

```python
# The trigger provides file information via task context
import json

# Get trigger info from job context
trigger_info = dbutils.jobs.taskValues.get(
    taskKey="__trigger_info__",
    key="file_arrival",
    debugValue={}
)

# Contains: url, files (list of new files)
print(f"New files: {trigger_info.get('files', [])}")
```

---

## Table Update Trigger

Run jobs when Unity Catalog tables are updated.

### DABs YAML

```yaml
resources:
  jobs:
    process_updates:
      name: "Process Table Updates"
      trigger:
        pause_status: UNPAUSED
        table_update:
          table_names:
            - "catalog.schema.source_table"
            - "catalog.schema.other_table"
          condition: ANY_UPDATED
          min_time_between_triggers_seconds: 300
          wait_after_last_change_seconds: 60
      tasks:
        - task_key: process
          notebook_task:
            notebook_path: ../src/process_changes.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (
    TriggerSettings,
    TableUpdateTriggerConfiguration,
    Condition,
    PauseStatus
)

w = WorkspaceClient()

job = w.jobs.create(
    name="Process Table Updates",
    trigger=TriggerSettings(
        pause_status=PauseStatus.UNPAUSED,
        table_update=TableUpdateTriggerConfiguration(
            table_names=["catalog.schema.source_table"],
            condition=Condition.ANY_UPDATED,
            min_time_between_triggers_seconds=300,
            wait_after_last_change_seconds=60
        )
    ),
    tasks=[...]
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `table_names` | Yes | List of Unity Catalog tables to monitor |
| `condition` | No | `ANY_UPDATED` (default) - trigger when any table updates |
| `min_time_between_triggers_seconds` | No | Minimum wait between triggers |
| `wait_after_last_change_seconds` | No | Wait time after last change |

### Requirements

- Tables must be in Unity Catalog
- Job identity needs `SELECT` permission on monitored tables
- Works with Delta tables (managed and external)

---

## Continuous Jobs

Always-running jobs that automatically restart.

### DABs YAML

```yaml
resources:
  jobs:
    streaming_job:
      name: "Streaming Processor"
      continuous:
        pause_status: UNPAUSED
      tasks:
        - task_key: stream
          notebook_task:
            notebook_path: ../src/streaming_processor.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Continuous, PauseStatus

w = WorkspaceClient()

job = w.jobs.create(
    name="Streaming Processor",
    continuous=Continuous(
        pause_status=PauseStatus.UNPAUSED
    ),
    tasks=[...]
)
```

### Continuous Job Behavior

- Job runs immediately when created/unpaused
- Automatically restarts after completion or failure
- Maintains one active run at a time
- Use `pause_status: PAUSED` to stop

### Control Continuous Jobs

```python
# Pause continuous job
w.jobs.update(
    job_id=12345,
    new_settings=JobSettings(
        continuous=Continuous(pause_status=PauseStatus.PAUSED)
    )
)

# Resume continuous job
w.jobs.update(
    job_id=12345,
    new_settings=JobSettings(
        continuous=Continuous(pause_status=PauseStatus.UNPAUSED)
    )
)
```

---

## Manual Runs

Run jobs on-demand without automatic triggers.

### No Trigger Configuration

Simply omit `schedule`, `trigger`, and `continuous`:

```yaml
resources:
  jobs:
    manual_job:
      name: "Manual Job"
      # No schedule/trigger = manual only
      tasks:
        - task_key: run
          notebook_task:
            notebook_path: ../src/manual_task.py
```

### Trigger Manual Run

**Python SDK:**
```python
# Run with default parameters
run = w.jobs.run_now(job_id=12345)

# Run with custom parameters
run = w.jobs.run_now(
    job_id=12345,
    job_parameters={"env": "prod", "date": "2024-01-15"}
)

# Wait for completion
run_result = w.jobs.run_now_and_wait(job_id=12345)
```

**CLI:**
```bash
# Run job
databricks jobs run-now 12345

# Run with parameters
databricks jobs run-now 12345 --job-params '{"env": "prod"}'
```

**DABs:**
```bash
databricks bundle run my_job_resource_key
```

---

## Combining Triggers

A job can have multiple trigger types (evaluated independently):

```yaml
resources:
  jobs:
    multi_trigger:
      name: "Multi-Trigger Job"
      # Cron schedule
      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
        timezone_id: "UTC"
        pause_status: UNPAUSED
      # Also trigger on file arrival
      trigger:
        pause_status: UNPAUSED
        file_arrival:
          url: "s3://my-bucket/urgent/"
      tasks:
        - task_key: process
          notebook_task:
            notebook_path: ../src/process.py
```

### Trigger Priority

When multiple triggers fire simultaneously:
- Job queues runs if `max_concurrent_runs > 1`
- Otherwise, subsequent triggers are skipped while a run is active

```yaml
max_concurrent_runs: 1  # Only one run at a time (default)
```

---

## Pause and Resume

### Pause Scheduled Job

```yaml
schedule:
  quartz_cron_expression: "0 0 8 * * ?"
  timezone_id: "UTC"
  pause_status: PAUSED  # Job won't run on schedule
```

### Pause via SDK

```python
from databricks.sdk.service.jobs import JobSettings, CronSchedule, PauseStatus

w.jobs.update(
    job_id=12345,
    new_settings=JobSettings(
        schedule=CronSchedule(
            quartz_cron_expression="0 0 8 * * ?",
            timezone_id="UTC",
            pause_status=PauseStatus.PAUSED
        )
    )
)
```

### Pause via CLI

```bash
databricks jobs update 12345 --json '{
  "new_settings": {
    "schedule": {
      "pause_status": "PAUSED"
    }
  }
}'
```
