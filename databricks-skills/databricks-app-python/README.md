# Databricks Python App Skill

Builds Python-based Databricks applications using Dash, Streamlit, Gradio, Flask, FastAPI, or Reflex.

## Overview

This skill guides you through building Python applications for Databricks Apps, covering framework selection, OAuth authorization (app and user auth), app resources, data connectivity (SQL warehouse, Lakebase, model serving), and deployment. It activates when users request a Python web app, dashboard, ML demo, or REST API for Databricks. For full code examples, see the [Databricks Apps Cookbook](https://apps-cookbook.dev/).

## What's Included

```
databricks-app-python/
├── SKILL.md               # Main skill: rules, framework selector, routing, architecture, issues
├── README.md              # This file
├── 1-authorization.md     # OAuth: app auth, user auth (OBO), scopes, per-framework examples
├── 2-app-resources.md     # Resource types, valueFrom, communication strategies
├── 3-frameworks.md        # All frameworks: Dash, Streamlit, Gradio, Flask, FastAPI, Reflex
├── 4-deployment.md        # CLI, DABs, app.yaml, post-deployment verification
├── 5-lakebase.md          # Lakebase (PostgreSQL) connectivity patterns
└── 6-mcp-approach.md      # MCP tools for app lifecycle management
```

## Key Topics

- Framework selection (Dash, Streamlit, Gradio, Flask, FastAPI, Reflex)
- OAuth authorization: app auth (service principal) and user auth (on-behalf-of)
- App resources: SQL warehouse, Lakebase, model serving, secrets, volumes
- `valueFrom` pattern in app.yaml for portable resource configuration
- SQL warehouse connectivity via `databricks-sql-connector`
- Lakebase (PostgreSQL) connectivity via `psycopg2` / `asyncpg`
- Model serving endpoint integration for AI/ML inference
- Deployment via Databricks CLI and Asset Bundles (DABs)
- MCP tools for programmatic app lifecycle management

## When to Use

- User requests a "Databricks app", "Python app", or "dashboard"
- User mentions Streamlit, Dash, Gradio, Flask, FastAPI, or Reflex
- Building data visualization or analytics dashboards
- Building ML model demos or chat interfaces
- Building REST APIs backed by Databricks data
- Connecting apps to SQL warehouse, Lakebase, or model serving
- Do NOT use if user specifies APX, React, or Node.js (use databricks-app-apx instead)

## Related Skills

- [Databricks Apps (APX)](../databricks-app-apx/) — full-stack apps with FastAPI + React
- [Asset Bundles](../asset-bundles/) — deploying apps via DABs
- [Databricks Python SDK](../databricks-python-sdk/) — backend SDK integration
- [Lakebase Provisioned](../lakebase-provisioned/) — adding persistent PostgreSQL state
- [Model Serving](../model-serving/) — serving ML models for app integration

## Resources

- [Databricks Apps Cookbook](https://apps-cookbook.dev/) — ready-to-use code snippets
- [Databricks Apps Documentation](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)
- [Resources](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)
- [System Environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)
