# Quickstart and Helper Scripts

End-to-end deployment recipe using the reference repo at `databricks-field-eng/databricks-aws-integrations` (folder: `genie_with_bedrock_agentcore/demo`). Five helper scripts cover the parts that would otherwise live on a manual checklist.

## Step 0: Capture identifiers

| Variable | Where to find |
| --- | --- |
| `DATABRICKS_HOST` | Workspace URL (no trailing slash), e.g. `https://e2-demo-field-eng.cloud.databricks.com` |
| `GENIE_SPACE_ID` | Genie UI → open space → URL contains `/spaces/<id>` |
| `DATABRICKS_CLIENT_ID` / `_SECRET` | Workspace → Settings → Identity & access → Service principals → OAuth secrets |
| `DATABRICKS_OAUTH_CLIENT_ID` / `_SECRET` | Account console → Settings → App connections → OAuth application integrations → custom integration |
| `AWS_REGION` | Pick a region with Bedrock + AgentCore availability |
| `CFN_DEPLOYER_ROLE_ARN` | (CFN path only) get from your FE Sandbox admin |

## Step 1: Optionally provision a sample Genie space

```bash
DATABRICKS_WAREHOUSE_ID=<any serverless warehouse> \
  python scripts/create_demo_genie_space.py
```

Creates a TPCH-based demo space with 5 sample NL→SQL questions, instructions, and a glossary via the Databricks Genie Spaces REST API.

If your workspace doesn't yet expose the create surface (it's been rolling out through preview), the script falls back to printing the JSON payload for you to paste into the Genie UI's "Create new space" dialog. Either way, the resulting `GENIE_SPACE_ID` goes into `.env`.

## Step 2: Provision AWS

Pick **one** path:

```bash
# external AWS account
cd terraform && terraform init && terraform apply ...

# or FE Sandbox / restricted account
cd cloudformation && ./deploy.sh
```

Capture outputs into `.env`: `AGENTCORE_GATEWAY_ID`, `DATABRICKS_OAUTH_PROVIDER_ARN`, `SCHEMA_S3_BUCKET`, `BEDROCK_AGENT_ID`, `BEDROCK_AGENT_ALIAS`.

## Step 3: Register Genie as a Gateway target

```bash
pip install -r src/requirements.txt
python src/register_gateway.py
```

The script:

1. Reads `docs/genie-mcp-schema.json`, substitutes your `DATABRICKS_HOST` and `GENIE_SPACE_ID`, uploads to `s3://$SCHEMA_S3_BUCKET/$SCHEMA_S3_KEY`
2. Calls `bedrock-agentcore-control:CreateGatewayTarget` with the OAuth credential provider ARN

Expected output:

```
Uploaded schema -> s3://dbx-genie-mcp-...-schemas/schemas/genie-mcp-<space-id>.json
Registered target:
{
  "targetId": "...",
  ...
}
```

## Step 4: Wire the Bedrock agent to the Gateway

```bash
python scripts/associate_gateway.py
```

Creates an action group on the Bedrock agent backed by the AgentCore Gateway via `bedrock-agent:CreateAgentActionGroup` with `actionGroupExecutor.agentCoreGatewayId`. Then calls `prepare_agent` to make the change live.

If the SDK surface for `agentCoreGatewayId` isn't yet available in your account/region, the script prints the exact console steps to follow:

1. Open the Bedrock console → Agents → select the provisioned agent
2. Action groups → Add → choose **AgentCore Gateway** as the source
3. Pick the gateway provisioned in Step 2
4. Save → Prepare → verify alias `live` is on the prepared version

## Step 5: (OBO only) Sync the OAuth redirect URI

```bash
python scripts/sync_oauth_redirect.py
```

This closes the OAuth two-pass loop:

1. Fetches the redirect URI from AgentCore Identity (`bedrock-agentcore-control:GetOauthCredentialProvider`)
2. Pushes it to the Databricks custom OAuth app via the Account API (`PATCH /api/2.0/accounts/{account_id}/oauth2/custom-app-integrations/{integration_id}`)
3. If the optional Account API env vars (`DATABRICKS_ACCOUNT_*`) aren't populated, just prints the URI for manual paste into the Account console

Without this step, OBO mode will `401` at token exchange because the Databricks OAuth app rejects the unfamiliar redirect URI.

## Step 6: Smoke test

```bash
python src/bedrock_agent_test.py "What were our top 5 customers by revenue last quarter?"
```

Expected:

- `[trace] tool call -> /tools/query_genie`
- A natural-language answer that cites the SQL Genie generated and the row count

## Step 7: Validate governance (OBO only)

Required before claiming user-level governance in a customer demo:

1. Run the same question as **two distinct end users** with different UC grants
2. Confirm different rows or `403` for the user without grants
3. Inspect `system.access.audit` — confirm the SQL is attributed to the **human end user**, not the OAuth app's client ID

## Helper script reference

| Script | What it does | Fallback |
| --- | --- | --- |
| `scripts/create_demo_genie_space.py` | Creates a TPCH-based Genie space with Trusted Assets via the Genie Spaces API | Prints JSON for manual paste into Genie UI |
| `src/register_gateway.py` | Uploads OpenAPI schema to S3, registers Genie as a Gateway target | None — required step |
| `scripts/associate_gateway.py` | Wires the Bedrock agent to the Gateway as an action group | Prints exact Bedrock console steps |
| `scripts/sync_oauth_redirect.py` | Pushes AgentCore redirect URI to the Databricks OAuth app | Prints URI for manual paste into Account console |
| `src/bedrock_agent_test.py` | End-to-end smoke test invoking the agent | None — diagnostic |

## Local-development bridge (optional)

`src/genie_mcp_proxy.py` is a FastAPI proxy that wraps the Genie Conversation API directly. Use it when you want to test custom orchestration locally before involving AgentCore Gateway:

```bash
AUTH_MODE=m2m python src/genie_mcp_proxy.py
# proxy is now at http://localhost:8080
curl -X POST http://localhost:8080/tools/query_genie \
  -H "Content-Type: application/json" \
  -d '{"question":"top 5 customers by revenue last quarter"}'
```

In `obo` mode the proxy expects an end-user bearer token in the `Authorization` header (the default when AgentCore Gateway calls a self-hosted target).
