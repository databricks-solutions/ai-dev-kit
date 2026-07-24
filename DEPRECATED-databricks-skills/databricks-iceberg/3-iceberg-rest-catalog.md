# Iceberg REST Catalog (IRC)

The Iceberg REST Catalog (IRC) is a REST API endpoint that lets external engines read and write Databricks-managed Iceberg data using the standard Apache Iceberg REST Catalog protocol. External tools connect to the IRC endpoint, authenticate, and receive vended credentials for direct cloud storage access.

**Endpoint**: `https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest`

> **Legacy endpoint warning**: The older `/api/2.1/unity-catalog/iceberg` endpoint is in maintenance mode and should not be used for new integrations. It was the original read-only endpoint documented for UniForm. All new integrations — both UniForm (Delta with Iceberg reads) and managed Iceberg tables — must use `/api/2.1/unity-catalog/iceberg-rest`.

**Requirements**: Unity Catalog, external data access enabled on the workspace, DBR 16.1+

---

## Prerequisites

### 1. Enable External Data Access

External data access must be enabled for your workspace. This is typically configured by a workspace admin.

### 2. Network Access to the IRC Endpoint

External engines must reach the Databricks workspace over HTTPS (port 443). If the workspace has **IP access lists** enabled, the CIDR range(s) of the Iceberg client must be explicitly allowed — otherwise connections will fail regardless of correct credentials or grants.

Check and manage IP access lists:
- Admin console: **Settings → Security → IP access list**
- REST API: `GET /api/2.0/ip-access-lists` to inspect, `POST /api/2.0/ip-access-lists` to add ranges

> **Common symptom**: Connections time out or return `403 Forbidden` even with valid credentials and correct grants. IP access list misconfiguration is a frequent root cause — check this before debugging auth.

### 3. Grant EXTERNAL USE SCHEMA

The connecting principal (user or service principal) must have the `EXTERNAL USE SCHEMA` grant on each schema they want to access:

```sql
-- Grant to a user
GRANT EXTERNAL USE SCHEMA ON SCHEMA my_catalog.my_schema TO `user@example.com`;

-- Grant to a service principal
GRANT EXTERNAL USE SCHEMA ON SCHEMA my_catalog.my_schema TO `my-service-principal`;

-- Grant to a group
GRANT EXTERNAL USE SCHEMA ON SCHEMA my_catalog.my_schema TO `data-engineers`;
```

> **Important**: `EXTERNAL USE SCHEMA` is separate from `SELECT` or `MODIFY` grants. A user needs both data permissions AND the external use grant.

---

## Authentication

### Personal Access Token (PAT)

```
Authorization: Bearer <pat-token>
```

### OAuth (M2M)

For service-to-service authentication, use OAuth with a service principal:

1. Create a service principal in the Databricks account
2. Generate an OAuth secret
3. Use the OAuth token endpoint to get an access token
4. Pass the access token as a Bearer token

---

## Read/Write Capability Matrix

| Table Type | IRC Read | IRC Write |
|------------|:-:|:-:|
| Managed Iceberg (`USING ICEBERG`) | Yes | Yes |
| Delta + UniForm | Yes | No |
| Delta + Compatibility Mode | Yes | No |
| Foreign Iceberg Table | No | No |

> **Key insight**: Only managed Iceberg tables support writes via IRC. UniForm and Compatibility Mode tables are read-only because the underlying format is Delta.

---

## Credential Vending

When an external engine connects via IRC, Databricks **vends temporary cloud credentials** (short-lived STS tokens for AWS, SAS tokens for Azure) so the engine can read/write data files directly in cloud storage. This is transparent to the client — the IRC protocol handles it automatically.

Benefits:
- No need to configure cloud credentials in the external engine
- Credentials are scoped to the specific table and operation
- Credentials automatically expire (typically 1 hour)

---

## Common Configuration Reference

| Parameter | Value |
|-----------|-------|
| **Catalog type** | `rest` |
| **URI** | `https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest` |
| **Warehouse** | Unity Catalog catalog name (e.g., `my_catalog`) |
| **Token** | Databricks PAT or OAuth access token |
| **Credential vending** | Automatic (handled by the REST protocol) |


---

## Related

- [4-snowflake-interop.md](4-snowflake-interop.md) — Snowflake reading Databricks via catalog integration (uses IRC)
- [5-external-engine-interop.md](5-external-engine-interop.md) — Per-engine connection configs: PyIceberg, OSS Spark, EMR, Flink, Kafka Connect, DuckDB, Trino
