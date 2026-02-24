# Notifications and Monitoring Reference

## Contents
- [Email Notifications](#email-notifications)
- [Webhook Notifications](#webhook-notifications)
- [Health Rules](#health-rules)
- [Timeout Configuration](#timeout-configuration)
- [Retry Configuration](#retry-configuration)
- [Run Queue Settings](#run-queue-settings)

---

## Email Notifications

Send email alerts for job lifecycle events.

### DABs YAML

```yaml
resources:
  jobs:
    monitored_job:
      name: "Monitored Job"
      email_notifications:
        on_start:
          - "team@example.com"
        on_success:
          - "team@example.com"
        on_failure:
          - "oncall@example.com"
          - "team@example.com"
        on_duration_warning_threshold_exceeded:
          - "oncall@example.com"
        no_alert_for_skipped_runs: true
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobEmailNotifications

w = WorkspaceClient()

job = w.jobs.create(
    name="Monitored Job",
    email_notifications=JobEmailNotifications(
        on_start=["team@example.com"],
        on_success=["team@example.com"],
        on_failure=["oncall@example.com", "team@example.com"],
        on_duration_warning_threshold_exceeded=["oncall@example.com"],
        no_alert_for_skipped_runs=True
    ),
    tasks=[...]
)
```

### Email Notification Events

| Event | Description |
|-------|-------------|
| `on_start` | When job run starts |
| `on_success` | When job run completes successfully |
| `on_failure` | When job run fails |
| `on_duration_warning_threshold_exceeded` | When run exceeds duration warning threshold |
| `on_streaming_backlog_exceeded` | When streaming backlog exceeds threshold |

### Task-Level Email Notifications

```yaml
tasks:
  - task_key: critical_task
    email_notifications:
      on_start:
        - "task-owner@example.com"
      on_success:
        - "task-owner@example.com"
      on_failure:
        - "oncall@example.com"
    notebook_task:
      notebook_path: ../src/critical.py
```

---

## Webhook Notifications

Send HTTP webhooks for job events (Slack, PagerDuty, custom endpoints).

### Create Notification Destination First

Before using webhooks, create a notification destination in the workspace:

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.settings import (
    CreateNotificationDestinationRequest,
    DestinationType,
    SlackConfig
)

w = WorkspaceClient()

# Create Slack destination
destination = w.notification_destinations.create(
    display_name="Slack Alerts",
    config=SlackConfig(
        url="https://hooks.slack.com/services/XXX/YYY/ZZZ"
    )
)

print(f"Destination ID: {destination.id}")
```

### DABs YAML

```yaml
resources:
  jobs:
    webhook_job:
      name: "Job with Webhooks"
      webhook_notifications:
        on_start:
          - id: "notification-destination-uuid"
        on_success:
          - id: "notification-destination-uuid"
        on_failure:
          - id: "pagerduty-destination-uuid"
        on_duration_warning_threshold_exceeded:
          - id: "slack-destination-uuid"
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import WebhookNotifications, Webhook

w = WorkspaceClient()

job = w.jobs.create(
    name="Job with Webhooks",
    webhook_notifications=WebhookNotifications(
        on_start=[Webhook(id="notification-destination-uuid")],
        on_success=[Webhook(id="notification-destination-uuid")],
        on_failure=[Webhook(id="pagerduty-destination-uuid")],
        on_duration_warning_threshold_exceeded=[Webhook(id="slack-destination-uuid")]
    ),
    tasks=[...]
)
```

### Supported Destinations

| Type | Configuration |
|------|---------------|
| Slack | Slack webhook URL |
| Microsoft Teams | Teams webhook URL |
| PagerDuty | PagerDuty integration key |
| Generic Webhook | Custom HTTP endpoint |
| Email | Email addresses |

### Task-Level Webhooks

```yaml
tasks:
  - task_key: critical_task
    webhook_notifications:
      on_failure:
        - id: "pagerduty-destination-uuid"
    notebook_task:
      notebook_path: ../src/critical.py
```

---

## Health Rules

Monitor job health metrics and trigger alerts.

### DABs YAML

```yaml
resources:
  jobs:
    health_monitored:
      name: "Health Monitored Job"
      health:
        rules:
          - metric: RUN_DURATION_SECONDS
            op: GREATER_THAN
            value: 3600  # Alert if run > 1 hour
          - metric: STREAMING_BACKLOG_BYTES
            op: GREATER_THAN
            value: 1073741824  # Alert if backlog > 1GB
          - metric: STREAMING_BACKLOG_SECONDS
            op: GREATER_THAN
            value: 300  # Alert if backlog > 5 minutes
          - metric: STREAMING_BACKLOG_FILES
            op: GREATER_THAN
            value: 1000  # Alert if backlog > 1000 files
          - metric: STREAMING_BACKLOG_RECORDS
            op: GREATER_THAN
            value: 100000  # Alert if backlog > 100k records
      email_notifications:
        on_duration_warning_threshold_exceeded:
          - "oncall@example.com"
        on_streaming_backlog_exceeded:
          - "oncall@example.com"
      tasks:
        - task_key: streaming
          notebook_task:
            notebook_path: ../src/streaming.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobsHealthRules, JobsHealthRule, JobsHealthMetric, JobsHealthOperator

w = WorkspaceClient()

job = w.jobs.create(
    name="Health Monitored Job",
    health=JobsHealthRules(
        rules=[
            JobsHealthRule(
                metric=JobsHealthMetric.RUN_DURATION_SECONDS,
                op=JobsHealthOperator.GREATER_THAN,
                value=3600
            ),
            JobsHealthRule(
                metric=JobsHealthMetric.STREAMING_BACKLOG_BYTES,
                op=JobsHealthOperator.GREATER_THAN,
                value=1073741824
            )
        ]
    ),
    tasks=[...]
)
```

### Health Metrics

| Metric | Description | Use Case |
|--------|-------------|----------|
| `RUN_DURATION_SECONDS` | Total run time | Detect stuck/slow jobs |
| `STREAMING_BACKLOG_BYTES` | Unprocessed data size | Streaming lag |
| `STREAMING_BACKLOG_SECONDS` | Processing delay time | Streaming lag |
| `STREAMING_BACKLOG_FILES` | Unprocessed file count | File processing lag |
| `STREAMING_BACKLOG_RECORDS` | Unprocessed record count | Record processing lag |

### Operators

| Operator | Description |
|----------|-------------|
| `GREATER_THAN` | Value exceeds threshold |

---

## Timeout Configuration

### Job-Level Timeout

```yaml
resources:
  jobs:
    timeout_job:
      name: "Job with Timeout"
      timeout_seconds: 7200  # 2 hours max run time
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Task-Level Timeout

```yaml
tasks:
  - task_key: long_running
    timeout_seconds: 3600  # 1 hour max for this task
    notebook_task:
      notebook_path: ../src/long_running.py
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, NotebookTask

Task(
    task_key="long_running",
    timeout_seconds=3600,
    notebook_task=NotebookTask(
        notebook_path="/Workspace/long_running"
    )
)
```

### Timeout Behavior

- Value `0` = no timeout (default)
- When timeout exceeds, task/job is cancelled
- Partial results may be lost
- Triggers `on_failure` notifications

---

## Retry Configuration

### Task Retry Settings

```yaml
tasks:
  - task_key: flaky_task
    max_retries: 3
    min_retry_interval_millis: 30000  # 30 seconds between retries
    retry_on_timeout: true
    notebook_task:
      notebook_path: ../src/flaky_task.py
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, NotebookTask

Task(
    task_key="flaky_task",
    max_retries=3,
    min_retry_interval_millis=30000,
    retry_on_timeout=True,
    notebook_task=NotebookTask(
        notebook_path="/Workspace/flaky_task"
    )
)
```

### Retry Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | 0 | Number of retry attempts |
| `min_retry_interval_millis` | 0 | Minimum wait between retries |
| `retry_on_timeout` | false | Retry when task times out |

### Retry Behavior

- Retries only apply to task failures
- Each retry is a new task attempt
- Retry count resets for each job run
- Dependencies wait for retries to complete

---

## Run Queue Settings

Control concurrent run behavior.

### Maximum Concurrent Runs

```yaml
resources:
  jobs:
    concurrent_job:
      name: "Concurrent Job"
      max_concurrent_runs: 5  # Allow up to 5 simultaneous runs
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Queue Settings

```yaml
resources:
  jobs:
    queued_job:
      name: "Queued Job"
      max_concurrent_runs: 1
      queue:
        enabled: true  # Queue additional runs instead of skipping
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import QueueSettings

w = WorkspaceClient()

job = w.jobs.create(
    name="Queued Job",
    max_concurrent_runs=1,
    queue=QueueSettings(enabled=True),
    tasks=[...]
)
```

### Behavior Options

| Setting | Behavior |
|---------|----------|
| `max_concurrent_runs=1`, `queue.enabled=false` | Skip if already running |
| `max_concurrent_runs=1`, `queue.enabled=true` | Queue runs, execute sequentially |
| `max_concurrent_runs=N` | Allow N simultaneous runs |

---

## Notification Settings

Fine-tune notification behavior.

### Job-Level Settings

```yaml
resources:
  jobs:
    notification_settings_job:
      name: "Job with Notification Settings"
      notification_settings:
        no_alert_for_skipped_runs: true
        no_alert_for_canceled_runs: true
      email_notifications:
        on_failure:
          - "team@example.com"
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobNotificationSettings

w = WorkspaceClient()

job = w.jobs.create(
    name="Job with Notification Settings",
    notification_settings=JobNotificationSettings(
        no_alert_for_skipped_runs=True,
        no_alert_for_canceled_runs=True
    ),
    tasks=[...]
)
```

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `no_alert_for_skipped_runs` | false | Suppress alerts when runs are skipped |
| `no_alert_for_canceled_runs` | false | Suppress alerts when runs are canceled |

---

## Complete Monitoring Example

```yaml
resources:
  jobs:
    fully_monitored:
      name: "[${bundle.target}] Fully Monitored ETL"

      # Timeout and retries
      timeout_seconds: 14400  # 4 hours max
      max_concurrent_runs: 1
      queue:
        enabled: true

      # Health monitoring
      health:
        rules:
          - metric: RUN_DURATION_SECONDS
            op: GREATER_THAN
            value: 7200  # Warn if > 2 hours

      # Email notifications
      email_notifications:
        on_start:
          - "team@example.com"
        on_success:
          - "team@example.com"
        on_failure:
          - "oncall@example.com"
          - "team@example.com"
        on_duration_warning_threshold_exceeded:
          - "oncall@example.com"
        no_alert_for_skipped_runs: true

      # Webhook notifications
      webhook_notifications:
        on_failure:
          - id: "pagerduty-destination-uuid"
        on_duration_warning_threshold_exceeded:
          - id: "slack-alerts-uuid"

      # Notification settings
      notification_settings:
        no_alert_for_canceled_runs: true

      tasks:
        - task_key: extract
          max_retries: 2
          min_retry_interval_millis: 60000
          timeout_seconds: 3600
          notebook_task:
            notebook_path: ../src/extract.py

        - task_key: transform
          depends_on:
            - task_key: extract
          max_retries: 1
          timeout_seconds: 3600
          notebook_task:
            notebook_path: ../src/transform.py

        - task_key: load
          depends_on:
            - task_key: transform
          timeout_seconds: 1800
          # Critical task - specific notifications
          email_notifications:
            on_failure:
              - "data-team-lead@example.com"
          notebook_task:
            notebook_path: ../src/load.py
```
