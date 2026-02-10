# Asset Bundles

Create and configure Databricks Asset Bundles (DABs) with best practices for multi-environment deployments.

## Overview

This skill provides comprehensive guidance for creating, configuring, and deploying Databricks Asset Bundles. It activates when you are setting up new DAB projects, adding resources like dashboards, pipelines, jobs, or alerts, or configuring multi-environment deployment targets. The skill ensures correct path resolution, permission settings, and variable parameterization across dev, staging, and production environments.

## What's Included

```
asset-bundles/
├── SKILL.md              # Main skill: bundle structure, resource types, commands, and troubleshooting
├── SDP_guidance.md       # Spark Declarative Pipeline configuration patterns for DABs
└── alerts_guidance.md    # SQL Alert v2 API schema and configuration (critical API differences)
```

## Key Topics

- Bundle project structure (`databricks.yml`, `resources/*.yml`, `src/`)
- Multi-environment target configuration (dev/staging/prod)
- Variable parameterization for catalog, schema, and warehouse
- Dashboard resources with `dataset_catalog` and `dataset_schema` parameters
- Pipeline resource configuration (serverless, streaming, batch)
- SQL Alert v2 API schema (evaluation, schedule, notification)
- Job resources with scheduling and permissions
- Volume resources with grants
- Apps resources and `app.yaml` configuration
- Path resolution rules (`../src/` vs `./src/`)
- Bundle validation, deployment, and monitoring commands

## When to Use

- Creating a new Databricks Asset Bundle project from scratch
- Adding dashboard, pipeline, job, alert, volume, or app resources to a bundle
- Configuring multi-environment deployments with variable substitution
- Setting up permissions for bundle resources
- Deploying or running bundle resources via the Databricks CLI
- Debugging path resolution, permission, or schema validation errors

## Related Skills

- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- pipeline definitions referenced by DABs
- [Databricks Apps (APX)](../databricks-app-apx/) -- app deployment via DABs
- [Databricks Apps (Python)](../databricks-app-python/) -- Python app deployment via DABs
- [Databricks Config](../databricks-config/) -- profile and authentication setup for CLI/SDK
- [Databricks Jobs](../databricks-jobs/) -- job orchestration managed through bundles

## Resources

- [Databricks Asset Bundles Documentation](https://docs.databricks.com/dev-tools/bundles/)
- [Bundle Resources Reference](https://docs.databricks.com/dev-tools/bundles/resources)
- [Bundle Configuration Reference](https://docs.databricks.com/dev-tools/bundles/settings)
- [Supported Resource Types](https://docs.databricks.com/aws/en/dev-tools/bundles/resources#resource-types)
- [DAB Examples Repository](https://github.com/databricks/bundle-examples)
