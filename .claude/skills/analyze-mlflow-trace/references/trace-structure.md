# Trace Structure — Complete Field Reference

## Table of Contents

- [Trace Composition](#trace-composition)
- [OpenTelemetry Compatibility](#opentelemetry-compatibility)
- [TraceInfo Fields](#traceinfo-fields) — trace_id, state, request_time, execution_duration, request_preview, response_preview, client_request_id, trace_location, trace_metadata, tags, assessments
- [Span Fields](#span-fields) — span_id, trace_id, parent_span_id, name, span_type, start_time_unix_nano/end_time_unix_nano, status, inputs, outputs, attributes, events
- [Assessment Fields](#assessment-fields) — Common (assessment_id, create_time_ms, last_update_time_ms, valid, overrides, run_id), Feedback (name, value, source, rationale, metadata, span_id, error), and Expectation (name, value, source, metadata, span_id)
- [Span Types — Analysis Cheat Sheet](#span-types--analysis-cheat-sheet)

## Trace Composition

```
Trace
├── TraceInfo (metadata)
│   ├── trace_id (str)
│   ├── state: OK | ERROR | IN_PROGRESS | STATE_UNSPECIFIED
│   ├── request_time (int, ms since epoch)
│   ├── execution_duration (int, ms)
│   ├── request_preview (str, truncated root span input)
│   ├── response_preview (str, truncated root span output)
│   ├── client_request_id (str, optional external ID)
│   ├── trace_location: experiment ID or UC schema
│   ├── trace_metadata (dict, immutable)
│   ├── tags (dict, mutable)
│   └── assessments (list)
│       ├── [common] assessment_id, create_time_ms, last_update_time_ms,
│       │            valid, overrides, run_id
│       ├── Feedback (name, value, rationale, source, error)
│       └── Expectation (name, value, source)
└── TraceData
    └── spans (list[Span])
        ├── span_id, trace_id, parent_span_id
        ├── name, span_type
        ├── start_time_unix_nano, end_time_unix_nano
        ├── status (code + message)
        ├── inputs, outputs
        ├── attributes (dict)
        └── events (list[SpanEvent])
            ├── name
            ├── timestamp
            └── attributes (dict)
```

## OpenTelemetry Compatibility

MLflow traces are fully compatible with the [OpenTelemetry trace spec](https://opentelemetry.io/docs/specs/otel/trace/api/#span). This has several implications for trace analysis:

- **MLflow spans are OpenTelemetry spans.** They carry the same core fields (trace ID, span ID, parent ID, name, timestamps, status, attributes, events) and serialize to OTLP format. MLflow adds convenience accessors for GenAI use cases (`inputs`, `outputs`, `span_type`) on top of the base OTel spec.
- **Traces can originate from any OTel-instrumented application.** MLflow Server exposes an OTLP endpoint (`/v1/traces`) that accepts traces from any language (Python, Java, Go, Rust, etc.) using native OpenTelemetry SDKs. These traces may not have MLflow-specific attributes like `mlflow.spanInputs` — their data will be in standard OTel attributes instead.
- **Semantic conventions vary.** MLflow recognizes GenAI Semantic Conventions, OpenInference, and OpenLLMetry conventions. Traces from different instrumentation libraries may use different attribute naming schemes for the same concepts (e.g., token usage, model name). When analyzing traces from external OTel sources, check the raw `attributes` dict rather than relying on MLflow convenience fields.

## TraceInfo Fields

### `trace_id` (str)

The unique identifier for this trace. This is the primary key used to fetch, reference, and correlate the trace across systems. When a user reports an issue with a specific request, the trace ID is how you look it up. Trace IDs may follow different formats depending on the MLflow version (e.g., `tr-` prefix + OpenTelemetry trace ID, or a URI-style `trace:/<location>/<id>` format).

### `state` (TraceState)

The overall execution outcome of the trace. One of:

- **`OK`**: The traced operation completed successfully. Note that "successful" means it didn't throw an unhandled exception — the output could still be semantically wrong. Check assessments to determine output quality.
- **`ERROR`**: At least one span in the trace raised an unhandled exception. This is the first thing to check when investigating failures. When you see `ERROR`, immediately look for spans with error status and examine their exception events.
- **`IN_PROGRESS`**: The trace is still being recorded. You may see this for long-running agent executions. If a trace is stuck in `IN_PROGRESS` for an unexpectedly long time, the application may have crashed or lost its connection to the tracking server without finalizing the trace.
- **`STATE_UNSPECIFIED`**: The state was not set. This usually indicates a bug in the tracing instrumentation or an incomplete trace export.

### `request_time` (int)

The timestamp when the trace began, in milliseconds since the Unix epoch. Use this to correlate the trace with external events — deployment timestamps, incident reports, or user-reported issue times. Useful for answering "did this happen before or after the last deployment?" or "was this during the outage window?"

### `execution_duration` (int)

The total wall-clock time of the traced operation, in milliseconds. This measures from the start of the root span to its completion. Use this to identify performance regressions or timeout issues. Compare against expected latency for the operation — an LLM agent call that normally takes 2 seconds but took 30 seconds suggests retries, a slow external service, or resource contention. For finer-grained timing analysis, examine individual span durations.

### `request_preview` (str | None)

A JSON-encoded preview of the input to the root span, which represents the top-level input to the traced application. This may be truncated (up to 10,000 chars on Databricks, 1,000 chars in OSS). Use this as a quick sanity check — was the input well-formed? Does it contain the expected user query or data? Malformed or unexpected inputs are a common root cause of downstream failures. For the full untruncated input, examine the root span's `inputs` field in the span data.

### `response_preview` (str | None)

A JSON-encoded preview of the output from the root span, representing the application's final response. Also subject to truncation. Compare this against assessment expectations or user reports to confirm whether the output matches what the user described. If the response preview looks correct but the user reported an issue, the problem may be in how the response was presented rather than how it was generated. For the full output, check the root span's `outputs` field.

### `client_request_id` (str | None)

An optional identifier provided by the calling system (e.g., a web server request ID, a batch job ID, or a customer-facing ticket number). This bridges the gap between MLflow's trace ID and whatever ID the external system uses. When a user says "request ABC-123 failed," this field lets you find the corresponding trace without knowing the MLflow trace ID.

### `trace_location` (TraceLocation)

Where this trace is stored. Can be:
- **MlflowExperimentLocation**: Stored in an MLflow experiment, identified by `experiment_id`. This is the most common case for development and OSS deployments.
- **UCSchemaLocation**: Stored in a Databricks Unity Catalog schema, identified by `catalog_name` and `schema_name`. Used in production Databricks deployments for governed trace storage.

The location determines which tracking server or catalog to query when fetching the trace's full data.

### `trace_metadata` (dict[str, str])

Immutable key-value pairs set when the trace is created. These cannot be changed after the fact, making them reliable for recording the conditions under which the trace was produced. Keys and values are capped at 250 characters.

**Standard metadata keys set by the MLflow client** (these are specific to MLflow's Python client and may not be present in traces from third-party OpenTelemetry clients or different MLflow usage patterns):

- **`mlflow.modelId`**: Identifies which model version produced this trace. Essential for comparing behavior across model versions — if a trace shows a regression, check whether it was produced by a new model deployment.
- **`mlflow.trace.user`**: The end-user who triggered this request. Use this to investigate user-specific issues ("user X is seeing bad results") or to filter traces for a specific user's session history.
- **`mlflow.trace.session`**: Groups traces belonging to the same user session or conversation. When investigating multi-turn conversation issues, fetch all traces for the session to understand the full context the model had at each turn.
- **`mlflow.trace.tokenUsage`**: A JSON string containing `input_tokens`, `output_tokens`, and `total_tokens` aggregated across all LLM spans in the trace. High token counts can explain high latency (more tokens = slower generation) or unexpected costs. A sudden spike in input tokens might indicate a prompt injection or an overly large context being passed to the model.
- **`mlflow.sourceRun`**: Links this trace to an MLflow run (training or evaluation). Use this to correlate production trace behavior with the experiment that produced the model.
- **`mlflow.traceInputs`** / **`mlflow.traceOutputs`**: The full (non-truncated) trace-level inputs and outputs stored as metadata. Check these when `request_preview` or `response_preview` are truncated and you need the complete data.

### `tags` (dict[str, str])

Mutable key-value pairs that can be added or updated after trace creation. Keys max 250 chars, values max 4,096 chars. Tags are commonly used for categorization, filtering, and annotation workflows.

**Standard tag keys set by the MLflow client** (these are specific to MLflow's Python client and may not be present in traces from third-party OpenTelemetry clients or different MLflow usage patterns):

- **`mlflow.traceName`**: A human-readable name for the trace (e.g., `"customer_support_query"`, `"document_summarization"`). Often set by the application to describe the operation type. Useful for quickly understanding what the trace represents without examining its spans.
- **`mlflow.trace.sourceScorer`**: If this trace was generated as a side effect of running a scorer (e.g., an LLM judge evaluating another trace), this tag identifies which scorer produced it. Helps distinguish "real" application traces from evaluation traces.
- **`mlflow.linkedPrompts`**: A JSON-encoded list of prompt template references used during this trace. Use this to identify which prompt versions were active when the trace was produced, enabling prompt-level debugging ("did the new prompt template cause this regression?").

Custom tags are frequently used for environment (`"production"`, `"staging"`), application version, A/B test variant, or issue tracking labels.

### `assessments` (list[Assessment])

Quality judgments attached to the trace by humans, LLM judges, or automated code. Assessments are the primary mechanism for understanding whether a trace's output was *correct* — the `state` field only tells you if it *succeeded technically*, not if the result was good. See the dedicated Assessments section below for details on Feedback and Expectation subtypes.

When investigating a trace, always check assessments first. A negative feedback score or a failed expectation tells you *what* went wrong, and the `rationale` field often explains *why*. This gives you a starting hypothesis before you dive into spans.

## Span Fields

### `span_id` (str)

A unique identifier for this span within the trace. Used to reference specific spans when logging span-level assessments, when tracing parent-child relationships, and when correlating spans with codebase functions. Each span ID is unique within its trace but not globally unique across traces.

### `trace_id` (str)

The trace this span belongs to. All spans in a trace share the same `trace_id`. Use this to confirm that a span belongs to the trace you're analyzing, especially when working with spans from batch queries.

### `parent_span_id` (str | None)

The `span_id` of this span's parent. `None` for the root span (the top-level operation). The parent-child relationships form a tree that mirrors the application's call stack. When investigating an error, trace upward from the failing span through its parents to understand the sequence of calls that led to the failure. When investigating quality issues, trace downward from the root span through its children to follow the execution flow.

### `name` (str)

The operation name, which typically corresponds to the function name in the application code. For example, a span named `retrieve_documents` likely maps to a function `def retrieve_documents(...)` in the codebase. For autologged spans (from framework integrations like LangChain, OpenAI, etc.), names follow framework conventions (e.g., `ChatOpenAI`, `RetrievalQA`). This is the key field for correlating trace data with source code.

### `span_type` (str)

Categorizes the operation this span represents. This tells you the *role* of the span in the application's execution without needing to read its code.

**This field is a free-form string, not an enum.** MLflow provides built-in span type constants (listed below), but applications can set any custom string value (e.g., `"ROUTER"`, `"VALIDATOR"`, `"CACHE_LOOKUP"`). When analyzing a trace, don't assume span types are limited to the built-in list — custom types reflect application-specific semantics defined by the developer.

**Built-in span types** (these are defined by the MLflow client; traces from third-party OpenTelemetry clients may use different type conventions or no span type at all — check the raw `attributes` dict for equivalent categorization):

- **`LLM`**: A language model inference call. Examine `inputs` for the prompt/messages and `outputs` for the model response. Check token usage in attributes. When investigating quality issues, LLM span inputs reveal exactly what the model saw, which may differ from what you'd expect after prompt template rendering, context injection, and message formatting.
- **`CHAT_MODEL`**: A chat-specific LLM call. Similar to `LLM` but specifically for chat completion APIs. Inputs contain message arrays (system, user, assistant messages) and outputs contain the model's response message. Useful for verifying conversation context is correctly constructed.
- **`AGENT`**: An autonomous agent execution that may involve planning, reasoning, and tool use across multiple steps. Agent spans typically have many child spans (LLM calls, tool calls). When an agent produces a wrong answer, examine the sequence of child spans to understand its reasoning chain — did it call the right tools? Did it interpret tool outputs correctly?
- **`TOOL`**: A tool or function call made by an agent or chain. Examine `inputs` to see what arguments were passed and `outputs` to see what the tool returned. Tool failures or unexpected return values are a frequent root cause of agent errors. If a tool returns an error or irrelevant data, the downstream LLM may hallucinate or fail.
- **`RETRIEVER`**: A document or data retrieval operation (e.g., vector search, database query). The `outputs` contain the retrieved documents or records. This is critical for RAG (Retrieval Augmented Generation) analysis — if the retriever returns irrelevant documents, the LLM will generate answers based on wrong context. Check whether the retrieved content actually answers the user's question.
- **`CHAIN`**: A sequence of operations chained together. Chains are the glue between components — they pass data from one step to the next. If the final output is wrong but individual components seem correct, examine the chain span to see how data flows between steps.
- **`EMBEDDING`**: Vector embedding generation (e.g., converting text to embeddings for retrieval). If retrieval results are poor, the embedding step might be using the wrong model or truncating input text.
- **`RERANKER`**: Reranking of retrieval results. If the retriever found relevant documents but they weren't used effectively, the reranker may have deprioritized them. Compare reranker inputs (candidate documents) with outputs (reordered documents).
- **`PARSER`**: Output parsing (e.g., extracting structured data from LLM text output). Parser failures often indicate the LLM produced output in an unexpected format. Check the parser's input (raw LLM text) against expected format.
- **`GUARDRAIL`**: A safety or content filter. Guardrail spans can *modify* or *block* responses. If a response seems truncated or generic, check whether a guardrail intervened. The guardrail's `inputs` show what it received, and `outputs` show what it passed through (or a blocking message).
- **`MEMORY`**: Memory read/write operations (e.g., conversation history, context window management). If the model seems to lack context from earlier in a conversation, check whether the memory span loaded the expected history.
- **`EVALUATOR`**: An evaluation operation (e.g., an LLM judge scoring output quality). These spans appear when evaluation is run inline with the application.
- **`WORKFLOW`** / **`TASK`**: Higher-level orchestration spans grouping multiple operations into a logical unit.
- **`UNKNOWN`**: The default when no type is specified.

### `start_time_unix_nano` / `end_time_unix_nano` (int)

Span start and end times in nanoseconds since epoch. The difference gives the span's wall-clock duration. Use these to build a timeline of execution:
- **Find the slowest span**: The span with the largest `end_time_unix_nano - start_time_unix_nano` is your bottleneck.
- **Find gaps**: If a parent span's duration is much longer than the sum of its children, time is being spent between child calls (e.g., data processing, serialization, network overhead).
- **Detect sequential vs. parallel**: If child spans overlap in time, operations are running in parallel. If they're strictly sequential, look for parallelization opportunities.
- **Identify retries**: Multiple child spans with the same name and sequential timing suggest retry behavior.

### `status` (SpanStatus)

The completion status of this span. Contains two fields: `code` and `message`.

The `code` field values are:

- **`STATUS_CODE_OK`**: The operation completed without error.
- **`STATUS_CODE_ERROR`**: The operation raised an exception or was explicitly marked as failed. When `status.code` is `STATUS_CODE_ERROR`, check the `events` list for exception details. The `status.message` field may contain the error message.
- **`STATUS_CODE_UNSET`**: The status was not explicitly set. This is the default for spans that complete normally without explicit status management. Treat as equivalent to `STATUS_CODE_OK` in most cases.

### `inputs` (Any)

The input data passed to the operation this span represents. The structure depends on the span type:
- **LLM spans**: The prompt, messages array, or completion request including model parameters (temperature, max_tokens, etc.)
- **Tool spans**: The arguments passed to the tool function
- **Retriever spans**: The search query or embedding vector used for retrieval
- **Chain spans**: The data passed into the chain from the previous step

Inputs are critical for root-cause analysis. When an operation produces unexpected output, check its inputs first — the problem may originate upstream. Compare the inputs against what the application code is supposed to pass to verify data flows correctly between components.

### `outputs` (Any)

The output data returned by the operation. The structure depends on the span type:
- **LLM spans**: The generated text, message, or completion response including token usage
- **Tool spans**: The return value of the tool function
- **Retriever spans**: The list of retrieved documents with scores/metadata
- **Chain spans**: The data passed to the next step or returned as the final result

Compare outputs against expectations to identify where the execution diverged from the desired behavior. For quality issues, trace the outputs forward through child spans to see how each component transformed the data.

### `attributes` (dict)

A key-value dictionary of additional span metadata. Attributes are set by the tracing instrumentation and may include framework-specific details.

**Common MLflow client attributes** (these are specific to the MLflow Python client; traces from third-party OpenTelemetry clients will use different attribute names — e.g., GenAI Semantic Conventions, OpenInference, or custom keys — check the raw `attributes` dict to find equivalent fields):

- **`mlflow.spanType`**: Redundant with `span_type` but present in raw attribute form.
- **`mlflow.spanInputs`** / **`mlflow.spanOutputs`**: Serialized input/output data (the `inputs`/`outputs` fields are derived from these).
- **`mlflow.spanFunctionName`**: The exact function name that was traced, useful when the span `name` has been customized to differ from the function name.
- **`mlflow.chat.tokenUsage`**: Token usage for LLM spans (`input_tokens`, `output_tokens`, `total_tokens`). Compare across LLM spans to find which call consumed the most tokens.
- **`mlflow.chat.tools`**: The tool definitions provided to an LLM call. Check these to verify the model had access to the right tools.

### `events` (list[SpanEvent])

Point-in-time occurrences recorded during the span's execution. The most important event type is **exception events**, which capture error details.

The exception event format below follows the [OpenTelemetry exception semantic conventions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/) and is used by the MLflow client. Traces from other OTel-compatible clients should use the same convention, though attribute names may vary:

- **`name`**: For exceptions, this is `"exception"`.
- **`timestamp`**: When the event occurred (nanoseconds). Useful for understanding whether the error happened early or late in the span's execution.
- **`attributes.exception.type`**: The exception class (e.g., `"ValueError"`, `"TimeoutError"`, `"openai.RateLimitError"`). This immediately categorizes the failure — rate limits, timeouts, validation errors, and authentication failures all require different remediation.
- **`attributes.exception.message`**: The error message string. Often contains the specific detail you need (e.g., "maximum context length exceeded", "invalid API key", "connection refused").
- **`attributes.exception.stacktrace`**: The full Python stacktrace. Use this to pinpoint the exact line of code that failed. Search the codebase for the file and line number referenced in the stacktrace to find the failing code.

Non-exception events may also be present for custom instrumentation (e.g., logging checkpoints, state transitions).

## Assessment Fields

The following fields are common to both Feedback and Expectation assessments.

### `assessment_id` (str | None)

The unique identifier for this assessment, generated by the backend when the assessment is created. Use this to reference a specific assessment when updating or overriding it. May be `None` if the assessment was created locally and not yet persisted to a tracking server.

### `create_time_ms` (int)

The timestamp when the assessment was first created, in milliseconds since the Unix epoch. Use this to understand when the assessment was produced relative to the trace itself — assessments created long after the trace may reflect delayed human review or batch evaluation runs.

### `last_update_time_ms` (int)

The timestamp of the most recent update to this assessment, in milliseconds since the Unix epoch. Compare with `create_time_ms` to determine if the assessment was modified after initial creation (e.g., a human reviewer revised their feedback).

### `valid` (bool | None)

Whether this assessment is currently valid (i.e., has not been overridden by a newer assessment). Set automatically by the backend — when a new assessment overrides this one, `valid` is set to `false`. When analyzing assessments, filter for `valid: true` to see only the most current judgments. An overridden assessment's `value` and `rationale` may be outdated.

### `overrides` (str | None)

The `assessment_id` of the assessment that this assessment supersedes. When a human corrects an LLM judge's feedback or re-evaluates a trace, the new assessment's `overrides` field points to the previous one. Use this to trace the revision history of assessments on a trace.

### `run_id` (str | None)

Links this assessment to an MLflow run (e.g., an evaluation run). When assessments are produced as part of `mlflow.evaluate()` or similar batch evaluation workflows, this field identifies which run generated them. Use this to group assessments by evaluation run or to find the evaluation configuration that produced a particular judgment.

### Feedback

Feedback assessments represent quality judgments about the trace's behavior or output. They are the primary signal for whether a trace produced a *good* result, as opposed to the trace `state` which only indicates technical success.

#### `name` (str)

The name identifying what aspect of quality this feedback measures (e.g., `"correctness"`, `"helpfulness"`, `"safety"`, `"relevance"`, `"rating"`). Different names represent different evaluation dimensions. When investigating quality issues, filter assessments by name to focus on the relevant dimension — a trace might score well on safety but poorly on correctness.

#### `value` (float | int | str | bool | list | dict)

The actual feedback score or label. The type and semantics depend on the scorer that produced it:
- **Boolean**: `true`/`false` for binary judgments (e.g., `"is_correct": true`)
- **Numeric**: Scores on a scale (e.g., `"relevance": 0.85` on a 0-1 scale)
- **String**: Categorical labels (e.g., `"rating": "positive"`, `"tone": "professional"`)
- **Dict/List**: Structured feedback with multiple components

A `false`, low numeric score, or negative label is the starting point for investigation. The `rationale` field will explain why the score is what it is.

#### `source` (AssessmentSource)

Who or what produced this feedback:
- **`source_type: HUMAN`**: A human reviewer rated this trace. Human feedback is typically the highest-signal assessment. If a human flagged an issue, it reflects a real user experience problem.
- **`source_type: LLM_JUDGE`**: An LLM-based scorer evaluated this trace. LLM judge feedback is automated and scalable but may have false positives. Cross-reference with the trace's actual content to validate the judgment.
- **`source_type: CODE`**: A programmatic rule or heuristic scored this trace (e.g., regex match, length check, format validation). Code-based feedback is deterministic and reliable for structural checks.

The **`source_id`** further identifies the specific source (e.g., a user's email, a model name like `"gpt-4"`, or a scorer function name).

#### `rationale` (str | None)

A free-text explanation of why the feedback value was assigned. This is often the **most valuable field for analysis** — it directly describes the issue in natural language. For LLM judge assessments, the rationale contains the judge's reasoning chain. For human feedback, it contains the reviewer's notes. Always read the rationale before diving into spans — it often tells you exactly what went wrong and where to look.

#### `metadata` (dict | None)

Additional context about the assessment. Common metadata keys set by the MLflow client (these may not be present in assessments from other systems or custom integrations):
- **`mlflow.assessment.sourceRunId`**: Links to the evaluation run that produced this assessment.
- **`mlflow.assessment.judgeCost`**: The LLM cost incurred to generate this judgment (for LLM judge assessments).
- **`mlflow.assessment.scorerTraceId`**: The trace ID of the scorer's own execution — useful for debugging the scorer itself if you suspect the judgment is wrong.
- **`mlflow.assessment.onlineScoringSessionId`**: Identifies the online scoring session that triggered this assessment.

#### `span_id` (str | None)

If set, this feedback applies to a specific span rather than the trace as a whole. Span-level feedback pinpoints quality issues to a specific operation — for example, feedback on a retriever span's relevance tells you the retrieval step specifically was the problem, not the LLM generation step.

#### `error` (AssessmentError | None)

If the feedback generation itself failed (e.g., the LLM judge timed out or returned an unparseable response), this field captures the error. Contains `error_code`, `error_message`, and optionally `stack_trace`. **An assessment error does not mean there is anything wrong with the trace itself** — it means the scorer/judge that tried to evaluate the trace encountered a problem. When feedback has an error, the `value` may be missing or unreliable. Check whether the scorer needs debugging by examining its trace via `metadata.mlflow.scorerTraceId`.

### Expectation

Expectation assessments represent ground-truth labels — the *correct* or *desired* output for a given input. They are typically set by humans during dataset creation or labeling workflows.

#### `name` (str)

The label name identifying what this expectation represents (e.g., `"expected_output"`, `"expected_tool_calls"`, `"expected_category"`). Multiple expectations with different names can exist on the same trace, each representing a different aspect of the expected behavior.

#### `value` (Any)

The ground-truth value (JSON-serializable). This is what the traced operation *should* have produced. Compare this against `response_preview` or the root span's `outputs` to identify discrepancies. The comparison might be:
- **Exact match**: For classification tasks, factoid questions, or structured outputs
- **Semantic similarity**: For open-ended generation where exact match is too strict
- **Structural match**: For tool call sequences or multi-step plans where order and structure matter

#### `source` (AssessmentSource)

Typically `source_type: HUMAN` since expectations are usually human-provided ground truth. The `source_id` may identify the labeler.

#### `metadata` (dict | None)

Additional context about the expectation, such as labeling instructions, confidence level, or dataset version.

#### `span_id` (str | None)

If set, this expectation applies to a specific span's output rather than the trace's overall output. Span-level expectations are useful for testing intermediate steps — for example, verifying that a retriever span returned the right documents regardless of what the LLM did with them.

## Span Types — Analysis Cheat Sheet

The types below are built into the MLflow client. Traces from third-party OpenTelemetry clients may use different type conventions or omit span types entirely — in that case, infer the operation's role from its name, attributes, and inputs/outputs.

| Type | What to check when investigating issues |
|---|---|
| `LLM` | Were the prompt/messages correct? Did the model receive the right context? Check token usage for context window issues. |
| `CHAT_MODEL` | Is the message history complete and correctly ordered? Are system instructions present? |
| `AGENT` | Did the agent choose the right tools? Did it interpret tool results correctly? How many steps did it take? |
| `TOOL` | Did the tool receive correct arguments? Did it return valid data? Did it error? |
| `RETRIEVER` | Did the query make sense? Were the retrieved documents relevant to the question? |
| `CHAIN` | Is data flowing correctly between steps? Is any transformation losing or corrupting information? |
| `EMBEDDING` | Is the embedding model appropriate? Was input text truncated? |
| `RERANKER` | Did reranking improve or degrade the document ordering? Compare input vs. output ranking. |
| `PARSER` | Did the LLM output match the expected format? What was the raw text before parsing? |
| `GUARDRAIL` | Did the guardrail block or modify the response? Was the intervention appropriate? |
| `MEMORY` | Was the expected conversation history loaded? Was any context lost or truncated? |
| *(custom)* | For app-defined types, infer purpose from the name and examine inputs/outputs. Check the codebase for the `span_type=` argument in `@mlflow.trace()` or `mlflow.start_span()`. |

