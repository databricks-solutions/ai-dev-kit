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

### Step 3: Create App

```python
# MCP Tool: create_app
result = create_app(
    name="my-dashboard",
    description="Customer analytics dashboard"
)
# Returns: {"name": "my-dashboard", "url": "https://..."}
```

### Step 4: Deploy

```python
# MCP Tool: deploy_app
result = deploy_app(
    app_name="my-dashboard",
    source_code_path="/Workspace/Users/user@example.com/my_app"
)
# Returns: {"deployment_id": "...", "status": "PENDING", ...}
```

### Step 5: Verify

```python
# MCP Tool: get_app
app = get_app(name="my-dashboard")
# Returns: {"name": "...", "url": "...", "status": "RUNNING", ...}

# MCP Tool: get_app_logs
logs = get_app_logs(app_name="my-dashboard")
# Returns: {"logs": "...", ...}
```

### Step 6: Iterate

1. Fix issues in local files
2. Re-upload with `upload_folder`
3. Re-deploy with `deploy_app`
4. Check `get_app_logs` for errors
5. Repeat until app is healthy

---

## Quick Reference: MCP Tools

| Tool | Description |
|------|-------------|
| **`create_app`** | Create a new Databricks App |
| **`get_app`** | Get app details and status |
| **`list_apps`** | List all apps in the workspace |
| **`deploy_app`** | Deploy app from workspace source path |
| **`delete_app`** | Delete an app |
| **`get_app_logs`** | Get app deployment and runtime logs |
| **`upload_folder`** | Upload local folder to workspace (shared tool) |

---

## Notes

- Add resources (SQL warehouse, Lakebase, etc.) via the Databricks Apps UI after creating the app
- MCP tools use the service principal's permissions — ensure it has access to required resources
- For manual deployment, see [4-deployment.md](4-deployment.md)
