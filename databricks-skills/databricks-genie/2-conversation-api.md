# Genie Conversation API

Use the Genie Conversation API to ask natural language questions to a curated Genie Space and receive SQL-generated answers.

## Overview

The Conversation API provides two MCP tools for interacting with Genie Spaces:

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `ask_genie` | Start a new conversation with a question | `space_id`, `question` |
| `ask_genie_followup` | Ask a follow-up in an existing conversation | `space_id`, `conversation_id`, `question` |

Both tools send a natural language question to a Genie Space, which generates SQL, executes it against the configured SQL warehouse, and returns structured results. The two-tool design enforces a clear separation: `ask_genie` always starts fresh, while `ask_genie_followup` requires an explicit `conversation_id` to maintain context.

## Tool Reference

### `ask_genie`

Starts a new conversation and asks a question.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `space_id` | string | Yes | — | The Genie Space ID to query |
| `question` | string | Yes | — | Natural language question (must be non-empty) |
| `timeout_seconds` | integer | No | 120 | Maximum seconds to wait for a response |

**Example:**
```
ask_genie(
    space_id="01f116b25cb61b919a9efa192d5a96e4",
    question="How many customers are there?"
)
```

### `ask_genie_followup`

Asks a follow-up question within an existing conversation. Genie uses the prior conversation context to resolve references like "that", "those", or "break it down".

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `space_id` | string | Yes | — | The same Genie Space ID used in the original question |
| `conversation_id` | string | Yes | — | The `conversation_id` returned by a previous `ask_genie` or `ask_genie_followup` call |
| `question` | string | Yes | — | The follow-up question |
| `timeout_seconds` | integer | No | 120 | Maximum seconds to wait for a response |

**Example:**
```
ask_genie_followup(
    space_id="01f116b25cb61b919a9efa192d5a96e4",
    conversation_id="01f11a9721091636b4f756a3ef43c3f7",
    question="Break that down by region"
)
```

## Response Shape

Both tools return the same response structure. Fields are present or absent depending on the outcome.

### Successful Query Response

When Genie generates and executes SQL successfully:

```json
{
    "question": "How many customers are there?",
    "conversation_id": "01f11a9721091636b4f756a3ef43c3f7",
    "message_id": "01f11a97212b171cae53a9d478929dd1",
    "status": "COMPLETED",
    "sql": "SELECT COUNT(DISTINCT `customer_id`) AS num_customers FROM ...",
    "description": "You want to know the total number of unique customers in the database.",
    "row_count": 1,
    "columns": ["num_customers"],
    "data": [["3000"]],
    "text_response": "There are **3,000 customers** in the dataset."
}
```

### Text-Only Response (No SQL Generated)

When Genie cannot or chooses not to generate SQL (e.g., the question is off-topic or needs clarification):

```json
{
    "question": "What is the meaning of life?",
    "conversation_id": "01f11a974255111a9c5fe447da964eae",
    "message_id": "01f11a97426b147ebd038be04db2f3b5",
    "status": "COMPLETED",
    "text_response": "This question is unrelated to the database schema, so I cannot provide an answer based on the available data."
}
```

Note: `status` is still `"COMPLETED"` — check for the presence of `sql` or `data` to distinguish from a successful query.

### Error Response

When the request itself fails (invalid IDs, permissions, empty question):

```json
{
    "question": "How many customers?",
    "status": "ERROR",
    "error": "You need \"Can View\" permission to perform this action."
}
```

### Timeout Response

When the response exceeds `timeout_seconds`:

```json
{
    "question": "Complex query...",
    "status": "TIMEOUT",
    "error": "Genie response timed out after 3s"
}
```

### Field Reference

| Field | Type | Present When | Description |
|-------|------|-------------|-------------|
| `question` | string | Always | The original question asked |
| `conversation_id` | string | Success or text-only | ID for follow-up questions via `ask_genie_followup` |
| `message_id` | string | Success or text-only | Unique identifier for this message |
| `status` | string | Always | `COMPLETED`, `ERROR`, or `TIMEOUT` |
| `sql` | string | Successful query | The SQL query Genie generated |
| `description` | string | Successful query | Genie's interpretation of the question |
| `columns` | list[string] | Successful query | Column names in the result set |
| `data` | list[list[string]] | Successful query | Query results — each row is a list of string values |
| `row_count` | integer | Successful query | Number of rows returned |
| `text_response` | string | Success or text-only | Natural language summary or explanation |
| `error` | string | ERROR or TIMEOUT | Error description |

**Important notes about `data` values:**
- All values are strings, even for numeric columns. A count of 3000 is returned as `"3000"`, not `3000`.
- Large numbers may use scientific notation (e.g., `"3.336E8"` instead of `"333600000"`).
- The `text_response` field typically contains human-friendly formatted numbers (e.g., "$333,607,274.99") which are easier to present to users.

## When to Use `ask_genie` vs `execute_sql`

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
| No Genie Space exists for this data | Can't use Genie without a space |
| Need precise control over the query | Direct SQL gives exact control |

## Multi-Turn Conversation Workflow

### Starting a Conversation

Every call to `ask_genie` starts a **new** conversation. The response includes a `conversation_id` that you pass to `ask_genie_followup` for subsequent turns.

```
# Turn 1: New conversation
result = ask_genie(space_id, "How many customers are there?")
# result["conversation_id"] = "01f11a9721091636b4f756a3ef43c3f7"

# Turn 2: Follow-up (Genie knows "that" = customers)
result2 = ask_genie_followup(space_id, result["conversation_id"],
    "Break that down by region")

# Turn 3: Another follow-up in the same conversation
result3 = ask_genie_followup(space_id, result["conversation_id"],
    "Which region has the highest average income?")
```

### When to Start a New Conversation

Start a **new** conversation (use `ask_genie`) when the topic changes:

```
# Topic 1: Customer analysis
r1 = ask_genie(space_id, "How many customers are there?")
r2 = ask_genie_followup(space_id, r1["conversation_id"],
    "Break that down by region")

# Topic 2: Loan analysis — new conversation
r3 = ask_genie(space_id, "What is the total loan portfolio value?")
r4 = ask_genie_followup(space_id, r3["conversation_id"],
    "Break that down by loan type")
```

Reusing a conversation across unrelated topics may confuse Genie's context resolution.

## Handling Responses

### Branching on Response Type

```python
result = ask_genie(space_id, question)

if result["status"] == "COMPLETED":
    if "sql" in result and result.get("data"):
        # Successful query with results
        print(f"SQL: {result['sql']}")
        print(f"Rows: {result['row_count']}")
        for row in result["data"]:
            print(row)
    elif result.get("text_response"):
        # Text-only response (clarification or off-topic)
        print(f"Genie says: {result['text_response']}")
elif result["status"] == "TIMEOUT":
    print("Query timed out — try increasing timeout_seconds or simplifying the question")
elif result["status"] == "ERROR":
    print(f"Error: {result['error']}")
```

### Timeout Guidance

| Query Complexity | Suggested `timeout_seconds` |
|-----------------|---------------------------|
| Simple aggregation (COUNT, SUM) | 30–60 |
| Multi-table joins | 60–120 |
| Large data scans or complex analytics | 120–180 |

## Error Handling

### Error Status Values

| Status | Meaning | Common Causes |
|--------|---------|---------------|
| `COMPLETED` | Request succeeded | Query ran, or Genie responded with text |
| `ERROR` | Request failed | Invalid `space_id`, invalid `conversation_id`, empty question, permission denied |
| `TIMEOUT` | Response exceeded `timeout_seconds` | Complex query, cold warehouse, low timeout value |

### Verified Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `You need "Can View" permission to perform this action.` | Invalid or inaccessible `space_id` | Verify the space_id with `list_genie` or `get_genie`; check permissions |
| `User <id> does not own conversation <id>.` | Invalid `conversation_id` in `ask_genie_followup` | Use the `conversation_id` from a previous response in the same session |
| `Field 'content' is required, expected non-default value (not "")!` | Empty `question` string | Provide a non-empty question |
| `Genie response timed out after <N>s` | Response exceeded `timeout_seconds` | Increase timeout, simplify question, or check warehouse status |

## Troubleshooting

### "You need Can View permission"

- Verify the `space_id` is correct — use `list_genie()` to see accessible spaces
- Confirm you have at least "Can View" permission on the Genie Space
- Check that the Genie Space hasn't been deleted

### "User does not own conversation"

- The `conversation_id` must come from a previous `ask_genie` or `ask_genie_followup` response in the same user session
- Conversation IDs from other users won't work
- If the conversation has expired, start a new one with `ask_genie`

### Query Timed Out

- Increase `timeout_seconds` (default is 120)
- Simplify the question — fewer joins and aggregations
- Check if the SQL warehouse is running (a cold start adds 30–60 seconds)
- Try the question in the Genie UI to see if it's inherently slow

### Genie Returns Text Instead of SQL

- The question may be off-topic for the configured tables
- Rephrase with more specific terms that match the table/column names
- Check the Genie Space configuration — it may need more tables or instructions
- The `text_response` often explains what Genie needs to answer the question

### Unexpected or Wrong Results

- Review the `sql` field in the response to see what Genie generated
- Check the `description` field — it shows how Genie interpreted the question
- Add SQL instructions or certified queries to the Genie Space via the Databricks UI
- Add sample questions that demonstrate correct query patterns
