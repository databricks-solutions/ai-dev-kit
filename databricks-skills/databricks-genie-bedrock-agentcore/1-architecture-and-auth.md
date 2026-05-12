# Architecture and Authentication

## Component map

| Component | Provided by | Role |
| --- | --- | --- |
| Bedrock Agent (Claude / Nova) | AWS | Conversational LLM, calls `query_genie` as a tool |
| AgentCore Gateway | AWS | Hosts the Genie MCP target, brokers tool calls |
| AgentCore Identity | AWS | OAuth credential provider — mints Databricks tokens for the Gateway |
| CloudWatch | AWS | Audit and tracing |
| Managed MCP Server | Databricks | `{DATABRICKS_HOST}/api/2.0/mcp/genie/{space_id}` |
| Genie Space + Trusted Assets | Databricks | NL → SQL with metric definitions |
| Unity Catalog | Databricks | Governance, lineage, audit attribution |
| Delta Lake | Databricks | Governed tables backing the Genie space |

## End-to-end flow (OBO mode)

1. End user sends an NL question to the Bedrock agent
2. The agent decides to call `query_genie` (an MCP tool registered via AgentCore Gateway)
3. AgentCore Gateway looks up the credential provider configured on the target
4. AgentCore Identity exchanges the user's session for a Databricks bearer token via the OAuth `authorization_code` flow against the Databricks workspace OAuth app
5. The Gateway calls `POST {DATABRICKS_HOST}/api/2.0/mcp/genie/{space_id}/tools/query_genie` with that bearer token
6. Databricks validates the token, executes the Genie conversation, runs the resulting SQL through Unity Catalog with the end-user's grants enforced
7. Result (SQL, narrative, rows) flows back to the agent
8. UC audit log attributes the SQL to the human end user

## Two auth modes

### `obo` (recommended for production)

End-user identity propagates via OAuth U2M.

- `grant_type=authorization_code`
- Scopes: `all-apis offline_access`
- Requires: a Databricks workspace OAuth app (custom integration) with a redirect URI matching what AgentCore Identity exposes

What you can claim:
- "Genie answers reflect each user's UC permissions" — true
- "UC audit logs name the human end user" — true
- "No data movement" — true

Caveats to disclose:
- The redirect URI is a two-pass setup (placeholder first, real URI after AgentCore provisions the credential provider). Use `scripts/sync_oauth_redirect.py` to close the loop.
- Refresh-token reuse / per-user TTL is roadmap (v0.2 in the reference repo)

### `m2m` (booth-demo quick start)

Every Genie call uses a Databricks service principal. **Do not claim user-level governance in this mode.**

- `grant_type=client_credentials`
- Scopes: `all-apis`
- Requires: a Databricks SP with workspace + UC read on the Genie space's underlying tables

What you can claim:
- "Bedrock agent answers governed numerical questions" — true (the SP has UC grants)
- "Metric definitions are consistent" — true (Trusted Assets remain authoritative)

Caveats to disclose:
- All callers see the same rows the SP can see; no per-user differentiation
- UC audit attributes SQL to the SP, not to the end user
- Acceptable for single-tenant testing; never ship as the production posture

## OAuth credential provider configuration

The AgentCore Identity OAuth credential provider is the linchpin. In Terraform (`awscc_bedrockagentcore_oauth_credential_provider`) or CloudFormation (`AWS::BedrockAgentCore::OAuthCredentialProvider`):

```hcl
resource "awscc_bedrockagentcore_oauth_credential_provider" "databricks" {
  name                       = "${local.name}-databricks-oauth"
  credential_provider_vendor = "CustomOauth2"
  oauth2_provider_config_input = {
    custom_oauth2_provider_config = {
      client_id              = var.auth_mode == "obo" ? var.databricks_oauth_client_id : var.databricks_client_id
      client_secret          = var.auth_mode == "obo" ? var.databricks_oauth_client_secret : var.databricks_client_secret
      authorization_endpoint = "${var.databricks_host}/oidc/v1/authorize"
      token_endpoint         = "${var.databricks_host}/oidc/v1/token"
      scopes                 = var.auth_mode == "obo" ? ["all-apis", "offline_access"] : ["all-apis"]
      grant_type             = var.auth_mode == "obo" ? "authorization_code" : "client_credentials"
    }
  }
}
```

The Databricks OAuth credentials live in Secrets Manager so the Gateway can fetch them at tool-invocation time. The Gateway target IAM role needs `secretsmanager:GetSecretValue` on the secret ARNs and `s3:GetObject` on the schema bucket.

## Identity flow gotchas

- **Redirect URI mismatch (OBO):** the most common cause of `403` on UC tables. After Terraform/CFN provisions the credential provider, run `aws bedrock-agentcore-control get-oauth-credential-provider` to read the redirect URI, then update the Databricks OAuth app to match. The reference repo's `scripts/sync_oauth_redirect.py` automates this via the Databricks Account API.
- **`DATABRICKS_OAUTH_PROVIDER_ARN` confusion:** this env var is the AgentCore Identity OAuth credential provider ARN, **not** a Secrets Manager ARN. Treating these as the same thing is a common bug — `register_gateway.py` requires the credential provider ARN.
- **AgentCore schema naming:** `AWS::BedrockAgentCore::OAuthCredentialProvider` and the corresponding `awscc_*` attribute names evolved during preview. If `terraform init` or `cfn deploy` errors on a renamed property, check the current CFN registry.

## Governance validation

After deploying in OBO mode, validate that user-level governance actually works before claiming it in a customer demo:

1. Run the same question as **two distinct end users** with different UC grants on the underlying tables
2. Confirm they get **different rows** (or `403` for the user without grants)
3. Inspect UC audit logs in `system.access.audit` — confirm the SQL is attributed to the **human end user**, not to the OAuth app's client ID

If any of those checks fail, the OBO wiring is wrong even if smoke tests pass with one user.
