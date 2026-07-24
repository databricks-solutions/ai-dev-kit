# External Engine Interoperability

This file covers connecting external engines to Databricks via the Iceberg REST Catalog (IRC). Each engine section includes the minimum configuration needed to read (and where supported, write) Databricks-managed Iceberg tables.

**Prerequisites for all engines**:
- Databricks workspace with external data access enabled
- `EXTERNAL USE SCHEMA` granted on target schemas
- PAT or OAuth (service principal) credentials for authentication with the required permissions.
- **Network access**: The client must reach the Databricks workspace on HTTPS (port 443). If workspace **IP access lists** are enabled, add the client's egress CIDR to the allowlist — this is a common setup issue that blocks connectivity even when credentials and grants are correct.

See [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md) for IRC endpoint details.

---

## PyIceberg

PyIceberg is a Python library for reading and writing Iceberg tables without Spark.

### Installation

Upgrade both packages explicitly — if `pyarrow` (v15) is too old, it causes write errors. Also install `adlfs` for Azure storage access:

```bash
pip install --upgrade "pyiceberg>=0.9,<0.10" "pyarrow>=17,<20"
pip install adlfs
```

For non-Databricks environments:

```bash
pip install "pyiceberg[pyarrow]>=0.9"
```

### Connect to Catalog

The `warehouse` parameter pins the catalog, so all subsequent table identifiers use `<schema>.<table>` (not `<catalog>.<schema>.<table>`):

```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "uc",
    uri="https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest",
    warehouse="<uc-catalog-name>",  # Unity Catalog catalog name
    token="<pat-token>",
)
```

### Read Table

```python
# Load table — identifier is <schema>.<table> because 'warehouse' pins the UC catalog
tbl = catalog.load_table("<schema>.<table>")

# Inspect schema and current snapshot
print(tbl)                    # schema, partitioning, snapshot summary
print(tbl.current_snapshot()) # snapshot metadata

# Read sample rows
df = tbl.scan(limit=10).to_pandas()
print(df.head())

# Pushdown filter (SQL-style filter strings are supported)
df = tbl.scan(
    row_filter="event_date >= '2025-01-01'",
    limit=1000,
).to_pandas()

# Read as Arrow
arrow_table = tbl.scan().to_arrow()
```

### Append Data

```python
import pyarrow as pa
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "uc",
    uri="https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest",
    warehouse="<uc-catalog-name>",
    token="<pat-token>",
)

tbl = catalog.load_table("<schema>.<table>")

# Schema must match the Iceberg table schema exactly — use explicit Arrow types
# PyArrow defaults to int64; if the Iceberg table uses int (32-bit), cast explicitly
arrow_schema = pa.schema([
    pa.field("id",   pa.int32()),
    pa.field("name", pa.string()),
    pa.field("qty",  pa.int32()),
])

rows = [
    {"id": 1, "name": "foo", "qty": 10},
    {"id": 2, "name": "bar", "qty": 20},
]
arrow_tbl = pa.Table.from_pylist(rows, schema=arrow_schema)

tbl.append(arrow_tbl)

# Verify
print("Current snapshot:", tbl.current_snapshot())
```

---

## OSS Apache Spark

> **CRITICAL**: Only configure this **outside** Databricks Runtime. Inside DBR, use the built-in Iceberg support — do NOT install the Iceberg library.

### Dependencies

Two JARs are required: the Spark runtime and a cloud-specific bundle for object storage access. Choose the bundle matching your Databricks metastore's cloud:

| Cloud | Bundle |
|-------|--------|
| AWS | `org.apache.iceberg:iceberg-aws-bundle:<version>` |
| Azure | `org.apache.iceberg:iceberg-azure-bundle:<version>` |
| GCP | `org.apache.iceberg:iceberg-gcp-bundle:<version>` |

### Spark Session Configuration

The Databricks docs recommend OAuth2 (service principal) for external Spark connections. Set `rest.auth.type=oauth2` and provide the OAuth2 server URI, credential, and scope:

```python
from pyspark.sql import SparkSession

WORKSPACE_URL       = "https://<workspace-url>"
UC_CATALOG_NAME     = "<uc-catalog-name>"
OAUTH_CLIENT_ID     = "<oauth-client-id>"
OAUTH_CLIENT_SECRET = "<oauth-client-secret>"
CATALOG_ALIAS       = "uc"    # arbitrary name used to reference this catalog in Spark SQL
ICEBERG_VER         = "1.7.1"

RUNTIME      = f"org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:{ICEBERG_VER}"
CLOUD_BUNDLE = f"org.apache.iceberg:iceberg-aws-bundle:{ICEBERG_VER}"   # or azure/gcp-bundle

spark = (
    SparkSession.builder
    .appName("uc-iceberg")
    .config("spark.jars.packages", f"{RUNTIME},{CLOUD_BUNDLE}")
    .config("spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}",
            "org.apache.iceberg.spark.SparkCatalog")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.type", "rest")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.rest.auth.type", "oauth2")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.uri",
            f"{WORKSPACE_URL}/api/2.1/unity-catalog/iceberg-rest")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.oauth2-server-uri",
            f"{WORKSPACE_URL}/oidc/v1/token")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.credential",
            f"{OAUTH_CLIENT_ID}:{OAUTH_CLIENT_SECRET}")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.scope", "all-apis")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.warehouse", UC_CATALOG_NAME)
    .getOrCreate()
)

# List schemas
spark.sql(f"SHOW NAMESPACES IN {CATALOG_ALIAS}").show(truncate=False)

# Query
spark.sql(f"SELECT * FROM {CATALOG_ALIAS}.<schema>.<table>").show()

# Write (managed Iceberg tables only)
df.writeTo(f"{CATALOG_ALIAS}.<schema>.<table>").append()
```

### Spark SQL

```sql
-- List schemas
SHOW NAMESPACES IN uc;

-- Query
SELECT * FROM uc.<schema>.<table>;

-- Insert
INSERT INTO uc.<schema>.<table> VALUES (1, 'foo', 10);
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Connection timeout or `403 Forbidden` with valid credentials** | Workspace IP access list is blocking the client — add the client's egress CIDR to the allowlist (admin console: **Settings → Security → IP access list**) |
| **`403 Forbidden`** | Check `EXTERNAL USE SCHEMA` grant and token validity |
| **`Table not found`** | Verify the `warehouse` config matches the UC catalog name; check schema and table names |
| **Class conflict in DBR** | You installed an Iceberg library in Databricks Runtime — remove it; DBR has built-in support |
| **Credential vending failure** | Ensure external data access is enabled on the workspace |
| **Slow reads** | Check if table needs compaction (`OPTIMIZE`); large numbers of small files degrade performance |
| **v3 table incompatibility** | Upgrade to Iceberg library 1.9.0+ for v3 support; older versions cannot read v3 tables |
| **PyArrow schema mismatch** | Cast to explicit types (e.g., `pa.int32()`) when the Iceberg table schema uses 32-bit integers |
| **PyIceberg write error on serverless** | Upgrade pyarrow (`>=17`) and install `adlfs` — the bundled pyarrow v15 is incompatible |

---

## Related

- [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md) — IRC endpoint details, auth, credential vending
- [4-snowflake-interop.md](4-snowflake-interop.md) — Snowflake-specific integration
