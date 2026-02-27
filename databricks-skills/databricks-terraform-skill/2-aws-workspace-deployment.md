# AWS Workspace Deployment

## Overview

Two deployment patterns for AWS:
1. **Basic (non-PrivateLink)** — public endpoints, suitable for dev/test
2. **PrivateLink (production)** — private networking, no public internet exposure

Reference examples: [aws-workspace-basic](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/aws-workspace-basic) | [aws-databricks-modular-privatelink](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/aws-databricks-modular-privatelink)

---

## Pattern 1: Basic AWS Workspace (Non-PrivateLink)

### Prerequisites

- AWS account with admin permissions
- Databricks account with account admin Service Principal
- Terraform ≥ 1.3.0

### File Structure

```
aws-workspace-basic/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
└── terraform.tfvars
```

### providers.tf

```hcl
terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.38.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Account-level provider for workspace creation
provider "databricks" {
  alias         = "mws"
  host          = "https://accounts.cloud.databricks.com"
  account_id    = var.databricks_account_id
  client_id     = var.client_id
  client_secret = var.client_secret
}
```

### main.tf — VPC & Networking

```hcl
# Availability zones data source (required by subnet resources below)
data "aws_availability_zones" "available" {
  state = "available"
}

# VPC
resource "aws_vpc" "databricks" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = merge(var.tags, { Name = "${var.prefix}-vpc" })
}

# Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.databricks.id
  tags   = merge(var.tags, { Name = "${var.prefix}-igw" })
}

# Public subnets for NAT Gateway
resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.databricks.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = merge(var.tags, { Name = "${var.prefix}-public-${count.index}" })
}

# Private subnets for Databricks nodes
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.databricks.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 4)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = merge(var.tags, { Name = "${var.prefix}-private-${count.index}" })
}

# NAT Gateway for outbound internet from private subnets
resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "ngw" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = merge(var.tags, { Name = "${var.prefix}-ngw" })
  depends_on    = [aws_internet_gateway.igw]
}

# Route tables
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.databricks.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = merge(var.tags, { Name = "${var.prefix}-rt-public" })
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.databricks.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.ngw.id
  }
  tags = merge(var.tags, { Name = "${var.prefix}-rt-private" })
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# Security Group for Databricks clusters
resource "aws_security_group" "databricks" {
  name        = "${var.prefix}-databricks-sg"
  description = "Security group for Databricks cluster nodes"
  vpc_id      = aws_vpc.databricks.id

  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self      = true
  }
  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "udp"
    self      = true
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(var.tags, { Name = "${var.prefix}-databricks-sg" })
}
```

### main.tf — S3 Root Bucket

```hcl
resource "aws_s3_bucket" "root" {
  bucket        = "${var.prefix}-databricks-root"
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "root" {
  bucket = aws_s3_bucket.root.id
  versioning_configuration { status = "Disabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "root" {
  bucket = aws_s3_bucket.root.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "root" {
  bucket                  = aws_s3_bucket.root.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "root_bucket_policy" {
  statement {
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [
      aws_s3_bucket.root.arn,
      "${aws_s3_bucket.root.arn}/*"
    ]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::414351767826:root"]  # Databricks AWS account ID
    }
  }
}

resource "aws_s3_bucket_policy" "root" {
  bucket = aws_s3_bucket.root.id
  policy = data.aws_iam_policy_document.root_bucket_policy.json
}
```

### main.tf — Cross-Account IAM Role

```hcl
data "aws_iam_policy_document" "cross_account_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::414351767826:root"]  # Databricks production AWS account
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.databricks_account_id]
    }
  }
}

resource "aws_iam_role" "cross_account" {
  name               = "${var.prefix}-databricks-crossaccount"
  assume_role_policy = data.aws_iam_policy_document.cross_account_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "cross_account_policy" {
  statement {
    effect  = "Allow"
    actions = [
      "ec2:AllocateAddress", "ec2:AssignPrivateIpAddresses", "ec2:AssociateDhcpOptions",
      "ec2:AssociateRouteTable", "ec2:AttachInternetGateway", "ec2:AttachNetworkInterface",
      "ec2:AuthorizeSecurityGroupEgress", "ec2:AuthorizeSecurityGroupIngress",
      "ec2:CancelSpotInstanceRequests", "ec2:CreateDhcpOptions", "ec2:CreateInternetGateway",
      "ec2:CreateKeyPair", "ec2:CreateNetworkInterface", "ec2:CreatePlacementGroup",
      "ec2:CreateRoute", "ec2:CreateRouteTable", "ec2:CreateSecurityGroup",
      "ec2:CreateSubnet", "ec2:CreateTags", "ec2:CreateVolume", "ec2:CreateVpc",
      "ec2:CreateVpcEndpoint", "ec2:DeleteDhcpOptions", "ec2:DeleteInternetGateway",
      "ec2:DeleteKeyPair", "ec2:DeleteNetworkInterface", "ec2:DeletePlacementGroup",
      "ec2:DeleteRoute", "ec2:DeleteRouteTable", "ec2:DeleteSecurityGroup",
      "ec2:DeleteSubnet", "ec2:DeleteTags", "ec2:DeleteVolume", "ec2:DeleteVpc",
      "ec2:DeleteVpcEndpoints", "ec2:DescribeAvailabilityZones", "ec2:DescribeIamInstanceProfileAssociations",
      "ec2:DescribeInstanceStatus", "ec2:DescribeInstances", "ec2:DescribeInternetGateways",
      "ec2:DescribeNetworkAcls", "ec2:DescribeNetworkInterfaces", "ec2:DescribePlacementGroups",
      "ec2:DescribePrefixLists", "ec2:DescribeReservedInstancesOfferings",
      "ec2:DescribeRouteTables", "ec2:DescribeSecurityGroups", "ec2:DescribeSpotInstanceRequests",
      "ec2:DescribeSpotPriceHistory", "ec2:DescribeSubnets", "ec2:DescribeVolumes",
      "ec2:DescribeVpcAttribute", "ec2:DescribeVpcs", "ec2:DetachInternetGateway",
      "ec2:DisassociateRouteTable", "ec2:GetSpotPlacementScores", "ec2:ModifyVpcAttribute",
      "ec2:ReleaseAddress", "ec2:RequestSpotInstances", "ec2:RevokeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress", "ec2:RunInstances", "ec2:TerminateInstances",
      "iam:CreateServiceLinkedRole", "iam:GetRole", "iam:ListInstanceProfiles", "iam:PassRole"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "cross_account" {
  name   = "${var.prefix}-databricks-crossaccount-policy"
  role   = aws_iam_role.cross_account.id
  policy = data.aws_iam_policy_document.cross_account_policy.json
}
```

### main.tf — Databricks Workspace (MWS)

```hcl
resource "databricks_mws_credentials" "this" {
  provider         = databricks.mws
  account_id       = var.databricks_account_id
  credentials_name = "${var.prefix}-credentials"
  role_arn         = aws_iam_role.cross_account.arn
}

resource "databricks_mws_storage_configurations" "this" {
  provider                   = databricks.mws
  account_id                 = var.databricks_account_id
  storage_configuration_name = "${var.prefix}-storage"
  bucket_name                = aws_s3_bucket.root.bucket
}

resource "databricks_mws_networks" "this" {
  provider           = databricks.mws
  account_id         = var.databricks_account_id
  network_name       = "${var.prefix}-network"
  security_group_ids = [aws_security_group.databricks.id]
  subnet_ids         = aws_subnet.private[*].id
  vpc_id             = aws_vpc.databricks.id
}

resource "databricks_mws_workspaces" "this" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = var.workspace_name
  aws_region     = var.region

  credentials_id           = databricks_mws_credentials.this.credentials_id
  storage_configuration_id = databricks_mws_storage_configurations.this.storage_configuration_id
  network_id               = databricks_mws_networks.this.network_id

  token {
    comment          = "Terraform-managed"
    lifetime_seconds = 86400  # 1 day; omit for non-expiring
  }
}
```

### variables.tf

```hcl
variable "databricks_account_id" { type = string }
variable "client_id"             { type = string }
variable "client_secret"         { type = string; sensitive = true }
variable "region"                { type = string; default = "us-east-1" }
variable "prefix"                { type = string; default = "demo" }
variable "workspace_name"        { type = string; default = "my-workspace" }
variable "vpc_cidr"              { type = string; default = "10.4.0.0/16" }
variable "tags"                  { type = map(string); default = {} }
```

### outputs.tf

```hcl
output "workspace_url" {
  value = databricks_mws_workspaces.this.workspace_url
}
output "workspace_id" {
  value = databricks_mws_workspaces.this.workspace_id
}
output "token" {
  value     = databricks_mws_workspaces.this.token[0].token_value
  sensitive = true
}
```

---

## Pattern 2: AWS Modular PrivateLink Deployment

For production workloads requiring private networking with no public internet exposure.

Reference: [aws-databricks-modular-privatelink](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/aws-databricks-modular-privatelink)

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Customer AWS Account                                    │
│                                                          │
│  ┌──────────────────────────────────────┐               │
│  │  VPC (10.109.0.0/17)                │               │
│  │                                      │               │
│  │  PrivateLink Subnets                │               │
│  │  ┌────────────────────────────────┐ │               │
│  │  │  VPC Endpoint (Workspace)      │ │               │
│  │  │  VPC Endpoint (Relay/SCC)      │ │               │
│  │  └────────────────────────────────┘ │               │
│  │                                      │               │
│  │  Workspace Subnet Pairs (1..N)      │               │
│  │  ┌────────────────┐  ┌────────────┐ │               │
│  │  │  Workspace 1   │  │ Workspace 2│ │               │
│  │  │  Subnet A + B  │  │ Subnet A+B │ │               │
│  │  └────────────────┘  └────────────┘ │               │
│  └──────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
                         │ PrivateLink
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Databricks Control Plane                                │
│  (aws-workspace-vpce-service, relay-vpce-service)       │
└─────────────────────────────────────────────────────────┘
```

### PrivateLink VPC Endpoints

> **Note**: The snippets below reference `aws_subnet.privatelink` and `aws_security_group.databricks_vpce` which must be declared alongside your existing VPC resources. Add dedicated PrivateLink subnets (at least one per AZ) and a security group that allows HTTPS (443) inbound from the workspace subnets.

```hcl
# Dedicated subnets for VPC endpoints (separate from workspace node subnets)
resource "aws_subnet" "privatelink" {
  count             = 2
  vpc_id            = aws_vpc.databricks.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 8)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = merge(var.tags, { Name = "${var.prefix}-pl-${count.index}" })
}

# Security group for VPC endpoints — allows HTTPS from workspace nodes
resource "aws_security_group" "databricks_vpce" {
  name        = "${var.prefix}-vpce-sg"
  description = "Security group for Databricks VPC endpoints"
  vpc_id      = aws_vpc.databricks.id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.databricks.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(var.tags, { Name = "${var.prefix}-vpce-sg" })
}

# Look up Databricks PrivateLink service endpoint for your region
# See: https://docs.databricks.com/administration-guide/cloud-configurations/aws/privatelink.html

resource "aws_vpc_endpoint" "workspace" {
  vpc_id              = aws_vpc.databricks.id
  service_name        = var.workspace_vpce_service  # e.g. "com.amazonaws.vpce.us-east-1.vpce-svc-xxxxxxxx"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.privatelink[*].id
  security_group_ids  = [aws_security_group.databricks_vpce.id]
  private_dns_enabled = true
  tags                = merge(var.tags, { Name = "${var.prefix}-workspace-vpce" })
}

resource "aws_vpc_endpoint" "relay" {
  vpc_id              = aws_vpc.databricks.id
  service_name        = var.relay_vpce_service  # Secure Cluster Connectivity relay
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.privatelink[*].id
  security_group_ids  = [aws_security_group.databricks_vpce.id]
  private_dns_enabled = true
  tags                = merge(var.tags, { Name = "${var.prefix}-relay-vpce" })
}
```

### Databricks Private Access Settings

```hcl
resource "databricks_mws_private_access_settings" "this" {
  provider                     = databricks.mws
  account_id                   = var.databricks_account_id
  private_access_settings_name = "${var.prefix}-pas"
  region                       = var.region
  public_access_enabled        = false  # Disable public access entirely
  private_access_level         = "ACCOUNT"  # or "ENDPOINT"
}

resource "databricks_mws_vpc_endpoint" "workspace" {
  provider            = databricks.mws
  account_id          = var.databricks_account_id
  aws_vpc_endpoint_id = aws_vpc_endpoint.workspace.id
  vpc_endpoint_name   = "${var.prefix}-workspace-vpce"
  region              = var.region
}

resource "databricks_mws_vpc_endpoint" "relay" {
  provider            = databricks.mws
  account_id          = var.databricks_account_id
  aws_vpc_endpoint_id = aws_vpc_endpoint.relay.id
  vpc_endpoint_name   = "${var.prefix}-relay-vpce"
  region              = var.region
}
```

### Workspace with PrivateLink

```hcl
resource "databricks_mws_workspaces" "privatelink" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = var.workspace_name
  aws_region     = var.region

  credentials_id           = databricks_mws_credentials.this.credentials_id
  storage_configuration_id = databricks_mws_storage_configurations.this.storage_configuration_id
  network_id               = databricks_mws_networks.this.network_id

  private_access_settings_id = databricks_mws_private_access_settings.this.private_access_settings_id

  # Register the VPC endpoints with the workspace
  custom_tags = var.tags
}
```

### Customer-Managed Keys (Optional — Enhanced Security)

```hcl
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "kms" {
  # Root account full access to manage the key
  statement {
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  # Databricks account must be able to use the key for managed services encryption
  statement {
    effect    = "Allow"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::414351767826:root"]  # Databricks production AWS account
    }
  }
}

resource "aws_kms_key" "databricks" {
  description             = "Databricks workspace encryption key"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms.json
  tags                    = var.tags
}

resource "aws_kms_alias" "databricks" {
  name          = "alias/${var.prefix}-databricks-key"
  target_key_id = aws_kms_key.databricks.key_id
}

resource "databricks_mws_customer_managed_keys" "workspace" {
  provider   = databricks.mws
  account_id = var.databricks_account_id

  aws_key_info {
    key_arn    = aws_kms_key.databricks.arn
    key_alias  = aws_kms_alias.databricks.name
    key_region = var.region
  }

  use_cases = ["MANAGED_SERVICES"]  # or ["STORAGE"], or ["MANAGED_SERVICES", "STORAGE"]
}
```

---

## IP Access Lists

```hcl
resource "databricks_workspace_conf" "this" {
  provider = databricks.workspace
  custom_config = {
    "enableIpAccessLists" = "true"  # custom_config is map(string) — must quote boolean values
  }
}

resource "databricks_ip_access_list" "allow" {
  provider  = databricks.workspace
  label     = "allow-corporate"
  list_type = "ALLOW"
  ip_addresses = [
    "203.0.113.0/24",   # Corporate VPN range
    "198.51.100.10/32", # Specific IP
  ]
  depends_on = [databricks_workspace_conf.this]
}

resource "databricks_ip_access_list" "block" {
  provider  = databricks.workspace
  label     = "block-known-bad"
  list_type = "BLOCK"
  ip_addresses = ["192.0.2.0/24"]
  depends_on   = [databricks_workspace_conf.this]
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **`InvalidVpcEndpointService`** | Verify the VPCE service name for your region from Databricks docs |
| **Workspace creation times out** | AWS credential propagation takes ~60 seconds; add `time_sleep` resource |
| **`InvalidCrossAccountRole`** | Verify trust policy includes correct Databricks AWS account ID (414351767826) |
| **NAT Gateway not routing** | Check route table associations — private subnets must point to NAT GW |
| **Security group self-reference** | Databricks requires nodes to communicate freely within the SG (self-rule) |
| **S3 bucket access denied** | Verify bucket policy includes Databricks AWS account as principal |
