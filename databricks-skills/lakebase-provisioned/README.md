# Lakebase Provisioned

Patterns and best practices for using Lakebase Provisioned (Databricks managed PostgreSQL) for OLTP workloads.

## Overview

This skill covers Lakebase Provisioned, Databricks' managed PostgreSQL database service designed for online transaction processing (OLTP) workloads. It activates when building applications that need a relational database for persistent state, implementing reverse ETL from Delta Lake, or integrating PostgreSQL with Databricks Apps and LangChain agents. The skill provides connection patterns ranging from simple scripts to production-grade setups with automatic OAuth token refresh.

## What's Included

```
lakebase-provisioned/
├── SKILL.md                 # Main skill: quick start, common patterns, CLI reference, troubleshooting
├── connection-patterns.md   # Detailed connection methods (psycopg, SQLAlchemy, pooling, DNS workaround)
└── reverse-etl.md           # Syncing data from Delta Lake tables to Lakebase PostgreSQL
```

## Key Topics

- Creating and managing Lakebase Provisioned instances
- OAuth token generation and automatic refresh (1-hour expiry)
- Direct psycopg3 connections for scripts and notebooks
- SQLAlchemy async engine with connection pooling and token injection
- DNS resolution workaround for macOS
- Databricks Apps integration with environment variables
- Unity Catalog registration for governance
- MLflow model resource declarations
- Reverse ETL: synced tables with FULL and INCREMENTAL modes
- Scheduling syncs via Databricks Jobs
- CLI commands for instance lifecycle management

## When to Use

- Building applications that need a PostgreSQL database for transactional workloads
- Adding persistent state to Databricks Apps
- Implementing reverse ETL from Delta Lake to an operational database
- Storing chat or agent memory for LangChain applications
- Setting up connection pooling with OAuth token refresh for production apps

## Related Skills

- [Databricks Apps (APX)](../databricks-app-apx/) -- full-stack apps that can use Lakebase for persistence
- [Databricks Apps (Python)](../databricks-app-python/) -- Python apps with Lakebase backend
- [Databricks Python SDK](../databricks-python-sdk/) -- SDK used for instance management and token generation
- [Asset Bundles](../asset-bundles/) -- deploying apps with Lakebase resources
- [Databricks Jobs](../databricks-jobs/) -- scheduling reverse ETL sync jobs

## Resources

- [Lakebase Documentation](https://docs.databricks.com/aws/en/database)
- [Databricks Python SDK - Database API](https://databricks-sdk-py.readthedocs.io/en/latest/)
- [psycopg 3 Documentation](https://www.psycopg.org/psycopg3/docs/)
- [SQLAlchemy Async Engine](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
