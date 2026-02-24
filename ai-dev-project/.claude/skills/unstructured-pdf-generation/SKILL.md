---
name: unstructured-pdf-generation
description: "Generate synthetic PDF documents for RAG and unstructured data use cases. Use when creating test PDFs, demo documents, or evaluation datasets for retrieval systems."
---

# Unstructured PDF Generation

Generate realistic synthetic PDF documents using LLM for RAG (Retrieval-Augmented Generation) and unstructured data use cases.

## Overview

This skill uses the `generate_pdf_documents` MCP tool to create professional PDF documents with:
- LLM-generated content based on your description
- Accompanying JSON files with questions and evaluation guidelines (for RAG testing)
- Automatic upload to Unity Catalog Volumes

## Quick Start

Use the `generate_pdf_documents` MCP tool:
- `catalog`: "my_catalog"
- `schema`: "my_schema"
- `description`: "Technical documentation for a cloud infrastructure platform including setup guides, troubleshooting procedures, and API references."
- `count`: 10

This generates 10 PDF documents and saves them to `/Volumes/my_catalog/my_schema/raw_data/pdf_documents/` (using default volume and folder).

### With Custom Location

Use the `generate_pdf_documents` MCP tool:
- `catalog`: "my_catalog"
- `schema`: "my_schema"
- `description`: "HR policy documents..."
- `count`: 10
- `volume`: "custom_volume"
- `folder`: "hr_policies"
- `overwrite_folder`: true

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `catalog` | string | Yes | - | Unity Catalog name |
| `schema` | string | Yes | - | Schema name |
| `description` | string | Yes | - | Detailed description of what PDFs should contain |
| `count` | int | Yes | - | Number of PDFs to generate |
| `volume` | string | No | `raw_data` | Volume name (created if not exists) |
| `folder` | string | No | `pdf_documents` | Folder within volume for output files |
| `doc_size` | string | No | `MEDIUM` | Document size: `SMALL` (~1 page), `MEDIUM` (~5 pages), `LARGE` (~10+ pages) |
| `overwrite_folder` | bool | No | `false` | If true, deletes existing folder contents first |

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

Use the `generate_pdf_documents` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "hr_demo"
- `description`: "HR policy documents for a technology company including employee handbook, leave policies, performance review procedures, benefits guide, and workplace conduct guidelines."
- `count`: 15
- `folder`: "hr_policies"
- `overwrite_folder`: true

### Pattern 2: Technical Documentation

Use the `generate_pdf_documents` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "tech_docs"
- `description`: "Technical documentation for a SaaS analytics platform including installation guides, API references, troubleshooting procedures, security best practices, and integration tutorials."
- `count`: 20
- `folder`: "product_docs"
- `overwrite_folder`: true

### Pattern 3: Financial Reports

Use the `generate_pdf_documents` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "finance_demo"
- `description`: "Financial documents for a retail company including quarterly reports, expense policies, budget guidelines, and audit procedures."
- `count`: 12
- `folder`: "reports"
- `overwrite_folder`: true

### Pattern 4: Training Materials

Use the `generate_pdf_documents` MCP tool:
- `catalog`: "ai_dev_kit"
- `schema`: "training"
- `description`: "Training materials for new software developers including onboarding guides, coding standards, code review procedures, and deployment workflows."
- `count`: 8
- `folder`: "courses"
- `overwrite_folder`: true

## Workflow

1. **Ask for destination**: Default to `ai_dev_kit` catalog, ask user for schema name
2. **Get description**: Ask what kind of documents they need
3. **Generate PDFs**: Call `generate_pdf_documents` MCP tool with appropriate parameters
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

## Environment Configuration

The tool requires LLM configuration via environment variables:

```bash
# Databricks Foundation Models (default)
LLM_PROVIDER=DATABRICKS
DATABRICKS_MODEL=databricks-meta-llama-3-3-70b-instruct

# Or Azure OpenAI
LLM_PROVIDER=AZURE
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **"No LLM endpoint configured"** | Set `DATABRICKS_MODEL` or `AZURE_OPENAI_DEPLOYMENT` environment variable |
| **"Volume does not exist"** | The tool creates volumes automatically; ensure you have CREATE VOLUME permission |
| **"PDF generation timeout"** | Reduce `count` or check LLM endpoint availability |
| **Low quality content** | Provide more detailed `description` with specific topics and document types |
