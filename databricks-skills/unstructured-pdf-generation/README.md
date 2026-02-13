# Unstructured PDF Generation

Generate synthetic PDF documents for RAG and unstructured data use cases.

## Overview

This skill uses the `generate_pdf_documents` MCP tool to create realistic, LLM-generated PDF documents with companion JSON evaluation files, then uploads them to Unity Catalog Volumes. It activates when you need test PDFs, demo documents, or evaluation datasets for retrieval systems. The generated JSON files include question/guideline pairs that enable automated RAG pipeline evaluation out of the box.

## What's Included

```
unstructured-pdf-generation/
└── SKILL.md    # Complete reference: parameters, patterns, output format, and integration guide
```

## Key Topics

- Generating synthetic PDFs with LLM-produced content based on a description
- Companion JSON files with question/guideline pairs for RAG evaluation
- Automatic upload to Unity Catalog Volumes
- Configurable document size (SMALL, MEDIUM, LARGE)
- Common patterns: HR policies, technical docs, financial reports, training materials
- Integration with RAG evaluation pipelines
- LLM provider configuration (Databricks Foundation Models or Azure OpenAI)

## When to Use

- You need test or demo PDF documents for a Knowledge Assistant
- You are building a RAG pipeline and need evaluation datasets with ground-truth questions
- You want to populate a Unity Catalog Volume with realistic synthetic documents
- You are prototyping a document Q&A system and need content quickly
- You need to generate documents at scale (5 to 50+) with specific domain focus

## Related Skills

- [Agent Bricks](../agent-bricks/) -- Create Knowledge Assistants that ingest the generated PDFs
- [Vector Search](../vector-search/) -- Index generated documents for semantic search and RAG
- [Synthetic Data Generation](../databricks-data-generation/) -- Generate structured tabular data (complement to unstructured PDFs)
- [MLflow Evaluation](../mlflow-evaluation/) -- Evaluate RAG systems using the generated question/guideline pairs

## Resources

- [Databricks Volumes Documentation](https://docs.databricks.com/volumes/)
- [Databricks RAG Applications](https://docs.databricks.com/generative-ai/retrieval-augmented-generation.html)
