#!/usr/bin/env python3
"""Extract test cases from Claude Code traces (local or MLflow).

Parses real agent transcripts and auto-generates ground_truth.yaml entries
from user prompt / assistant response pairs.

Supports three trace sources:
1. Local session.jsonl files (--trace)
2. MLflow experiment traces (--experiment-id)
3. Individual MLflow traces (--trace-id or --run-id)

Usage:
    # --- From local session.jsonl ---
    uv run python .test/scripts/trace_to_examples.py \
      --trace ~/.claude/projects/.../session.jsonl \
      --skill databricks-model-serving

    # --- From MLflow experiment (browse traces, pick best ones) ---
    # List recent traces in an experiment
    uv run python .test/scripts/trace_to_examples.py \
      --experiment-id 2452310130108632 --list

    # Extract from all recent traces in an experiment
    uv run python .test/scripts/trace_to_examples.py \
      --experiment-id 2452310130108632 \
      --skill databricks-model-serving

    # Extract from a specific MLflow run
    uv run python .test/scripts/trace_to_examples.py \
      --run-id abc123def456 \
      --skill databricks-model-serving

    # Extract from a specific MLflow trace ID
    uv run python .test/scripts/trace_to_examples.py \
      --trace-id tr-d416fccdab46e2dea6bad1d0bd8aaaa8 \
      --skill databricks-model-serving

    # --- Common options ---
    # With LLM refinement of expectations
    uv run python .test/scripts/trace_to_examples.py \
      --experiment-id 2452310130108632 \
      --skill databricks-model-serving --refine

    # Auto-append to ground_truth.yaml (skip manual review)
    uv run python .test/scripts/trace_to_examples.py \
      --experiment-id 2452310130108632 \
      --skill databricks-model-serving --trust

    # Limit number of traces to process from an experiment
    uv run python .test/scripts/trace_to_examples.py \
      --experiment-id 2452310130108632 \
      --skill databricks-model-serving --limit 5
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import setup_path

setup_path()


def _extract_text_content(message: dict) -> str:
    """Extract text from a message's content array."""
    content = message.get("content", [])
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "\n".join(parts)
    return ""


def _extract_code_blocks(text: str) -> list[dict]:
    """Extract fenced code blocks with language tags."""
    blocks = []
    for match in re.finditer(r"```(\w*)\n(.*?)```", text, re.DOTALL):
        lang = match.group(1) or "text"
        code = match.group(2).strip()
        blocks.append({"language": lang, "code": code})
    return blocks


def _extract_patterns_from_code(code_blocks: list[dict]) -> list[str]:
    """Auto-extract patterns from code blocks (function/class names, SQL keywords)."""
    patterns = []
    for block in code_blocks:
        code = block["code"]
        lang = block["language"]

        if lang == "python":
            for m in re.finditer(r"class\s+(\w+)", code):
                patterns.append(m.group(1))
            for m in re.finditer(r"def\s+(\w+)", code):
                patterns.append(m.group(1))
            for m in re.finditer(r"from\s+([\w.]+)\s+import", code):
                patterns.append(m.group(1))

        elif lang == "sql":
            for m in re.finditer(r"(?:CREATE|ALTER|DROP)\s+(?:TABLE|VIEW|SCHEMA)\s+(\S+)", code, re.I):
                patterns.append(m.group(1))
            for m in re.finditer(r"(?:STREAMING TABLE|MATERIALIZED VIEW)\s+(\S+)", code, re.I):
                patterns.append(m.group(1))

    return list(dict.fromkeys(patterns))  # dedupe preserving order


def _extract_facts_from_response(response: str) -> list[str]:
    """Auto-extract key facts: API names, function calls, class references."""
    facts = []
    for m in re.finditer(r"(mlflow\.\w+(?:\.\w+)*)\(", response):
        facts.append(m.group(1))
    for m in re.finditer(r"(spark\.\w+(?:\.\w+)*)\(", response):
        facts.append(m.group(1))
    for m in re.finditer(r"\b([A-Z]\w+(?:Agent|Client|Config|Builder))\b", response):
        facts.append(m.group(1))
    return list(dict.fromkeys(facts))[:10]


def _categorize_by_tools(tool_names: list[str]) -> str:
    """Infer category from tool usage in the turn."""
    if any("sql" in t.lower() or "dbsql" in t.lower() for t in tool_names):
        return "sql"
    if any("bash" in t.lower() for t in tool_names):
        return "deployment"
    if any("write" in t.lower() or "edit" in t.lower() for t in tool_names):
        return "code_generation"
    return "general"


# ---------------------------------------------------------------------------
# Local trace extraction (session.jsonl)
# ---------------------------------------------------------------------------

def extract_examples_from_file(trace_path: Path, skill_name: str | None = None) -> list[dict]:
    """Parse a session.jsonl and extract test case candidates."""
    from skill_test.trace.parser import parse_transcript_file, link_tool_results

    entries = parse_transcript_file(trace_path)
    link_tool_results(entries)

    examples = []
    idx = 0

    for i, entry in enumerate(entries):
        if entry.type != "user":
            continue
        if entry.tool_use_result:
            continue

        user_text = _extract_text_content(entry.message)
        if not user_text or len(user_text) < 10:
            continue

        assistant_text = ""
        tool_names = []
        for j in range(i + 1, len(entries)):
            if entries[j].type == "assistant":
                assistant_text = _extract_text_content(entries[j].message)
                tool_names = [tc.name for tc in entries[j].tool_calls]
                break
            if entries[j].type == "user" and not entries[j].tool_use_result:
                break

        if not assistant_text or len(assistant_text) < 50:
            continue

        code_blocks = _extract_code_blocks(assistant_text)
        auto_patterns = _extract_patterns_from_code(code_blocks)
        auto_facts = _extract_facts_from_response(assistant_text)
        category = _categorize_by_tools(tool_names)

        prefix = skill_name or "trace"
        example = {
            "id": f"{prefix}_{idx:03d}",
            "inputs": {"prompt": user_text},
            "outputs": {"response": assistant_text},
            "expectations": {},
            "metadata": {
                "category": category,
                "source": "trace",
                "trace_file": str(trace_path.name),
            },
        }

        if auto_patterns:
            example["expectations"]["expected_patterns"] = auto_patterns
        if auto_facts:
            example["expectations"]["expected_facts"] = auto_facts
        if code_blocks:
            langs = list({b["language"] for b in code_blocks if b["language"] != "text"})
            if langs:
                example["metadata"]["languages"] = langs

        examples.append(example)
        idx += 1

    return examples


# ---------------------------------------------------------------------------
# MLflow trace extraction
# ---------------------------------------------------------------------------

def _extract_examples_from_mlflow_trace(trace: Any, skill_name: str | None, idx_offset: int = 0) -> list[dict]:
    """Extract test case candidates from an MLflow Trace object.

    MLflow traces from `mlflow autolog claude` contain spans representing
    the agent conversation. We look for the root span's input/output which
    contains the user prompt and final assistant response.
    """
    examples = []
    prefix = skill_name or "mlflow"

    trace_info = trace.info
    trace_id = trace_info.request_id if hasattr(trace_info, "request_id") else "unknown"

    # Try to get input/output from the trace data
    user_text = ""
    assistant_text = ""

    if trace.data:
        # The root span typically has the full conversation
        spans = trace.data.spans if hasattr(trace.data, "spans") else []

        # Look for the root span (no parent) or the first AGENT/CHAIN span
        root_span = None
        for span in spans:
            parent = getattr(span, "parent_id", None)
            if parent is None or parent == "0":
                root_span = span
                break

        if root_span is None and spans:
            root_span = spans[0]

        if root_span:
            inputs = getattr(root_span, "inputs", None)
            outputs = getattr(root_span, "outputs", None)

            # Extract user prompt from inputs
            if isinstance(inputs, dict):
                # Common patterns: {"messages": [...]}, {"input": "..."}, {"prompt": "..."}
                if "messages" in inputs:
                    msgs = inputs["messages"]
                    if isinstance(msgs, list):
                        for msg in reversed(msgs):
                            if isinstance(msg, dict) and msg.get("role") == "user":
                                user_text = msg.get("content", "")
                                break
                elif "input" in inputs:
                    user_text = str(inputs["input"])
                elif "prompt" in inputs:
                    user_text = str(inputs["prompt"])
            elif isinstance(inputs, str):
                user_text = inputs

            # Extract assistant response from outputs
            if isinstance(outputs, dict):
                if "choices" in outputs:
                    choices = outputs["choices"]
                    if isinstance(choices, list) and choices:
                        msg = choices[0].get("message", {})
                        assistant_text = msg.get("content", "")
                elif "output" in outputs:
                    assistant_text = str(outputs["output"])
                elif "response" in outputs:
                    assistant_text = str(outputs["response"])
            elif isinstance(outputs, str):
                assistant_text = outputs

    if not user_text or len(user_text) < 10:
        return examples
    if not assistant_text or len(assistant_text) < 50:
        return examples

    # Build the test case
    code_blocks = _extract_code_blocks(assistant_text)
    auto_patterns = _extract_patterns_from_code(code_blocks)
    auto_facts = _extract_facts_from_response(assistant_text)

    # Categorize by looking at tool spans
    tool_names = []
    if trace.data and hasattr(trace.data, "spans"):
        for span in trace.data.spans:
            span_type = getattr(span, "span_type", "")
            if span_type == "TOOL" or "tool" in getattr(span, "name", "").lower():
                tool_names.append(getattr(span, "name", "unknown"))

    category = _categorize_by_tools(tool_names)

    example = {
        "id": f"{prefix}_{idx_offset:03d}",
        "inputs": {"prompt": user_text},
        "outputs": {"response": assistant_text},
        "expectations": {},
        "metadata": {
            "category": category,
            "source": "mlflow_trace",
            "trace_id": trace_id,
        },
    }

    if auto_patterns:
        example["expectations"]["expected_patterns"] = auto_patterns
    if auto_facts:
        example["expectations"]["expected_facts"] = auto_facts
    if code_blocks:
        langs = list({b["language"] for b in code_blocks if b["language"] != "text"})
        if langs:
            example["metadata"]["languages"] = langs

    examples.append(example)
    return examples


def list_mlflow_traces(experiment_id: str, limit: int = 20) -> None:
    """List recent traces in an MLflow experiment."""
    import mlflow

    from skill_test.trace.mlflow_integration import _configure_mlflow
    _configure_mlflow()

    print(f"Fetching traces from experiment {experiment_id}...")
    try:
        traces_df = mlflow.search_traces(
            experiment_ids=[experiment_id],
            max_results=limit,
        )
    except Exception as e:
        print(f"Error fetching traces: {e}")
        print("\nMake sure you have authentication configured:")
        print("  export DATABRICKS_HOST='https://<workspace>.cloud.databricks.com'")
        print("  export DATABRICKS_TOKEN='dapi...'")
        sys.exit(1)

    if traces_df.empty:
        print("No traces found in experiment.")
        return

    print(f"\nFound {len(traces_df)} traces:\n")
    print(f"{'Trace ID':<45} {'Status':<10} {'Timestamp':<25} {'Duration'}")
    print("-" * 100)

    for _, row in traces_df.iterrows():
        trace_id = row.get("request_id", "unknown")
        status = row.get("status", "?")
        ts = row.get("timestamp_ms", 0)
        duration = row.get("execution_time_ms", 0)

        from datetime import datetime
        ts_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S") if ts else "?"
        dur_str = f"{duration / 1000:.1f}s" if duration else "?"

        print(f"{trace_id:<45} {status:<10} {ts_str:<25} {dur_str}")

    print(f"\nTo extract examples from a specific trace:")
    print(f"  uv run python .test/scripts/trace_to_examples.py --trace-id <TRACE_ID> --skill <SKILL_NAME>")
    print(f"\nTo extract from all traces in this experiment:")
    print(f"  uv run python .test/scripts/trace_to_examples.py --experiment-id {experiment_id} --skill <SKILL_NAME>")


def extract_examples_from_experiment(experiment_id: str, skill_name: str | None, limit: int = 10) -> list[dict]:
    """Extract examples from recent traces in an MLflow experiment."""
    import mlflow

    from skill_test.trace.mlflow_integration import _configure_mlflow
    _configure_mlflow()

    print(f"Fetching up to {limit} traces from experiment {experiment_id}...")
    try:
        traces_df = mlflow.search_traces(
            experiment_ids=[experiment_id],
            max_results=limit,
            filter_string="status = 'OK'",
        )
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    if traces_df.empty:
        print("No successful traces found.")
        return []

    print(f"Processing {len(traces_df)} traces...")
    all_examples = []

    for _, row in traces_df.iterrows():
        trace_id = row.get("request_id")
        if not trace_id:
            continue
        try:
            trace = mlflow.get_trace(trace_id)
            if trace:
                examples = _extract_examples_from_mlflow_trace(
                    trace, skill_name, idx_offset=len(all_examples)
                )
                all_examples.extend(examples)
                if examples:
                    print(f"  {trace_id}: extracted {len(examples)} example(s)")
        except Exception as e:
            print(f"  {trace_id}: skipped ({e})")

    return all_examples


def extract_examples_from_trace_id(trace_id: str, skill_name: str | None) -> list[dict]:
    """Extract examples from a single MLflow trace by ID."""
    import mlflow

    from skill_test.trace.mlflow_integration import _configure_mlflow
    _configure_mlflow()

    print(f"Fetching trace {trace_id}...")
    trace = mlflow.get_trace(trace_id)
    if trace is None:
        print(f"Trace not found: {trace_id}")
        return []

    return _extract_examples_from_mlflow_trace(trace, skill_name)


def extract_examples_from_run_id(run_id: str, skill_name: str | None) -> list[dict]:
    """Extract examples from an MLflow run (downloads session.jsonl artifact)."""
    from skill_test.trace.mlflow_integration import _configure_mlflow
    _configure_mlflow()

    import mlflow

    print(f"Fetching artifacts from run {run_id}...")

    # Try to download session.jsonl artifact
    artifact_names = ["trace.jsonl", "session.jsonl", "transcript.jsonl"]
    artifact_path = None

    for name in artifact_names:
        try:
            artifact_path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=name)
            print(f"  Downloaded {name}")
            break
        except Exception:
            continue

    if artifact_path:
        return extract_examples_from_file(Path(artifact_path), skill_name)

    # Fallback: try MLflow traces API
    print("  No JSONL artifact found, trying traces API...")
    try:
        traces_df = mlflow.search_traces(
            experiment_ids=[mlflow.get_run(run_id).info.experiment_id],
            filter_string=f"run_id = '{run_id}'",
            max_results=10,
        )
        if not traces_df.empty:
            all_examples = []
            for _, row in traces_df.iterrows():
                tid = row.get("request_id")
                if tid:
                    trace = mlflow.get_trace(tid)
                    if trace:
                        all_examples.extend(
                            _extract_examples_from_mlflow_trace(trace, skill_name, len(all_examples))
                        )
            return all_examples
    except Exception as e:
        print(f"  Traces API failed: {e}")

    print("  No extractable data found in this run.")
    return []


# ---------------------------------------------------------------------------
# LLM refinement and output
# ---------------------------------------------------------------------------

def refine_with_llm(examples: list[dict], skill_name: str) -> list[dict]:
    """Use an LLM to review and refine auto-extracted expectations."""
    import litellm
    import json

    for ex in examples:
        prompt_text = ex["inputs"]["prompt"][:200]
        response_text = ex["outputs"]["response"][:1000]
        current_patterns = ex["expectations"].get("expected_patterns", [])
        current_facts = ex["expectations"].get("expected_facts", [])

        messages = [
            {
                "role": "system",
                "content": (
                    "You are reviewing auto-extracted test expectations for a "
                    f"Databricks skill called '{skill_name}'. Refine the patterns "
                    "and facts to be more precise and meaningful. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Prompt: {prompt_text}\n\n"
                    f"Response excerpt: {response_text}\n\n"
                    f"Auto-extracted patterns: {json.dumps(current_patterns)}\n"
                    f"Auto-extracted facts: {json.dumps(current_facts)}\n\n"
                    "Return a JSON object with:\n"
                    '- "expected_patterns": list of regex pattern strings\n'
                    '- "expected_facts": list of fact strings that must appear\n'
                    "Keep only patterns/facts that are genuinely important for correctness."
                ),
            },
        ]

        try:
            from skill_test.optimize.config import DEFAULT_GEN_LM
            resp = litellm.completion(model=DEFAULT_GEN_LM, messages=messages)
            content = resp.choices[0].message.content
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                refined = json.loads(json_match.group())
                if "expected_patterns" in refined:
                    ex["expectations"]["expected_patterns"] = refined["expected_patterns"]
                if "expected_facts" in refined:
                    ex["expectations"]["expected_facts"] = refined["expected_facts"]
        except Exception as e:
            print(f"  Warning: LLM refinement failed for {ex['id']}: {e}")

    return examples


def save_examples(examples: list[dict], output_path: Path) -> None:
    """Save examples to a YAML file."""
    import yaml

    data = {"test_cases": examples}
    with open(output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"Saved {len(examples)} examples to {output_path}")


def append_to_ground_truth(examples: list[dict], skill_name: str) -> None:
    """Append examples directly to a skill's ground_truth.yaml."""
    import yaml

    from skill_test.dataset import get_dataset_source

    try:
        source = get_dataset_source(skill_name)
        existing = source.load()
        existing_ids = {r.id for r in existing}
        gt_path = source.yaml_path
    except FileNotFoundError:
        gt_path = Path(".test/skills") / skill_name / "ground_truth.yaml"
        gt_path.parent.mkdir(parents=True, exist_ok=True)
        existing_ids = set()

    new_examples = [ex for ex in examples if ex["id"] not in existing_ids]
    if not new_examples:
        print("No new examples to add (all IDs already exist).")
        return

    if gt_path.exists():
        with open(gt_path) as f:
            data = yaml.safe_load(f) or {"test_cases": []}
    else:
        data = {"test_cases": []}

    data["test_cases"].extend(new_examples)

    with open(gt_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Appended {len(new_examples)} examples to {gt_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract test cases from Claude Code traces (local or MLflow)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Trace sources (mutually exclusive)
    source_group = parser.add_argument_group("trace source (pick one)")
    source_group.add_argument(
        "--trace", "-t",
        type=Path,
        default=None,
        help="Path to local session.jsonl transcript file",
    )
    source_group.add_argument(
        "--experiment-id",
        default=None,
        help="MLflow experiment ID to extract traces from (e.g., 2452310130108632)",
    )
    source_group.add_argument(
        "--run-id",
        default=None,
        help="MLflow run ID to extract traces from",
    )
    source_group.add_argument(
        "--trace-id",
        default=None,
        help="MLflow trace ID (e.g., tr-d416fccdab46e2dea6bad1d0bd8aaaa8)",
    )

    # Common options
    parser.add_argument(
        "--skill", "-s",
        default=None,
        help="Skill name to tag examples with (e.g., databricks-model-serving)",
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Use LLM to review and refine auto-extracted expectations",
    )
    parser.add_argument(
        "--trust",
        action="store_true",
        help="Auto-append to ground_truth.yaml instead of writing candidates.yaml",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output file path (default: candidates.yaml in skill dir or cwd)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max number of traces to process from an experiment (default: 10)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_traces",
        help="List traces in the experiment without extracting (use with --experiment-id)",
    )

    args = parser.parse_args()

    # Validate: at least one source required
    sources = [args.trace, args.experiment_id, args.run_id, args.trace_id]
    if not any(sources):
        parser.error("Provide a trace source: --trace, --experiment-id, --run-id, or --trace-id")

    # List mode
    if args.list_traces:
        if not args.experiment_id:
            parser.error("--list requires --experiment-id")
        list_mlflow_traces(args.experiment_id, limit=args.limit)
        return

    # Extract examples based on source
    examples = []

    if args.trace:
        if not args.trace.exists():
            print(f"Error: trace file not found: {args.trace}")
            sys.exit(1)
        print(f"Parsing local trace: {args.trace}")
        examples = extract_examples_from_file(args.trace, args.skill)

    elif args.experiment_id:
        examples = extract_examples_from_experiment(args.experiment_id, args.skill, limit=args.limit)

    elif args.run_id:
        examples = extract_examples_from_run_id(args.run_id, args.skill)

    elif args.trace_id:
        examples = extract_examples_from_trace_id(args.trace_id, args.skill)

    print(f"\nExtracted {len(examples)} candidate test cases")

    if not examples:
        print("No suitable prompt/response pairs found.")
        sys.exit(0)

    if args.refine:
        print("Refining expectations with LLM...")
        examples = refine_with_llm(examples, args.skill or "unknown")

    if args.trust and args.skill:
        append_to_ground_truth(examples, args.skill)
    else:
        output_path = args.output
        if output_path is None:
            if args.skill:
                output_path = Path(".test/skills") / args.skill / "candidates.yaml"
            else:
                output_path = Path("candidates.yaml")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_examples(examples, output_path)


if __name__ == "__main__":
    main()
