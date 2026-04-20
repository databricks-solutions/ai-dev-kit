# Knowledge Assistants - Details

For commands, see [SKILL.md](SKILL.md).

## Source Types

### Files (Volume)

```json
{
  "source_type": "files",
  "files": {"path": "/Volumes/catalog/schema/volume/folder/"}
}
```

Supported formats: PDF, TXT, MD, DOCX

### Vector Search Index

Use existing index instead of auto-indexing:

```json
{
  "source_type": "index",
  "index": {
    "index_name": "catalog.schema.my_index",
    "text_col": "content",
    "doc_uri_col": "source_url"
  }
}
```

## Updating Content

1. Add/modify/remove files in the Volume
2. Re-sync: `databricks knowledge-assistants sync-knowledge-sources "knowledge-assistants/{ka_id}"`

## Troubleshooting

**KA stays in CREATING:**
- Wait up to 10 minutes
- Check workspace quotas
- Verify volume path exists

**Documents not indexed:**
- Check file format (PDF, TXT, MD, DOCX)
- Verify volume path (trailing slash matters)
- Check file permissions

**Poor answer quality:**
- Ensure documents are well-structured
- Break large documents into smaller files
- Add clear headings and sections

## Evaluation Questions

When testing a KA, check if the volume or project contains a `pdf_eval_questions.json` file with test questions:

```json
{
  "api_errors_guide.pdf": {
    "question": "What is the solution for error ERR-4521?",
    "expected_fact": "Call /api/v2/auth/refresh with refresh_token before the 3600s TTL expires"
  }
}
```

Use these questions to validate retrieval accuracy. See [databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md) for generating test PDFs with eval questions.
