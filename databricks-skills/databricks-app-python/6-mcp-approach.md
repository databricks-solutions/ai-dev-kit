# MCP Tools for App Lifecycle

Use MCP tools to create, deploy, and manage Databricks Apps programmatically. This mirrors the CLI workflow but can be invoked by AI agents.

---

## Workflow

### Step 1: Write App Files Locally

Create your app files in a local folder:

```
my_app/
├── app.py             # Main application
├── models.py          # Pydantic models
├── backend.py         # Data access layer
├── requirements.txt   # Additional dependencies
└── app.yaml           # Databricks Apps configuration
```

### Step 2: Upload to Workspace

```python
# MCP Tool: upload_folder
upload_folder(
    local_folder="/path/to/my_app",
    workspace_folder="/Workspace/Users/user@example.com/my_app"
)
```

### Step 3: Create and Deploy App

```python
# MCP Tool: create_or_update_app (creates if needed + deploys)
result = create_or_update_app(
    name="my-dashboard",
    description="Customer analytics dashboard",
    source_code_path="/Workspace/Users/user@example.com/my_app"
)
# Returns: {"name": "my-dashboard", "url": "...", "created": True, "deployment": {...}}
```

### Step 4: Verify

```python
# MCP Tool: get_app (with logs)
app = get_app(name="my-dashboard", include_logs=True)
# Returns: {"name": "...", "url": "...", "status": "RUNNING", "logs": "...", ...}
```

### Step 5: Iterate

1. Fix issues in local files
2. Re-upload with `upload_folder`
3. Re-deploy with `create_or_update_app` (will update existing + deploy)
4. Check `get_app(name=..., include_logs=True)` for errors
5. Repeat until app is healthy

---

## Quick Reference: MCP Tools

| Tool | Description |
|------|-------------|
| **`create_or_update_app`** | Create app if it doesn't exist, optionally deploy (pass `source_code_path`) |
| **`get_app`** | Get app details by name (with `include_logs=True` for logs), or list all apps |
| **`delete_app`** | Delete an app |
| **`upload_folder`** | Upload local folder to workspace (shared tool) |

---

## Notes

- Add resources (SQL warehouse, Lakebase, etc.) via the Databricks Apps UI after creating the app
- MCP tools use the service principal's permissions — ensure it has access to required resources
- For manual deployment, see [4-deployment.md](4-deployment.md)
