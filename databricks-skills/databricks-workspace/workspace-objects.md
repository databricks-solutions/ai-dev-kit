# Workspace Objects Reference

## Object Types

The Databricks workspace contains several types of objects:

| Type | Description | Has Language |
|------|-------------|-------------|
| `NOTEBOOK` | Interactive notebook (Python, SQL, Scala, R) | Yes |
| `FILE` | Arbitrary file (scripts, configs, data) | No |
| `DIRECTORY` | Folder container | No |
| `LIBRARY` | Uploaded library (JAR, wheel, egg) | No |
| `REPO` | Git repo mounted via Repos feature | No |

## Notebook Languages

| Language | Value | File Extension |
|----------|-------|----------------|
| Python | `PYTHON` | `.py` |
| SQL | `SQL` | `.sql` |
| Scala | `SCALA` | `.scala` |
| R | `R` | `.r` |

## Export Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| `SOURCE` | Raw source code (decoded text) | Reading/editing notebook content |
| `HTML` | Rendered HTML (base64) | Sharing as static pages |
| `JUPYTER` | Jupyter `.ipynb` JSON | Interop with Jupyter ecosystem |
| `DBC` | Databricks archive (base64) | Backup/restore of notebook bundles |
| `RAW` | Raw bytes | Binary files |
| `R_MARKDOWN` | R Markdown format | R ecosystem interop |
| `AUTO` | Auto-detect format | When format is unknown |

Default format is `SOURCE`, which returns decoded text suitable for reading and modification.

## Workspace Path Hierarchy

```
/
├── Users/
│   └── user@example.com/      # Per-user home directory
│       ├── notebooks/
│       └── projects/
├── Shared/                     # Shared workspace area
│   └── team-notebooks/
├── Repos/                      # Git repos (managed via Repos API)
│   └── user@example.com/
│       └── my-repo/
└── Workspace/                  # Root workspace (some deployments)
```

### Path Rules

- Paths are **case-sensitive**
- Paths use forward slashes (`/`)
- No trailing slash required
- Maximum path length: 4096 characters
- Notebook paths do **not** include file extensions (e.g., `/Users/me/notebook`, not `/Users/me/notebook.py`)

### Common Root Paths

| Path | Access | Description |
|------|--------|-------------|
| `/Users/{email}` | Owner only (by default) | Personal workspace |
| `/Shared` | All workspace users | Shared notebooks and files |
| `/Repos/{email}/{repo}` | Depends on repo permissions | Git repo checkouts |

## Permissions

Workspace objects inherit permissions from their parent directory. Key rules:

- Users have full access to their own `/Users/{email}` directory
- `/Shared` is accessible to all workspace users by default
- Admins can modify ACLs on any workspace object
- Repos permissions are managed separately via the Repos API

## Size Limits

| Limit | Value |
|-------|-------|
| Notebook size (SOURCE import) | 10 MB |
| File upload size | 500 MB |
| Directory depth | No hard limit (practical: ~50 levels) |
| Objects per directory listing | Returns all objects (no pagination in MCP tool) |
