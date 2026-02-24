# Genie Conversations

Use the Genie Conversation API to ask natural language questions to a curated Genie Space.

## Overview

The `ask_genie` tool allows you to programmatically send questions to a Genie Space and receive SQL-generated answers. Instead of writing SQL directly, you delegate the query generation to Genie, which has been curated with business logic, instructions, and certified queries.

## When to Use `ask_genie`

### Use `ask_genie` When:

| Scenario | Why |
|----------|-----|
| Genie Space has curated business logic | Genie knows rules like "active customer = ordered in 90 days" |
| User explicitly says "ask Genie" or "use my Genie Space" | User intent to use their curated space |
| Complex business metrics with specific definitions | Genie has certified queries for official metrics |
| Testing a Genie Space after creating it | Validate the space works correctly |
| User wants conversational data exploration | Genie handles context for follow-up questions |

### Use Direct SQL (`execute_sql`) Instead When:

| Scenario | Why |
|----------|-----|
| Simple ad-hoc query | Direct SQL is faster, no curation needed |
| You already have the exact SQL | No need for Genie to regenerate |
| Genie Space doesn't exist for this data | Can't use Genie without a space |
| Need precise control over the query | Direct SQL gives exact control |

## MCP Tools

| Tool | Purpose |
|------|---------|
| `ask_genie` | Ask a question, start new conversation |
| `ask_genie_followup` | Ask follow-up in existing conversation |

## Basic Usage

### Ask a Question

```python
ask_genie(
    space_id="01abc123...",
    question="What were total sales last month?"
)
```

**Response:**
```python
{
    "question": "What were total sales last month?",
    "conversation_id": "conv_xyz789",
    "message_id": "msg_123",
    "status": "COMPLETED",
    "sql": "SELECT SUM(total_amount) AS total_sales FROM orders WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH) AND order_date < DATE_TRUNC('month', CURRENT_DATE)",
    "columns": ["total_sales"],
    "data": [[125430.50]],
    "row_count": 1
}
```

### Ask Follow-up Questions

Use the `conversation_id` from the first response to ask follow-up questions with context:

```python
# First question
result = ask_genie(
    space_id="01abc123...",
    question="What were total sales last month?"
)

# Follow-up (uses context from first question)
ask_genie_followup(
    space_id="01abc123...",
    conversation_id=result["conversation_id"],
    question="Break that down by region"
)
```

Genie remembers the context, so "that" refers to "total sales last month".

## Response Fields

| Field | Description |
|-------|-------------|
| `question` | The original question asked |
| `conversation_id` | ID for follow-up questions |
| `message_id` | Unique message identifier |
| `status` | `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT` |
| `sql` | The SQL query Genie generated |
| `columns` | List of column names in result |
| `data` | Query results as list of rows |
| `row_count` | Number of rows returned |
| `text_response` | Text explanation (if Genie asks for clarification) |
| `error` | Error message (if status is not COMPLETED) |

## Handling Responses

### Successful Response

```python
result = ask_genie(space_id, "Who are our top 10 customers?")

if result["status"] == "COMPLETED":
    print(f"SQL: {result['sql']}")
    print(f"Rows: {result['row_count']}")
    for row in result["data"]:
        print(row)
```

### Failed Response

```python
result = ask_genie(space_id, "What is the meaning of life?")

if result["status"] == "FAILED":
    print(f"Error: {result['error']}")
    # Genie couldn't answer - may need to rephrase or use direct SQL
```

### Timeout

```python
result = ask_genie(space_id, question, timeout_seconds=60)

if result["status"] == "TIMEOUT":
    print("Query took too long - try a simpler question or increase timeout")
```

## Example Workflows

### Workflow 1: User Asks to Use Genie

```
User: "Ask my Sales Genie what the churn rate is"

Claude:
1. Identifies user wants to use Genie (explicit request)
2. Calls ask_genie(space_id="sales_genie_id", question="What is the churn rate?")
3. Returns: "Based on your Sales Genie, the churn rate is 4.2%.
   Genie used this SQL: SELECT ..."
```

### Workflow 2: Testing a New Genie Space

```
User: "I just created a Genie Space for HR data. Can you test it?"

Claude:
1. Gets the space_id from the user or recent create_or_update_genie result
2. Calls ask_genie with test questions:
   - "How many employees do we have?"
   - "What is the average salary by department?"
3. Reports results: "Your HR Genie is working. It correctly answered..."
```

### Workflow 3: Data Exploration with Follow-ups

```
User: "Use my analytics Genie to explore sales trends"

Claude:
1. ask_genie(space_id, "What were total sales by month this year?")
2. User: "Which month had the highest growth?"
3. ask_genie_followup(space_id, conv_id, "Which month had the highest growth?")
4. User: "What products drove that growth?"
5. ask_genie_followup(space_id, conv_id, "What products drove that growth?")
```

## Best Practices

### Start New Conversations for New Topics

Don't reuse conversations across unrelated questions:

```python
# Good: New conversation for new topic
result1 = ask_genie(space_id, "What were sales last month?")  # New conversation
result2 = ask_genie(space_id, "How many employees do we have?")  # New conversation

# Good: Follow-up for related question
result1 = ask_genie(space_id, "What were sales last month?")
result2 = ask_genie_followup(space_id, result1["conversation_id"],
                              "Break that down by product")  # Related follow-up
```

### Handle Clarification Requests

Genie may ask for clarification instead of returning results:

```python
result = ask_genie(space_id, "Show me the data")

if result.get("text_response"):
    # Genie is asking for clarification
    print(f"Genie asks: {result['text_response']}")
    # Rephrase with more specifics
```

### Set Appropriate Timeouts

- Simple aggregations: 30-60 seconds
- Complex joins: 60-120 seconds
- Large data scans: 120+ seconds

```python
# Quick question
ask_genie(space_id, "How many orders today?", timeout_seconds=30)

# Complex analysis
ask_genie(space_id, "Calculate customer lifetime value for all customers",
          timeout_seconds=180)
```

## Troubleshooting

### "Genie Space not found"

- Verify the `space_id` is correct
- Check you have access to the space
- Use `get_genie(space_id)` to verify it exists

### "Query timed out"

- Increase `timeout_seconds`
- Simplify the question
- Check if the SQL warehouse is running

### "Failed to generate SQL"

- Rephrase the question more clearly
- Check if the question is answerable with the available tables
- Add more instructions/curation to the Genie Space

### Unexpected Results

- Review the generated SQL in the response
- Add SQL instructions to the Genie Space via the Databricks UI
- Add sample questions that demonstrate correct patterns
