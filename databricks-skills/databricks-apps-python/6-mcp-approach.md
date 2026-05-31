# MCP Tools for App Lifecycle

Use MCP tools to create, deploy, and manage Databricks Apps programmatically. This mirrors the CLI workflow but can be invoked by AI agents.

---

## manage_app - App Lifecycle Management

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `create_or_update` | Idempotent create, deploys if source_code_path provided | name |
| `get` | Get app details (with optional logs) | name |
| `list` | List all apps | (none, optional name_contains filter) |
| `delete` | Delete an app | name |

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
# MCP Tool: manage_workspace_files
manage_workspace_files(
    action="upload",
    local_path="/path/to/my_app",
    workspace_path="/Workspace/Users/user@example.com/my_app"
)
```

### Step 3: Create and Deploy App

```python
# MCP Tool: manage_app (creates if needed + deploys)
result = manage_app(
    action="create_or_update",
    name="my-dashboard",
    description="Customer analytics dashboard",
    source_code_path="/Workspace/Users/user@example.com/my_app"
)
# Returns: {"name": "my-dashboard", "url": "...", "created": True, "deployment": {...}}
```

### Step 4: Verify

```python
# MCP Tool: manage_app (get with logs)
app = manage_app(action="get", name="my-dashboard", include_logs=True)
# Returns: {"name": "...", "url": "...", "status": "RUNNING", "logs": "...", ...}
```

### Step 5: Iterate

1. Fix issues in local files
2. Re-upload with `manage_workspace_files(action="upload", ...)`
3. Re-deploy with `manage_app(action="create_or_update", ...)` (will update existing + deploy)
4. Check `manage_app(action="get", name=..., include_logs=True)` for errors
5. Repeat until app is healthy

---

## Notes

- Add resources (SQL warehouse, Lakebase, etc.) via the Databricks Apps UI after creating the app
- MCP tools use the service principal's permissions — ensure it has access to required resources
- For manual deployment, see [4-deployment.md](4-deployment.md)
