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

1. **Generate synthetic data** using `synthetic-data-generation` skill:
   - Creates parquet files in `/Volumes/catalog/schema/raw_data/`

2. **Create tables** using `spark-declarative-pipelines` skill:
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
