# Knowledge Assistants (KA)

Knowledge Assistants are document-based Q&A systems that use RAG (Retrieval-Augmented Generation) to answer questions from indexed documents.

## What is a Knowledge Assistant?

A KA connects to documents stored in a Unity Catalog Volume and allows users to ask natural language questions. The system:

1. **Indexes** all documents in the volume (PDFs, text files, etc.)
2. **Retrieves** relevant chunks when a question is asked
3. **Generates** an answer using the retrieved context

## When to Use

Use a Knowledge Assistant when:
- You have a collection of documents (policies, manuals, guides, reports)
- Users need to find specific information without reading entire documents
- You want to provide a conversational interface to documentation

## Prerequisites

Before creating a KA, you need documents in a Unity Catalog Volume:

**Option 1: Use existing documents**
- Upload PDFs/text files to a Volume manually or via SDK

**Option 2: Generate synthetic documents**
- Use the `databricks-unstructured-pdf-generation` skill to create realistic PDF documents
- Each PDF gets a companion JSON file with question/guideline pairs for evaluation

## Creating a Knowledge Assistant

Use the `manage_ka` tool with `action="create_or_update"`:

- `name`: "HR Policy Assistant"
- `volume_path`: "/Volumes/my_catalog/my_schema/raw_data/hr_docs"
- `description`: "Answers questions about HR policies and procedures"
- `instructions`: "Be helpful and always cite the specific policy document when answering. If you're unsure, say so."

The tool will:
1. Create the KA with the specified volume as a knowledge source
2. Scan the volume for JSON files with example questions (from PDF generation)
3. Queue examples to be added once the endpoint is ready

## Provisioning Timeline

After creation, the KA endpoint needs to provision:

| Status | Meaning | Duration |
|--------|---------|----------|
| `PROVISIONING` | Creating the endpoint | 2-5 minutes |
| `ONLINE` | Ready to use | - |
| `OFFLINE` | Not currently running | - |

Use `manage_ka` with `action="get"` to check the status:

- `tile_id`: "<the tile_id from create>"

## Adding Example Questions

Example questions help with:
- **Evaluation**: Test if the KA answers correctly
- **User onboarding**: Show users what to ask

### Automatic (from PDF generation)

If you used `generate_pdf_documents`, each PDF has a companion JSON with:
```json
{
  "question": "What is the company's remote work policy?",
  "guideline": "Should mention the 3-day minimum in-office requirement"
}
```

These are automatically added when `add_examples_from_volume=true` (default).

### Manual

Examples can also be specified in the `manage_ka` create_or_update call if needed.

## Best Practices

### Document Organization

- **One volume per topic**: e.g., `/Volumes/catalog/schema/raw_data/hr_docs`, `/Volumes/catalog/schema/raw_data/tech_docs`
- **Clear naming**: Name files descriptively so chunks are identifiable

### Instructions

Good instructions improve answer quality:

```
Be helpful and professional. When answering:
1. Always cite the specific document and section
2. If multiple documents are relevant, mention all of them
3. If the information isn't in the documents, clearly say so
4. Use bullet points for multi-part answers
```

### Updating Content

To update the indexed documents:
1. Add/remove/modify files in the volume
2. Call `manage_ka` with `action="create_or_update"`, the same name and `tile_id`
3. The KA will re-index the updated content

## Example Workflow

1. **Generate PDF documents** using `databricks-unstructured-pdf-generation` skill:
   - Creates PDFs in `/Volumes/catalog/schema/raw_data/pdf_documents`
   - Creates JSON files with question/guideline pairs

2. **Create the Knowledge Assistant**:
   - `name`: "My Document Assistant"
   - `volume_path`: "/Volumes/catalog/schema/raw_data/pdf_documents"

3. **Wait for ONLINE status** (2-5 minutes)

4. **Examples are automatically added** from the JSON files

5. **Test the KA** in the Databricks UI

## Using KA in Supervisor Agents

Knowledge Assistants can be used as agents in a Supervisor Agent (formerly Multi-Agent Supervisor, MAS). Each KA has an associated model serving endpoint.

### Finding the Endpoint Name

Use `manage_ka` with `action="get"` to retrieve the KA details. The response includes:
- `tile_id`: The unique identifier for the KA
- `name`: The KA name (sanitized)
- `endpoint_status`: Current status (ONLINE, PROVISIONING, etc.)

The endpoint name follows this pattern: `ka-{tile_id}-endpoint`

### Finding a KA by Name

If you know the KA name but not the tile_id, use `manage_ka` with `action="find_by_name"`:

```python
manage_ka(action="find_by_name", name="HR_Policy_Assistant")
# Returns: {"found": True, "tile_id": "01abc...", "name": "HR_Policy_Assistant", "endpoint_name": "ka-01abc...-endpoint"}
```

### Example: Adding KA to Supervisor Agent

```python
# First, find the KA
manage_ka(action="find_by_name", name="HR_Policy_Assistant")

# Then use the tile_id in a Supervisor Agent
manage_mas(
    action="create_or_update",
    name="Support_MAS",
    agents=[
        {
            "name": "hr_agent",
            "ka_tile_id": "<tile_id from find_by_name>",
            "description": "Answers HR policy questions from the employee handbook"
        }
    ]
)
```

## Troubleshooting

### Endpoint stays in PROVISIONING

- Check workspace capacity and quotas
- Verify the volume path is accessible
- Wait up to 10 minutes before investigating further

### Documents not indexed

- Ensure files are in a supported format (PDF, TXT, MD)
- Check file permissions in the volume
- Verify the volume path is correct

### Poor answer quality

- Add more specific instructions
- Ensure documents are well-structured
- Consider breaking large documents into smaller files
