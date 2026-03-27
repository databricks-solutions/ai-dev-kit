---
name: databricks-unstructured-pdf-generation
description: "Generate synthetic PDF documents for RAG and unstructured data use cases. Use when creating test PDFs, demo documents, or evaluation datasets for retrieval systems."
---

# Unstructured PDF Generation

Generate realistic synthetic PDF documents using LLM for RAG (Retrieval-Augmented Generation) and unstructured data use cases.

## Overview

This skill provides two MCP tools for creating professional PDF documents:

1. **`generate_and_upload_pdfs`** - Generate multiple PDFs from a description (LLM generates document specs)
2. **`generate_and_upload_pdf`** - Generate one PDF with precise control over content

Both tools:
- Use LLM to generate professional HTML content, then convert to PDF
- Create accompanying JSON files with questions and evaluation guidelines (for RAG testing)
- Upload directly to Unity Catalog Volumes

## Quick Start

### Generate Multiple PDFs (Batch)

Use the `generate_and_upload_pdfs` MCP tool:
- `catalog`: "my_catalog"
- `schema`: "my_schema"
- `description`: "Technical documentation for a cloud infrastructure platform including setup guides, troubleshooting procedures, and API references."
- `count`: 10

This generates 10 PDF documents and saves them to `/Volumes/my_catalog/my_schema/raw_data/pdf_documents/` (using default volume and folder).

### Generate a Single PDF (Precise Control)

Use the `generate_and_upload_pdf` MCP tool when you need control over exactly what document to create:
- `title`: "API Authentication Guide"
- `description`: "Complete guide to REST API authentication for a cloud platform including OAuth2, API keys, and JWT tokens."
- `question`: "What authentication methods are supported?"
- `guideline`: "Answer should mention OAuth2, API keys, and JWT with use cases"
- `catalog`: "my_catalog"
- `schema`: "my_schema"

## Tool 1: generate_and_upload_pdfs (Batch)

Generates multiple PDFs using a 2-step LLM process:
1. LLM generates diverse document specifications based on your description
2. PDFs are generated in parallel from those specifications

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `catalog` | string | Yes | - | Unity Catalog name |
| `schema` | string | Yes | - | Schema name |
| `description` | string | Yes | - | Detailed description of what PDFs should contain |
| `count` | int | Yes | - | Number of PDFs to generate |
| `volume` | string | No | `raw_data` | Volume name (must exist) |
| `folder` | string | No | `pdf_documents` | Folder within volume for output files |
| `doc_size` | string | No | `MEDIUM` | Document size: `SMALL` (~1 page), `MEDIUM` (~5 pages), `LARGE` (~10+ pages) |
| `overwrite_folder` | bool | No | `false` | If true, deletes existing folder contents first |

## Tool 2: generate_and_upload_pdf (Precise Control)

Generates exactly one PDF with full control over its content and metadata.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | string | Yes | - | Document title (also used to generate filename) |
| `description` | string | Yes | - | What this document should contain, including domain context |
| `question` | string | Yes | - | A question answerable by reading this document |
| `guideline` | string | Yes | - | How to evaluate if an answer is correct |
| `catalog` | string | Yes | - | Unity Catalog name |
| `schema` | string | Yes | - | Schema name |
| `volume` | string | No | `raw_data` | Volume name (must exist) |
| `folder` | string | No | `pdf_documents` | Folder within volume |
| `doc_size` | string | No | `MEDIUM` | Document size: `SMALL`, `MEDIUM`, `LARGE` |

### Document Size Guide

- **SMALL**: ~1 page, concise content. Best for quick demos or testing.
- **MEDIUM**: ~4-6 pages, comprehensive coverage. Good balance for most use cases.
- **LARGE**: ~10+ pages, exhaustive documentation. Use for thorough RAG evaluation.

## Output Files

For each document, the tool creates two files:

1. **PDF file** (`<model_id>.pdf`): The generated document
2. **JSON file** (`<model_id>.json`): Metadata for RAG evaluation

### JSON Structure

```json
{
  "title": "API Authentication Guide",
  "category": "Technical",
  "pdf_path": "/Volumes/catalog/schema/volume/folder/doc_001.pdf",
  "question": "What authentication methods are supported by the API?",
  "guideline": "Answer should mention OAuth 2.0, API keys, and JWT tokens with their use cases."
}
```

## Common Patterns

### Pattern 1: HR Policy Documents

Use the `generate_and_upload_pdfs` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "hr_demo"
- `description`: "HR policy documents for a technology company including employee handbook, leave policies, performance review procedures, benefits guide, and workplace conduct guidelines."
- `count`: 15
- `folder`: "hr_policies"
- `overwrite_folder`: true

### Pattern 2: Technical Documentation

Use the `generate_and_upload_pdfs` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "tech_docs"
- `description`: "Technical documentation for a SaaS analytics platform including installation guides, API references, troubleshooting procedures, security best practices, and integration tutorials."
- `count`: 20
- `folder`: "product_docs"
- `overwrite_folder`: true

### Pattern 3: Financial Reports

Use the `generate_and_upload_pdfs` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "finance_demo"
- `description`: "Financial documents for a retail company including quarterly reports, expense policies, budget guidelines, and audit procedures."
- `count`: 12
- `folder`: "reports"
- `overwrite_folder`: true

### Pattern 4: Training Materials

Use the `generate_and_upload_pdfs` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "training"
- `description`: "Training materials for new software developers including onboarding guides, coding standards, code review procedures, and deployment workflows."
- `count`: 8
- `folder`: "courses"
- `overwrite_folder`: true

## Workflow

1. **Ask for destination**: Default to `ai_dev_kit` catalog, ask user for schema name
2. **Get description**: Ask what kind of documents they need
3. **Generate PDFs**: Call `generate_and_upload_pdfs` MCP tool with appropriate parameters
4. **Verify output**: Check the volume path for generated files

## Best Practices

1. **Detailed descriptions**: The more specific your description, the better the generated content
   - BAD: "Generate some HR documents"
   - GOOD: "HR policy documents for a technology company including employee handbook covering remote work policies, leave policies with PTO and sick leave details, performance review procedures with quarterly and annual cycles, and workplace conduct guidelines"

2. **Appropriate count**:
   - For demos: 5-10 documents
   - For RAG testing: 15-30 documents
   - For comprehensive evaluation: 50+ documents

3. **Folder organization**: Use descriptive folder names that indicate content type
   - `hr_policies/`
   - `technical_docs/`
   - `training_materials/`

4. **Use overwrite_folder**: Set to `true` when regenerating to ensure clean state

## Integration with RAG Pipelines

The generated JSON files are designed for RAG evaluation:

1. **Ingest PDFs**: Use the PDF files as source documents for your vector database
2. **Test retrieval**: Use the `question` field to query your RAG system
3. **Evaluate answers**: Use the `guideline` field to assess if the RAG response is correct

Example evaluation workflow:
```python
# Load questions from JSON files
questions = load_json_files(f"/Volumes/{catalog}/{schema}/{volume}/{folder}/*.json")

for q in questions:
    # Query RAG system
    response = rag_system.query(q["question"])

    # Evaluate using guideline
    is_correct = evaluate_response(response, q["guideline"])
```

## LLM Configuration

The tools automatically discover `databricks-gpt-*` endpoints in your workspace. Override with environment variables if needed:

```bash
# Optional: Override auto-discovery
DATABRICKS_MODEL=databricks-gpt-5-4           # Main model for content generation
DATABRICKS_MODEL_NANO=databricks-gpt-5-4-nano # Smaller model (used by default for speed)
```

**Auto-discovery**: If no environment variables are set, the tool lists all serving endpoints and finds the latest `databricks-gpt-*` endpoint (highest version number, must be in READY state).

## Common Issues

| Issue | Solution |
|-------|----------|
| **"No LLM endpoint configured"** | No `databricks-gpt-*` endpoints found. Either deploy one or set `DATABRICKS_MODEL` environment variable |
| **"Volume does not exist"** | Create the volume first; the tool does not auto-create volumes |
| **"PDF generation timeout"** | Reduce `count` or use `doc_size: "SMALL"` |
| **Low quality content** | Provide more detailed `description` with specific topics and document types |

## Related Skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Create Knowledge Assistants that ingest the generated PDFs
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** - Index generated documents for semantic search and RAG
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate structured tabular data (complement to unstructured PDFs)
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - Evaluate RAG systems using the generated question/guideline pairs
