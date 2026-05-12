"""
Parallel Foundation Model Calls

This example demonstrates how to make multiple foundation model API calls in parallel
for improved performance. It uses the same bounded job-runner pattern as the
production Databricks App, but keeps the example generic enough to reuse in
other review, extraction, or scoring workflows.

Use cases:
- Document evaluation with multiple independent checks
- Batch processing of independent prompts
- Multi-aspect analysis of the same content
- A/B testing different prompts

Performance impact:
- Serial: 5 calls × 2s each = 10s total
- Parallel (max_workers=5): ~2s to 3s total depending on endpoint overhead

Configuration:
- LLM_MAX_CONCURRENCY env var controls parallelism (positive integer, default: 5)
- Balance between throughput and rate limits
- DATABRICKS_MODEL must be set to a valid serving endpoint name
"""

import time
from typing import Any, Callable, Dict, List, Tuple

from openai import OpenAI

from llm_config import (
    create_foundation_model_client,
    get_model_name,
    run_jobs_parallel,
)


# =============================================================================
# LLM Call Helper
# =============================================================================
def llm_call(
    client: OpenAI,
    prompt: str,
    model: str | None = None,
    max_tokens: int = 500,
) -> Tuple[str, int]:
    """Make a single LLM call and return (response, latency_ms)."""
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model or get_model_name(),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    content = resp.choices[0].message.content or ""
    return content, elapsed_ms


# =============================================================================
# Example: Generic Technical Document Checks
# =============================================================================
def check_structure(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if a technical document has clear section structure."""
    prompt = f"""Evaluate the structure of this technical document. Does it have clear section headings and a logical progression?

DOCUMENT:
{text[:2000]}

Answer with: PASS or FAIL, then brief explanation."""

    response, latency_ms = llm_call(client, prompt)
    passed = "PASS" in response.upper().split("\n")[0]

    return {
        "check": "structure",
        "passed": passed,
        "response": response,
        "latency_ms": latency_ms,
    }


def check_summary(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if content has a concise executive summary near the top."""
    prompt = f"""Does this technical document start with a concise summary or key takeaways section in the first 10 percent?

DOCUMENT:
{text[:2000]}

Answer with: PASS or FAIL, then brief explanation."""

    response, latency_ms = llm_call(client, prompt)
    passed = "PASS" in response.upper().split("\n")[0]

    return {
        "check": "summary",
        "passed": passed,
        "response": response,
        "latency_ms": latency_ms,
    }


def check_examples(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if content includes concrete examples."""
    prompt = f"""Does this technical document include concrete examples, code, or step-by-step guidance readers can adapt?

DOCUMENT:
{text[:2000]}

Answer with: PASS or FAIL, then brief explanation."""

    response, latency_ms = llm_call(client, prompt)
    passed = "PASS" in response.upper().split("\n")[0]

    return {
        "check": "examples",
        "passed": passed,
        "response": response,
        "latency_ms": latency_ms,
    }


def check_troubleshooting(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if content covers troubleshooting or failure modes."""
    prompt = f"""Does this technical document include troubleshooting guidance, failure modes, or common pitfalls?

DOCUMENT:
{text[:2000]}

Answer with: PASS or FAIL, then brief explanation."""

    response, latency_ms = llm_call(client, prompt)
    passed = "PASS" in response.upper().split("\n")[0]

    return {
        "check": "troubleshooting",
        "passed": passed,
        "response": response,
        "latency_ms": latency_ms,
    }


def check_audience_fit(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if content matches a technical practitioner audience."""
    prompt = f"""Does this technical document appear written for practitioners, with the right level of specificity and useful context?

DOCUMENT:
{text[:2000]}

Answer with: PASS or FAIL, then brief explanation."""

    response, latency_ms = llm_call(client, prompt)
    passed = "PASS" in response.upper().split("\n")[0]

    return {
        "check": "audience_fit",
        "passed": passed,
        "response": response,
        "latency_ms": latency_ms,
    }


# =============================================================================
# Example Usage: Parallel Execution
# =============================================================================
if __name__ == "__main__":
    # Sample technical document
    sample_text = """
    Summary: This guide shows how to deploy a Databricks App in three steps.

    ## Introduction
    Databricks Apps provides a way to deploy web applications...

    ## Step 1: Create Your App
    First, create an app.py file...

    ## Step 2: Configure app.yaml
    Next, set up your configuration...

    ## Step 3: Deploy
    Finally, deploy using the CLI...
    """

    client = create_foundation_model_client()

    print("Making 5 parallel LLM calls...")
    print(f"Model: {get_model_name()}\n")

    # Define independent parallel jobs
    jobs = {
        "structure": (check_structure, (client, sample_text), {}),
        "summary": (check_summary, (client, sample_text), {}),
        "examples": (check_examples, (client, sample_text), {}),
        "troubleshooting": (check_troubleshooting, (client, sample_text), {}),
        "audience_fit": (check_audience_fit, (client, sample_text), {}),
    }

    # Execute in parallel using the shared bounded job runner.
    start = time.perf_counter()
    results, errors = run_jobs_parallel(jobs)
    total_time = time.perf_counter() - start

    # Display results
    print("=" * 60)
    print(f"Completed in {total_time:.2f}s (parallel execution)")
    print("=" * 60)

    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print(f"  ❌ {error}")

    print("\nResults:")
    for job_name, result in results.items():
        if result:
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            print(f"\n{job_name.upper()}: {status}")
            print(f"  Latency: {result['latency_ms']}ms")
            print(f"  Response: {result['response'][:150]}...")
        else:
            print(f"\n{job_name.upper()}: ❌ FAILED (see errors above)")

    # Calculate time saved
    total_latency = sum(r["latency_ms"] for r in results.values() if r)
    time_saved = (total_latency / 1000) - total_time
    print(f"\n{'='*60}")
    print(f"Time saved vs serial execution: {time_saved:.2f}s")
    print(f"Speedup: {(total_latency/1000) / total_time:.1f}×")
    print(f"{'='*60}")


# =============================================================================
# Production Best Practices
# =============================================================================
"""
Best practices from databricksters-check-and-pub:

1. Configurable concurrency
   - Use LLM_MAX_CONCURRENCY env var (default: 5 in the production app)
   - Balance throughput vs rate limits
   - Too high = rate limit errors
   - Too low = underutilized resources

2. Error handling
   - Capture exceptions per job
   - Return None for failed jobs
   - Collect error messages for debugging
   - Continue execution even if some jobs fail

3. Bounded execution
   - Only parallelize independent checks
   - Cap concurrency with an env var rather than firing unlimited requests
   - Keep the job contract simple: name -> (callable, args, kwargs)

4. When to use parallel calls
   - Multiple independent evaluations of same content
   - Batch processing multiple documents
   - A/B testing different prompts
   - Multi-aspect analysis

5. When NOT to use parallel calls
   - Dependent/sequential operations
   - Single evaluation needed
   - Rate limits are very strict
   - Debugging (use serial for easier troubleshooting)
"""
