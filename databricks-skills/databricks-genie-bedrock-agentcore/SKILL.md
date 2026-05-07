---
name: databricks-genie-bedrock-agentcore
description: "Expose Databricks Genie spaces as a governed MCP tool to Amazon Bedrock agents through AgentCore Gateway. Use when integrating Databricks Genie with Bedrock agents on AWS, when a customer wants Unity Catalog governance on Bedrock-side analytics, or when avoiding data movement into Bedrock Knowledge Bases. Covers two auth modes (OBO and M2M), two IaC paths (Terraform and CloudFormation), and the AWS+Databricks plumbing required end-to-end."
---

# Databricks Genie via Amazon Bedrock AgentCore Gateway (MCP)

Patterns for exposing **Databricks Genie spaces** as a governed **MCP tool** to **Amazon Bedrock agents** through **AgentCore Gateway** — no data movement into Knowledge Bases, no parallel metric definitions, Unity Catalog governance preserved end-to-end.

## Overview

Bedrock customers building NL-to-SQL agents typically face two unappealing options:

1. **Copy data into a Bedrock Knowledge Base** — loses UC governance, forces metric definitions to be reimplemented outside the data platform
2. **Build a custom NL-to-SQL chain** — reinvents what Genie does and drifts from dashboard semantics

This skill covers the third path: leave the metric definitions and the data in Databricks, expose Genie via the managed MCP endpoint, register it as an AgentCore Gateway target, propagate end-user identity via AgentCore Identity OAuth on-behalf-of-user.

The Databricks-managed Genie MCP endpoint (`{DATABRICKS_HOST}/api/2.0/mcp/genie/{space_id}`) is registered as a target on an AgentCore Gateway. Any Bedrock agent associated with that gateway can call `query_genie` as a tool.

## When to use this skill

- A Bedrock customer wants UC governance for their agent's analytics tools
- A Databricks customer is evaluating Bedrock as the agent surface and needs the Databricks plumbing
- A Field Engineer is preparing a Genie + Bedrock demo (FSI portfolio risk, healthcare clinical ops, retail merch planning, FP&A variance, etc.)

## Two auth modes

| Mode | When | What end-user sees |
| --- | --- | --- |
| `obo` (recommended for production) | Customer demos, multi-user systems | Genie answers reflect each user's UC permissions; UC audit attributes SQL to the human |
| `m2m` (booth-demo quick start) | Single-tenant testing, booth demos | Every call uses a service principal token; all callers see the same rows the SP can see |

**Always disclose auth mode in talk track.** Saying "row-level UC permissions per end user" is a misrepresentation in `m2m` mode. See [1-architecture-and-auth.md](1-architecture-and-auth.md) for full identity-flow detail.

## Two IaC paths

| Path | When |
| --- | --- |
| **Terraform** (uses `awscc` provider for AgentCore primitives) | External AWS account where caller has direct IAM/Bedrock-AgentCore privileges |
| **CloudFormation** (deployed via a pre-blessed exec role) | FE Sandbox / restricted AWS accounts where the caller's SSO role lacks `iam:CreateRole` and `bedrock-agentcore:*` |

The CloudFormation path uses Ioannis Papadopoulos's pre-blessed-exec-role pattern (`aws cloudformation deploy --role-arn $CFN_DEPLOYER_ROLE_ARN`) — see [2-deployment-tf-vs-cfn.md](2-deployment-tf-vs-cfn.md).

## Quick Start

End-to-end deployment recipe (per [3-quickstart-and-scripts.md](3-quickstart-and-scripts.md) for full detail):

```bash
# 1. Clone the reference architecture
git clone https://github.com/databricks-field-eng/databricks-aws-integrations.git
cd databricks-aws-integrations/genie_with_bedrock_agentcore/demo

# 2. Configure
cp .env.example .env
# Fill in: DATABRICKS_HOST, GENIE_SPACE_ID, AWS_REGION
#   For OBO: DATABRICKS_OAUTH_CLIENT_ID/SECRET
#   For M2M: DATABRICKS_CLIENT_ID/SECRET

# 3. (Optional) Stand up a sample Genie space programmatically
DATABRICKS_WAREHOUSE_ID=<any serverless warehouse> \
  python scripts/create_demo_genie_space.py

# 4. Provision AWS — pick one
cd terraform && terraform init && terraform apply       # external AWS
# or
cd cloudformation && ./deploy.sh                        # FE Sandbox

# 5. Register Genie as a Gateway target (uploads schema to S3, calls
#    bedrock-agentcore-control:CreateGatewayTarget)
python src/register_gateway.py

# 6. Wire the Bedrock agent to the Gateway as an action group
python scripts/associate_gateway.py

# 7. (OBO only) Sync the AgentCore redirect URI back to the Databricks OAuth app
python scripts/sync_oauth_redirect.py

# 8. Smoke test
python src/bedrock_agent_test.py "Top 5 customers by revenue last quarter?"
```

## Common Patterns

### Pattern 1: OBO production deployment

End-user identity propagates from the Bedrock agent into Databricks via AgentCore Identity OAuth U2M. UC enforces row/column-level security per user; audit logs attribute SQL to the human.

Required:
- Databricks workspace OAuth app (custom integration) with redirect URI matching AgentCore Identity's
- AgentCore Identity OAuth credential provider configured with `grant_type=authorization_code` and scope `all-apis offline_access`
- The OAuth-redirect two-pass setup (placeholder URI first, real URI after AgentCore provisions the credential provider) — `scripts/sync_oauth_redirect.py` automates this

### Pattern 2: M2M booth demo

Every Genie call uses a Databricks service principal. Acceptable for single-tenant testing, **never claim user-level governance** in this mode.

Required:
- Databricks SP with workspace + UC read on the Genie space's underlying tables
- AgentCore Identity OAuth credential provider configured with `grant_type=client_credentials` and scope `all-apis`

### Pattern 3: FE Sandbox deployment

When the AWS account is FE Sandbox or otherwise restricted, the SSO caller cannot directly create IAM roles or Bedrock-AgentCore resources. Pattern:

1. **One-time:** an account admin creates an IAM role (e.g. `cfn-bedrock-agentcore-deployer`) with the privileges CloudFormation needs (`iam:*Role*`, `bedrock-agentcore:*`, `bedrock:*Agent*`, `secretsmanager:*`, `s3:*`). The exact policy is in [2-deployment-tf-vs-cfn.md](2-deployment-tf-vs-cfn.md).
2. **Each deploy:** `aws cloudformation deploy --role-arn $CFN_DEPLOYER_ROLE_ARN ...` so CFN executes as the pre-blessed role.

The caller only needs `cloudformation:*` and `sts:AssumeRole` on the deployer role — both usually allowed on FE Sandbox.

### Pattern 4: Multi-space discovery (roadmap)

For agents that need to choose between multiple Genie spaces, register a `list_genie_spaces` tool alongside `query_genie`. Not in v0.1; documented in the reference repo's roadmap.

## Reference Files

- [1-architecture-and-auth.md](1-architecture-and-auth.md) — auth modes, OAuth credential provider configuration, identity flow, governance validation
- [2-deployment-tf-vs-cfn.md](2-deployment-tf-vs-cfn.md) — both IaC paths, the FE Sandbox exec-role pattern, the IAM policy needed
- [3-quickstart-and-scripts.md](3-quickstart-and-scripts.md) — end-to-end deployment recipe, helper scripts, expected outputs

## Common Issues

| Issue | Solution |
|-------|----------|
| **`terraform init` errors on `awscc_bedrockagentcore_*` attribute** | AgentCore CFN registry schema renamed a property post-preview; check the current schema and update the Terraform/CFN. The IaC was authored against the 2026-05 registry. |
| **`aws cloudformation deploy` errors `User is not authorized to perform iam:CreateRole`** | You're on a restricted account — use the `--role-arn $CFN_DEPLOYER_ROLE_ARN` path, not direct deploy. See [2-deployment-tf-vs-cfn.md](2-deployment-tf-vs-cfn.md). |
| **`401` from Genie endpoint** | M2M: SP lacks workspace/UC privileges or token URL is wrong. OBO: the bearer token isn't being forwarded — confirm AgentCore Identity is exchanging it correctly. |
| **`403` on UC tables (OBO)** | End-user identity isn't propagating. Most often the Databricks OAuth app's redirect URI doesn't match AgentCore Identity's — re-run `scripts/sync_oauth_redirect.py`. |
| **`query_genie` not visible to agent** | Action group isn't attached. Re-run `scripts/associate_gateway.py`. If the SDK surface isn't yet available in your account/region, the script falls back to printing exact console steps. |
| **README claims OBO governance but agent answers don't reflect user permissions** | Check `AUTH_MODE` in `.env` — the proxy and the gateway target both honor it, and the README's claim only holds when both are set to `obo`. |
| **Genie space not created via `scripts/create_demo_genie_space.py`** | The Genie Spaces API is recent and may not be enabled on every workspace. The script falls back to printing the JSON payload for manual creation in the Genie UI. |

## See also

- [databricks-genie](../databricks-genie/SKILL.md) — Genie Space management (create, query, export, import). Use that skill for the Databricks-side Genie work; this skill covers the AWS-side integration.
- [databricks-agent-bricks](../databricks-agent-bricks/SKILL.md) — Knowledge Assistants, Genie Spaces, and Supervisor Agents on Databricks. Use for Databricks-native multi-agent orchestration.
- Reference architecture: [databricks-field-eng/databricks-aws-integrations/genie_with_bedrock_agentcore](https://github.com/databricks-field-eng/databricks-aws-integrations/tree/main/genie_with_bedrock_agentcore) — full deployable demo with Terraform, CloudFormation, and helper scripts.
