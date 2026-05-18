# Supervisor Agents - Details

For commands, see [SKILL.md](SKILL.md). All operations use the native `databricks supervisor-agents` CLI (Beta, requires CLI ≥ 0.299.2).

## Unity Catalog Functions

Call registered UC functions from the Supervisor Agent.

**Prerequisites:**
- UC Function exists (`CREATE FUNCTION` or Python UDF)
- Grant execute: `GRANT EXECUTE ON FUNCTION catalog.schema.func TO \`<agent_sp>\`;`

**Attach as a tool:**
```bash
databricks supervisor-agents create-tool supervisor-agents/<id> enricher --json '{
    "tool_type": "uc_function",
    "description": "Enriches customer records",
    "uc_function": {"name": "catalog.schema.enrich_data"}
}'
```

## External MCP Servers

Connect to external systems (ERP, CRM) via UC HTTP Connection implementing MCP protocol.

**1. Create UC HTTP Connection:**
```sql
CREATE CONNECTION my_mcp TYPE HTTP
OPTIONS (
  host 'https://my-app.databricksapps.com',
  port '443',
  base_path '/api/mcp',
  client_id '<sp_id>',
  client_secret '<sp_secret>',
  oauth_scope 'all-apis',
  token_endpoint 'https://<workspace>.azuredatabricks.net/oidc/v1/token',
  is_mcp_connection 'true'
);
```

**2. Grant access:**
```sql
GRANT USE CONNECTION ON my_mcp TO `<agent_sp>`;
```

**3. Attach as a tool:**
```bash
databricks supervisor-agents create-tool supervisor-agents/<id> operations --json '{
    "tool_type": "uc_connection",
    "description": "Execute operations: approve invoices, trigger workflows",
    "uc_connection": {"name": "my_mcp"}
}'
```

**Test connection:**
```sql
SELECT http_request(conn => 'my_mcp', method => 'POST', path => '', json => '{"jsonrpc":"2.0","method":"tools/list","id":1}');
```

## Writing Good Descriptions

The `description` field drives routing. Be specific:

| Good | Bad |
|------|-----|
| "Handles billing: invoices, payments, refunds, subscriptions" | "Billing agent" |
| "Answers API errors, integration issues, product bugs" | "Technical" |
| "HR policies, PTO, benefits, employee handbook" | "Handles stuff" |

## Adding Examples

Examples help evaluation and routing optimization. **The serving endpoint must be ONLINE.** Right after `create-supervisor-agent` (or a structural `update-supervisor-agent`), the endpoint takes **up to ~10 minutes** to come ONLINE. Examples can be added before that — they're stored on the agent definition — but querying the endpoint to evaluate routing requires readiness.

```bash
# Add an example (guidelines is a repeated string — must use --json)
databricks supervisor-agents create-example supervisor-agents/<id> --json '{
    "question": "I need my invoice for March",
    "guidelines": ["Route to billing_agent"]
}'

databricks supervisor-agents create-example supervisor-agents/<id> --json '{
    "question": "API returns 500 error",
    "guidelines": ["Route to tech_agent"]
}'

# List / inspect / remove
databricks supervisor-agents list-examples supervisor-agents/<id>
databricks supervisor-agents get-example supervisor-agents/<id>/examples/<ex_id>
databricks supervisor-agents delete-example supervisor-agents/<id>/examples/<ex_id>

# Check endpoint readiness before querying
databricks serving-endpoints get <endpoint_name>
```

## Troubleshooting

**Wrong routing:**
- Improve agent descriptions (more specific, less overlap)
- Add examples demonstrating correct routing

**Endpoint not responding:**
- Verify underlying endpoints are running
- Check endpoint logs

**Slow responses:**
- Check underlying endpoint latency
- Review endpoint scaling settings
