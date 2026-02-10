# Databricks Lakeflow Jobs

Orchestrate data workflows with multi-task DAGs, flexible triggers, and comprehensive monitoring on Databricks.

## Overview

This skill covers creating, configuring, running, and monitoring Databricks Jobs using the Python SDK, CLI, or Asset Bundles. It activates whenever users need to create jobs, set up schedules or event-driven triggers, configure notifications, or manage job runs. The skill provides complete reference material for all task types (notebook, Python, SQL, dbt, pipeline, and more), trigger mechanisms (cron, periodic, file arrival, table update, continuous), and monitoring capabilities (email/webhook notifications, health rules, retries, timeouts).

## What's Included

```
databricks-jobs/
├── SKILL.md
├── task-types.md
├── triggers-schedules.md
├── notifications-monitoring.md
└── examples.md
```

## Key Topics

- Multi-task DAG workflows with `depends_on` and conditional `run_if` logic
- Task types: notebook, Spark Python, Python wheel, SQL, dbt, pipeline, Spark JAR, run-job, for-each
- Trigger types: cron schedule, periodic interval, file arrival, table update, continuous
- Compute configuration: job clusters, autoscaling, existing clusters, serverless
- Job parameters and `dbutils.widgets.get()` access in notebooks
- Email and webhook notifications for job lifecycle events
- Health rules, timeout configuration, and retry policies
- Run queue settings
- Permissions model (CAN_VIEW, CAN_MANAGE_RUN, CAN_MANAGE)
- Python SDK, CLI, and Asset Bundle (DABs) workflows
- Complete examples: ETL pipelines, scheduled refreshes, event-driven pipelines, ML training, multi-environment deployments, streaming jobs, cross-job orchestration

## When to Use

- Creating a new Databricks job or workflow
- Setting up cron-based or event-driven job schedules
- Configuring file arrival or table update triggers
- Building multi-task DAG pipelines with task dependencies
- Adding email or webhook notifications and health monitoring
- Running or managing jobs via Python SDK or CLI
- Deploying jobs through Databricks Asset Bundles
- Troubleshooting job failures, schedule issues, or permission errors

## Related Skills

- [Asset Bundles](../asset-bundles/) -- for deploying jobs via Databricks Asset Bundles
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- for configuring pipelines triggered by jobs
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- for system tables tracking job execution history

## Resources

- [Jobs API Reference](https://docs.databricks.com/api/workspace/jobs)
- [Jobs Documentation](https://docs.databricks.com/en/jobs/index.html)
- [DABs Job Task Types](https://docs.databricks.com/en/dev-tools/bundles/job-task-types.html)
- [Bundle Examples Repository](https://github.com/databricks/bundle-examples)
