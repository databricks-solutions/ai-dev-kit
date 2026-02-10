# Databricks Apps (APX Framework)

Build full-stack Databricks applications using APX framework (FastAPI + React).

## Overview

This skill guides you through building full-stack Databricks applications using the APX framework, which combines a FastAPI backend with a React frontend powered by TanStack Router and auto-generated OpenAPI clients. It activates when users request a "Databricks app" or mention the APX framework, and walks through a structured workflow from initialization through backend modeling, frontend development, testing, deployment, and documentation.

## What's Included

```
databricks-app-apx/
├── SKILL.md               # Main skill: workflow phases, trigger conditions, and success criteria
├── backend-patterns.md    # Pydantic model templates and CRUD route patterns
├── best-practices.md      # Critical rules, anti-patterns, debugging checklists
└── frontend-patterns.md   # List/detail page templates, navigation, formatters
```

## Key Topics

- APX framework initialization and MCP server setup
- Three-model Pydantic pattern (EntityIn, EntityOut, EntityListOut)
- FastAPI route conventions with `response_model` and `operation_id`
- Auto-generated OpenAPI client and React hooks
- React Suspense boundaries with skeleton fallbacks
- TanStack Router file-based routing
- shadcn/ui component integration
- Type safety across Python and TypeScript
- Deployment to Databricks via DABs
- Application log monitoring

## When to Use

- User requests a "Databricks app" or "Databricks application"
- Building a full-stack app for Databricks without specifying a framework
- User explicitly mentions the APX framework
- Do NOT use if the user specifies Streamlit, Dash, Node.js, Shiny, Gradio, Flask, or other frameworks

## Related Skills

- [Databricks Apps (Python)](../databricks-app-python/) -- for Streamlit, Dash, Gradio, or Flask apps
- [Asset Bundles](../asset-bundles/) -- deploying APX apps via DABs
- [Databricks Python SDK](../databricks-python-sdk/) -- backend SDK integration
- [Lakebase Provisioned](../lakebase-provisioned/) -- adding persistent PostgreSQL state to apps

## Resources

- [Databricks Apps Documentation](https://docs.databricks.com/dev-tools/databricks-apps/)
- [APX GitHub Repository](https://github.com/databricks-solutions/apx)
