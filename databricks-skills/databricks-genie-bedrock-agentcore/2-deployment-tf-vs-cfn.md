# Deployment: Terraform vs CloudFormation

Two IaC paths, picked based on which AWS account you're deploying into.

## Decision matrix

| Account type | Path | Why |
| --- | --- | --- |
| External customer AWS account | Terraform | Caller has direct IAM/Bedrock-AgentCore privileges; `awscc` provider gives Terraform-native AgentCore primitives |
| FE Sandbox AWS account | CloudFormation | Caller's SSO role lacks `iam:CreateRole` and `bedrock-agentcore:*` — must deploy via a pre-blessed exec role |
| Other restricted AWS account | CloudFormation | Same reason as FE Sandbox; the exec-role pattern generalizes |
| Customer is mandated CloudFormation-only | CloudFormation | Some enterprises prohibit Terraform — meet them where they are |

## What both paths provision

| Resource | Purpose |
| --- | --- |
| S3 bucket | Holds the Genie MCP OpenAPI schema |
| Secrets Manager (M2M) | Databricks SP credentials |
| Secrets Manager (OBO) | Databricks workspace OAuth app credentials |
| IAM role for Gateway target | `secretsmanager:GetSecretValue`, `s3:GetObject` |
| AgentCore OAuth credential provider | Mints Databricks tokens (M2M or OBO depending on `AUTH_MODE`) |
| AgentCore Gateway | Hosts the Genie MCP target |
| IAM role for Bedrock agent | `bedrock:InvokeModel`, `bedrock-agentcore:InvokeGateway` |
| Bedrock agent + alias | The conversational runtime |

## Terraform path (external AWS)

Uses the `awscc` provider for AgentCore primitives because the AWS provider doesn't ship native `aws_bedrockagentcore_*` resources at the time of writing.

```hcl
terraform {
  required_providers {
    aws  = { source = "hashicorp/aws",  version = "~> 5.60" }
    awscc = { source = "hashicorp/awscc", version = "~> 1.0" }
  }
}
```

Deploy:

```bash
cd terraform
terraform init
terraform apply \
  -var "databricks_host=$DATABRICKS_HOST" \
  -var "databricks_client_id=$DATABRICKS_CLIENT_ID" \
  -var "databricks_client_secret=$DATABRICKS_CLIENT_SECRET" \
  -var "databricks_oauth_client_id=$DATABRICKS_OAUTH_CLIENT_ID" \
  -var "databricks_oauth_client_secret=$DATABRICKS_OAUTH_CLIENT_SECRET" \
  -var "genie_space_id=$GENIE_SPACE_ID" \
  -var "auth_mode=$AUTH_MODE"
```

Outputs to capture into `.env`: `gateway_id`, `oauth_provider_arn`, `schema_s3_bucket`, `bedrock_agent_id`, `bedrock_agent_alias_id`.

## CloudFormation path (FE Sandbox / restricted accounts)

### The pre-blessed exec-role pattern

The problem: on FE Sandbox the SSO role typically has

- ✅ `cloudformation:*`, `s3:*`
- ❌ `iam:CreateRole`, `iam:PutRolePolicy`
- ❌ `bedrock-agentcore:CreateGateway`, `CreateOauthCredentialProvider`
- ❌ `bedrock:CreateAgent`

That blocks Terraform-as-you AND `aws cloudformation deploy --capabilities CAPABILITY_NAMED_IAM` from the SSO role. The workaround (Ioannis Papadopoulos's pattern, originated for the Agent Bricks ↔ Bedrock/AgentCore demo):

1. **One-time, by an account admin:** create an IAM role `cfn-bedrock-agentcore-deployer` with all the privileges CFN needs. Trust policy lets your SSO role call `sts:AssumeRole`.
2. **Each deploy:** `aws cloudformation deploy --role-arn $CFN_DEPLOYER_ROLE_ARN ...` — CFN executes as the pre-blessed role.
3. **You only need:** `cloudformation:*` and `sts:AssumeRole` on the deployer role. Both usually allowed on FE Sandbox.

### IAM policy for the deployer role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3SchemaBucket",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket", "s3:DeleteBucket", "s3:GetBucketLocation",
        "s3:GetBucketPolicy", "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketVersioning", "s3:ListBucket", "s3:PutBucketPolicy",
        "s3:PutBucketPublicAccessBlock", "s3:PutBucketVersioning",
        "s3:DeleteObject", "s3:GetObject", "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::dbx-genie-mcp-*",
        "arn:aws:s3:::dbx-genie-mcp-*/*"
      ]
    },
    {
      "Sid": "SecretsManager",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret", "secretsmanager:DeleteSecret",
        "secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue", "secretsmanager:TagResource",
        "secretsmanager:UntagResource", "secretsmanager:UpdateSecret"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:dbx-genie-mcp-*"
    },
    {
      "Sid": "IAM",
      "Effect": "Allow",
      "Action": [
        "iam:AttachRolePolicy", "iam:CreateRole", "iam:DeleteRole",
        "iam:DeleteRolePolicy", "iam:DetachRolePolicy", "iam:GetRole",
        "iam:GetRolePolicy", "iam:ListAttachedRolePolicies",
        "iam:ListRolePolicies", "iam:PassRole", "iam:PutRolePolicy",
        "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": ["arn:aws:iam::*:role/dbx-genie-mcp-*"]
    },
    {
      "Sid": "BedrockAgentCore",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateGateway", "bedrock-agentcore:DeleteGateway",
        "bedrock-agentcore:GetGateway", "bedrock-agentcore:ListGateways",
        "bedrock-agentcore:UpdateGateway",
        "bedrock-agentcore:CreateGatewayTarget",
        "bedrock-agentcore:DeleteGatewayTarget",
        "bedrock-agentcore:GetGatewayTarget",
        "bedrock-agentcore:ListGatewayTargets",
        "bedrock-agentcore:UpdateGatewayTarget",
        "bedrock-agentcore:CreateOauthCredentialProvider",
        "bedrock-agentcore:DeleteOauthCredentialProvider",
        "bedrock-agentcore:GetOauthCredentialProvider",
        "bedrock-agentcore:ListOauthCredentialProviders",
        "bedrock-agentcore:UpdateOauthCredentialProvider"
      ],
      "Resource": "*"
    },
    {
      "Sid": "BedrockAgent",
      "Effect": "Allow",
      "Action": [
        "bedrock:CreateAgent", "bedrock:CreateAgentAlias",
        "bedrock:DeleteAgent", "bedrock:DeleteAgentAlias",
        "bedrock:GetAgent", "bedrock:GetAgentAlias",
        "bedrock:ListAgents", "bedrock:ListAgentAliases",
        "bedrock:PrepareAgent", "bedrock:UpdateAgent",
        "bedrock:UpdateAgentAlias",
        "bedrock:AssociateAgentKnowledgeBase",
        "bedrock:DisassociateAgentKnowledgeBase",
        "bedrock:TagResource", "bedrock:UntagResource"
      ],
      "Resource": "*"
    }
  ]
}
```

The policy is resource-scoped to `dbx-genie-mcp-*` so the deployer role can't be reused against unrelated infra. A copy-paste Slack template for the admin ask is at `cloudformation/REQUEST_DEPLOYER_ROLE.md` in the reference repo.

### Deploy

```bash
export CFN_DEPLOYER_ROLE_ARN=arn:aws:iam::<account>:role/cfn-bedrock-agentcore-deployer
cd cloudformation
./deploy.sh
```

`deploy.sh` reads `.env`, then runs:

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --template-file stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --role-arn "$CFN_DEPLOYER_ROLE_ARN" \
  --parameter-overrides ...
```

Outputs are surfaced via `aws cloudformation describe-stacks --query 'Stacks[0].Outputs' --output table` — capture into `.env`.

## Picking between the two

- If you might run this on FE Sandbox at any point, **maintain the CloudFormation path** as the source of truth and treat Terraform as the convenience layer. Sandbox is the harder constraint.
- If you're only deploying to external customer AWS accounts, **stick with Terraform** — it's the more expressive of the two, and customers running Terraform shops will prefer it.
- The reference repo (`databricks-aws-integrations/genie_with_bedrock_agentcore`) keeps both paths to cover both audiences. Drift between them is the primary maintenance cost — when changing one, change the other.

## Schema-name caveat

`AWS::BedrockAgentCore::*` resource names and properties evolved through preview. The IaC referenced here was authored against the 2026-05 CFN registry. If `terraform init` errors on `awscc_bedrockagentcore_*`, or `aws cloudformation validate-template` errors on a `BedrockAgentCore::*` property, check the current registry schema and patch.
