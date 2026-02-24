# Creating Genie Spaces

This guide covers creating and managing Genie Spaces for SQL-based data exploration.

## What is a Genie Space?

A Genie Space connects to Unity Catalog tables and translates natural language questions into SQL queries. The system:

1. **Understands** the table schemas and relationships
2. **Generates** SQL queries from natural language
3. **Executes** queries on a SQL warehouse
4. **Presents** results in a conversational format

## Creation Workflow

### Step 1: Inspect Table Schemas (Required)

**Before creating a Genie Space, you MUST inspect the table schemas** to understand what data is available:

```python
get_table_details(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="SIMPLE"
)
```

This returns:
- Table names and row counts
- Column names and data types
- Sample values and cardinality
- Null counts and statistics

### Step 2: Analyze and Plan

Based on the schema information:

1. **Select relevant tables** - Choose tables that support the user's use case
2. **Identify key columns** - Note date columns, metrics, dimensions, and foreign keys
3. **Understand relationships** - How do tables join together?
4. **Plan sample questions** - What questions can this data answer?

### Step 3: Create the Genie Space

Create the space with content tailored to the actual data:

```python
create_or_update_genie(
    display_name="Sales Analytics",
    table_identifiers=[
        "my_catalog.sales.customers",
        "my_catalog.sales.orders",
        "my_catalog.sales.products"
    ],
    description="""Explore retail sales data with three related tables:
- customers: Customer demographics including region, segment, and signup date
- orders: Transaction history with order_date, total_amount, and status
- products: Product catalog with category, price, and inventory

Tables join on customer_id and product_id.""",
    sample_questions=[
        "What were total sales last month?",
        "Who are our top 10 customers by total_amount?",
        "How many orders were placed in Q4 by region?",
        "What's the average order value by customer segment?",
        "Which product categories have the highest revenue?",
        "Show me customers who haven't ordered in 90 days"
    ]
)
```

## Why This Workflow Matters

**Sample questions that reference actual column names** help Genie:
- Learn the vocabulary of your data
- Generate more accurate SQL queries
- Provide better autocomplete suggestions

**A description that explains table relationships** helps Genie:
- Understand how to join tables correctly
- Know which table contains which information
- Provide more relevant answers

## Auto-Detection of Warehouse

When `warehouse_id` is not specified, the tool:

1. Lists all SQL warehouses in the workspace
2. Prioritizes by:
   - **Running** warehouses first (already available)
   - **Starting** warehouses second
   - **Smaller sizes** preferred (cost-efficient)
3. Returns an error if no warehouses exist

To use a specific warehouse, provide the `warehouse_id` explicitly.

## Table Selection

Choose tables carefully for best results:

| Layer | Recommended | Why |
|-------|-------------|-----|
| Bronze | No | Raw data, may have quality issues |
| Silver | Yes | Cleaned and validated |
| Gold | Yes | Aggregated, optimized for analytics |

### Tips for Table Selection

- **Include related tables**: If users ask about customers and orders, include both
- **Use descriptive column names**: `customer_name` is better than `cust_nm`
- **Add table comments**: Genie uses metadata to understand the data

## Sample Questions

Sample questions help users understand what they can ask:

**Good sample questions:**
- "What were total sales last month?"
- "Who are our top 10 customers by revenue?"
- "How many orders were placed in Q4?"
- "What's the average order value by region?"

These appear in the Genie UI to guide users.

## Best Practices

### Table Design for Genie

1. **Descriptive names**: Use `customer_lifetime_value` not `clv`
2. **Add comments**: `COMMENT ON TABLE sales.customers IS 'Customer master data'`
3. **Primary keys**: Define relationships clearly
4. **Date columns**: Include proper date/timestamp columns for time-based queries

### Description and Context

Provide context in the description:

```
Explore retail sales data from our e-commerce platform. Includes:
- Customers: demographics, segments, and account status
- Orders: transaction history with amounts and dates
- Products: catalog with categories and pricing

Time range: Last 6 months of data
```

### Sample Questions

Write sample questions that:
- Cover common use cases
- Demonstrate the data's capabilities
- Use natural language (not SQL terms)

## Updating a Genie Space

To update an existing space:

1. **Add/remove tables**: Call `create_or_update_genie` with updated `table_identifiers`
2. **Update questions**: Include new `sample_questions`
3. **Change warehouse**: Provide a different `warehouse_id`

The tool finds the existing space by name and updates it.

## Example End-to-End Workflow

1. **Generate synthetic data** using `databricks-synthetic-data-generation` skill:
   - Creates parquet files in `/Volumes/catalog/schema/raw_data/`

2. **Create tables** using `databricks-spark-declarative-pipelines` skill:
   - Creates `catalog.schema.bronze_*` → `catalog.schema.silver_*` → `catalog.schema.gold_*`

3. **Inspect the tables**:
   ```python
   get_table_details(catalog="catalog", schema="schema")
   ```

4. **Create the Genie Space**:
   - `display_name`: "My Data Explorer"
   - `table_identifiers`: `["catalog.schema.silver_customers", "catalog.schema.silver_orders"]`

5. **Add sample questions** based on actual column names

6. **Test** in the Databricks UI

## Troubleshooting

### No warehouse available

- Create a SQL warehouse in the Databricks workspace
- Or provide a specific `warehouse_id`

### Queries are slow

- Ensure the warehouse is running (not stopped)
- Consider using a larger warehouse size
- Check if tables are optimized (OPTIMIZE, Z-ORDER)

### Poor query generation

- Use descriptive column names
- Add table and column comments
- Include sample questions that demonstrate the vocabulary
- Add instructions via the Databricks Genie UI

---

## Advanced: serialized_space API

The `create_or_update_genie` tool only populates the basic sections. To fully configure a Genie Space (General Instructions, SQL Queries & Functions, Common SQL Expressions, Benchmarks), use the `serialized_space` API directly.

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/2.0/genie/spaces/{id}?include_serialized_space=true` | Full space with serialized_space JSON |
| `GET` | `/api/2.0/genie/spaces/{id}` | Basic space (no serialized_space) |
| `PATCH` | `/api/2.0/genie/spaces/{id}` | Update serialized_space (**this works**) |
| `PATCH` | `/api/2.0/data-rooms/{id}` | Update description/warehouse/tables only (NOT serialized_space) |

> **Critical**: `PATCH /api/2.0/data-rooms/{id}` silently empties `table_identifiers` if not re-sent. Always include all table identifiers in every call.
>
> `PUT /api/2.0/genie/spaces/{id}` does NOT exist (returns 404).

### serialized_space JSON Schema

```json
{
  "version": 2,
  "config": {
    "sample_questions": [{"id": "hex32chars", "question": ["question text"]}]
  },
  "data_sources": {
    "tables": [{"identifier": "catalog.schema.table", "description": ["optional context"]}]
  },
  "instructions": {
    "text_instructions": [{"id": "hex32chars", "content": ["Combined instructions string"]}],
    "example_question_sqls": [{"id": "hex32chars", "question": ["Question?"], "sql": ["SELECT ..."]}],
    "join_specs": [
      {
        "id": "hex32chars",
        "left":  {"identifier": "catalog.schema.table_a", "alias": "table_a"},
        "right": {"identifier": "catalog.schema.table_b", "alias": "table_b"},
        "sql": [
          "`table_a`.`key_col` = `table_b`.`key_col`",
          "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--"
        ],
        "instruction": ["Human-readable description of why this join is used"]
      }
    ],
    "sql_snippets": {
      "filters": [{"id": "hex32chars", "sql": ["filter_expr"], "display_name": "label"}],
      "expressions": [{"id": "hex32chars", "alias": "alias", "sql": ["SQL expr"]}],
      "measures": [{"id": "hex32chars", "alias": "measure", "sql": ["AGG expr"]}]
    }
  },
  "benchmarks": {
    "questions": [
      {"id": "hex32chars", "question": ["Business question?"],
       "answer": [{"format": "SQL", "content": ["SELECT ..."]}]}
    ]
  }
}
```

### Known Constraints

- **`text_instructions`**: Maximum **1 item**. Combine all instructions into a single `content` string.
- **All lists must be sorted by `id`** (lexicographic hex sort). The API returns 400 if not sorted.
- **`data_sources.tables` must be sorted by `identifier`** alphabetically.
- **`join_specs`**: Supported. See dedicated section below for exact format. The `sql` field takes **backtick-quoted `alias`.`COL`** syntax (NOT plain `table.column`) and a second element with the cardinality marker.
- IDs must be 32-char hex strings: `uuid.uuid4().hex`.

### join_specs: Format and Code Example

The `join_specs` section populates the **Joins** tab in the Genie UI. Each spec defines a relationship between two tables, and Genie uses them to build JOINs automatically.

#### Exact structure (reverse-engineered from Genie UI)

```json
{
  "id": "hex32chars",
  "left":  {"identifier": "catalog.schema.table_a", "alias": "table_a"},
  "right": {"identifier": "catalog.schema.table_b", "alias": "table_b"},
  "sql": [
    "`table_a`.`CLAVE_BODEGA` = `table_b`.`CLAVE_BODEGA` AND `table_a`.`CLAVE_CLIENTE` = `table_b`.`CLAVE_CLIENTE`",
    "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--"
  ],
  "instruction": ["Join to get all transactions for each client"]
}
```

**Key fields:**

| Field | Required | Notes |
|---|---|---|
| `left.identifier` | Yes | Full `catalog.schema.table` |
| `left.alias` | Yes | Table name only (last segment after `.`) |
| `right.identifier` / `right.alias` | Yes | Same as left |
| `sql[0]` | Yes | Join condition using **`` `alias`.`COLUMN` ``** format with backticks |
| `sql[1]` | Yes | Cardinality marker string (see below) |
| `instruction` | Yes | List with 1 string: description of the join |

**Cardinality markers (`sql[1]`):**

```
--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--
--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--
--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--
--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--
```

> **Why it failed before**: We tried plain SQL like `table.col = table.col` — the API requires `` `alias`.`col` `` with backticks, plus the cardinality marker as a second `sql` element.

#### Helper function

```python
RT_ONE_TO_ONE   = "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--"
RT_ONE_TO_MANY  = "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--"
RT_MANY_TO_ONE  = "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"
RT_MANY_TO_MANY = "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--"

def make_join(left_id, right_id, col_pairs, cardinality, instruction):
    """
    col_pairs: list of (left_col, right_col) tuples
    Uses the short table name (after last dot) as alias.
    """
    left_alias  = left_id.split(".")[-1]
    right_alias = right_id.split(".")[-1]
    cond = " AND ".join(
        f"`{left_alias}`.`{lc}` = `{right_alias}`.`{rc}`"
        for lc, rc in col_pairs
    )
    return {
        "id": uid(),
        "left":  {"identifier": left_id,  "alias": left_alias},
        "right": {"identifier": right_id, "alias": right_alias},
        "sql": [cond, cardinality],
        "instruction": [instruction],
    }

# Example usage:
join_specs = sorted([
    make_join(
        "catalog.schema.dim_customer",
        "catalog.schema.fact_orders",
        [("customer_id", "customer_id")],
        RT_ONE_TO_MANY,
        "Join to get all orders for each customer"
    ),
    make_join(
        "catalog.schema.fact_orders",
        "catalog.schema.fact_order_items",
        [("order_id", "order_id")],
        RT_ONE_TO_MANY,
        "Join to get line items for each order"
    ),
], key=lambda x: x["id"])  # MUST be sorted by id
```

### How to Apply serialized_space

```python
import requests, json, uuid

WORKSPACE_URL = "https://adb-XXXXXXXXXXXXXXXXX.XX.azuredatabricks.net"
TOKEN = "your_token"
SPACE_ID = "your_space_id"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def uid():
    return uuid.uuid4().hex

# 1. Fetch existing data to preserve sample_questions and tables
resp = requests.get(
    f"{WORKSPACE_URL}/api/2.0/genie/spaces/{SPACE_ID}?include_serialized_space=true",
    headers=HEADERS
)
existing_ss = json.loads(resp.json()["serialized_space"])

# 2. Build serialized_space
serialized_space = {
    "version": 2,
    "config": {
        "sample_questions": sorted(existing_ss["config"]["sample_questions"], key=lambda x: x["id"])
    },
    "data_sources": {
        "tables": sorted(existing_ss["data_sources"]["tables"], key=lambda t: t["identifier"])
    },
    "instructions": {
        # Only 1 text_instructions item allowed — combine all general instructions
        "text_instructions": [{"id": uid(), "content": [
            "TERMINOLOGY: 'active customers' = status = 2.\n\n"
            "CURRENT STATE: Always filter with MAX(date_col) for snapshots."
        ]}],
        "example_question_sqls": sorted([
            {"id": uid(), "question": ["How many active customers?"],
             "sql": ["SELECT COUNT(*) FROM catalog.schema.customers WHERE status = 2"]}
        ], key=lambda x: x["id"]),
        "join_specs": sorted([
            make_join(
                "catalog.schema.dim_customer",
                "catalog.schema.fact_orders",
                [("customer_id", "customer_id")],
                RT_ONE_TO_MANY,
                "Join to get all orders for each customer"
            ),
        ], key=lambda x: x["id"]),
        "sql_snippets": {
            "filters": sorted([
                {"id": uid(), "sql": ["status = 2"], "display_name": "active customers"}
            ], key=lambda x: x["id"]),
            "expressions": sorted([
                {"id": uid(), "alias": "current_date_filter",
                 "sql": ["(SELECT MAX(date_col) FROM catalog.schema.table)"]}
            ], key=lambda x: x["id"]),
            "measures": sorted([
                {"id": uid(), "alias": "completion_rate",
                 "sql": ["ROUND(100.0 * SUM(completed) / COUNT(*), 1)"]}
            ], key=lambda x: x["id"]),
        }
    },
    "benchmarks": {
        "questions": sorted([
            {"id": uid(), "question": ["How many active customers?"],
             "answer": [{"format": "SQL", "content": [
                 "SELECT COUNT(*) FROM catalog.schema.table WHERE status = 2"
             ]}]}
        ], key=lambda x: x["id"])
    }
}

# 3. Apply via PATCH (400 if lists not sorted by id)
response = requests.patch(
    f"{WORKSPACE_URL}/api/2.0/genie/spaces/{SPACE_ID}",
    headers=HEADERS,
    json={"serialized_space": json.dumps(serialized_space)}
)
print(response.status_code)  # 200 = success
```

### UI Section Mapping

| serialized_space section | Genie UI section |
|---|---|
| `instructions.text_instructions` | General Instructions |
| `instructions.join_specs` | Joins |
| `instructions.example_question_sqls` | SQL queries & functions |
| `instructions.sql_snippets.filters` | Common SQL Expressions > Filters |
| `instructions.sql_snippets.expressions` | Common SQL Expressions > Expressions |
| `instructions.sql_snippets.measures` | Common SQL Expressions > Measures |
| `benchmarks.questions` | Benchmarks |
| `config.sample_questions` | Sample Questions (homepage) |
