# Databricks Model Serving

Deploy MLflow models and AI agents to scalable REST API endpoints.

## Overview

This skill provides end-to-end guidance for deploying classical ML models, custom PyFunc models, and GenAI agents (ResponsesAgent/LangGraph) to Databricks Model Serving endpoints. It activates when you need to log, register, deploy, or query any model type on Databricks. The nine reference files walk through every stage from training to production, including tool integration, async deployment, and package management.

## What's Included

```
model-serving/
├── SKILL.md                    # Main skill reference: decision matrix, MCP tools, quick starts
├── 1-classical-ml.md           # sklearn, xgboost, autolog, and deployment via SDK/UI
├── 2-custom-pyfunc.md          # Custom PythonModel with preprocessing, signatures, and artifacts
├── 3-genai-agents.md           # ResponsesAgent and LangGraph agent patterns
├── 4-tools-integration.md      # UC Functions, Vector Search, and custom @tool integration
├── 5-development-testing.md    # MCP-based upload, install, test, and iterate workflow
├── 6-logging-registration.md   # mlflow.pyfunc.log_model, resources, Unity Catalog registration
├── 7-deployment.md             # Async job-based deployment for agents, SDK deployment for ML
├── 8-querying-endpoints.md     # MCP tools, Python SDK, REST API, and OpenAI-compatible queries
└── 9-package-requirements.md   # DBR versions, pip installs, tested package combinations
```

## Key Topics

- Classical ML deployment with MLflow autolog (sklearn, xgboost, LightGBM, PyTorch)
- Custom PyFunc models with preprocessing, signatures, and external dependencies
- GenAI agents using MLflow 3 ResponsesAgent and LangGraph
- Tool integration: Unity Catalog Functions, Vector Search retriever, custom tools
- MCP-based development and testing workflow (upload, install, run, iterate)
- Model logging and Unity Catalog registration with resource declarations
- Async job-based deployment to avoid MCP timeouts
- Querying endpoints via MCP tools, Python SDK, REST API, and OpenAI-compatible clients
- Package requirements and DBR version compatibility (DBR 16.1+ recommended)
- ResponsesAgent output format (helper methods vs. raw dicts)

## When to Use

- You are deploying an ML model (sklearn, xgboost, custom PyFunc) to a serving endpoint
- You are building and deploying a GenAI agent with ResponsesAgent or LangGraph
- You need to integrate Unity Catalog Functions or Vector Search into an agent
- You are logging and registering a model to Unity Catalog
- You need to query a deployed model or agent endpoint
- You are checking endpoint status or troubleshooting deployment issues
- You need to determine the correct package versions for agent development

## Related Skills

- [Agent Bricks](../agent-bricks/) -- Pre-built agent tiles that deploy to model-serving endpoints
- [Vector Search](../vector-search/) -- Create vector indexes used as retriever tools in agents
- [Databricks Genie](../databricks-genie/) -- Genie Spaces can serve as agents in multi-agent setups
- [MLflow](../mlflow/) -- Evaluate model and agent quality before deployment
- [Databricks Jobs](../databricks-jobs/) -- Job-based async deployment used for agent endpoints

## Resources

- [Model Serving Documentation](https://docs.databricks.com/machine-learning/model-serving/)
- [MLflow 3 ResponsesAgent](https://mlflow.org/docs/latest/llms/responses-agent-intro/)
- [Agent Framework](https://docs.databricks.com/generative-ai/agent-framework/)
