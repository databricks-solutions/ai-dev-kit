"""
Parallel Foundation Model Calls

This example demonstrates how to make multiple foundation model API calls in parallel
for improved performance. Pattern extracted from databricksters-check-and-pub production app.

Use cases:
- Content evaluation with multiple checks (compliance, quality, etc.)
- Batch processing of independent prompts
- Multi-aspect analysis of the same content
- A/B testing different prompts

Performance impact:
- Serial: 3 calls × 2s each = 6s total
- Parallel (max_workers=3): ~2s total (3× faster)

Configuration:
- LLM_MAX_CONCURRENCY env var controls parallelism (default: 3)
- Balance between throughput and rate limits
"""

import os
import time
import concurrent.futures
from typing import Any, Dict, List, Tuple, Callable, Optional

from openai import OpenAI

# =============================================================================
# CONFIGURATION
# =============================================================================
DATABRICKS_SERVING_BASE_URL = os.environ.get(
    "DATABRICKS_SERVING_BASE_URL",
    "https://<your-workspace-host>/serving-endpoints",
)
DATABRICKS_MODEL = os.environ.get(
    "DATABRICKS_MODEL",
    "databricks-meta-llama-3-1-70b-instruct"
)
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN")  # For this example

# Concurrency control
LLM_MAX_CONCURRENCY = int(os.environ.get("LLM_MAX_CONCURRENCY", "3"))


# =============================================================================
# Pattern: Parallel Job Execution
# =============================================================================
def run_jobs_parallel(
    jobs: Dict[str, Tuple[Callable, Tuple[Any, ...], Dict[str, Any]]],
    max_workers: int = LLM_MAX_CONCURRENCY,
) -> Tuple[Dict[str, Any], List[str]]:
    """Run a set of callables in parallel and wait for all results.

    This is the pattern used in databricksters-check-and-pub for making multiple
    LLM calls simultaneously.

    Args:
        jobs: Dict mapping job_name -> (function, args, kwargs)
        max_workers: Max parallel executions (default from LLM_MAX_CONCURRENCY)

    Returns:
        (results_dict, errors_list) where:
        - results_dict: job_name -> result (or None if failed)
        - errors_list: List of error messages for failed jobs

    Example:
        jobs = {
            "check_1": (my_llm_call, (prompt1,), {}),
            "check_2": (my_llm_call, (prompt2,), {}),
        }
        results, errors = run_jobs_parallel(jobs)
    """
    results: Dict[str, Any] = {}
    errors: List[str] = []

    def _call(fn, args, kwargs):
        return fn(*args, **kwargs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        futures = {
            executor.submit(_call, fn, args, kwargs): name
            for name, (fn, args, kwargs) in jobs.items()
        }

        # Wait for all to complete
        concurrent.futures.wait(list(futures.keys()))

        # Harvest results
        for future, job_name in futures.items():
            try:
                results[job_name] = future.result()
            except Exception as e:
                error_msg = f"{job_name}: {type(e).__name__}: {str(e)[:200]}"
                errors.append(error_msg)
                results[job_name] = None

    return results, errors


# =============================================================================
# LLM Call Helper
# =============================================================================
def llm_call(
    client: OpenAI,
    prompt: str,
    model: str = DATABRICKS_MODEL,
    max_tokens: int = 500,
) -> Tuple[str, int]:
    """Make a single LLM call and return (response, latency_ms)."""
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    content = resp.choices[0].message.content or ""
    return content, elapsed_ms


# =============================================================================
# Example: Content Quality Checks (from databricksters-check-and-pub)
# =============================================================================
def check_structure(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if content has clear heading structure."""
    prompt = f"""Evaluate the structure of this blog post. Does it have clear H2/H3 headings that segment the content?

Blog post:
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


def check_tldr(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if content has TL;DR near the top."""
    prompt = f"""Does this blog post start with a TL;DR or Key Takeaways section in the first 10%?

Blog post:
{text[:2000]}

Answer with: PASS or FAIL, then brief explanation."""

    response, latency_ms = llm_call(client, prompt)
    passed = "PASS" in response.upper().split("\n")[0]

    return {
        "check": "tldr",
        "passed": passed,
        "response": response,
        "latency_ms": latency_ms,
    }


def check_actionability(client: OpenAI, text: str) -> Dict[str, Any]:
    """Check if content has actionable takeaways."""
    prompt = f"""Does this blog post include actionable steps or concrete examples readers can use?

Blog post:
{text[:2000]}

Answer with: PASS or FAIL, then brief explanation."""

    response, latency_ms = llm_call(client, prompt)
    passed = "PASS" in response.upper().split("\n")[0]

    return {
        "check": "actionability",
        "passed": passed,
        "response": response,
        "latency_ms": latency_ms,
    }


# =============================================================================
# Example Usage: Parallel Execution
# =============================================================================
if __name__ == "__main__":
    # Sample blog content
    sample_text = """
    TL;DR: This post shows you how to deploy Databricks Apps in 3 steps.

    ## Introduction
    Databricks Apps provides a way to deploy web applications...

    ## Step 1: Create Your App
    First, create an app.py file...

    ## Step 2: Configure app.yaml
    Next, set up your configuration...

    ## Step 3: Deploy
    Finally, deploy using the CLI...
    """

    # Create OpenAI client
    if not DATABRICKS_TOKEN:
        print("Error: Set DATABRICKS_TOKEN environment variable")
        exit(1)

    client = OpenAI(api_key=DATABRICKS_TOKEN, base_url=DATABRICKS_SERVING_BASE_URL)

    print(f"Making 3 parallel LLM calls with max_workers={LLM_MAX_CONCURRENCY}...")
    print(f"Model: {DATABRICKS_MODEL}\n")

    # Define parallel jobs
    jobs = {
        "structure": (check_structure, (client, sample_text), {}),
        "tldr": (check_tldr, (client, sample_text), {}),
        "actionability": (check_actionability, (client, sample_text), {}),
    }

    # Execute in parallel (this is the key pattern!)
    start = time.perf_counter()
    results, errors = run_jobs_parallel(jobs, max_workers=LLM_MAX_CONCURRENCY)
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
   - Use LLM_MAX_CONCURRENCY env var (default: 3)
   - Balance throughput vs rate limits
   - Too high = rate limit errors
   - Too low = underutilized resources

2. Error handling
   - Capture exceptions per job
   - Return None for failed jobs
   - Collect error messages for debugging
   - Continue execution even if some jobs fail

3. Phased execution
   - Group related checks together
   - Run critical checks first (e.g., compliance)
   - Then run optimization checks
   - Avoid overwhelming the endpoint

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
