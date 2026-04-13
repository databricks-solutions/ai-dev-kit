---
name: databricks-unstructured-pdf-generation
description: "Generate PDF documents from HTML and upload to Unity Catalog volumes. Use for creating test PDFs, demo documents, reports, or evaluation datasets."
---

# PDF Generation from HTML

Convert HTML content to PDF documents and upload them to Unity Catalog Volumes.

## Overview

Generate PDFs from HTML using the self-contained `scripts/pdf_generator.py` script. You (the LLM) generate the HTML content, and the Python script handles conversion and upload using the Databricks CLI.

## Installation

Install plutoprint for HTML to PDF conversion:

```bash
# Preferred: use uv for faster installation
uv pip install plutoprint

# Fallback: use pip if uv is not available
pip install plutoprint
```

## Python Script Pattern

```python
# Import from the skill's pdf_generator.py
from pdf_generator import generate_and_upload_pdf

result = generate_and_upload_pdf(
    html_content=html_content,  # Complete HTML document
    filename="report.pdf",       # PDF filename
    catalog="my_catalog",        # Unity Catalog name
    schema="my_schema",          # Schema name
    volume="raw_data",           # Volume name (default: "raw_data")
    folder=None,                 # Optional subfolder
)
print(f"Uploaded to: {result.volume_path}")
```

**Returns:**
```json
{
    "success": true,
    "volume_path": "/Volumes/catalog/schema/volume/filename.pdf",
    "error": null
}
```

## CLI Usage

The script can also be run directly from command line:

```bash
# Generate from inline HTML
python scripts/pdf_generator.py generate --html '<html><body><h1>Hello</h1></body></html>' \
    --filename hello.pdf --catalog my_catalog --schema my_schema

# Generate from HTML file
python scripts/pdf_generator.py generate --html-file input.html \
    --filename report.pdf --catalog my_catalog --schema my_schema --folder reports

# Get JSON output
python scripts/pdf_generator.py generate --html '...' --filename test.pdf \
    --catalog my_catalog --schema my_schema --json
```

## Quick Start

Generate a simple PDF:

```python
from pdf_generator import generate_and_upload_pdf

generate_and_upload_pdf(
    html_content='''<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }
        .section { margin: 20px 0; }
    </style>
</head>
<body>
    <h1>Quarterly Report Q1 2024</h1>
    <div class="section">
        <h2>Executive Summary</h2>
        <p>Revenue increased 15% year-over-year...</p>
    </div>
</body>
</html>''',
    filename="q1_report.pdf",
    catalog="my_catalog",
    schema="my_schema"
)
```

## Performance: Generate Multiple PDFs in Parallel

**IMPORTANT**: PDF generation and upload can take 2-5 seconds per document. When generating multiple PDFs, use concurrent execution to maximize throughput.

### Example: Generate 5 PDFs in Parallel

```python
import concurrent.futures
from pdf_generator import generate_and_upload_pdf

pdfs_to_generate = [
    {"html_content": "<html>...Employee Handbook content...</html>", "filename": "employee_handbook.pdf"},
    {"html_content": "<html>...Leave Policy content...</html>", "filename": "leave_policy.pdf"},
    {"html_content": "<html>...Code of Conduct content...</html>", "filename": "code_of_conduct.pdf"},
    {"html_content": "<html>...Benefits Guide content...</html>", "filename": "benefits_guide.pdf"},
    {"html_content": "<html>...Remote Work Policy content...</html>", "filename": "remote_work_policy.pdf"},
]

def generate_pdf(pdf_config):
    return generate_and_upload_pdf(
        html_content=pdf_config["html_content"],
        filename=pdf_config["filename"],
        catalog="hr_catalog",
        schema="policies",
        folder="2024"
    )

# Generate in parallel
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(generate_pdf, pdfs_to_generate))

for result in results:
    print(f"Uploaded: {result.volume_path}")
```

By calling these in parallel (not sequentially), 5 PDFs that would take 15-25 seconds sequentially complete in 3-5 seconds total.

## HTML Best Practices

### Use Complete HTML5 Structure

Always include the full HTML structure:

```html
<!DOCTYPE html>
<html>
<head>
    <style>
        /* Your CSS here */
    </style>
</head>
<body>
    <!-- Your content here -->
</body>
</html>
```

### CSS Features Supported

PlutoPrint supports modern CSS3:
- Flexbox and Grid layouts
- CSS variables (`--var-name`)
- Web fonts (system fonts recommended)
- Colors, backgrounds, borders
- Tables with styling

### CSS to Avoid

- Animations and transitions (static PDF)
- Interactive elements (forms, hover effects)
- External resources (images via URL) - use embedded base64 if needed

### Professional Document Template

```html
<!DOCTYPE html>
<html>
<head>
    <style>
        :root {
            --primary: #1a73e8;
            --text: #202124;
            --gray: #5f6368;
        }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 50px;
            color: var(--text);
            line-height: 1.6;
        }
        h1 {
            color: var(--primary);
            border-bottom: 3px solid var(--primary);
            padding-bottom: 15px;
        }
        h2 { color: var(--text); margin-top: 30px; }
        .highlight {
            background: #e8f0fe;
            padding: 15px;
            border-left: 4px solid var(--primary);
            margin: 20px 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            border: 1px solid #dadce0;
            padding: 12px;
            text-align: left;
        }
        th { background: #f1f3f4; }
        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #dadce0;
            color: var(--gray);
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <h1>Document Title</h1>

    <h2>Section 1</h2>
    <p>Content here...</p>

    <div class="highlight">
        <strong>Important:</strong> Key information highlighted here.
    </div>

    <h2>Data Table</h2>
    <table>
        <tr><th>Column 1</th><th>Column 2</th><th>Column 3</th></tr>
        <tr><td>Data</td><td>Data</td><td>Data</td></tr>
    </table>

    <div class="footer">
        Generated on 2024-01-15 | Confidential
    </div>
</body>
</html>
```

## Common Patterns

### Pattern 1: Technical Documentation

Generate API documentation, user guides, or technical specs:

```python
from pdf_generator import generate_and_upload_pdf

generate_and_upload_pdf(
    html_content='''<!DOCTYPE html>
<html>
<head><style>
    body { font-family: monospace; margin: 40px; }
    code { background: #f4f4f4; padding: 2px 6px; }
    pre { background: #f4f4f4; padding: 15px; overflow-x: auto; }
    .endpoint { background: #e3f2fd; padding: 10px; margin: 10px 0; }
</style></head>
<body>
    <h1>API Reference</h1>
    <div class="endpoint">
        <code>GET /api/v1/users</code>
        <p>Returns a list of all users.</p>
    </div>
    <h2>Request Headers</h2>
    <pre>Authorization: Bearer {token}
Content-Type: application/json</pre>
</body>
</html>''',
    filename="api_reference.pdf",
    catalog="docs_catalog",
    schema="api_docs"
)
```

### Pattern 2: Business Reports

```python
from pdf_generator import generate_and_upload_pdf

generate_and_upload_pdf(
    html_content='''<!DOCTYPE html>
<html>
<head><style>
    body { font-family: Georgia, serif; margin: 50px; }
    .metric { display: inline-block; text-align: center; margin: 20px; }
    .metric-value { font-size: 2em; color: #1a73e8; }
    .metric-label { color: #666; }
</style></head>
<body>
    <h1>Q1 2024 Performance Report</h1>
    <div class="metric">
        <div class="metric-value">$2.4M</div>
        <div class="metric-label">Revenue</div>
    </div>
    <div class="metric">
        <div class="metric-value">+15%</div>
        <div class="metric-label">Growth</div>
    </div>
</body>
</html>''',
    filename="q1_2024_report.pdf",
    catalog="finance",
    schema="reports",
    folder="quarterly"
)
```

### Pattern 3: HR Policies

```python
from pdf_generator import generate_and_upload_pdf

generate_and_upload_pdf(
    html_content='''<!DOCTYPE html>
<html>
<head><style>
    body { font-family: Arial; margin: 40px; line-height: 1.8; }
    .policy-section { margin: 30px 0; }
    .important { background: #fff3e0; padding: 15px; border-radius: 5px; }
</style></head>
<body>
    <h1>Employee Leave Policy</h1>
    <p><em>Effective: January 1, 2024</em></p>

    <div class="policy-section">
        <h2>1. Annual Leave</h2>
        <p>All full-time employees are entitled to 20 days of paid annual leave per calendar year.</p>
    </div>

    <div class="important">
        <strong>Note:</strong> Leave requests must be submitted at least 2 weeks in advance.
    </div>
</body>
</html>''',
    filename="leave_policy.pdf",
    catalog="hr_catalog",
    schema="policies"
)
```

## Workflow for Multiple Documents

When asked to generate multiple PDFs:

1. **Plan the documents**: Determine titles, content structure for each
2. **Generate HTML for each**: Create complete HTML documents
3. **Call tool in parallel**: Make multiple simultaneous `generate_and_upload_pdf` calls
4. **Report results**: Summarize successful uploads and any errors

## Prerequisites

- Unity Catalog schema must exist
- Volume must exist (default: `raw_data`)
- User must have WRITE permission on the volume
- Databricks CLI must be configured and authenticated

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Volume does not exist" | Create the volume first or use an existing one |
| "Schema does not exist" | Create the schema or check the name |
| PDF looks wrong | Check HTML/CSS syntax, use supported CSS features |
| Slow generation | Call multiple PDFs in parallel, not sequentially |
| CLI not found | Ensure `databricks` CLI is installed and in PATH |
