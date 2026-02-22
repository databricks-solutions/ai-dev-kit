# Azure Workspace Deployment

## Overview

Two deployment patterns for Azure:
1. **Basic (VNet injection)** — standard deployment with custom VNet
2. **Private Link Standard** — two-VNet architecture, no public endpoints

Reference examples: [adb-vnet-injection](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/adb-vnet-injection) | [adb-with-private-link-standard](https://github.com/databricks/terraform-databricks-examples/tree/main/examples/adb-with-private-link-standard)

---

## Pattern 1: Basic Azure Workspace with VNet Injection

### Prerequisites

- Azure subscription with `Contributor` permissions
- `Microsoft.Databricks` resource provider registered
- Terraform ≥ 1.3.0, AzureRM provider ≥ 3.0

### providers.tf

```hcl
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.38.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

# Workspace provider — only available after workspace is created
provider "databricks" {
  azure_workspace_resource_id = azurerm_databricks_workspace.this.id
  # Uses Azure CLI or SP credentials from environment
}
```

### main.tf — Resource Group & Networking

```hcl
resource "azurerm_resource_group" "databricks" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = var.tags
}

# Main VNet
resource "azurerm_virtual_network" "databricks" {
  name                = "${var.prefix}-vnet"
  location            = azurerm_resource_group.databricks.location
  resource_group_name = azurerm_resource_group.databricks.name
  address_space       = [var.vnet_cidr]
  tags                = var.tags
}

# Host subnet (public — used by Azure Databricks control plane)
resource "azurerm_subnet" "public" {
  name                 = "${var.prefix}-public-subnet"
  resource_group_name  = azurerm_resource_group.databricks.name
  virtual_network_name = azurerm_virtual_network.databricks.name
  address_prefixes     = [var.public_subnet_cidr]

  delegation {
    name = "databricks-delegation"
    service_delegation {
      name    = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action"
      ]
    }
  }
}

# Container subnet (private — used by worker nodes)
resource "azurerm_subnet" "private" {
  name                 = "${var.prefix}-private-subnet"
  resource_group_name  = azurerm_resource_group.databricks.name
  virtual_network_name = azurerm_virtual_network.databricks.name
  address_prefixes     = [var.private_subnet_cidr]

  delegation {
    name = "databricks-delegation"
    service_delegation {
      name    = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action"
      ]
    }
  }
}

# Network Security Groups (NSGs) — Databricks manages rules automatically
resource "azurerm_network_security_group" "public" {
  name                = "${var.prefix}-public-nsg"
  location            = azurerm_resource_group.databricks.location
  resource_group_name = azurerm_resource_group.databricks.name
  tags                = var.tags
}

resource "azurerm_network_security_group" "private" {
  name                = "${var.prefix}-private-nsg"
  location            = azurerm_resource_group.databricks.location
  resource_group_name = azurerm_resource_group.databricks.name
  tags                = var.tags
}

resource "azurerm_subnet_network_security_group_association" "public" {
  subnet_id                 = azurerm_subnet.public.id
  network_security_group_id = azurerm_network_security_group.public.id
}

resource "azurerm_subnet_network_security_group_association" "private" {
  subnet_id                 = azurerm_subnet.private.id
  network_security_group_id = azurerm_network_security_group.private.id
}
```

### main.tf — Databricks Workspace

```hcl
resource "azurerm_databricks_workspace" "this" {
  name                        = "${var.prefix}-workspace"
  resource_group_name         = azurerm_resource_group.databricks.name
  location                    = azurerm_resource_group.databricks.location
  sku                         = "premium"   # Required for Unity Catalog
  tags                        = var.tags

  custom_parameters {
    virtual_network_id                                   = azurerm_virtual_network.databricks.id
    public_subnet_name                                   = azurerm_subnet.public.name
    private_subnet_name                                  = azurerm_subnet.private.name
    public_subnet_network_security_group_association_id  = azurerm_subnet_network_security_group_association.public.id
    private_subnet_network_security_group_association_id = azurerm_subnet_network_security_group_association.private.id

    # Disable public IP for worker nodes (recommended)
    no_public_ip = true
  }
}
```

### outputs.tf

```hcl
output "workspace_url" {
  value = "https://${azurerm_databricks_workspace.this.workspace_url}"
}
output "workspace_id" {
  value = azurerm_databricks_workspace.this.workspace_id
}
output "workspace_resource_id" {
  value = azurerm_databricks_workspace.this.id
}
```

### variables.tf (Pattern 1)

```hcl
variable "subscription_id"     { type = string }
variable "location"            { type = string; default = "eastus2" }
variable "prefix"              { type = string; default = "demo" }
variable "vnet_cidr"           { type = string; default = "10.179.0.0/20" }
variable "public_subnet_cidr"  { type = string; default = "10.179.0.0/24" }
variable "private_subnet_cidr" { type = string; default = "10.179.1.0/24" }
variable "tags"                { type = map(string); default = {} }
```

---

## Pattern 2: Azure Private Link Standard Deployment

Two-VNet architecture eliminating all public internet exposure.

### Architecture

```
┌──────────────────────────────────────────────────────┐
│  Transit VNet (cidr_transit)                          │
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │  Private Endpoint: Frontend (Web UI)         │    │
│  │  Private Endpoint: Authentication (SSO)      │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
│  Test VM (for validation from within the VNet)        │
└──────────────────────────────────────────────────────┘
                        │
                 VNet Peering
                        │
┌──────────────────────────────────────────────────────┐
│  Data Plane VNet (cidr_dp)                            │
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │  Public Subnet  (Databricks Host)            │    │
│  │  Private Subnet (Databricks Container)        │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
│  Private Endpoint: Backend (Control Plane)            │
└──────────────────────────────────────────────────────┘
                        │
          Private Link (no public internet)
                        │
                Databricks Control Plane
```

### providers.tf

> **Note**: The Private Link standard example requires AzureRM provider **v4.0+** (differs from Pattern 1 which uses `~> 3.100`). If combining both patterns in one configuration, pin to `>= 4.0.0`.

```hcl
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.0.0"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.38.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
```

### main.tf — Data Plane VNet

```hcl
resource "azurerm_resource_group" "dp" {
  name     = var.create_data_plane_resource_group ? "${var.prefix}-dp-rg" : var.existing_data_plane_resource_group_name
  location = var.location
}

resource "azurerm_virtual_network" "dp" {
  name                = "${var.prefix}-dp-vnet"
  location            = azurerm_resource_group.dp.location
  resource_group_name = azurerm_resource_group.dp.name
  address_space       = [var.cidr_dp]
  tags                = var.tags
}

# Host (public) and container (private) subnets with delegation
resource "azurerm_subnet" "dp_public" {
  name                 = "databricks-public"
  resource_group_name  = azurerm_resource_group.dp.name
  virtual_network_name = azurerm_virtual_network.dp.name
  address_prefixes     = [cidrsubnet(var.cidr_dp, 3, 0)]

  delegation {
    name = "databricks"
    service_delegation {
      name    = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action"
      ]
    }
  }
}

resource "azurerm_subnet" "dp_private" {
  name                 = "databricks-private"
  resource_group_name  = azurerm_resource_group.dp.name
  virtual_network_name = azurerm_virtual_network.dp.name
  address_prefixes     = [cidrsubnet(var.cidr_dp, 3, 1)]

  delegation {
    name = "databricks"
    service_delegation {
      name    = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action"
      ]
    }
  }
}

# Subnet for backend private endpoint (no delegation)
resource "azurerm_subnet" "dp_pe" {
  name                 = "private-endpoint"
  resource_group_name  = azurerm_resource_group.dp.name
  virtual_network_name = azurerm_virtual_network.dp.name
  address_prefixes     = [cidrsubnet(var.cidr_dp, 3, 2)]
}
```

### main.tf — Workspace with Private Link

```hcl
# NSGs for the data plane subnets (required before workspace creation)
resource "azurerm_network_security_group" "dp_public" {
  name                = "${var.prefix}-dp-public-nsg"
  location            = azurerm_resource_group.dp.location
  resource_group_name = azurerm_resource_group.dp.name
  tags                = var.tags
}

resource "azurerm_network_security_group" "dp_private" {
  name                = "${var.prefix}-dp-private-nsg"
  location            = azurerm_resource_group.dp.location
  resource_group_name = azurerm_resource_group.dp.name
  tags                = var.tags
}

resource "azurerm_subnet_network_security_group_association" "dp_public" {
  subnet_id                 = azurerm_subnet.dp_public.id
  network_security_group_id = azurerm_network_security_group.dp_public.id
}

resource "azurerm_subnet_network_security_group_association" "dp_private" {
  subnet_id                 = azurerm_subnet.dp_private.id
  network_security_group_id = azurerm_network_security_group.dp_private.id
}

resource "azurerm_databricks_workspace" "this" {
  name                = "${var.prefix}-workspace"
  resource_group_name = azurerm_resource_group.dp.name
  location            = azurerm_resource_group.dp.location
  sku                 = "premium"
  tags                = var.tags

  public_network_access_enabled         = false  # No public access
  network_security_group_rules_required = "NoAzureDatabricksRules"

  custom_parameters {
    virtual_network_id  = azurerm_virtual_network.dp.id
    public_subnet_name  = azurerm_subnet.dp_public.name
    private_subnet_name = azurerm_subnet.dp_private.name
    public_subnet_network_security_group_association_id  = azurerm_subnet_network_security_group_association.dp_public.id
    private_subnet_network_security_group_association_id = azurerm_subnet_network_security_group_association.dp_private.id
    no_public_ip        = true
  }
}
```

### main.tf — Backend Private Endpoint (Data Plane VNet)

```hcl
resource "azurerm_private_endpoint" "backend" {
  name                = "${var.prefix}-backend-pe"
  location            = azurerm_resource_group.dp.location
  resource_group_name = azurerm_resource_group.dp.name
  subnet_id           = azurerm_subnet.dp_pe.id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.prefix}-backend-psc"
    private_connection_resource_id = azurerm_databricks_workspace.this.id
    subresource_names              = ["databricks_ui_api"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "databricks-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.databricks.id]
  }
}
```

### main.tf — Transit VNet & Frontend/Auth Endpoints

```hcl
resource "azurerm_resource_group" "transit" {
  name     = "${var.prefix}-transit-rg"
  location = var.location
}

resource "azurerm_virtual_network" "transit" {
  name                = "${var.prefix}-transit-vnet"
  location            = azurerm_resource_group.transit.location
  resource_group_name = azurerm_resource_group.transit.name
  address_space       = [var.cidr_transit]
  tags                = var.tags
}

resource "azurerm_subnet" "transit_pe" {
  name                 = "private-endpoint"
  resource_group_name  = azurerm_resource_group.transit.name
  virtual_network_name = azurerm_virtual_network.transit.name
  address_prefixes     = [cidrsubnet(var.cidr_transit, 3, 0)]
}

# Frontend (Web UI) Private Endpoint
resource "azurerm_private_endpoint" "frontend" {
  name                = "${var.prefix}-frontend-pe"
  location            = azurerm_resource_group.transit.location
  resource_group_name = azurerm_resource_group.transit.name
  subnet_id           = azurerm_subnet.transit_pe.id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.prefix}-frontend-psc"
    private_connection_resource_id = azurerm_databricks_workspace.this.id
    subresource_names              = ["databricks_ui_api"]
    is_manual_connection           = false
  }
}

# Web Authentication Private Endpoint
resource "azurerm_private_endpoint" "auth" {
  name                = "${var.prefix}-auth-pe"
  location            = azurerm_resource_group.transit.location
  resource_group_name = azurerm_resource_group.transit.name
  subnet_id           = azurerm_subnet.transit_pe.id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.prefix}-auth-psc"
    private_connection_resource_id = azurerm_databricks_workspace.this.id
    subresource_names              = ["browser_authentication"]
    is_manual_connection           = false
  }
}

# VNet Peering between transit and data plane
resource "azurerm_virtual_network_peering" "dp_to_transit" {
  name                         = "dp-to-transit"
  resource_group_name          = azurerm_resource_group.dp.name
  virtual_network_name         = azurerm_virtual_network.dp.name
  remote_virtual_network_id    = azurerm_virtual_network.transit.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
}

resource "azurerm_virtual_network_peering" "transit_to_dp" {
  name                         = "transit-to-dp"
  resource_group_name          = azurerm_resource_group.transit.name
  virtual_network_name         = azurerm_virtual_network.transit.name
  remote_virtual_network_id    = azurerm_virtual_network.dp.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
}
```

### Private DNS Zone

```hcl
resource "azurerm_private_dns_zone" "databricks" {
  name                = "privatelink.azuredatabricks.net"
  resource_group_name = azurerm_resource_group.dp.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "dp" {
  name                  = "dp-link"
  resource_group_name   = azurerm_resource_group.dp.name
  private_dns_zone_name = azurerm_private_dns_zone.databricks.name
  virtual_network_id    = azurerm_virtual_network.dp.id
}

resource "azurerm_private_dns_zone_virtual_network_link" "transit" {
  name                  = "transit-link"
  resource_group_name   = azurerm_resource_group.dp.name
  private_dns_zone_name = azurerm_private_dns_zone.databricks.name
  virtual_network_id    = azurerm_virtual_network.transit.id
}
```

### variables.tf (Pattern 2 additions)

```hcl
variable "cidr_dp"      { type = string; default = "10.180.0.0/20" }
variable "cidr_transit" { type = string; default = "10.181.0.0/24" }

variable "create_data_plane_resource_group" {
  type    = bool
  default = true
  description = "Set false to reuse an existing resource group"
}
variable "existing_data_plane_resource_group_name" {
  type    = string
  default = ""
}
```

---

## Customer-Managed Keys (Azure Key Vault)

```hcl
resource "azurerm_key_vault" "databricks" {
  name                = "${var.prefix}-kv"
  location            = azurerm_resource_group.databricks.location
  resource_group_name = azurerm_resource_group.databricks.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "premium"  # Premium required for HSM-backed keys
}

resource "azurerm_key_vault_key" "databricks" {
  name         = "${var.prefix}-key"
  key_vault_id = azurerm_key_vault.databricks.id
  key_type     = "RSA"
  key_size     = 2048
  key_opts     = ["decrypt", "encrypt", "sign", "unwrapKey", "verify", "wrapKey"]
}

resource "azurerm_databricks_workspace_customer_managed_key" "this" {
  workspace_id     = azurerm_databricks_workspace.this.id
  key_vault_key_id = azurerm_key_vault_key.databricks.id
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **`Subnet delegation already exists`** | Each subnet can only have one delegation; verify no conflicting resources |
| **`InsufficientSubnetSize`** | Databricks requires at minimum /26 for public and /26 for private subnets |
| **Private endpoint DNS not resolving** | Ensure DNS zone is linked to both VNets and propagation time (~5 min) has passed |
| **`NoAzureDatabricksRules` NSG conflict** | With Private Link, remove all manually added NSG rules; Databricks manages them |
| **`premium` SKU required for UC** | Set `sku = "premium"` for Unity Catalog compatibility |
| **VNet peering failing** | Both sides of peering must be created; use `depends_on` to ensure order |
| **Azure SP needs additional role** | For ADLS Gen2 access, SP needs `Storage Blob Data Contributor` on the storage account |
