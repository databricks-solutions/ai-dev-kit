---
name: analyzing-mlflow-session
description: Analyzes an MLflow session — a sequence of traces from a multi-turn chat conversation or interaction. Use when the user asks to debug a chat conversation, review session or chat history, find where a multi-turn chat went wrong, or analyze patterns across turns. Triggers on "analyze this session", "what happened in this conversation", "debug session", "review chat history", "where did this chat go wrong", "session traces", "analyze chat", "debug this chat".
---

# Analyzing an MLflow Chat Session

## What is a Session?

A session groups multiple traces that belong to the same chat conversation or user interaction. Each trace in the session represents one turn: the user's input and the system's response. Traces within a session are linked by a shared session ID stored in trace metadata.

The session ID is stored in trace metadata under the key `mlflow.trace.session`. This key contains dots, which affects filter syntax (see below). All traces sharing the same value for this key belong to the same session.

## Reconstructing the Conversation

Reconstructing a session's conversation is a multi-step process: discover the input/output schema from the first trace, extract those fields efficiently across all session traces, then inspect specific turns as needed. **Do NOT fetch full traces for every turn** — use `--extract-fields` on the search command instead.

**Step 1: Discover the schema.** First, find a trace ID from the session, then fetch its full JSON to inspect the schema:

```bash
# Get the first trace in the session
mlflow traces search \
  --experiment-id <EXPERIMENT_ID> \
  --filter-string 'metadata.`mlflow.trace.session` = "<SESSION_ID>"' \
  --order-by "timestamp_ms ASC" \
  --extract-fields 'info.trace_id' \
  --output json \
  --max-results 1 > /tmp/first_trace.json

# Fetch the full trace (always outputs JSON, no --output flag needed)
mlflow traces get \
  --trace-id <TRACE_ID_FROM_ABOVE> > /tmp/trace_detail.json
```

Find the **root span** — the span with `parent_span_id` equal to `null` (i.e., it has no parent). This is the top-level operation in the trace:

```bash
# Find the root span
jq '.data.spans[] | select(.parent_span_id == null)' /tmp/trace_detail.json
```

Examine its `attributes` dict to identify which keys hold the user input and system output. These could be:

- **MLflow standard attributes**: `mlflow.spanInputs` and `mlflow.spanOutputs` (set by the MLflow Python client)
- **Custom attributes**: Application-specific keys set via `@mlflow.trace` or `mlflow.start_span()` with custom attribute logging
- **Third-party OTel attributes**: Keys following GenAI Semantic Conventions, OpenInference, or other instrumentation conventions

The structure of these values also varies by application (e.g., a `query` string, a `messages` array, a dict with multiple fields). Inspect the actual attribute values to understand the format.

**If the root span has empty or missing inputs/outputs**, it may be a wrapper span (e.g., an orchestrator or middleware) that doesn't directly carry the chat turn data. In that case, look at its immediate children — find the closest span to the top of the hierarchy that has meaningful inputs and outputs corresponding to a chat turn:

The following example assumes the trace comes from the MLflow Python client (which stores inputs/outputs in `mlflow.spanInputs`/`mlflow.spanOutputs`) and that the relevant span is a direct child of root. In practice, the relevant span may be deeper in the hierarchy, and traces from other clients may use different attribute keys — explore the span tree as needed:

```bash
# Get the root span's ID
ROOT_ID=$(jq -r '.data.spans[] | select(.parent_span_id == null) | .span_id' /tmp/trace_detail.json)

# List immediate children of the root span with their inputs/outputs
jq --arg root "$ROOT_ID" '.data.spans[] | select(.parent_span_id == $root) | {name: .name, inputs: .attributes["mlflow.spanInputs"], outputs: .attributes["mlflow.spanOutputs"]}' /tmp/trace_detail.json
```

Also check the first trace's assessments. **Session-level assessments are attached to the first trace in the session** — these evaluate the session as a whole (e.g., overall conversation quality, multi-turn coherence) and can indicate the presence of issues somewhere across the entire session, not just the first turn. The first trace may also have per-turn assessments for that specific turn.

Both types appear in `.info.assessments`. Session-level assessments are identified by the presence of `mlflow.trace.session` in their `metadata` field:

```bash
# Show session-level assessments (exclude scorer errors)
jq '[.info.assessments[] | select(.feedback.error == null) | select(.metadata["mlflow.trace.session"]) | {name: .assessment_name, value: .feedback.value}]' /tmp/trace_detail.json

# Show per-turn assessments (exclude scorer errors)
jq '[.info.assessments[] | select(.feedback.error == null) | select(.metadata["mlflow.trace.session"] == null) | {name: .assessment_name, value: .feedback.value}]' /tmp/trace_detail.json
```

**Assessment errors are not trace errors.** If an assessment has a `feedback.error` field, it means the scorer or judge failed — not that the trace itself has a problem. Exclude these when using assessments to identify trace issues.

**Always consult the rationale when interpreting assessment values.** The `value` alone can be misleading — for example, a `user_frustration` assessment with `value: "no"` could mean "no frustration detected" or "the frustration check did not pass" (i.e., frustration *is* present), depending on how the scorer was configured. The `.rationale` field (a top-level assessment field, **not** nested under `.feedback`) explains what the value means in context. Include rationale when extracting assessments:

```bash
jq '[.info.assessments[] | select(.feedback.error == null) | {name: .assessment_name, value: .feedback.value, rationale: .rationale}]' /tmp/trace_detail.json
```

**Step 2: Extract across all session traces.** Once you know which attribute keys hold inputs and outputs, search for all traces in the session using `--extract-fields` to pull those fields along with assessments (see [Handling CLI Output](#handling-cli-output) for why output is written to a file):

```bash
mlflow traces search \
  --experiment-id <EXPERIMENT_ID> \
  --filter-string 'metadata.`mlflow.trace.session` = "<SESSION_ID>"' \
  --order-by "timestamp_ms ASC" \
  --extract-fields 'info.trace_id,info.state,info.request_time,info.assessments,info.trace_metadata.`mlflow.traceInputs`,info.trace_metadata.`mlflow.traceOutputs`' \
  --output json \
  --max-results 100 > /tmp/session_traces.json
```

Then use bash commands (e.g., `jq`, `wc`, `head`) on the file to analyze it.

The `--extract-fields` example above uses `mlflow.traceInputs`/`mlflow.traceOutputs` from trace metadata — adjust the field paths based on what you discovered in step 1.

Assessments contain quality judgments (e.g., correctness, relevance) that can pinpoint which turns had issues without needing to read every trace in detail. To identify which turns have assessment signals (excluding scorer errors):

```bash
# List turns with their valid assessments (scorer errors filtered out)
jq '.traces[] | {
  trace_id: .info.trace_id,
  time: .info.request_time,
  state: .info.state,
  assessments: [.info.assessments[]? | select(.feedback.error == null) | {
    name: .assessment_name,
    value: .feedback.value
  }]
}' /tmp/session_traces.json
```

**CLI syntax notes:**

- **`--experiment-id` is required** for all `mlflow traces search` commands. The command will fail without it.
- Metadata keys containing dots **must** be escaped with backticks in filter strings and extract-fields: `` metadata.`mlflow.trace.session` ``
- **Shell quoting**: Backticks inside **double quotes** are interpreted by bash as command substitution (e.g., bash will try to run `` `mlflow.trace.session` `` as a command). Always use **single quotes** for the outer string when the value contains backticks. For example: `--filter-string 'metadata.\`mlflow.trace.session\` = "value"'`
- `--max-results` defaults to 100, which is sufficient for most sessions. Increase up to 500 (the maximum) for longer conversations. If 500 results are returned, use pagination to retrieve the rest.

## Handling CLI Output

MLflow trace output can be large, and Claude Code's Bash tool has a ~30KB output limit for piped commands. When output exceeds this threshold, it gets saved to a file instead of being piped, causing silent failures.

**Safe approach (always works):**
```bash
# Step 1: Save to file
mlflow traces search \
  --experiment-id <EXPERIMENT_ID> \
  [...] \
  --output json > /tmp/output.json

# Step 2: Process the file
cat /tmp/output.json | jq '.traces[0].info.trace_id'
head -50 /tmp/output.json
wc -l /tmp/output.json
```

**Never pipe MLflow CLI output directly** (e.g., `mlflow traces search ... | jq '.'`). This can silently produce no output. Always redirect to a file first, then run commands on the file.

To inspect a specific turn in detail (e.g., after identifying a problematic turn), fetch its full trace:

```bash
mlflow traces get --trace-id <TRACE_ID> > /tmp/turn_detail.json
```


## Codebase Correlation

- **Session ID assignment**: Search the codebase for where `mlflow.trace.session` is set to understand how sessions are created — per user login, per browser tab, per explicit "new conversation" action, etc.
- **Context window management**: Look for how the application constructs the message history passed to the LLM at each turn. Common patterns include sliding window (last N messages), summarization of older turns, or full history. This implementation determines what context the model sees and is a frequent source of multi-turn failures.
- **Memory and state**: Some applications maintain state across turns beyond message history (e.g., extracted entities, user preferences, accumulated tool results). Search for how this state is stored and passed between turns.

## Reference Scripts

The `scripts/` subdirectory contains ready-to-run bash scripts for each analysis step. All scripts follow the output handling rules above (redirect to file, then process).

- **`scripts/discover_schema.sh <EXPERIMENT_ID> <SESSION_ID>`** — Finds the first trace in the session, fetches its full detail, and prints the root span's attribute keys and input/output values.
- **`scripts/inspect_turn.sh <TRACE_ID>`** — Fetches a specific trace, lists all spans, highlights error spans, and shows assessments.

## Example: Wrong Answer on Chat Turn 5

A user reports that their chatbot gave an incorrect answer on the 5th message of a chat conversation.

**1. Discover the schema and reconstruct the conversation.**

Fetch the first trace in the session and inspect the root span's attributes to find which keys hold inputs and outputs. In this case, `mlflow.spanInputs` contains the user query and `mlflow.spanOutputs` contains the assistant response. Then search all session traces, extracting those fields in chronological order. Scanning the extracted inputs and outputs confirms that turn 5's response is wrong, and reveals whether earlier turns look correct.

**2. Check if the error originated in an earlier turn.**

Turn 3's response contains a factual error that the user didn't challenge. Turn 4 builds on that incorrect information, and turn 5 compounds it. The root cause is in turn 3, not turn 5.

**3. Analyze the root-cause turn as a single trace.**

Fetch the full trace for turn 3 and analyze it — examine assessments (if any), walk the span tree, check retriever results, and correlate with code. The retriever returned an outdated document, causing the wrong answer.

**4. Recommendations.**

- Fix the retriever's data source to exclude or update outdated documents.
- Add per-turn assessments to detect errors before they propagate across the conversation.
- Consider implementing conversation-level error detection (e.g., checking consistency of answers across turns).
