# Claude Code Trace Integration Plan

## Status: Phase 0 Complete ✅

This document captures the plan for integrating Claude Code JSONL trace capture and MLflow tracing with the skill-test framework.

---

## Completed Work

### Files Created

| File | Purpose |
|------|---------|
| `.test/src/skill_test/trace/__init__.py` | Package exports |
| `.test/src/skill_test/trace/models.py` | Data models for traces |
| `.test/src/skill_test/trace/parser.py` | JSONL parsing utilities |
| `.test/src/skill_test/scorers/trace.py` | 7 trace-based scorers |

### Data Models (`trace/models.py`)

```python
@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int

@dataclass
class ToolCall:
    id: str           # "toolu_01S7qwmk3nEirzyaDwPHESzo"
    name: str         # "Write", "Bash", "mcp__databricks__execute_sql"
    input: Dict       # Tool parameters
    timestamp: datetime
    result: str       # Tool output
    success: bool     # Determined from result

@dataclass
class FileOperation:
    type: str         # "create", "edit", "read"
    file_path: str
    content: str

@dataclass
class TraceMetrics:
    session_id: str
    start_time: datetime
    end_time: datetime

    # Tokens
    total_input_tokens: int
    total_output_tokens: int
    total_cache_creation_tokens: int
    total_cache_read_tokens: int

    # Tools
    total_tool_calls: int
    tool_counts: Dict[str, int]      # tool_name -> count
    tool_category_counts: Dict[str, int]  # category -> count
    tool_calls: List[ToolCall]

    # Files
    files_created: List[str]
    files_modified: List[str]
    files_read: List[str]

    # Conversation
    num_turns: int
    num_user_messages: int
    model: str
```

### Trace Scorers (`scorers/trace.py`)

| Scorer | Expectation Key | Purpose |
|--------|-----------------|---------|
| `tool_count` | `tool_limits: {Bash: 5}` | Verify tool usage within limits |
| `token_budget` | `token_budget: {max_total: 50000}` | Check token usage under threshold |
| `required_tools` | `required_tools: [Read, Edit]` | Ensure specific tools were called |
| `banned_tools` | `banned_tools: [rm -rf]` | Ensure dangerous tools avoided |
| `file_existence` | `expected_files: [*.sql]` | Check files were created |
| `tool_sequence` | `tool_sequence: [Read, Edit]` | Verify execution order |
| `category_limits` | `category_limits: {bash: 10}` | Limit by tool category |

### Verified Transcript Structure

Claude Code transcripts are JSONL files at `~/.claude/projects/{project}/{session}.jsonl`.

**Assistant entry with tool_use:**
```json
{
  "type": "assistant",
  "message": {
    "model": "claude-opus-4-5-20251101",
    "content": [
      {"type": "text", "text": "..."},
      {"type": "tool_use", "id": "toolu_...", "name": "Write", "input": {...}}
    ],
    "usage": {
      "input_tokens": 1,
      "cache_creation_input_tokens": 11521,
      "cache_read_input_tokens": 13368,
      "output_tokens": 1757
    }
  },
  "timestamp": "2026-01-13T18:47:29.913Z"
}
```

**Tool result entry:**
```json
{
  "type": "user",
  "message": {
    "content": [{"tool_use_id": "toolu_...", "type": "tool_result", "content": "..."}]
  },
  "toolUseResult": {
    "type": "create",
    "filePath": "/path/to/file.md"
  }
}
```

---

## Remaining Work

### Phase 1: CLI Integration

**File:** `.test/src/skill_test/cli/commands.py`

Add new command `trace-eval`:

```bash
# Score a JSONL file against expectations
skill-test trace-eval spark-declarative-pipelines --trace session.jsonl

# Score from MLflow run
skill-test trace-eval spark-declarative-pipelines --run-id abc123

# Score all traces in a directory
skill-test trace-eval spark-declarative-pipelines --trace-dir ./traces/
```

**Implementation:**
```python
def trace_eval(skill_name: str, trace_path: Optional[str], run_id: Optional[str], ctx: CLIContext):
    """Evaluate a trace against skill expectations."""
    from ..trace.parser import parse_and_compute_metrics
    from ..scorers.trace import get_trace_scorers

    # Load trace
    if trace_path:
        metrics = parse_and_compute_metrics(trace_path)
    elif run_id:
        metrics = get_trace_from_mlflow(run_id)

    # Load expectations from manifest
    manifest = load_manifest(skill_name)
    expectations = manifest.get("trace_expectations", {})

    # Run scorers
    trace_dict = metrics.to_dict()
    results = []
    for scorer in get_trace_scorers():
        result = scorer(trace=trace_dict, expectations=expectations)
        results.append(result)

    return results
```

### Phase 2: YAML Schema Extensions

**manifest.yaml:**
```yaml
scorers:
  enabled:
    - python_syntax
    - tool_count        # NEW
    - token_budget      # NEW
    - file_existence    # NEW

  trace_expectations:   # NEW section
    tool_limits:
      mcp__databricks__execute_sql: 5
      Bash: 3
    token_budget:
      max_input: 50000
      max_output: 10000
    required_tools:
      - Read
      - mcp__databricks__execute_sql
    banned_tools:
      - "rm -rf"
      - "DROP DATABASE"
```

**ground_truth.yaml (per-test overrides):**
```yaml
test_cases:
  - id: "sdp_bronze_001"
    inputs:
      prompt: "Create bronze ingestion pipeline"
    expectations:
      # Existing
      expected_patterns: [...]
      # NEW: per-test trace expectations
      tool_limits:
        mcp__databricks__create_pipeline: 1
      expected_files:
        - "bronze_orders.sql"
    metadata:
      trace_run_id: "abc123"  # Link to MLflow trace
```

### Phase 3: MLflow Autolog Integration

**Setup:** Already configured via:
```bash
mlflow autolog claude -u databricks -n "/Users/alex.miller@databricks.com/Claude Code Skill Traces" .
```

**File:** `.test/src/skill_test/trace/mlflow_integration.py`

```python
def get_trace_from_mlflow(run_id: str) -> TraceMetrics:
    """Extract TraceMetrics from MLflow run."""
    import mlflow

    mlflow.set_tracking_uri("databricks")
    run = mlflow.get_run(run_id)

    # Get trace artifact
    artifact_path = mlflow.artifacts.download_artifacts(
        run_id=run_id, artifact_path="trace.jsonl"
    )

    return parse_and_compute_metrics(artifact_path)

def setup_autolog(project_path: Path, experiment_name: str) -> None:
    """Configure mlflow autolog claude for a project."""
    import subprocess
    subprocess.run([
        "mlflow", "autolog", "claude",
        "-u", "databricks",
        "-n", experiment_name,
        str(project_path)
    ])
```

### Phase 4: GRP Integration

**File:** `.test/src/skill_test/grp/pipeline.py`

Add trace capture to `interactive` command:

```python
def interactive_with_trace(
    skill_name: str,
    prompt: str,
    capture_trace: bool = True,
    ctx: CLIContext
):
    """Run interactive session with trace capture."""

    if capture_trace:
        # Trace is automatically captured via MLflow autolog hooks
        # After session ends, retrieve the trace
        pass

    # Generate response (existing logic)
    response = invoke_claude(prompt)

    # Create GRP candidate with trace metadata
    candidate = GRPCandidate(
        prompt=prompt,
        response=response,
        # ... existing fields ...
        trace_run_id=get_latest_run_id()  # NEW
    )
```

### Phase 5: Evaluate Runner Integration

**File:** `.test/src/skill_test/runners/evaluate.py`

Add trace scorers to evaluation:

```python
from ..scorers.trace import get_trace_scorers

def build_scorers(scorer_config: Dict[str, Any]) -> List:
    # ... existing scorers ...

    # Add trace scorers if enabled
    trace_scorers_enabled = scorer_config.get("trace_scorers", [])
    for name in trace_scorers_enabled:
        if name in TRACE_SCORER_MAP:
            scorers.append(TRACE_SCORER_MAP[name])

    return scorers
```

---

## Testing

### Unit Tests

**File:** `.test/tests/test_trace_parser.py`

```python
def test_parse_transcript():
    """Test parsing a real transcript file."""
    from skill_test.trace.parser import parse_and_compute_metrics

    path = Path.home() / ".claude/projects/.../session.jsonl"
    metrics = parse_and_compute_metrics(path)

    assert metrics.session_id is not None
    assert metrics.total_tool_calls > 0
    assert metrics.total_tokens > 0

def test_tool_count_scorer():
    """Test tool_count scorer with violations."""
    from skill_test.scorers.trace import tool_count

    trace = {"tools": {"by_name": {"Bash": 10}}}
    expectations = {"tool_limits": {"Bash": 5}}

    result = tool_count(trace=trace, expectations=expectations)
    assert result.value == "no"
    assert "10 > 5" in result.rationale
```

### Integration Test

```bash
# 1. Parse existing transcript
python -c "
from skill_test.trace.parser import parse_and_compute_metrics
import json
metrics = parse_and_compute_metrics('~/.claude/projects/.../session.jsonl')
print(json.dumps(metrics.to_dict(), indent=2))
"

# 2. Run trace scorers
skill-test trace-eval spark-declarative-pipelines --trace session.jsonl
```

---

## Dependencies

Add to `pyproject.toml`:
```toml
dependencies = [
    "mlflow[databricks]>=3.4",
    # existing deps...
]
```

---

## Example Usage Flow

```bash
# 1. Setup autolog (already done)
mlflow autolog claude -u databricks -n "Claude Code Skill Traces" .

# 2. Run Claude Code session (trace captured automatically)
claude "Create a bronze ingestion pipeline for JSON files"

# 3. Score the trace
skill-test trace-eval spark-declarative-pipelines --run-id <latest>

# 4. Or run full evaluation including traces
skill-test mlflow-eval spark-declarative-pipelines --include-traces
```

---

## Sources

- [MLflow Tracing Claude Code - Databricks](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code)
- [MLflow autolog claude - MLflow Docs](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/claude_code/)
- [OpenAI Eval Skills Blog](https://developers.openai.com/blog/eval-skills/)
