## Production Patterns

This file owns the patterns that make App-side foundation-model usage robust in production instead of merely functional in a happy-path demo.

## Parallel Calls

Use parallel execution only when the LLM calls are independent:

- content evaluation with multiple checks
- multi-aspect analysis
- batch processing with bounded concurrency

Do not use it for dependent workflows where one answer feeds the next prompt.

Reference implementation: [`examples/3-parallel-llm-calls.py`](examples/3-parallel-llm-calls.py)

Use a bounded job runner rather than firing requests ad hoc:

- store work as `job_name -> (callable, args, kwargs)`
- cap concurrency with a positive-integer `LLM_MAX_CONCURRENCY`
- collect per-job errors instead of failing the entire batch
- preserve the result map so the caller can decide which failures are fatal

## Structured Outputs

When a response must be machine-readable:

- set `temperature=0.0`
- provide an explicit schema in the prompt
- normalize the returned content to text
- strip code fences and extra prose before parsing
- retry with stricter JSON-only instructions if parsing fails

Reference implementation: [`examples/4-structured-outputs.py`](examples/4-structured-outputs.py)

## Caching

Use caching at three different layers when appropriate:

- auth token caching to avoid re-minting OAuth tokens
- endpoint-validation caching so the app does not re-check the same endpoint on every call
- `@st.cache_data(ttl=...)` for expensive, repeatable structured-output calls

Keep the TTL aligned with how stale the result can be.

## Timeouts And Error Handling

- set explicit HTTP timeouts during token minting
- catch per-job errors in parallel workloads so one failed request does not discard the whole batch
- make local-development identity handling best effort rather than fatal

## Quick Reference

| Pattern | Use When | Avoid When |
|---------|----------|------------|
| Bounded parallel calls | Requests are independent and latency matters | Requests depend on each other |
| Structured outputs | Response is parsed by code | Free-form chat UX |
| `@st.cache_data` | Inputs are stable and repeated | Results must be real-time |
| Token cache | The app may issue repeated or concurrent OAuth-backed calls | One-shot scripts using PAT only |
| Validation cache | The same endpoint is reused across many calls | Endpoint choice changes every request |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Running every call in parallel by default | Bound concurrency and only parallelize independent calls |
| Treating parallelism as all-or-nothing | Group independent jobs together and keep dependent work serial |
| Parsing model output with `json.loads` only | Add normalization, code-fence stripping, and retry logic |
| Using creative temperatures for extraction tasks | Use `temperature=0.0` for deterministic structured outputs |
| Repeating the same retry and parsing logic in every script | Keep one canonical implementation in the example set |
