# Supervisor Agents - Details

For commands, see [SKILL.md](SKILL.md).

## Unity Catalog Functions

Call registered UC functions from the Supervisor Agent.

**Prerequisites:**
- UC Function exists (`CREATE FUNCTION` or Python UDF)
- Grant execute: `GRANT EXECUTE ON FUNCTION catalog.schema.func TO \`<agent_sp>\`;`

**Config:**
```json
{"name": "enricher", "uc_function_name": "catalog.schema.enrich_data", "description": "Enriches customer records"}
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

**3. Config:**
```json
{"name": "operations", "connection_name": "my_mcp", "description": "Execute operations: approve invoices, trigger workflows"}
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

Examples help evaluation and routing optimization. MAS must be ONLINE.

```bash
python scripts/mas_manager.py add_examples TILE_ID '[
    {"question": "I need my invoice for March", "guideline": "Route to billing_agent"},
    {"question": "API returns 500 error", "guideline": "Route to tech_agent"}
]'

python scripts/mas_manager.py list_examples TILE_ID
```

**In automated jobs** (waits for ONLINE):
```bash
python scripts/mas_manager.py add_examples_wait TILE_ID '[...]'
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
