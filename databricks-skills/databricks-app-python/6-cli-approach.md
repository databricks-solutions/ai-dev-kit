# CLI Commands for App Lifecycle

Use the Databricks CLI to create, deploy, and manage Databricks Apps.

---

## databricks apps - App Lifecycle Management

```bash
# List all apps
databricks apps list

# Create an app
databricks apps create --name my-dashboard --json '{"description": "Customer analytics dashboard"}'

# Get app details
databricks apps get my-dashboard

# Deploy an app (from workspace source code)
databricks apps deploy my-dashboard --source-code-path /Workspace/Users/user@example.com/my_app

# Get app logs
databricks apps logs my-dashboard

# Delete an app
databricks apps delete my-dashboard

# By default, after creation, tag apps to track resources created with this skill
databricks workspace-entity-tag-assignments create-tag-assignment \
  apps my-dashboard aidevkit_project --tag-value ai-dev-kit
```

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

```bash
# Upload local folder to workspace
databricks workspace import-dir /path/to/my_app /Workspace/Users/user@example.com/my_app
```

### Step 3: Create and Deploy App

```bash
# Create the app
databricks apps create --name my-dashboard --json '{"description": "Customer analytics dashboard"}'

# Deploy from workspace source
databricks apps deploy my-dashboard --source-code-path /Workspace/Users/user@example.com/my_app
```

### Step 4: Verify

```bash
# Check app status
databricks apps get my-dashboard

# Check logs for errors
databricks apps logs my-dashboard
```

### Step 5: Iterate

1. Fix issues in local files
2. Re-upload with `databricks workspace import-dir /path/to/my_app /Workspace/Users/user@example.com/my_app`
3. Re-deploy with `databricks apps deploy my-dashboard --source-code-path ...`
4. Check `databricks apps logs my-dashboard` for errors
5. Repeat until app is healthy

---

## Notes

- Add resources (SQL warehouse, Lakebase, etc.) via the Databricks Apps UI after creating the app
- CLI uses your configured profile's credentials — ensure you have access to required resources
- For DABs deployment, see [4-deployment.md](4-deployment.md)
