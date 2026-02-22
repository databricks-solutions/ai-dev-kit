# GCP Workspace Deployment

## Overview

Two deployment patterns for GCP:
1. **Managed VPC (Basic)** — Databricks manages the VPC, simplest setup
2. **BYOVPC (Customer-Managed VPC)** — full control over networking

Reference examples: [gcp-basic](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/gcp-basic) | [gcp-byovpc](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/gcp-byovpc)

---

## Prerequisites

Before deploying GCP workspaces, provision a service account for Databricks. This is a two-step process:

1. **Step 1** — Create and configure the GCP service account ([gcp-sa-provisioning](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/gcp-sa-provisionning))
2. **Step 2** — Deploy the workspace using the service account

### Step 1: Service Account Provisioning

```hcl
# Required GCP APIs to enable
resource "google_project_service" "required" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "compute.googleapis.com",
    "serviceusage.googleapis.com",
    "databricks.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

# Service account for Databricks
resource "google_service_account" "databricks" {
  account_id   = "${var.prefix}-databricks-sa"
  display_name = "Databricks Workspace Service Account"
  project      = var.google_project
}

# Required IAM roles for the service account
locals {
  databricks_sa_roles = [
    "roles/compute.admin",
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountTokenCreator",
    "roles/storage.admin",
    "roles/logging.logWriter"
  ]
}

resource "google_project_iam_member" "databricks_sa" {
  for_each = toset(local.databricks_sa_roles)
  project  = var.google_project
  role     = each.value
  member   = "serviceAccount:${google_service_account.databricks.email}"
}

# Allow users/SPs to impersonate the service account
resource "google_service_account_iam_binding" "impersonation" {
  service_account_id = google_service_account.databricks.name
  role               = "roles/iam.serviceAccountTokenCreator"
  members            = var.delegate_from  # e.g., ["user:admin@company.com"]
}
```

---

## Pattern 1: Managed VPC (gcp-basic)

Databricks creates and manages the VPC. Simplest deployment option.

### providers.tf

```hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.38.0"
    }
  }
}

provider "google" {
  project = var.google_project
  region  = var.google_region
  zone    = var.google_zone
}

# Account-level Databricks provider (for workspace creation)
provider "databricks" {
  alias                  = "mws"
  host                   = "https://accounts.gcp.databricks.com"
  account_id             = var.databricks_account_id
  google_service_account = var.databricks_google_service_account
}

# Workspace-level provider (after workspace creation)
provider "databricks" {
  alias = "workspace"
  host  = databricks_mws_workspaces.this.workspace_url
  google_service_account = var.databricks_google_service_account
}
```

### main.tf

```hcl
# GCS bucket for workspace root storage
resource "google_storage_bucket" "root" {
  name          = "${var.prefix}-databricks-root"
  location      = upper(var.google_region)
  force_destroy = true

  uniform_bucket_level_access = true

  versioning { enabled = false }
}

# Grant Databricks SA access to root bucket
resource "google_storage_bucket_iam_member" "root_admin" {
  bucket = google_storage_bucket.root.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${var.databricks_google_service_account}"
}

# Databricks workspace (managed VPC)
resource "databricks_mws_workspaces" "this" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = var.workspace_name

  location = var.google_region
  cloud    = "gcp"

  gcp_managed_network_config {
    gke_cluster_pod_ip_range     = "10.3.0.0/16"
    gke_cluster_service_ip_range = "10.4.0.0/16"
    subnet_cidr                  = "10.0.0.0/22"
  }

  gke_config {
    connectivity_type = "PRIVATE_NODE_PUBLIC_MASTER"
    master_ip_range   = "10.3.0.0/28"
  }

  storage_configuration {
    gcs {
      bucket_name = google_storage_bucket.root.name
    }
  }

  token {
    comment = "Terraform-managed token"
  }
}

output "databricks_host" {
  value = databricks_mws_workspaces.this.workspace_url
}
output "databricks_token" {
  value     = databricks_mws_workspaces.this.token[0].token_value
  sensitive = true
}
```

### variables.tf

```hcl
variable "databricks_account_id"            { type = string }
variable "databricks_google_service_account" { type = string }
variable "google_project"                   { type = string }
variable "google_region"                    { type = string; default = "us-central1" }
variable "google_zone"                      { type = string; default = "us-central1-a" }
variable "prefix"                           { type = string; default = "demo" }
variable "workspace_name"                   { type = string; default = "my-workspace" }
variable "delegate_from"                    { type = list(string); default = [] }
```

---

## Pattern 2: BYOVPC (Customer-Managed VPC)

Full control over networking — required for Private Service Connect (PSC) or custom firewall rules.

### main.tf — VPC & Subnets

```hcl
# Custom VPC
resource "google_compute_network" "databricks" {
  name                    = "${var.prefix}-vpc"
  auto_create_subnetworks = false
  project                 = var.google_project
}

# Primary subnet for Databricks nodes
resource "google_compute_subnetwork" "databricks" {
  name                     = var.subnet_name
  ip_cidr_range            = var.subnet_ip_cidr_range  # e.g., "10.0.0.0/22"
  region                   = var.google_region
  network                  = google_compute_network.databricks.id
  private_ip_google_access = true

  # Secondary ranges for GKE pods and services
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pod_ip_cidr_range  # e.g., "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.svc_ip_cidr_range  # e.g., "10.2.0.0/20"
  }
}

# Cloud Router for NAT (outbound internet)
resource "google_compute_router" "databricks" {
  name    = var.router_name
  region  = var.google_region
  network = google_compute_network.databricks.id
}

# Cloud NAT for outbound internet from private nodes
resource "google_compute_router_nat" "databricks" {
  name                               = var.nat_name
  router                             = google_compute_router.databricks.name
  region                             = var.google_region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Firewall rules
resource "google_compute_firewall" "databricks_internal" {
  name    = "${var.prefix}-databricks-internal"
  network = google_compute_network.databricks.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  source_tags = ["databricks"]
  target_tags = ["databricks"]
}

resource "google_compute_firewall" "databricks_egress" {
  name      = "${var.prefix}-databricks-egress"
  network   = google_compute_network.databricks.name
  direction = "EGRESS"

  allow { protocol = "all" }

  target_tags        = ["databricks"]
  destination_ranges = ["0.0.0.0/0"]
}
```

### main.tf — Network Configuration & Workspace

```hcl
resource "databricks_mws_networks" "this" {
  provider     = databricks.mws
  account_id   = var.databricks_account_id
  network_name = "${var.prefix}-network"

  gcp_network_info {
    network_project_id    = var.google_project
    vpc_id                = google_compute_network.databricks.name
    subnet_id             = google_compute_subnetwork.databricks.name
    subnet_region         = var.google_region
    pod_ip_range_name     = "pods"
    service_ip_range_name = "services"
  }
}

resource "databricks_mws_workspaces" "byovpc" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = var.workspace_name

  location = var.google_region
  cloud    = "gcp"

  network_id = databricks_mws_networks.this.network_id

  gke_config {
    connectivity_type = "PRIVATE_NODE_PUBLIC_MASTER"  # or "PRIVATE_NODE_PRIVATE_MASTER" for PSC
    master_ip_range   = "10.3.0.0/28"
  }

  storage_configuration {
    gcs {
      bucket_name = google_storage_bucket.root.name
    }
  }
}
```

### variables.tf (BYOVPC additions)

```hcl
variable "subnet_name"           { type = string; default = "databricks-subnet" }
variable "subnet_ip_cidr_range"  { type = string; default = "10.0.0.0/22" }
variable "pod_ip_cidr_range"     { type = string; default = "10.1.0.0/16" }
variable "svc_ip_cidr_range"     { type = string; default = "10.2.0.0/20" }
variable "router_name"           { type = string; default = "databricks-router" }
variable "nat_name"              { type = string; default = "databricks-nat" }
```

---

## Pattern 3: Private Service Connect (PSC) — No Public Internet

For maximum isolation using Google Private Service Connect.

```hcl
# PSC endpoint for Databricks relay
resource "google_compute_address" "psc_relay" {
  name         = "${var.prefix}-psc-relay"
  subnetwork   = google_compute_subnetwork.databricks.id
  address_type = "INTERNAL"
  region       = var.google_region
}

resource "google_compute_forwarding_rule" "psc_relay" {
  name                  = "${var.prefix}-psc-relay-fw"
  region                = var.google_region
  network               = google_compute_network.databricks.id
  subnetwork            = google_compute_subnetwork.databricks.id
  ip_address            = google_compute_address.psc_relay.id
  target                = var.relay_psc_service_attachment  # From Databricks docs for your region
  load_balancing_scheme = ""  # PSC
}

resource "databricks_mws_workspaces" "psc" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = var.workspace_name
  location       = var.google_region
  cloud          = "gcp"
  network_id     = databricks_mws_networks.this.network_id

  gke_config {
    connectivity_type = "PRIVATE_NODE_PRIVATE_MASTER"  # Full private
    master_ip_range   = "10.3.0.0/28"
  }

  storage_configuration {
    gcs { bucket_name = google_storage_bucket.root.name }
  }

  private_access_settings_id = databricks_mws_private_access_settings.psc.id
}

resource "databricks_mws_private_access_settings" "psc" {
  provider                     = databricks.mws
  account_id                   = var.databricks_account_id
  private_access_settings_name = "${var.prefix}-psc"
  region                       = var.google_region
  public_access_enabled        = false
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **`googleapi: Error 403: Required permission missing`** | Ensure SA has all required IAM roles; check `gcp-sa-provisioning` step first |
| **`Databricks API requires service account`** | GCP provider auth must use service account, not user credentials |
| **GKE pod CIDR conflict** | Secondary ranges must not overlap with primary subnet or other existing ranges |
| **Workspace creation hangs** | GKE cluster creation takes 5-10 minutes; increase `timeouts` in workspace resource |
| **NAT gateway not routing** | Verify `private_ip_google_access = true` on subnet and NAT covers all ranges |
| **PSC endpoint service name** | Look up region-specific PSC service attachments in Databricks GCP docs |
| **Storage bucket permission denied** | SA needs `roles/storage.admin` on the root GCS bucket |
