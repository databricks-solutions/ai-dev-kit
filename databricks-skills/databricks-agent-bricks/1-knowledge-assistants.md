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
