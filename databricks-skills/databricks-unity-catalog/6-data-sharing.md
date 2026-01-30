# Delta Sharing

Share data with external partners without copying data.

## Overview

Delta Sharing enables secure data sharing:
- **Provider**: Organization sharing data
- **Share**: Collection of tables/schemas to share
- **Recipient**: External party receiving access
- **Activation Link**: One-time link for recipient setup

---

## Creating Shares

### Create a Share

**SQL:**
```sql
-- Create empty share
CREATE SHARE customer_insights
COMMENT 'Customer analytics data for partners';

-- Create share with tables
CREATE SHARE sales_data
COMMENT 'Sales data for external analytics';

-- Add tables to share
ALTER SHARE sales_data ADD TABLE analytics.gold.orders;
ALTER SHARE sales_data ADD TABLE analytics.gold.products;
ALTER SHARE sales_data ADD TABLE analytics.gold.customers;

-- Add table with alias (different name for recipient)
ALTER SHARE sales_data ADD TABLE analytics.gold.customer_360
AS shared.customer_summary;

-- Add table with partition filter
ALTER SHARE sales_data ADD TABLE analytics.gold.transactions
PARTITION (region = 'US');

-- Add entire schema
ALTER SHARE sales_data ADD SCHEMA analytics.gold;
```

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sharing import (
    SharedDataObject,
    SharedDataObjectUpdate,
    SharedDataObjectUpdateAction,
)

w = WorkspaceClient()

# Create share
share = w.shares.create(
    name="customer_insights",
    comment="Customer analytics data for partners"
)

# Add table to share (must wrap in SharedDataObjectUpdate with action)
w.shares.update(
    name="customer_insights",
    updates=[
        SharedDataObjectUpdate(
            action=SharedDataObjectUpdateAction.ADD,
            data_object=SharedDataObject(
                name="analytics.gold.customers",
                data_object_type="TABLE",
                comment="Customer master data"
            ),
        )
    ],
)

# Add table with alias
w.shares.update(
    name="customer_insights",
    updates=[
        SharedDataObjectUpdate(
            action=SharedDataObjectUpdateAction.ADD,
            data_object=SharedDataObject(
                name="analytics.gold.customer_360",
                data_object_type="TABLE",
                shared_as="shared_data.customer_summary"
            ),
        )
    ],
)
```

**CLI:**
```bash
# Create share
databricks shares create customer_insights --comment "Customer data for partners"

# Update share with tables
databricks shares update customer_insights --json '{
    "updates": [
        {
            "action": "ADD",
            "data_object": {
                "name": "analytics.gold.customers",
                "data_object_type": "TABLE"
            }
        }
    ]
}'

# List shares
databricks shares list

# Get share details
databricks shares get customer_insights
```

### Manage Shares

**SQL:**
```sql
-- List all shares
SHOW SHARES;

-- Describe share metadata
DESCRIBE SHARE customer_insights;

-- List all objects in share
SHOW ALL IN SHARE customer_insights;

-- Remove table from share
ALTER SHARE sales_data REMOVE TABLE analytics.gold.old_table;

-- Delete share
DROP SHARE old_share;
```

**Python SDK:**
```python
# List all shares
for share in w.shares.list_shares():
    print(f"{share.name}: {share.comment}")

# Get share details
share = w.shares.get("customer_insights")
for obj in share.objects:
    print(f"  {obj.name}: {obj.data_object_type}")

# Delete share
w.shares.delete("old_share")
```

---

## Managing Recipients

### Create Recipients

**SQL:**
```sql
-- Create recipient (TOKEN auth, default for external partners)
CREATE RECIPIENT IF NOT EXISTS partner_analytics
COMMENT 'External analytics partner';

-- Create recipient for Databricks-to-Databricks sharing
CREATE RECIPIENT partner_databricks
USING ID 'aws:us-west-2:abc12345-6789-0def-ghij-klmnopqrstuv'
COMMENT 'Partner Databricks workspace';
```

> IP access lists for recipients are managed via SDK/API, not SQL.

**Python SDK:**
```python
from databricks.sdk.service.sharing import AuthenticationType

# Create recipient
recipient = w.recipients.create(
    name="partner_analytics",
    comment="External analytics partner",
    authentication_type=AuthenticationType.TOKEN
)

# Get activation link (one-time use)
print(f"Activation link: {recipient.activation_link}")

# Create recipient with IP ACL
recipient = w.recipients.create(
    name="secure_partner",
    comment="Partner with IP restrictions",
    ip_access_list={
        "allowed_ip_addresses": ["10.0.0.0/8", "192.168.1.0/24"]
    }
)
```

**CLI:**
```bash
# Create recipient
databricks recipients create partner_analytics --comment "External partner"

# List recipients
databricks recipients list

# Get recipient details (includes activation link if not activated)
databricks recipients get partner_analytics
```

### Grant Share to Recipient

**SQL:**
```sql
-- Grant share access to recipient
GRANT SELECT ON SHARE customer_insights TO RECIPIENT partner_analytics;

-- Grant multiple shares
GRANT SELECT ON SHARE sales_data TO RECIPIENT partner_analytics;
GRANT SELECT ON SHARE product_catalog TO RECIPIENT partner_analytics;

-- Revoke access
REVOKE SELECT ON SHARE customer_insights FROM RECIPIENT partner_analytics;
```

**Python SDK:**
```python
from databricks.sdk.service.catalog import PermissionsChange, Privilege

# Grant share to recipient
w.shares.update_permissions(
    name="customer_insights",
    changes=[
        PermissionsChange(
            principal="partner_analytics",
            add=[Privilege.SELECT]
        )
    ]
)

# Get share permissions
perms = w.shares.share_permissions(name="customer_insights")
for p in perms.privilege_assignments:
    print(f"{p.principal}: {p.privileges}")
```

### Recipient Activation

After creating a recipient, share the activation link with them.

```python
# Get activation link
recipient = w.recipients.get("partner_analytics")
if recipient.activation_url:
    print(f"Send this to partner: {recipient.activation_url}")
else:
    print("Recipient already activated")

# Check activation status
print(f"Activated: {recipient.activated}")
print(f"Activation time: {recipient.activated_time}")
```

### Rotate Recipient Token

> Token rotation is managed via SDK or CLI (not SQL).

**Python SDK:**
```python
# Rotate token (invalidates old token, generates new activation link)
w.recipients.rotate_token("partner_analytics")
```

**CLI:**
```bash
databricks recipients rotate-token partner_analytics
```

---

## Provider Management

### Consuming Shared Data (as Recipient)

On the recipient side, after activation:

**SQL:**
```sql
-- Create provider (represents the sharer)
CREATE PROVIDER acme_corp
COMMENT 'ACME Corporation data provider';

-- Create catalog from share
CREATE CATALOG acme_data
USING PROVIDER acme_corp
SHARE customer_insights
COMMENT 'Data from ACME';

-- Query shared data
SELECT * FROM acme_data.shared_data.customers LIMIT 10;
```

**Python SDK:**
```python
# Create provider
provider = w.providers.create(
    name="acme_corp",
    comment="ACME Corporation data provider"
)

# List available shares from provider
for share in w.providers.list_shares("acme_corp"):
    print(f"{share.name}")
```

### List Providers

**SQL:**
```sql
-- List providers
SHOW PROVIDERS;

-- Describe provider
DESCRIBE PROVIDER acme_corp;

-- List shares from provider
SHOW SHARES IN PROVIDER acme_corp;
```

---

## Share Permissions

### Grant Permissions on Shares

**SQL:**
```sql
-- Grant ability to create shares
GRANT CREATE SHARE ON METASTORE TO `data_stewards`;

-- Grant ability to create recipients
GRANT CREATE RECIPIENT ON METASTORE TO `data_stewards`;

-- Grant ownership of share
ALTER SHARE customer_insights SET OWNER TO `data_governance_team`;
```

---

## Monitoring Shares

### Query Share Usage

**SQL:**
```sql
-- Check share access logs (if audit logging enabled)
SELECT
    event_time,
    user_identity.email AS accessor,
    action_name,
    request_params
FROM system.access.audit
WHERE action_name LIKE '%share%'
  AND event_date >= current_date() - 30
ORDER BY event_time DESC;

-- List recipients and their status
SELECT
    r.name AS recipient_name,
    r.activated,
    r.comment
FROM system.information_schema.recipients r;
```

### Share Information

**SQL:**
```sql
-- Share details
SELECT * FROM system.information_schema.shares;

-- Share objects
SELECT
    share_name,
    name AS object_name,
    data_object_type,
    shared_as
FROM system.information_schema.shared_data_objects
WHERE share_name = 'customer_insights';

-- Recipient grants
SELECT
    share_name,
    recipient_name,
    privilege
FROM system.information_schema.share_recipients;
```

---

## Clean Rooms

Privacy-preserving analytics without sharing raw data.

> Clean rooms are managed via SDK, CLI, or UI (not SQL).

### Manage Clean Rooms

**Python SDK:**
```python
# Create clean room
room = w.clean_rooms.create(
    name="joint_analytics",
    comment="Joint analytics with partner"
)

# List clean rooms
for room in w.clean_rooms.list():
    print(f"{room.name}: {room.comment}")

# Add table asset to clean room
from databricks.sdk.service.cleanrooms import CleanRoomAsset, CleanRoomAssetAssetType

w.clean_room_assets.create(
    clean_room_name="joint_analytics",
    asset=CleanRoomAsset(
        name="shared_catalog.shared_schema.customers",
        asset_type=CleanRoomAssetAssetType.TABLE
    )
)

# Add notebook asset
w.clean_room_assets.create(
    clean_room_name="joint_analytics",
    asset=CleanRoomAsset(
        name="approved_analysis",
        asset_type=CleanRoomAssetAssetType.NOTEBOOK
    )
)

# List assets in clean room
for asset in w.clean_room_assets.list(clean_room_name="joint_analytics"):
    print(f"{asset.name}: {asset.asset_type}")
```

---

## Best Practices

### Shares
1. **Meaningful names**: `{domain}_{purpose}` like `sales_partner_analytics`
2. **Use aliases**: Hide internal naming from recipients
3. **Partition filtering**: Share only relevant data
4. **Regular review**: Audit what's shared quarterly

### Recipients
1. **IP restrictions**: Use for sensitive data
2. **Token rotation**: Rotate annually or after personnel changes
3. **Track activation**: Monitor for unused recipients
4. **Document purpose**: Comment explaining the relationship

### Security
1. **Least privilege**: Share minimum necessary tables/columns
2. **No PII without masking**: Apply column masks before sharing
3. **Audit access**: Monitor recipient queries
4. **Revoke promptly**: When partnerships end

### Data Quality
1. **Document data**: Ensure recipients understand the schema
2. **Versioning**: Communicate breaking changes
3. **SLAs**: Define update frequency
4. **Support channel**: Provide contact for questions

---

## Complete Example

```sql
-- 1. Create share
CREATE SHARE partner_retail_data
COMMENT 'Retail analytics for Partner Corp';

-- 2. Add tables with proper aliases
ALTER SHARE partner_retail_data
ADD TABLE analytics.gold.daily_sales
AS retail.sales_summary;

ALTER SHARE partner_retail_data
ADD TABLE analytics.gold.product_catalog
AS retail.products
PARTITION (category IN ('electronics', 'clothing'));

-- 3. Create recipient
CREATE RECIPIENT partner_corp
COMMENT 'Partner Corporation - Contact: partner@corp.com';

-- 4. Grant access
GRANT SELECT ON SHARE partner_retail_data TO RECIPIENT partner_corp;

-- 5. Get activation link
DESCRIBE RECIPIENT partner_corp;
-- Share the activation_link with partner

-- 6. Monitor usage
SELECT * FROM system.access.audit
WHERE action_name LIKE '%share%'
  AND request_params['share_name'] = 'partner_retail_data';
```
