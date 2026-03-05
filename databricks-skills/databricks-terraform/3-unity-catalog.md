# Unity Catalog Resources

Manage the full Unity Catalog hierarchy and governance via Terraform.

## Namespace Hierarchy

```
metastore (account-level)
└── catalog
    └── schema
        ├── table / view / materialized view
        ├── volume (managed or external)
        └── function
```

---

## Metastore (Account-Level)

```hcl
resource "databricks_metastore" "primary" {
  provider      = databricks.account
  name          = "primary-metastore"
  region        = "us-west-2"
  storage_root  = "s3://my-metastore-bucket/metastore"
  force_destroy = true
}

resource "databricks_metastore_assignment" "default" {
  provider     = databricks.account
  metastore_id = databricks_metastore.primary.id
  workspace_id = var.workspace_id
}
```

---

## Catalogs

```hcl
resource "databricks_catalog" "analytics" {
  name           = "analytics"
  comment        = "Production analytics catalog"
  isolation_mode = "OPEN"
}

resource "databricks_catalog" "sandbox" {
  name    = "sandbox"
  comment = "Development sandbox"
  properties = {
    "environment" = "dev"
  }
}
```

### Foreign Catalog (Lakehouse Federation)

```hcl
resource "databricks_catalog" "postgres_erp" {
  name            = "erp"
  comment         = "Federated PostgreSQL ERP database"
  connection_name = databricks_connection.postgres.name

  options = {
    "database" = "erp_production"
  }
}
```

---

## Schemas

```hcl
resource "databricks_schema" "bronze" {
  catalog_name = databricks_catalog.analytics.name
  name         = "bronze"
  comment      = "Raw ingestion layer"
}

resource "databricks_schema" "silver" {
  catalog_name = databricks_catalog.analytics.name
  name         = "silver"
  comment      = "Cleaned and conformed data"
}

resource "databricks_schema" "gold" {
  catalog_name = databricks_catalog.analytics.name
  name         = "gold"
  comment      = "Business-level aggregations"
}
```

### Medallion Pattern Module

```hcl
variable "catalog_name" {
  type = string
}

variable "layers" {
  type    = list(string)
  default = ["bronze", "silver", "gold"]
}

resource "databricks_schema" "layer" {
  for_each     = toset(var.layers)
  catalog_name = var.catalog_name
  name         = each.value
  comment      = "${title(each.value)} data layer"
}
```

---

## Volumes

```hcl
resource "databricks_volume" "raw_files" {
  catalog_name = databricks_catalog.analytics.name
  schema_name  = databricks_schema.bronze.name
  name         = "raw_files"
  volume_type  = "MANAGED"
  comment      = "Raw ingestion files"
}

resource "databricks_volume" "landing_zone" {
  catalog_name     = databricks_catalog.analytics.name
  schema_name      = databricks_schema.bronze.name
  name             = "landing_zone"
  volume_type      = "EXTERNAL"
  storage_location = "s3://my-bucket/landing/"
  comment          = "External landing zone"
}
```

---

## Storage Credentials & External Locations

```hcl
resource "databricks_storage_credential" "s3_access" {
  name = "s3-analytics-credential"

  aws_iam_role {
    role_arn = var.iam_role_arn
  }

  comment = "Access to analytics S3 bucket"
}

resource "databricks_external_location" "landing" {
  name            = "analytics-landing"
  url             = "s3://my-bucket/landing/"
  credential_name = databricks_storage_credential.s3_access.name
  comment         = "Landing zone for raw data"
}
```

---

## Grants

Grants use a single `databricks_grants` resource per securable object.

```hcl
resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.analytics.name

  grant {
    principal  = "data-engineering"
    privileges = ["USE_CATALOG", "CREATE_SCHEMA"]
  }

  grant {
    principal  = "data-analysts"
    privileges = ["USE_CATALOG"]
  }
}

resource "databricks_grants" "schema" {
  schema = "${databricks_catalog.analytics.name}.${databricks_schema.gold.name}"

  grant {
    principal  = "data-analysts"
    privileges = ["USE_SCHEMA", "SELECT"]
  }

  grant {
    principal  = "data-engineering"
    privileges = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE", "CREATE_VOLUME"]
  }
}

resource "databricks_grants" "volume" {
  volume = "${databricks_catalog.analytics.name}.${databricks_schema.bronze.name}.${databricks_volume.raw_files.name}"

  grant {
    principal  = "data-engineering"
    privileges = ["READ_VOLUME", "WRITE_VOLUME"]
  }
}
```

### Grant on External Location

```hcl
resource "databricks_grants" "ext_location" {
  external_location = databricks_external_location.landing.id

  grant {
    principal  = "data-engineering"
    privileges = ["CREATE_EXTERNAL_TABLE", "CREATE_EXTERNAL_VOLUME", "READ_FILES", "WRITE_FILES"]
  }
}
```

---

## Connections (Lakehouse Federation)

```hcl
resource "databricks_connection" "postgres" {
  name            = "postgres-erp"
  connection_type = "POSTGRESQL"
  comment         = "ERP PostgreSQL database"

  options = {
    "host"     = var.postgres_host
    "port"     = "5432"
    "user"     = var.postgres_user
    "password" = var.postgres_password
  }
}
```

---

## Delta Sharing

```hcl
resource "databricks_share" "partner_data" {
  name = "partner-data-share"

  object {
    name                        = "analytics.gold.quarterly_metrics"
    data_object_type            = "TABLE"
    shared_as                   = "quarterly_metrics"
  }
}

resource "databricks_recipient" "partner" {
  name                = "acme-corp"
  authentication_type = "TOKEN"
  comment             = "Acme Corp data team"
}

resource "databricks_grants" "share_grant" {
  share = databricks_share.partner_data.name

  grant {
    principal  = databricks_recipient.partner.name
    privileges = ["SELECT"]
  }
}
```

---

## Complete Unity Catalog Setup

```hcl
locals {
  catalog_name = "analytics"
  layers       = ["bronze", "silver", "gold"]
  teams = {
    "data-engineering" = {
      catalog_privs = ["USE_CATALOG", "CREATE_SCHEMA"]
      schema_privs  = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
    }
    "data-analysts" = {
      catalog_privs = ["USE_CATALOG"]
      schema_privs  = ["USE_SCHEMA", "SELECT"]
    }
  }
}

resource "databricks_catalog" "main" {
  name    = local.catalog_name
  comment = "Main analytics catalog"
}

resource "databricks_schema" "layers" {
  for_each     = toset(local.layers)
  catalog_name = databricks_catalog.main.name
  name         = each.value
  comment      = "${title(each.value)} data layer"
}

resource "databricks_grants" "catalog_grants" {
  catalog = databricks_catalog.main.name

  dynamic "grant" {
    for_each = local.teams
    content {
      principal  = grant.key
      privileges = grant.value.catalog_privs
    }
  }
}

resource "databricks_grants" "schema_grants" {
  for_each = databricks_schema.layers
  schema   = "${databricks_catalog.main.name}.${each.value.name}"

  dynamic "grant" {
    for_each = local.teams
    content {
      principal  = grant.key
      privileges = grant.value.schema_privs
    }
  }
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Catalog not found" on schema creation** | Ensure catalog resource is referenced (implicit dependency) or use `depends_on` |
| **Grants conflict** | Only one `databricks_grants` resource per securable object; combine all grants in one block |
| **External volume fails** | Storage credential and external location must exist first |
| **Metastore operations fail** | Metastore resources require account-level provider (`provider = databricks.account`) |
| **Import existing UC objects** | Use `terraform import databricks_catalog.name "catalog_name"` |
