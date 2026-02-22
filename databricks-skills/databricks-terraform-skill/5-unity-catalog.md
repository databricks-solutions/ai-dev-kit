# Unity Catalog Deployment

## Overview

Unity Catalog (UC) is Databricks' unified governance layer. Deployment involves:
1. **Metastore** — top-level container, one per region per account
2. **Storage credentials** — cloud IAM credentials for storage access
3. **External locations** — storage path references
4. **Catalogs** → **Schemas** → **Tables/Volumes** — data hierarchy
5. **Grants** — fine-grained access control

Reference examples: [aws-databricks-uc](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/aws-databricks-uc) | [adb-uc](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/adb-uc) | [aws-workspace-uc-simple](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/aws-workspace-uc-simple)

---

## Stage 1: Bootstrap — Users & Service Principal

UC deployment requires an **account admin** Service Principal (not account owner). The bootstrap stage creates this identity.

### AWS Bootstrap

```hcl
# provider: databricks.mws (account-level)

resource "databricks_service_principal" "uc_admin" {
  provider     = databricks.mws
  display_name = "UC Admin Service Principal"
  # application_id is set externally; use aws_iam or Azure AD to create SP
}

resource "databricks_service_principal_role" "account_admin" {
  provider             = databricks.mws
  service_principal_id = databricks_service_principal.uc_admin.id
  role                 = "account_admin"
}

# Create account-level users
resource "databricks_user" "users" {
  provider  = databricks.mws
  for_each  = toset(var.databricks_users)
  user_name = each.key
  force     = true
}

resource "databricks_user" "admins" {
  provider  = databricks.mws
  for_each  = toset(var.databricks_account_admins)
  user_name = each.key
  force     = true
}

# Admin group (will be metastore owner)
resource "databricks_group" "admin_group" {
  provider     = databricks.mws
  display_name = var.unity_admin_group
}

resource "databricks_group_member" "admin_members" {
  provider  = databricks.mws
  for_each  = toset(var.databricks_account_admins)
  group_id  = databricks_group.admin_group.id
  member_id = databricks_user.admins[each.value].id
}

resource "databricks_user_role" "account_admins" {
  provider = databricks.mws
  for_each = toset(var.databricks_account_admins)
  user_id  = databricks_user.admins[each.value].id
  role     = "account_admin"
}
```

---

## Stage 2: Metastore Setup

One metastore per region per Databricks account. Choose the section matching your cloud.

### AWS Metastore Setup

#### S3 Bucket & IAM Role for UC

```hcl
# S3 bucket for UC metastore root
resource "aws_s3_bucket" "metastore" {
  bucket        = "${var.prefix}-uc-metastore"
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "metastore" {
  bucket = aws_s3_bucket.metastore.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "metastore" {
  bucket                  = aws_s3_bucket.metastore.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# IAM policy for Unity Catalog metastore access
data "aws_iam_policy_document" "unity_metastore" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.metastore.arn, "${aws_s3_bucket.metastore.arn}/*"]
  }
}

# IAM policy for external data access
data "aws_iam_policy_document" "external_data_access" {
  statement {
    actions = [
      "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:PutObjectAcl",
      "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"
    ]
    resources = [
      aws_s3_bucket.external.arn,
      "${aws_s3_bucket.external.arn}/*"
    ]
  }
  # Allow sts:AssumeRole for credential passthrough
  statement {
    actions   = ["sts:AssumeRole"]
    resources = ["arn:aws:iam::${var.aws_account_id}:role/${var.prefix}-uc-data-access"]
  }
}

# Trust policy: Databricks can assume this role
data "aws_iam_policy_document" "uc_role_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::414351767826:role/unity-catalog-prod-UCMasterRole-14S5ZJVKOTYTL"]
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.databricks_account_id]
    }
  }
  # Self-assume for credential passthrough
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.aws_account_id}:root"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = ["arn:aws:iam::${var.aws_account_id}:role/${var.prefix}-uc-data-access"]
    }
  }
}

resource "aws_iam_role" "uc_metastore" {
  name               = "${var.prefix}-uc-metastore-role"
  assume_role_policy = data.aws_iam_policy_document.uc_role_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "uc_metastore" {
  name   = "${var.prefix}-uc-metastore-policy"
  role   = aws_iam_role.uc_metastore.id
  policy = data.aws_iam_policy_document.unity_metastore.json
}

resource "aws_iam_role" "uc_data_access" {
  name               = "${var.prefix}-uc-data-access"
  assume_role_policy = data.aws_iam_policy_document.uc_role_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "uc_data_access" {
  name   = "${var.prefix}-uc-data-access-policy"
  role   = aws_iam_role.uc_data_access.id
  policy = data.aws_iam_policy_document.external_data_access.json
}
```

### Metastore & Assignment

```hcl
# Create metastore (one per region per account)
resource "databricks_metastore" "this" {
  provider      = databricks.mws
  name          = "${var.prefix}-metastore"
  region        = var.region
  storage_root  = "s3://${aws_s3_bucket.metastore.bucket}/metastore"
  owner         = var.unity_admin_group
  force_destroy = true
}

# Assign metastore to workspace(s)
resource "databricks_metastore_assignment" "this" {
  provider     = databricks.mws
  for_each     = toset(var.databricks_workspace_ids)
  metastore_id = databricks_metastore.this.id
  workspace_id = each.key
}

# Configure data access (storage credential for metastore root)
resource "databricks_metastore_data_access" "this" {
  provider     = databricks.mws
  metastore_id = databricks_metastore.this.id
  name         = "${var.prefix}-metastore-access"

  aws_iam_role {
    role_arn = aws_iam_role.uc_metastore.arn
  }

  is_default = true
  depends_on = [databricks_metastore_assignment.this]
}
```

---

### Azure Metastore Setup

#### ADLS Gen2 Storage Account & Access Connector

```hcl
# ADLS Gen2 storage account for UC metastore root
resource "azurerm_storage_account" "uc_metastore" {
  name                     = "${replace(var.prefix, "-", "")}ucmetastore"  # 3-24 chars, alphanumeric only
  resource_group_name      = azurerm_resource_group.databricks.name
  location                 = azurerm_resource_group.databricks.location
  account_tier             = "Standard"
  account_replication_type = "GRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true  # ADLS Gen2 (hierarchical namespace) required
  tags                     = var.tags
}

# Container for metastore root
resource "azurerm_storage_container" "metastore" {
  name                  = "metastore"
  storage_account_name  = azurerm_storage_account.uc_metastore.name
  container_access_type = "private"
}

# Access Connector (Azure managed identity for Databricks <-> ADLS)
resource "azurerm_databricks_access_connector" "uc_metastore" {
  name                = "${var.prefix}-uc-metastore-connector"
  resource_group_name = azurerm_resource_group.databricks.name
  location            = azurerm_resource_group.databricks.location
  tags                = var.tags

  identity {
    type = "SystemAssigned"
  }
}

# Grant the access connector identity permission on the metastore storage account
resource "azurerm_role_assignment" "uc_metastore_adls" {
  scope                = azurerm_storage_account.uc_metastore.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.uc_metastore.identity[0].principal_id
}
```

#### Metastore & Assignment (Azure)

```hcl
# Create metastore with ADLS Gen2 storage root
# Azure account-level host: https://accounts.azuredatabricks.net
resource "databricks_metastore" "azure" {
  provider = databricks.mws
  name     = "${var.prefix}-metastore"
  # Azure: use azuredatabricks.net account host, not accounts.cloud.databricks.com
  storage_root  = "abfss://${azurerm_storage_container.metastore.name}@${azurerm_storage_account.uc_metastore.name}.dfs.core.windows.net/"
  owner         = var.unity_admin_group
  region        = var.location  # Azure region string, e.g. "eastus2"
  force_destroy = true
}

resource "databricks_metastore_assignment" "azure" {
  provider     = databricks.mws
  for_each     = toset(var.databricks_workspace_ids)
  metastore_id = databricks_metastore.azure.id
  workspace_id = each.key
}

# Default data access configuration using the access connector managed identity
resource "databricks_metastore_data_access" "azure" {
  provider     = databricks.mws
  metastore_id = databricks_metastore.azure.id
  name         = "${var.prefix}-metastore-access"

  azure_managed_identity {
    access_connector_id = azurerm_databricks_access_connector.uc_metastore.id
  }

  is_default = true
  depends_on = [databricks_metastore_assignment.azure]
}
```

> **Azure account-level provider host**: Use `"https://accounts.azuredatabricks.net"` (not `.cloud.databricks.com`) for the `databricks.mws` provider alias when deploying Azure resources.

---

### GCP Metastore Setup

#### GCS Bucket & Service Account

```hcl
# GCS bucket for UC metastore root
resource "google_storage_bucket" "uc_metastore" {
  name                        = "${var.prefix}-uc-metastore"
  location                    = upper(var.google_region)  # GCS uses uppercase region, e.g. "US-CENTRAL1"
  force_destroy               = true
  uniform_bucket_level_access = true

  versioning { enabled = true }  # Recommended for metastore storage
}

# Service account dedicated to UC data access
resource "google_service_account" "uc_access" {
  account_id   = "${var.prefix}-uc-access"
  display_name = "Databricks Unity Catalog Access SA"
  project      = var.google_project
}

# Grant UC access SA admin rights on the metastore bucket
resource "google_storage_bucket_iam_member" "uc_metastore_admin" {
  bucket = google_storage_bucket.uc_metastore.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.uc_access.email}"
}

# GCS bucket for external data access (separate from metastore root)
resource "google_storage_bucket" "uc_external" {
  name                        = "${var.prefix}-uc-external-data"
  location                    = upper(var.google_region)
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "uc_external_admin" {
  bucket = google_storage_bucket.uc_external.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.uc_access.email}"
}
```

#### Metastore & Assignment (GCP)

```hcl
# GCP account-level host: https://accounts.gcp.databricks.com
resource "databricks_metastore" "gcp" {
  provider      = databricks.mws
  name          = "${var.prefix}-metastore"
  storage_root  = "gs://${google_storage_bucket.uc_metastore.name}/metastore"
  owner         = var.unity_admin_group
  region        = var.google_region  # GCP region string, e.g. "us-central1"
  force_destroy = true
}

resource "databricks_metastore_assignment" "gcp" {
  provider     = databricks.mws
  for_each     = toset(var.databricks_workspace_ids)
  metastore_id = databricks_metastore.gcp.id
  workspace_id = each.key
}

# Default data access — Databricks creates a managed GCP service account automatically
resource "databricks_metastore_data_access" "gcp" {
  provider     = databricks.mws
  metastore_id = databricks_metastore.gcp.id
  name         = "${var.prefix}-metastore-access"

  # Option A: Let Databricks auto-create a managed GCP service account
  databricks_gcp_service_account {}

  is_default = true
  depends_on = [databricks_metastore_assignment.gcp]
}

# After apply, grant the auto-created Databricks SA access to the metastore bucket.
# The SA email is available via: databricks_metastore_data_access.gcp.databricks_gcp_service_account[0].email
resource "google_storage_bucket_iam_member" "databricks_managed_sa" {
  bucket = google_storage_bucket.uc_metastore.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${databricks_metastore_data_access.gcp.databricks_gcp_service_account[0].email}"
}
```

> **GCP two-step apply**: `databricks_metastore_data_access` with `databricks_gcp_service_account {}` creates a Databricks-managed SA. Run `terraform apply` once to get the SA email, then the `google_storage_bucket_iam_member` can be applied in the same or subsequent run.

---

## Stage 3: Storage Credentials & External Locations

### AWS Storage Credential

```hcl
resource "databricks_storage_credential" "external" {
  provider = databricks.workspace
  name     = "${var.prefix}-s3-credential"

  aws_iam_role {
    role_arn = aws_iam_role.uc_data_access.arn
  }

  comment    = "Managed by Terraform"
  depends_on = [databricks_metastore_assignment.this]
}

resource "databricks_external_location" "data" {
  provider        = databricks.workspace
  name            = "${var.prefix}-data-location"
  url             = "s3://${aws_s3_bucket.external.bucket}/data"
  credential_name = databricks_storage_credential.external.name
  comment         = "External location for data"

  depends_on = [databricks_metastore_assignment.this]
}
```

### Azure Storage Credential (Managed Identity)

The access connector for the **external data** location is separate from the metastore connector created in Stage 2.

```hcl
# ADLS Gen2 storage account for external data (separate from metastore root)
resource "azurerm_storage_account" "uc_external" {
  name                     = "${replace(var.prefix, "-", "")}ucexternal"
  resource_group_name      = azurerm_resource_group.databricks.name
  location                 = azurerm_resource_group.databricks.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true  # ADLS Gen2 required
  tags                     = var.tags
}

resource "azurerm_storage_container" "external_data" {
  name                  = "data"
  storage_account_name  = azurerm_storage_account.uc_external.name
  container_access_type = "private"
}

# Access connector for external data storage credential
resource "azurerm_databricks_access_connector" "uc_external" {
  name                = "${var.prefix}-uc-external-connector"
  resource_group_name = azurerm_resource_group.databricks.name
  location            = azurerm_resource_group.databricks.location
  tags                = var.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "uc_external_adls" {
  scope                = azurerm_storage_account.uc_external.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.uc_external.identity[0].principal_id
}

resource "databricks_storage_credential" "azure" {
  provider = databricks.workspace
  name     = "${var.prefix}-azure-credential"

  azure_managed_identity {
    access_connector_id = azurerm_databricks_access_connector.uc_external.id
  }

  depends_on = [databricks_metastore_assignment.azure]
}

resource "databricks_external_location" "azure_data" {
  provider        = databricks.workspace
  name            = "${var.prefix}-azure-location"
  url             = "abfss://${azurerm_storage_container.external_data.name}@${azurerm_storage_account.uc_external.name}.dfs.core.windows.net/"
  credential_name = databricks_storage_credential.azure.name

  depends_on = [databricks_metastore_assignment.azure]
}
```

### GCP Storage Credential (Service Account)

```hcl
# Storage credential using the Databricks-managed GCP SA (auto-created in Stage 2)
resource "databricks_storage_credential" "gcp" {
  provider = databricks.workspace
  name     = "${var.prefix}-gcs-credential"

  # Option A: Reuse the Databricks-managed SA created by metastore_data_access
  databricks_gcp_service_account {}

  depends_on = [databricks_metastore_assignment.gcp]
}

# External location pointing to the external GCS bucket created in Stage 2
resource "databricks_external_location" "gcs_data" {
  provider        = databricks.workspace
  name            = "${var.prefix}-gcs-location"
  url             = "gs://${google_storage_bucket.uc_external.name}/"
  credential_name = databricks_storage_credential.gcp.name

  depends_on = [databricks_metastore_assignment.gcp]
}

# Grant the new Databricks-managed SA access to the external bucket
resource "google_storage_bucket_iam_member" "gcs_external_access" {
  bucket = google_storage_bucket.uc_external.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${databricks_storage_credential.gcp.databricks_gcp_service_account[0].email}"
}
```

---

## Stage 4: Catalogs, Schemas & Tables

### Catalog

```hcl
resource "databricks_catalog" "main" {
  provider = databricks.workspace
  name     = var.catalog_name
  comment  = "Managed by Terraform"

  # Optional: pin to specific storage location (overrides metastore root)
  # storage_root = "s3://my-bucket/catalog"

  properties = {
    purpose = "production"
    team    = "data-engineering"
  }

  depends_on = [databricks_metastore_assignment.this]
}

# Delta Sharing catalog (from provider)
resource "databricks_catalog" "shared" {
  provider      = databricks.workspace
  name          = "shared_data"
  provider_name = var.delta_sharing_provider   # provider must exist first
  share_name    = var.delta_sharing_share_name
}
```

### Schema

```hcl
resource "databricks_schema" "bronze" {
  provider     = databricks.workspace
  catalog_name = databricks_catalog.main.name
  name         = "bronze"
  comment      = "Raw ingestion layer"

  # Optional: separate storage location
  # storage_root = "s3://my-bucket/bronze"

  properties = {
    layer = "bronze"
  }
}

resource "databricks_schema" "silver" {
  provider     = databricks.workspace
  catalog_name = databricks_catalog.main.name
  name         = "silver"
  comment      = "Curated layer"
}

resource "databricks_schema" "gold" {
  provider     = databricks.workspace
  catalog_name = databricks_catalog.main.name
  name         = "gold"
  comment      = "Business-ready layer"
}
```

### Volume

```hcl
resource "databricks_volume" "landing" {
  provider         = databricks.workspace
  name             = "landing"
  catalog_name     = databricks_catalog.main.name
  schema_name      = databricks_schema.bronze.name
  volume_type      = "EXTERNAL"
  storage_location = "${databricks_external_location.data.url}/landing"
  comment          = "Landing zone for raw files"
}

resource "databricks_volume" "managed" {
  provider     = databricks.workspace
  name         = "managed-files"
  catalog_name = databricks_catalog.main.name
  schema_name  = databricks_schema.bronze.name
  volume_type  = "MANAGED"
}
```

---

## Stage 5: Grants (Permissions)

> **CRITICAL**: `databricks_grants` is **authoritative** — it overwrites ALL existing grants on the securable. Always include every principal that should have access.

### Metastore Grants

```hcl
resource "databricks_grants" "metastore" {
  provider   = databricks.workspace
  metastore  = databricks_metastore.this.id

  grant {
    principal  = "data_engineers"
    privileges = ["CREATE_CATALOG", "CREATE_EXTERNAL_LOCATION"]
  }
  grant {
    principal  = "data_analysts"
    privileges = ["CREATE_CATALOG"]
  }
}
```

### Catalog Grants

```hcl
resource "databricks_grants" "main_catalog" {
  provider = databricks.workspace
  catalog  = databricks_catalog.main.name

  grant {
    principal  = "data_engineers"
    privileges = ["USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE", "CREATE_VOLUME"]
  }
  grant {
    principal  = "data_analysts"
    privileges = ["USE_CATALOG"]
  }
  grant {
    principal  = "ml_team"
    privileges = ["USE_CATALOG", "CREATE_SCHEMA"]
  }
}
```

### Schema Grants

```hcl
resource "databricks_grants" "bronze_schema" {
  provider = databricks.workspace
  schema   = "${databricks_catalog.main.name}.${databricks_schema.bronze.name}"

  grant {
    principal  = "data_engineers"
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "CREATE_VOLUME", "MODIFY", "SELECT"]
  }
  grant {
    principal  = "data_analysts"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}

resource "databricks_grants" "gold_schema" {
  provider = databricks.workspace
  schema   = "${databricks_catalog.main.name}.${databricks_schema.gold.name}"

  grant {
    principal  = "data_analysts"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
  grant {
    principal  = "data_engineers"
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
  }
}
```

### Table Grants

```hcl
resource "databricks_grants" "sensitive_table" {
  provider = databricks.workspace
  table    = "${databricks_catalog.main.name}.${databricks_schema.gold.name}.customer_data"

  grant {
    principal  = "pii_access_group"
    privileges = ["SELECT", "MODIFY"]
  }
  grant {
    principal  = "auditors"
    privileges = ["SELECT"]
  }
}
```

### Storage Credential Grants

```hcl
resource "databricks_grants" "storage_credential" {
  provider           = databricks.workspace
  storage_credential = databricks_storage_credential.external.id

  grant {
    principal  = "data_engineers"
    privileges = ["CREATE_EXTERNAL_LOCATION", "READ_FILES", "WRITE_FILES"]
  }
}
```

### External Location Grants

```hcl
resource "databricks_grants" "external_location" {
  provider          = databricks.workspace
  external_location = databricks_external_location.data.id

  grant {
    principal  = "data_engineers"
    privileges = ["CREATE_EXTERNAL_TABLE", "READ_FILES", "WRITE_FILES", "CREATE_MANAGED_STORAGE"]
  }
  grant {
    principal  = "data_analysts"
    privileges = ["READ_FILES"]
  }
}
```

---

## Complete UC Deployment Reference

### Required Provider Aliases

```hcl
# providers.tf
provider "databricks" {
  alias         = "mws"                                    # Account-level
  host          = "https://accounts.cloud.databricks.com" # AWS
  account_id    = var.databricks_account_id
  client_id     = var.client_id
  client_secret = var.client_secret
}

provider "databricks" {
  alias         = "workspace"                             # Workspace-level
  host          = var.workspace_url
  client_id     = var.client_id
  client_secret = var.client_secret
}
```

### Dependency Order

```
databricks_metastore
    └── databricks_metastore_assignment  (requires: workspace exists)
        └── databricks_metastore_data_access
            └── databricks_storage_credential
                └── databricks_external_location
                    └── databricks_catalog
                        └── databricks_schema
                            ├── databricks_volume
                            ├── databricks_grants (schema)
                            └── databricks_grants (table)
```

### Privilege Reference Table

| Securable | Common Privileges | Notes |
|-----------|-------------------|-------|
| **Metastore** | `CREATE_CATALOG`, `CREATE_EXTERNAL_LOCATION`, `CREATE_STORAGE_CREDENTIAL` | Granted to account admins/data admins |
| **Catalog** | `USE_CATALOG`, `CREATE_SCHEMA`, `CREATE_TABLE`, `ALL_PRIVILEGES` | `USE_CATALOG` required to access anything within |
| **Schema** | `USE_SCHEMA`, `CREATE_TABLE`, `CREATE_VOLUME`, `SELECT`, `MODIFY` | `USE_SCHEMA` required to access tables/volumes |
| **Table** | `SELECT`, `MODIFY`, `ALL_PRIVILEGES` | Row/column-level security via row filters/column masks |
| **Volume** | `READ_VOLUME`, `WRITE_VOLUME`, `ALL_PRIVILEGES` | For file-level access |
| **External Location** | `READ_FILES`, `WRITE_FILES`, `CREATE_EXTERNAL_TABLE`, `CREATE_MANAGED_STORAGE` | |
| **Storage Credential** | `CREATE_EXTERNAL_LOCATION`, `READ_FILES`, `WRITE_FILES` | |

---

## Workspace Configuration for UC

```hcl
# Enable UC features on workspace
resource "databricks_workspace_conf" "uc" {
  provider = databricks.workspace
  # custom_config is map(string) — all values must be quoted strings, including booleans
  custom_config = {
    "enableIpAccessLists"  = "true"
    "maxTokenLifetimeDays" = "90"
  }
}

# Set default catalog for workspace users
resource "databricks_default_namespace_setting" "this" {
  provider = databricks.workspace
  namespace {
    value = databricks_catalog.main.name
  }
}
```

---

## Complete UC Deployment — Cloud Comparison

| Step | AWS | Azure | GCP |
|------|-----|-------|-----|
| **Metastore storage** | S3 bucket | ADLS Gen2 (`is_hns_enabled = true`) | GCS bucket |
| **Metastore storage_root** | `s3://bucket/metastore` | `abfss://container@account.dfs.core.windows.net/` | `gs://bucket/metastore` |
| **Identity for data access** | IAM role with trust policy | Access Connector (system-assigned managed identity) | Databricks-managed GCP SA or existing SA |
| **Account-level provider host** | `accounts.cloud.databricks.com` | `accounts.azuredatabricks.net` | `accounts.gcp.databricks.com` |
| **metastore_data_access block** | `aws_iam_role { role_arn }` | `azure_managed_identity { access_connector_id }` | `databricks_gcp_service_account {}` |
| **Storage credential block** | `aws_iam_role { role_arn }` | `azure_managed_identity { access_connector_id }` | `databricks_gcp_service_account {}` |

## Common Issues

| Issue | Solution |
|-------|----------|
| **`METASTORE_ALREADY_EXISTS` in region** | Only one metastore per region; use data source to reference existing: `data "databricks_metastore" "this"` |
| **`grants` removes admin permissions** | `databricks_grants` is authoritative — always include ALL principals including admins |
| **External location validation fails** | Set `skip_validation = true` temporarily, then fix IAM role trust policy |
| **`metastore_assignment` fails with workspace not found** | Workspace must be fully created before assignment; use `depends_on` |
| **Catalog deletion fails** | Use `force_destroy = true` and first delete all child objects, or set `depends_on` order |
| **Azure: `is_hns_enabled` must be true** | ADLS Gen2 hierarchical namespace is required for UC storage root; cannot be changed after creation |
| **Azure: Access Connector role propagation** | After creating connector, allow ~5 minutes for `Storage Blob Data Contributor` role to propagate |
| **Azure: wrong account host** | Use `accounts.azuredatabricks.net` for Azure account provider, NOT `accounts.cloud.databricks.com` |
| **GCP: two-step apply for managed SA** | `databricks_gcp_service_account {}` creates SA on first apply; grant bucket IAM in same or subsequent apply |
| **GCP SA credential validation** | Ensure SA has `roles/storage.objectAdmin` on the target GCS bucket |
| **GCP: storage bucket location** | Use `upper(var.google_region)` for GCS bucket location (GCS uses uppercase region names) |
