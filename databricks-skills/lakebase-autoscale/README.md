# Lakebase Autoscaling

Patterns and best practices for using Lakebase Autoscaling (next-gen managed PostgreSQL) with autoscaling, branching, scale-to-zero, and instant restore.

## Overview

This skill covers Lakebase Autoscaling, Databricks' next-generation managed PostgreSQL database service with autoscaling compute, Git-like branching, scale-to-zero, and instant point-in-time restore. It activates when building applications that need an operational database with dynamic scaling, working with database branching for dev/test workflows, implementing reverse ETL from Delta Lake, or managing Lakebase Autoscaling projects, branches, and computes via SDK, CLI, or MCP tools.

## What's Included

```
lakebase-autoscale/
├── SKILL.md                 # Main skill: quick start, common patterns, CLI reference, troubleshooting
├── projects.md              # Project management patterns and settings
├── branches.md              # Branching workflows, protection, and expiration
├── computes.md              # Compute sizing, autoscaling, and scale-to-zero
├── connection-patterns.md   # Connection methods (psycopg, SQLAlchemy, pooling, DNS workaround)
└── reverse-etl.md           # Syncing data from Delta Lake tables to Lakebase PostgreSQL
```

## Key Topics

- Creating and managing Lakebase Autoscaling projects (top-level containers)
- Branch management: create, protect, expire, reset from parent
- Compute sizing from 0.5 to 112 CU with autoscaling ranges
- Scale-to-zero configuration for cost optimization
- OAuth token generation and automatic refresh (1-hour expiry)
- Direct psycopg3 connections for scripts and notebooks
- SQLAlchemy async engine with connection pooling and token injection
- DNS resolution workaround for macOS
- Reverse ETL: synced tables with Snapshot, Triggered, and Continuous modes
- CLI commands for project/branch/compute lifecycle management
- Key differences from Lakebase Provisioned

## When to Use

- Building applications that need a PostgreSQL database with autoscaling compute
- Working with database branching for dev/test/staging workflows
- Adding persistent state to applications with scale-to-zero cost savings
- Implementing reverse ETL from Delta Lake to an operational database via synced tables
- Managing Lakebase Autoscaling projects, branches, computes, or credentials

## Related Skills

- [Lakebase Provisioned](../lakebase-provisioned/) -- fixed-capacity managed PostgreSQL (predecessor)
- [Databricks Apps (APX)](../databricks-app-apx/) -- full-stack apps that can use Lakebase for persistence
- [Databricks Apps (Python)](../databricks-app-python/) -- Python apps with Lakebase backend
- [Databricks Python SDK](../databricks-python-sdk/) -- SDK used for project management and token generation
- [Asset Bundles](../asset-bundles/) -- deploying apps with Lakebase resources
- [Databricks Jobs](../databricks-jobs/) -- scheduling reverse ETL sync jobs

## Resources

- [Lakebase Autoscaling Documentation](https://docs.databricks.com/aws/en/oltp/projects/)
- [Lakebase Autoscaling API Guide](https://docs.databricks.com/aws/en/oltp/projects/api-usage)
- [Databricks Python SDK - Postgres API](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/postgres/postgres.html)
- [psycopg 3 Documentation](https://www.psycopg.org/psycopg3/docs/)
- [SQLAlchemy Async Engine](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
