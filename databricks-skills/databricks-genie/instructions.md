# Genie Instructions, Functions & Benchmarks

Guide to improving Genie Space accuracy with SQL instructions, text rules, certified functions, and benchmark questions.

## When to Use What

| Type | Purpose | Example |
|------|---------|---------|
| **SQL instruction** | Teach Genie how to write a specific query | Computed columns, join patterns, date filters |
| **Text instruction** | Business rules the LLM should follow | "Revenue means net revenue after returns" |
| **SQL function** | Register a UC function as a certified answer | `catalog.schema.calc_churn_rate` |
| **Benchmark** | Validate Genie answers a question correctly | Question + expected SQL pair |
| **Sample question** | Suggest questions in the Genie UI | End-user prompts shown on the space homepage |

## SQL Instructions

SQL instructions teach Genie reusable query patterns. Each has a title (short label) and content (the SQL).

### Computed Columns

```python
manage_genie_instructions(
    action="add_sql",
    space_id="abc123",
    title="Customer Lifetime Value",
    content="""
    SELECT customer_id,
           SUM(order_total) AS lifetime_value
    FROM catalog.sales.orders
    GROUP BY customer_id
    """
)
```

### Join Hints

```python
manage_genie_instructions(
    action="add_sql",
    space_id="abc123",
    title="Orders with Customer Names",
    content="""
    SELECT o.order_id, c.full_name, o.total
    FROM catalog.sales.orders o
    JOIN catalog.sales.customers c ON o.customer_id = c.id
    """
)
```

### Date Filters

```python
manage_genie_instructions(
    action="add_sql",
    space_id="abc123",
    title="Last 30 Days Filter",
    content="SELECT * FROM catalog.sales.orders WHERE order_date >= CURRENT_DATE - INTERVAL 30 DAYS"
)
```

## Text Instructions

Text instructions set business rules and naming conventions that Genie follows when generating SQL.

### Business Logic

```python
manage_genie_instructions(
    action="add_text",
    space_id="abc123",
    title="Revenue Definition",
    content="Revenue always means net revenue (gross - returns - discounts). Never use gross_amount alone."
)
```

### Naming Conventions

```python
manage_genie_instructions(
    action="add_text",
    space_id="abc123",
    title="Column Naming",
    content="When users say 'customer name', use the full_name column, not first_name or last_name separately."
)
```

### Date Defaults

```python
manage_genie_instructions(
    action="add_text",
    space_id="abc123",
    content="When no date range is specified, default to the last 12 months. Use fiscal_year for yearly comparisons."
)
```

## SQL Functions (Certified Answers)

Register Unity Catalog functions so Genie can call them directly. The function must already exist in UC.

```python
manage_genie_instructions(
    action="add_function",
    space_id="abc123",
    function_name="catalog.analytics.calc_churn_rate"
)
```

When a user asks "what is the churn rate?", Genie will use `catalog.analytics.calc_churn_rate()` instead of generating its own SQL.

## Benchmarks

Benchmarks are question-answer pairs for evaluating Genie accuracy. Each benchmark has a question (natural language) and an expected answer (SQL).

```python
manage_genie_instructions(
    action="add_benchmark",
    space_id="abc123",
    question_text="What were total sales last month?",
    answer_text="SELECT SUM(amount) FROM catalog.sales.orders WHERE order_date >= DATE_TRUNC('MONTH', CURRENT_DATE - INTERVAL 1 MONTH) AND order_date < DATE_TRUNC('MONTH', CURRENT_DATE)"
)
```

Use benchmarks to track regression when modifying instructions or tables.

## Batch Operations

For initial setup or bulk updates, use `add_batch` to add many items at once.

### Batch SQL Instructions

```python
manage_genie_instructions(
    action="add_batch",
    space_id="abc123",
    batch_type="sql_instructions",
    items=[
        {"title": "Top Customers", "content": "SELECT customer_id, SUM(amount) AS total FROM orders GROUP BY 1 ORDER BY 2 DESC LIMIT 10"},
        {"title": "Monthly Trend", "content": "SELECT DATE_TRUNC('MONTH', order_date) AS month, SUM(amount) FROM orders GROUP BY 1 ORDER BY 1"},
    ]
)
```

### Batch Functions

```python
manage_genie_instructions(
    action="add_batch",
    space_id="abc123",
    batch_type="functions",
    items=["catalog.schema.calc_revenue", "catalog.schema.calc_margin", "catalog.schema.get_active_customers"]
)
```

### Batch Benchmarks

```python
manage_genie_instructions(
    action="add_batch",
    space_id="abc123",
    batch_type="benchmarks",
    items=[
        {"question_text": "How many customers?", "answer_text": "SELECT COUNT(DISTINCT customer_id) FROM customers"},
        {"question_text": "Average order value?", "answer_text": "SELECT AVG(amount) FROM orders"},
    ]
)
```

## Listing Everything

Retrieve all instructions and curated questions for a space:

```python
manage_genie_instructions(action="list", space_id="abc123")
# Returns: {"instructions": [...], "curated_questions": [...]}
```

Filter by question type:

```python
manage_genie_instructions(action="list", space_id="abc123", question_type="BENCHMARK")
```

Valid question types: `SAMPLE_QUESTION`, `BENCHMARK`.

## Iterative Workflow

The recommended workflow for tuning a Genie Space:

1. **Create the space** with `create_or_update_genie` and initial tables
2. **Ask a test question** with `ask_genie` to see baseline behavior
3. **Add instructions** based on where Genie gets it wrong:
   - Wrong join? Add a SQL instruction with the correct join
   - Wrong column? Add a text instruction clarifying the column mapping
   - Missing function? Register it with `add_function`
4. **Re-ask the same question** to verify improvement
5. **Add benchmarks** for questions that must always work correctly
6. **List instructions** periodically to review and prune

### Example Iteration

```python
# Step 1: Test
result = ask_genie(space_id="abc123", question="What is our churn rate?")
# Genie writes bad SQL -- it doesn't know about the churn function

# Step 2: Fix
manage_genie_instructions(
    action="add_function",
    space_id="abc123",
    function_name="catalog.analytics.calc_churn_rate"
)

# Step 3: Re-test
result = ask_genie(space_id="abc123", question="What is our churn rate?")
# Now uses the registered function

# Step 4: Lock it in as a benchmark
manage_genie_instructions(
    action="add_benchmark",
    space_id="abc123",
    question_text="What is our churn rate?",
    answer_text="SELECT catalog.analytics.calc_churn_rate()"
)
```
