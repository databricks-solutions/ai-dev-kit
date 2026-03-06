## Production Patterns

This file owns the patterns that make App-side foundation-model usage robust in production instead of merely functional in a happy-path demo.

## Parallel Calls

Use parallel execution only when the LLM calls are independent:

- content evaluation with multiple checks
- multi-aspect analysis
- batch processing with bounded concurrency

Do not use it for dependent workflows where one answer feeds the next prompt.

Reference implementation: [`examples/3-parallel-llm-calls.py`](examples/3-parallel-llm-calls.py)

## Structured Outputs

When a response must be machine-readable:

- set `temperature=0.0`
- provide an explicit schema in the prompt
- normalize the returned content to text
- strip code fences and extra prose before parsing
- retry with stricter JSON-only instructions if parsing fails

Reference implementation: [`examples/4-structured-outputs.py`](examples/4-structured-outputs.py)

## Caching

Use caching at two different layers when appropriate:

- auth token caching in `st.session_state` to avoid re-minting OAuth tokens
- `@st.cache_data(ttl=...)` for expensive, repeatable structured-output calls

Keep the TTL aligned with how stale the result can be.

## Timeouts And Error Handling

- set explicit HTTP timeouts during token minting
- catch per-job errors in parallel workloads so one failed request does not discard the whole batch
- make local-development identity handling best effort rather than fatal

## Quick Reference

| Pattern | Use When | Avoid When |
|---------|----------|------------|
| Parallel calls | Requests are independent and latency matters | Requests depend on each other |
| Structured outputs | Response is parsed by code | Free-form chat UX |
| `@st.cache_data` | Inputs are stable and repeated | Results must be real-time |
| Token cache | App reruns often | One-shot scripts without state |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Running every call in parallel by default | Bound concurrency and only parallelize independent calls |
| Parsing model output with `json.loads` only | Add normalization, code-fence stripping, and retry logic |
| Using creative temperatures for extraction tasks | Use `temperature=0.0` for deterministic structured outputs |
| Repeating the same retry and parsing logic in every script | Keep one canonical implementation in the example set |
