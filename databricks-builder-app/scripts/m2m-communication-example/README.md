# M2M Communication Example -- App-to-App Integration

A minimal Databricks App that demonstrates calling the **Builder App** as an agent-as-a-service. It shows the full pattern: M2M OAuth authentication, agent invocation, and SSE response streaming.

## How It Works

```
+------------------------+    Bearer token    +------------------------+
|  M2M Communication     | ----------------> |     Builder App        |
|  Example (this app)    | <-- SSE stream -- |     (agent API)        |
+------------------------+                   +------------------------+
```

1. This app's auto-provisioned **service principal** authenticates to the builder app using `WorkspaceClient().config.authenticate()`, which generates an M2M OAuth Bearer token.
2. The builder app validates the token via `WorkspaceClient(token=...).current_user.me()` to resolve the caller's identity.
3. This app invokes the agent (`POST /api/invoke_agent`), then streams events (`POST /api/stream_progress/{id}`) back to the browser.

## Prerequisites

- The **Builder App** must be deployed first (see `databricks-builder-app/README.md`)
- Python 3.11+
- A Databricks workspace with apps enabled

## Setup

### 1. Deploy the Builder App

If not already deployed:

```bash
cd databricks-builder-app
./scripts/deploy.sh <builder-app-name>
```

### 2. Deploy This App

```bash
# Create the app
databricks apps create m2m-communication-example

# Copy and configure app.yaml
cp app.yaml.example app.yaml
# Edit app.yaml: set BUILDER_APP_URL to the builder app's URL

# Upload and deploy
databricks workspace import-dir . /Workspace/Users/<you>/apps/m2m-communication-example --overwrite
databricks apps deploy m2m-communication-example --source-code-path /Workspace/Users/<you>/apps/m2m-communication-example
```

### 3. Grant Permissions (Both Directions)

Each app's service principal needs **CAN USE** permission on the other app. This is required because:

- **This app's SP** needs access to the **builder app** to call its API endpoints
- **The builder app's SP** needs access to **this app** if it ever needs to call back (and for workspace-level auth resolution)

Find each app's service principal name in the Databricks UI (Apps > your app > Settings), then grant permissions:

```bash
# Grant this app's SP access to the builder app
databricks apps update-permissions <builder-app-name> --json '{
  "access_control_list": [{
    "service_principal_name": "<m2m-example-sp-name>",
    "permission_level": "CAN_USE"
  }]
}'

# Grant the builder app's SP access to this app
databricks apps update-permissions m2m-communication-example --json '{
  "access_control_list": [{
    "service_principal_name": "<builder-app-sp-name>",
    "permission_level": "CAN_USE"
  }]
}'
```

> **Note:** If the `users` group already has `CAN_USE` on both apps (the default), these explicit grants may not be needed. Check your app permissions to confirm.

### 4. Verify

Open this app's URL in your browser. Type a message and click **Send**. You should see the agent's response stream in real time.

## Local Development

For local testing, run both apps on your machine:

### Terminal 1 -- Start the Builder App

```bash
cd databricks-builder-app
./scripts/start_dev.sh
```

The builder app runs at `http://localhost:8000`.

### Terminal 2 -- Start This App

```bash
cd databricks-builder-app/scripts/m2m-communication-example

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export BUILDER_APP_URL=http://localhost:8000
export DATABRICKS_TOKEN=dapi...  # Your PAT

# Run
uvicorn app:app --host 0.0.0.0 --port 8001
```

Open `http://localhost:8001` in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | HTML demo UI |
| `POST` | `/ask` | Send message, wait for full response |
| `POST` | `/invoke` | Start agent, get `execution_id` for streaming |
| `GET` | `/stream/{execution_id}` | SSE proxy for real-time streaming |
| `GET` | `/health` | Health check (also pings builder app) |

## File Structure

```
m2m-communication-example/
+-- app.py              # FastAPI app with HTML UI + endpoints
+-- builder_client.py   # HTTP client for builder app (auth, REST, SSE)
+-- app.yaml.example    # Databricks Apps deployment config (copy to app.yaml)
+-- requirements.txt    # Python dependencies
+-- README.md           # This file
```

## Auth Details

### In Databricks Apps (Production)

The calling app authenticates using its auto-provisioned service principal:

```python
from databricks.sdk import WorkspaceClient

# SDK automatically uses the app's SP credentials
headers = WorkspaceClient().config.authenticate()
# headers = {"Authorization": "Bearer <m2m-oauth-token>"}
```

The builder app resolves the caller's identity by validating the token:

```python
client = WorkspaceClient(host=host, token=bearer_token)
me = client.current_user.me()
# Returns the service principal's identity
```

### In Local Development

Use a Personal Access Token (PAT):

```bash
export DATABRICKS_TOKEN=dapi...
```

The client sends it as `Authorization: Bearer <pat>`. The builder app resolves the PAT to your user identity the same way.

## Troubleshooting

### "Failed to invoke agent" / 403

- Ensure both apps' service principals have the correct permissions (see Step 3 above)
- Check that `BUILDER_APP_URL` is correct and reachable

### "BUILDER_APP_URL environment variable is required"

- Set the `BUILDER_APP_URL` in `app.yaml` (deployed) or as an env var (local)

### Connection timeouts

- The SSE stream uses a 60s read timeout to accommodate the builder app's 50s streaming window
- If the builder app is under heavy load, responses may take longer to start
