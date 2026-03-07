# Setup and Authentication

Complete setup guide for Zerobus Ingest: endpoint configuration, service principal creation, table preparation, SDK installation, and firewall requirements.

---

## 1. Determine Your Server Endpoint

The Zerobus server endpoint format depends on your cloud provider:

| Cloud | Server Endpoint Format | Workspace URL Format |
|-------|------------------------|----------------------|
| **AWS** | `<workspace-id>.zerobus.<region>.cloud.databricks.com` | `https://<instance>.cloud.databricks.com` |
| **Azure** | `<workspace-id>.zerobus.<region>.azuredatabricks.net` | `https://<instance>.azuredatabricks.net` |

**Example (AWS):**
```
Server endpoint: 1234567890123456.zerobus.us-west-2.cloud.databricks.com
Workspace URL:   https://dbc-a1b2c3d4-e5f6.cloud.databricks.com
```

**Finding your workspace ID:** Extract the numeric ID from your workspace URL or workspace settings page. It is the first segment of the server endpoint.

---

## 2. Create the Target Table

Zerobus does **not** create or alter tables. You must pre-create your target table as a **managed Delta table** in Unity Catalog:

```sql
CREATE TABLE catalog.schema.my_events (
    event_id     STRING,
    device_name  STRING,
    temp         INT,
    humidity     LONG,
    event_time   TIMESTAMP
);
```

**Constraints:**
- Must be a **managed** Delta table (no external storage)
- Table names limited to ASCII letters, digits, and underscores
- Maximum 2000 columns
- Table must be in a [supported region](#supported-regions)

---

## 3. Create a Service Principal

Zerobus authenticates via OAuth2 service principals (M2M). Create one via the Databricks UI or CLI:

### Via UI
1. Go to **Settings > Identity and Access > Service principals**
2. Click **Add service principal**
3. Generate an OAuth secret: note the **client ID** and **client secret**

### Via Databricks CLI
```bash
databricks service-principals create --display-name "zerobus-producer"
```

### Grant Table Permissions

The service principal needs catalog, schema, and table access:

```sql
-- Grant catalog access
GRANT USE CATALOG ON CATALOG my_catalog TO `<service-principal-uuid>`;

-- Grant schema access
GRANT USE SCHEMA ON SCHEMA my_catalog.my_schema TO `<service-principal-uuid>`;

-- Grant table write access
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.my_events TO `<service-principal-uuid>`;
```

**Tip:** For broader access (e.g., writing to multiple tables in a schema), grant `MODIFY` and `SELECT` at the schema level instead.

---

## 4. Install the SDK

### Python (3.9+)

```bash
pip install databricks-zerobus-ingest-sdk
```

Or with a virtual environment:
```bash
uv pip install databricks-zerobus-ingest-sdk
```

### Java (8+)

Maven:
```xml
<dependency>
    <groupId>com.databricks</groupId>
    <artifactId>zerobus-ingest-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

Gradle:
```groovy
implementation 'com.databricks:zerobus-ingest-sdk:0.1.0'
```

### Go (1.21+)

```bash
go get github.com/databricks/zerobus-sdk-go
```

### TypeScript / Node.js (16+)

```bash
npm install @databricks/zerobus-ingest-sdk
```

### Rust (1.70+)

```bash
cargo add databricks-zerobus-ingest-sdk
cargo add tokio --features macros,rt-multi-thread
```

---

## 5. Configure Environment Variables

Store credentials as environment variables rather than hardcoding them:

```bash
export ZEROBUS_SERVER_ENDPOINT="1234567890123456.zerobus.us-west-2.cloud.databricks.com"
export DATABRICKS_WORKSPACE_URL="https://dbc-a1b2c3d4-e5f6.cloud.databricks.com"
export ZEROBUS_TABLE_NAME="my_catalog.my_schema.my_events"
export DATABRICKS_CLIENT_ID="<service-principal-client-id>"
export DATABRICKS_CLIENT_SECRET="<service-principal-client-secret>"
```

---

## 6. Firewall Allowlisting

If your client application sits behind a firewall, you must allowlist the Zerobus IP addresses for your region before testing connectivity. Contact your Databricks representative or consult the [Zerobus documentation](https://docs.databricks.com/aws/en/ingestion/zerobus-overview) for the current IP ranges.

---

## Supported Regions

Workspace and target tables must reside in a supported region for your cloud provider.

### AWS

| Region Code | Location |
|-------------|----------|
| `us-east-1` | US East (N. Virginia) |
| `us-east-2` | US East (Ohio) |
| `us-west-2` | US West (Oregon) |
| `eu-central-1` | Europe (Frankfurt) |
| `eu-west-1` | Europe (Ireland) |
| `ap-southeast-1` | Asia Pacific (Singapore) |
| `ap-southeast-2` | Asia Pacific (Sydney) |
| `ap-northeast-1` | Asia Pacific (Tokyo) |
| `ca-central-1` | Canada (Central) |

### Azure

| Region Code | Location |
|-------------|----------|
| `canadacentral` | Canada Central |
| `westus` | West US |
| `eastus` | East US |
| `eastus2` | East US 2 |
| `centralus` | Central US |
| `northcentralus` | North Central US |
| `swedencentral` | Sweden Central |
| `westeurope` | West Europe |
| `northeurope` | North Europe |
| `australiaeast` | Australia East |
| `southeastasia` | Southeast Asia |

---

## Verification Checklist

Before writing your first record, confirm:

```
- [ ] Server endpoint matches your cloud provider and region
- [ ] Workspace URL is correct
- [ ] Target table exists as a managed Delta table
- [ ] Service principal has USE CATALOG, USE SCHEMA, MODIFY, SELECT grants
- [ ] SDK is installed for your target language
- [ ] Environment variables are set (or credentials are configured in code)
- [ ] Firewall allows outbound connections to the Zerobus endpoint (if applicable)
```
