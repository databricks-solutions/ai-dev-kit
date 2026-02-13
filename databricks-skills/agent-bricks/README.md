# Agent Bricks

Create and manage Databricks Agent Bricks: Knowledge Assistants (KA) for document Q&A, Genie Spaces for SQL exploration, and Supervisor Agents (MAS) for multi-agent orchestration.

## Overview

This skill covers building conversational AI applications on Databricks using three pre-built Agent Brick types. It activates when you need to create document-based Q&A systems, natural language SQL interfaces, or orchestrate multiple specialized agents into a unified experience. Agent Bricks dramatically reduce the effort needed to go from raw data to a production-ready conversational AI.

## What's Included

```
agent-bricks/
├── SKILL.md                        # Main skill reference: tools, workflows, and best practices
├── 1-knowledge-assistants.md       # Deep dive into KA creation, provisioning, and examples
└── 3-multi-agent-supervisors.md    # Deep dive into MAS routing, agent config, and hierarchical patterns
```

## Key Topics

- Knowledge Assistants (KA) for RAG-based document Q&A over Unity Catalog Volumes
- Genie Spaces for natural language to SQL exploration (delegated to the `databricks-genie` skill)
- Supervisor Agents (MAS) for routing queries across multiple specialized agents
- MCP tools for creating, updating, finding, and deleting each brick type
- Provisioning lifecycle and endpoint status monitoring
- Automatic example ingestion from companion JSON files
- Agent description best practices for accurate MAS query routing
- Hierarchical multi-level MAS architectures

## When to Use

- You need to build a document Q&A chatbot from PDFs or text files stored in Volumes
- You want a natural language interface over structured data in Unity Catalog tables
- You are combining multiple specialized agents (billing, HR, technical support) behind a single conversational endpoint
- You need to find an existing KA or MAS by name to retrieve its tile ID or endpoint name
- You are orchestrating KA endpoints, Genie Spaces, and custom model-serving endpoints together in one MAS

## Related Skills

- [Databricks Genie](../databricks-genie/) -- Comprehensive Genie Space creation, curation, and Conversation API guidance
- [Unstructured PDF Generation](../unstructured-pdf-generation/) -- Generate synthetic PDFs to feed into Knowledge Assistants
- [Synthetic Data Generation](../synthetic-data-generation/) -- Create raw data for Genie Space tables
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- Build bronze/silver/gold tables consumed by Genie Spaces
- [Model Serving](../model-serving/) -- Deploy custom agent endpoints used as MAS agents
- [Vector Search](../vector-search/) -- Build vector indexes for RAG applications paired with KAs

## Resources

- [Databricks Agent Framework Documentation](https://docs.databricks.com/generative-ai/agent-framework/)
- [Databricks Model Serving Documentation](https://docs.databricks.com/machine-learning/model-serving/)
