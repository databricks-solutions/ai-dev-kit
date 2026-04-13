# Genie Conversations

Use the Genie Conversation API to ask natural language questions to a curated Genie Space.

## Overview

The `conversation.py` script in this skill folder allows you to programmatically send questions to a Genie Space and receive SQL-generated answers. Instead of writing SQL directly, you delegate the query generation to Genie, which has been curated with business logic, instructions, and certified queries.

## When to Use the Conversation API

### Use Conversation API When:

| Scenario | Why |
|----------|-----|
| Genie Space has curated business logic | Genie knows rules like "active customer = ordered in 90 days" |
| User explicitly says "ask Genie" or "use my Genie Space" | User intent to use their curated space |
| Complex business metrics with specific definitions | Genie has certified queries for official metrics |
| Testing a Genie Space after creating it | Validate the space works correctly |
| User wants conversational data exploration | Genie handles context for follow-up questions |

### Use Direct SQL Instead When:

| Scenario | Why |
|----------|-----|
| Simple ad-hoc query | Direct SQL is faster, no curation needed |
| You already have the exact SQL | No need for Genie to regenerate |
| Genie Space doesn't exist for this data | Can't use Genie without a space |
| Need precise control over the query | Direct SQL gives exact control |

## CLI Usage

Use the `conversation.py` script to ask questions:

```bash
python conversation.py ask SPACE_ID "Your question here"
```

## Basic Usage

### Ask a Question

```bash
python conversation.py ask 01abc123... "What were total sales last month?"
```

**Response:**
```json
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

```bash
# First question - capture the conversation_id from output
python conversation.py ask 01abc123... "What were total sales last month?"
# Output includes: "conversation_id": "conv_xyz789"

# Follow-up (uses context from first question)
python conversation.py ask 01abc123... "Break that down by region" --conversation-id conv_xyz789
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

The script returns JSON that can be parsed:

```bash
python conversation.py ask SPACE_ID "Who are our top 10 customers?" | jq '.status'
# Output: "COMPLETED"
```

Response fields when status is `COMPLETED`:
- `sql`: The SQL query Genie generated
- `columns`: List of column names
- `data`: Query results as list of rows
- `row_count`: Number of rows returned

### Failed Response

```bash
python conversation.py ask SPACE_ID "What is the meaning of life?" | jq '.status, .error'
# Output: "FAILED"
# Output: "Could not generate SQL for this question"
```

Genie couldn't answer - may need to rephrase or use direct SQL.

### Timeout

```bash
python conversation.py ask SPACE_ID "Complex query" --timeout 120 | jq '.status'
# If timeout occurs: "TIMEOUT"
```

Query took too long - try a simpler question or increase timeout.

## Example Workflows

### Workflow 1: User Asks to Use Genie

```
User: "Ask my Sales Genie what the churn rate is"

Claude:
1. Identifies user wants to use Genie (explicit request)
2. Runs: python conversation.py ask sales_genie_id "What is the churn rate?"
3. Returns: "Based on your Sales Genie, the churn rate is 4.2%.
   Genie used this SQL: SELECT ..."
```

### Workflow 2: Testing a New Genie Space

```
User: "I just created a Genie Space for HR data. Can you test it?"

Claude:
1. Gets the space_id from the user or recent databricks genie create-space result
2. Runs conversation.py with test questions:
   - python conversation.py ask SPACE_ID "How many employees do we have?"
   - python conversation.py ask SPACE_ID "What is the average salary by department?"
3. Reports results: "Your HR Genie is working. It correctly answered..."
```

### Workflow 3: Data Exploration with Follow-ups

```
User: "Use my analytics Genie to explore sales trends"

Claude:
1. python conversation.py ask SPACE_ID "What were total sales by month this year?"
   # Returns conversation_id: conv_xyz
2. User: "Which month had the highest growth?"
3. python conversation.py ask SPACE_ID "Which month had the highest growth?" -c conv_xyz
4. User: "What products drove that growth?"
5. python conversation.py ask SPACE_ID "What products drove that growth?" -c conv_xyz
```

## Best Practices

### Start New Conversations for New Topics

Don't reuse conversations across unrelated questions:

```bash
# Good: New conversation for new topic
python conversation.py ask SPACE_ID "What were sales last month?"  # New conversation
python conversation.py ask SPACE_ID "How many employees do we have?"  # New conversation

# Good: Follow-up for related question
python conversation.py ask SPACE_ID "What were sales last month?"
# Get conversation_id from output, then:
python conversation.py ask SPACE_ID "Break that down by product" -c CONV_ID  # Related follow-up
```

### Handle Clarification Requests

Genie may ask for clarification instead of returning results:

```bash
python conversation.py ask SPACE_ID "Show me the data" | jq '.text_response'
# If Genie needs clarification, text_response will contain the question
# Rephrase with more specifics
```

### Set Appropriate Timeouts

- Simple aggregations: 30-60 seconds
- Complex joins: 60-120 seconds
- Large data scans: 120+ seconds

```bash
# Quick question (default 60s)
python conversation.py ask SPACE_ID "How many orders today?"

# Complex analysis with longer timeout
python conversation.py ask SPACE_ID "Calculate customer lifetime value for all customers" --timeout 180
```

## Troubleshooting

### "Genie Space not found"

- Verify the `space_id` is correct
- Check you have access to the space
- Use `databricks genie get-space SPACE_ID` to verify it exists

### "Query timed out"

- Increase timeout: `--timeout 120`
- Simplify the question
- Check if the SQL warehouse is running: `databricks warehouses list`

### "Failed to generate SQL"

- Rephrase the question more clearly
- Check if the question is answerable with the available tables
- Add more instructions/curation to the Genie Space via the Databricks UI

### Unexpected Results

- Review the generated SQL in the response (`jq '.sql'`)
- Add SQL instructions to the Genie Space via the Databricks UI
- Add sample questions that demonstrate correct patterns
