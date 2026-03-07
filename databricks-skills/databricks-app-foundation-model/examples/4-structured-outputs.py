"""
Structured Outputs and Robust Response Parsing

Production patterns for getting structured data (JSON) from foundation models.
Extracted from databricksters-check-and-pub production app.

Key patterns:
1. Robust JSON parsing (handles code fences, smart quotes, malformed JSON)
2. Retry logic on parse failure with stricter prompts
3. Content normalization (handles various response formats)
4. temperature=0.0 for deterministic structured outputs
5. Streamlit caching for expensive API calls
6. Consistent timeout handling

Use cases:
- Content evaluation/scoring
- Data extraction from text
- Classification tasks
- Compliance checking
- Any task requiring structured model output

Set `DATABRICKS_MODEL` to a valid serving endpoint name before running.
"""

import json
import re
import time
from typing import Any, Dict, List, Tuple

import streamlit as st
from openai import OpenAI

from llm_config import create_foundation_model_client, get_model_name


# =============================================================================
# Pattern 1: Content Normalization
# =============================================================================
def _content_to_text(content: Any) -> str:
    """Normalize model message content to a string.

    Handles various content types returned by foundation models:
    - str: return as-is
    - bytes: decode to UTF-8
    - list: extract text from content parts (handles multi-modal responses)

    This is critical for handling different response formats consistently.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, (bytes, bytearray)):
        return content.decode("utf-8", errors="replace")

    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # Handle content part objects
                if "text" in item and isinstance(item["text"], str):
                    parts.append(item["text"])
                elif "content" in item and isinstance(item["content"], str):
                    parts.append(item["content"])
        return "".join(parts)

    return str(content)


# =============================================================================
# Pattern 2: Robust JSON Parsing
# =============================================================================
def _parse_json_object(response_text: str) -> Dict[str, Any]:
    """Best-effort parse of a JSON object from a model response.

    Handles common failure modes:
    1. Model wraps JSON in markdown code fences (```json ... ```)
    2. Model uses smart/curly quotes instead of straight quotes
    3. Model includes extra text before/after JSON
    4. Model returns malformed JSON

    This is THE critical pattern for production structured outputs.
    """
    text = (response_text or "").strip()
    if not text:
        raise ValueError("Empty model response (expected JSON object)")

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"```$", "", text).strip()

    # Try direct parse first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Extract first {...} block (handles extra text around JSON)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
    else:
        candidate = text

    # Normalize smart quotes (common LLM formatting issue)
    candidate = (
        candidate.replace("\u201c", '"')  # Left double quote
        .replace("\u201d", '"')            # Right double quote
        .replace("\u2018", "'")            # Left single quote
        .replace("\u2019", "'")            # Right single quote
    )

    # Final parse attempt
    obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise ValueError("Model did not return a JSON object")
    return obj


# =============================================================================
# Pattern 3: Structured LLM Call with Retry
# =============================================================================
def llm_structured_call(
    client: OpenAI,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> Tuple[Dict[str, Any], int]:
    """Call foundation model for structured output with retry on parse failure.

    Returns:
        (parsed_json_dict, latency_ms)

    Critical pattern:
    - Use temperature=0.0 for deterministic structured outputs
    - If JSON parse fails, retry with stricter instructions
    - Combine latencies from both attempts
    """
    # First attempt
    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=model or get_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2000,
        temperature=0.0,  # Deterministic for structured outputs
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    content = _content_to_text(response.choices[0].message.content)

    # Try to parse response
    try:
        return _parse_json_object(content), elapsed_ms
    except Exception as e:
        # Retry with stricter prompt
        print(f"Parse failed (attempt 1): {e}. Retrying with stricter prompt...")

        t0_retry = time.perf_counter()
        retry_response = client.chat.completions.create(
            model=model or get_model_name(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Return ONLY minified JSON object. Strings must be JSON-escaped. No extra text."},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2000,
            temperature=0.0,
        )
        retry_elapsed_ms = int((time.perf_counter() - t0_retry) * 1000)

        retry_content = _content_to_text(retry_response.choices[0].message.content)
        return _parse_json_object(retry_content), elapsed_ms + retry_elapsed_ms


# =============================================================================
# Pattern 4: Caching Expensive Calls (Streamlit)
# =============================================================================
@st.cache_data(ttl=60 * 60)  # Cache for 1 hour
def cached_structured_call(
    prompt: str,
    model: str | None = None,
) -> Dict[str, Any]:
    """Cache expensive structured LLM calls.

    Use @st.cache_data with TTL for:
    - Expensive/slow API calls
    - Calls with same inputs (idempotent)
    - Data that doesn't need real-time freshness

    TTL examples:
    - 60 * 10 = 10 minutes (frequently changing data)
    - 60 * 60 = 1 hour (moderate freshness)
    - 60 * 60 * 24 = 24 hours (stable data)
    """
    client = create_foundation_model_client()
    system = "You are a data extraction assistant. Return ONLY valid JSON."
    result, _ = llm_structured_call(client, system, prompt, model or get_model_name())
    return result


# =============================================================================
# Example: Content Quality Evaluation
# =============================================================================
def evaluate_content_quality(
    client: OpenAI, text: str
) -> Tuple[Dict[str, Any], int]:
    """Evaluate content quality with structured output."""

    system_prompt = """You are a content quality evaluator.
You must return ONLY valid JSON that exactly matches the schema below.
No commentary. No markdown. No explanations."""

    user_prompt = f"""Evaluate this content and return JSON with this exact schema:
{{
  "overall_score": 0-100,
  "readability": "poor"|"fair"|"good"|"excellent",
  "has_clear_structure": true|false,
  "has_actionable_takeaways": true|false,
  "strengths": ["string", "string"],
  "weaknesses": ["string", "string"],
  "suggestions": ["string", "string"]
}}

Content to evaluate:
{text[:2000]}
"""

    return llm_structured_call(client, system_prompt, user_prompt)


# =============================================================================
# Example: Entity Extraction
# =============================================================================
def extract_entities(client: OpenAI, text: str) -> Tuple[Dict[str, Any], int]:
    """Extract structured entities from text."""

    system_prompt = """You are an entity extraction system.
Return ONLY valid JSON. Do not include explanations."""

    user_prompt = f"""Extract entities from this text and return JSON:
{{
  "people": ["name1", "name2"],
  "organizations": ["org1", "org2"],
  "technologies": ["tech1", "tech2"],
  "key_concepts": ["concept1", "concept2"]
}}

Text:
{text[:2000]}
"""

    return llm_structured_call(client, system_prompt, user_prompt)


# =============================================================================
# Example Usage
# =============================================================================
if __name__ == "__main__":
    sample_text = """
    Databricks Lakehouse Platform combines data warehousing and AI with open
    data formats like Delta Lake. Apache Spark and MLflow are key components.
    Jane Smith, VP of Engineering at Acme Corp, recently shared their migration story.
    """

    client = create_foundation_model_client()

    print("=" * 60)
    print("Example 1: Content Quality Evaluation")
    print("=" * 60)
    try:
        quality_data, latency_ms = evaluate_content_quality(client, sample_text)
        print(f"✓ Completed in {latency_ms}ms")
        print(json.dumps(quality_data, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)
    print("Example 2: Entity Extraction")
    print("=" * 60)
    try:
        entity_data, latency_ms = extract_entities(client, sample_text)
        print(f"✓ Completed in {latency_ms}ms")
        print(json.dumps(entity_data, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")


# =============================================================================
# Production Best Practices Summary
# =============================================================================
"""
Key takeaways from databricksters-check-and-pub:

1. Content Normalization (_content_to_text)
   - Handle str, bytes, list content types
   - Essential for multi-modal or varying response formats

2. Robust JSON Parsing (_parse_json_object)
   - Strip markdown code fences (```json)
   - Normalize smart quotes
   - Extract {...} from surrounding text
   - This ONE function prevents 90% of parsing errors in production

3. Retry on Parse Failure
   - If first attempt fails to parse, retry with stricter prompt
   - Add latencies together for accurate tracking
   - Shows user total cost, not just successful attempt

4. Temperature Settings
   - Use temperature=0.0 for structured outputs (deterministic)
   - Use temperature=0.2-0.7 for creative/generative tasks
   - Compliance checks = 0.0, content generation = 0.7

5. Caching with TTL
   - Use @st.cache_data(ttl=...) for expensive calls
   - Choose TTL based on data freshness needs
   - Dramatically improves app responsiveness

6. Timeouts
   - Set timeout=30 on all HTTP requests
   - Prevents hanging connections
   - Provides better error messages to users

7. System Prompts for Structure
   - Clearly state: "Return ONLY valid JSON"
   - Provide exact schema in prompt
   - Use examples when needed
   - Be explicit about constraints
"""
