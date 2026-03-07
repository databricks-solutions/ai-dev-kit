# MLflow 3 Trace Analysis Patterns

Working code patterns for analyzing MLflow traces across agent architectures.

## When to Use MCP vs Python SDK

| Use Case | Recommended Approach |
|----------|---------------------|
| Interactive trace exploration | **MLflow MCP Server** - Quick searches, field extraction |
| Agent-based analysis | **MLflow MCP Server** - Sub-agents search and tag traces |
| Evaluation script generation | **MLflow Python SDK** - Generate runnable Python code |
| Custom analysis pipelines | **MLflow Python SDK** - Full control, complex aggregation |
| Dataset building from traces | **MLflow Python SDK** - Convert traces to eval format |
| CI/CD integration | **MLflow Python SDK** - Standalone scripts |

### MLflow MCP Server (for Agent Use)

Best for interactive exploration and agent-based trace analysis:
- `search_traces` - Filter and search with `extract_fields`
- `get_trace` - Deep dive with selective field extraction
- `set_trace_tag` - Tag traces for later dataset building
- `log_feedback` - Store analysis findings persistently
- `log_expectation` - Store ground truth for evaluation

### MLflow Python SDK (for Code Generation)

Best for generating runnable evaluation scripts:
- `mlflow.search_traces()` - Programmatic trace access
- `mlflow.genai.evaluate()` - Run evaluations
- `MlflowClient()` - Full API access
- DataFrame operations - Complex aggregation and analysis

---

## Table of Contents

| # | Pattern | Description |
|---|---------|-------------|
| 1 | [Fetching Traces](#pattern-1-fetching-traces-from-mlflow) | Get traces from experiment |
| 2 | [Get Single Trace](#pattern-2-get-single-trace-by-id) | Fetch specific trace by ID |
| 3 | [Span Hierarchy](#pattern-3-span-hierarchy-analysis) | Analyze parent-child structure |
| 4 | [Latency by Span Type](#pattern-4-latency-breakdown-by-span-type) | LLM, TOOL, RETRIEVER breakdown |
| 5 | [Latency by Component](#pattern-5-latency-breakdown-by-component-name) | Stage/component timing |
| 6 | [Bottleneck Detection](#pattern-6-bottleneck-detection) | Find slowest components |
| 7 | [Error Detection](#pattern-7-error-pattern-detection) | Find and categorize errors |
| 8 | [Tool Call Analysis](#pattern-8-tool-call-analysis) | Analyze tool/function calls |
| 9 | [LLM Call Analysis](#pattern-9-llm-call-analysis) | Token usage and latency |
| 10 | [Trace Comparison](#pattern-10-trace-comparison) | Compare multiple traces |
| 11 | [Trace Report](#pattern-11-generate-trace-analysis-report) | Comprehensive report generation |
| 12 | [MCP Server Usage](#pattern-12-using-mlflow-mcp-server-for-trace-analysis) | Quick trace lookups via MCP |
| 13 | [Architecture Detection](#pattern-13-architecture-detection) | Auto-detect agent type |
| 14 | [Assessments via MCP](#pattern-14-using-assessments-for-persistent-analysis) | Store findings in MLflow |

---

## Pattern 1: Fetching Traces from MLflow

Get traces from an experiment for analysis.

```python
import mlflow
from mlflow import MlflowClient

client = MlflowClient()

# Get traces from experiment by ID
traces = client.search_traces(
    experiment_ids=["your_experiment_id"],
    max_results=100
)

# Get traces from experiment by name
experiment = mlflow.get_experiment_by_name("/Users/user@domain.com/my-experiment")
traces = client.search_traces(
    experiment_ids=[experiment.experiment_id],
    max_results=50
)

# Filter traces by time range
from datetime import datetime, timedelta
yesterday = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
traces = client.search_traces(
    experiment_ids=["your_experiment_id"],
    filter_string=f"timestamp_ms > {yesterday}"
)
```

---

## Pattern 2: Get Single Trace by ID

Fetch a specific trace for detailed analysis.

```python
from mlflow import MlflowClient

client = MlflowClient()

# Get trace by ID
trace = client.get_trace(trace_id="tr-abc123def456")

# Access trace info
print(f"Trace ID: {trace.info.trace_id}")
print(f"Status: {trace.info.status}")
print(f"Execution time: {trace.info.execution_time_ms}ms")

# Access trace data (spans)
spans = trace.data.spans
print(f"Total spans: {len(spans)}")
```

---

## Pattern 3: Span Hierarchy Analysis

Analyze the hierarchical structure of spans in a trace.

```python
from mlflow.entities import Trace
from typing import Dict, List, Any

def analyze_span_hierarchy(trace: Trace) -> Dict[str, Any]:
    """Analyze span hierarchy and structure.

    Works for any agent architecture (DSPy, LangGraph, etc.)
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    # Build parent-child relationships
    span_by_id = {s.span_id: s for s in spans}
    children = {}
    root_spans = []

    for span in spans:
        if span.parent_id is None:
            root_spans.append(span)
        else:
            if span.parent_id not in children:
                children[span.parent_id] = []
            children[span.parent_id].append(span)

    def build_tree(span, depth=0):
        """Recursively build span tree."""
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        node = {
            "name": span.name,
            "span_type": str(span.span_type) if span.span_type else "UNKNOWN",
            "duration_ms": round(duration_ms, 2),
            "depth": depth,
            "children": []
        }
        for child in children.get(span.span_id, []):
            node["children"].append(build_tree(child, depth + 1))
        return node

    return {
        "root_count": len(root_spans),
        "total_spans": len(spans),
        "hierarchy": [build_tree(root) for root in root_spans]
    }

# Usage
hierarchy = analyze_span_hierarchy(trace)
print(f"Root spans: {hierarchy['root_count']}")
print(f"Total spans: {hierarchy['total_spans']}")
```

---

## Pattern 4: Latency Breakdown by Span Type

Analyze latency distribution across span types.

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, List
from collections import defaultdict

def latency_by_span_type(trace: Trace) -> Dict[str, Dict]:
    """Break down latency by span type.

    Returns latency stats for each span type (LLM, TOOL, RETRIEVER, etc.)
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    type_latencies = defaultdict(list)

    for span in spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        span_type = str(span.span_type) if span.span_type else "UNKNOWN"
        type_latencies[span_type].append({
            "name": span.name,
            "duration_ms": duration_ms
        })

    results = {}
    for span_type, items in type_latencies.items():
        durations = [i["duration_ms"] for i in items]
        results[span_type] = {
            "count": len(items),
            "total_ms": round(sum(durations), 2),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "max_ms": round(max(durations), 2),
            "min_ms": round(min(durations), 2),
            "spans": items
        }

    return results

# Usage
latency_stats = latency_by_span_type(trace)
for span_type, stats in sorted(latency_stats.items(), key=lambda x: -x[1]["total_ms"]):
    print(f"{span_type}: {stats['total_ms']}ms total ({stats['count']} spans)")
```

---

## Pattern 5: Latency Breakdown by Component Name

Analyze latency by component/stage names (architecture-agnostic).

```python
from mlflow.entities import Trace
from typing import Dict, List
from collections import defaultdict

def latency_by_component(
    trace: Trace,
    component_patterns: List[str] = None
) -> Dict[str, Dict]:
    """Break down latency by component name patterns.

    Args:
        trace: MLflow trace to analyze
        component_patterns: Optional list of patterns to look for.
                           If None, extracts all unique span names.

    Works with any architecture - DSPy stages, LangGraph nodes, etc.
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    component_latencies = defaultdict(list)

    for span in spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        span_name = span.name.lower()

        if component_patterns:
            # Match against patterns
            for pattern in component_patterns:
                if pattern.lower() in span_name:
                    component_latencies[pattern].append({
                        "span_name": span.name,
                        "duration_ms": duration_ms
                    })
                    break
        else:
            # Use span name directly
            component_latencies[span.name].append({
                "duration_ms": duration_ms
            })

    results = {}
    for component, items in component_latencies.items():
        durations = [i["duration_ms"] for i in items]
        results[component] = {
            "count": len(items),
            "total_ms": round(sum(durations), 2),
            "avg_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "max_ms": round(max(durations), 2) if durations else 0,
        }

    return results

# Usage - DSPy multi-agent
dspy_components = ["classifier", "rewriter", "gatherer", "executor"]
stats = latency_by_component(trace, dspy_components)

# Usage - LangGraph
langgraph_components = ["planner", "executor", "tool_call", "compress"]
stats = latency_by_component(trace, langgraph_components)

# Usage - auto-detect all components
stats = latency_by_component(trace)
```

---

## Pattern 6: Bottleneck Detection

Find the slowest components in a trace.

```python
from mlflow.entities import Trace
from typing import Dict, List, Tuple

def find_bottlenecks(
    trace: Trace,
    top_n: int = 5,
    exclude_patterns: List[str] = None
) -> List[Dict]:
    """Find the slowest spans in a trace.

    Args:
        trace: MLflow trace to analyze
        top_n: Number of slowest spans to return
        exclude_patterns: Span name patterns to exclude (e.g., wrapper spans)

    Returns:
        List of slowest spans with timing info
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()
    exclude_patterns = exclude_patterns or ["forward", "predict", "root"]

    span_timings = []
    for span in spans:
        # Skip excluded patterns
        span_name_lower = span.name.lower()
        if any(p in span_name_lower for p in exclude_patterns):
            continue

        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        span_timings.append({
            "name": span.name,
            "span_type": str(span.span_type) if span.span_type else "UNKNOWN",
            "duration_ms": round(duration_ms, 2),
            "span_id": span.span_id
        })

    # Sort by duration descending
    span_timings.sort(key=lambda x: -x["duration_ms"])

    return span_timings[:top_n]

# Usage
bottlenecks = find_bottlenecks(trace, top_n=5)
print("Top 5 Slowest Spans:")
for i, b in enumerate(bottlenecks, 1):
    print(f"  {i}. {b['name']} ({b['span_type']}): {b['duration_ms']}ms")
```

---

## Pattern 7: Error Pattern Detection

Find and analyze error patterns in traces.

```python
from mlflow.entities import Trace, SpanStatusCode
from typing import Dict, List

def detect_errors(trace: Trace) -> Dict[str, List]:
    """Detect error patterns in a trace.

    Returns categorized errors with context.
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    errors = {
        "failed_spans": [],
        "exceptions": [],
        "empty_outputs": [],
        "warnings": []
    }

    for span in spans:
        # Check span status
        if span.status and span.status.status_code == SpanStatusCode.ERROR:
            errors["failed_spans"].append({
                "name": span.name,
                "span_type": str(span.span_type),
                "error_message": span.status.description if span.status.description else "Unknown error"
            })

        # Check for exceptions in events
        if span.events:
            for event in span.events:
                if "exception" in event.name.lower():
                    errors["exceptions"].append({
                        "span_name": span.name,
                        "event": event.name,
                        "attributes": event.attributes
                    })

        # Check for empty outputs (potential issue)
        if span.outputs is None or span.outputs == {} or span.outputs == []:
            errors["empty_outputs"].append({
                "name": span.name,
                "span_type": str(span.span_type)
            })

    return errors

# Usage
errors = detect_errors(trace)
if errors["failed_spans"]:
    print(f"Found {len(errors['failed_spans'])} failed spans")
    for e in errors["failed_spans"]:
        print(f"  - {e['name']}: {e['error_message']}")
```

---

## Pattern 8: Tool Call Analysis

Analyze tool/function calls in a trace.

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, List

def analyze_tool_calls(trace: Trace) -> Dict[str, Any]:
    """Analyze tool calls in a trace.

    Works with UC functions, LangChain tools, or any TOOL span type.
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    # Find tool spans
    tool_spans = [s for s in spans if s.span_type == SpanType.TOOL]

    tool_calls = []
    for span in tool_spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6

        # Extract tool name (handle fully qualified names)
        tool_name = span.name
        if "." in tool_name:
            tool_name_short = tool_name.split(".")[-1]
        else:
            tool_name_short = tool_name

        tool_calls.append({
            "tool_name": tool_name_short,
            "full_name": span.name,
            "duration_ms": round(duration_ms, 2),
            "inputs": span.inputs,
            "outputs_preview": str(span.outputs)[:200] if span.outputs else None,
            "success": span.status.status_code != SpanStatusCode.ERROR if span.status else True
        })

    # Aggregate stats
    tool_stats = {}
    for tc in tool_calls:
        name = tc["tool_name"]
        if name not in tool_stats:
            tool_stats[name] = {"count": 0, "total_ms": 0, "successes": 0}
        tool_stats[name]["count"] += 1
        tool_stats[name]["total_ms"] += tc["duration_ms"]
        if tc["success"]:
            tool_stats[name]["successes"] += 1

    return {
        "total_tool_calls": len(tool_calls),
        "unique_tools": len(tool_stats),
        "calls": tool_calls,
        "stats": tool_stats
    }

# Usage
tool_analysis = analyze_tool_calls(trace)
print(f"Total tool calls: {tool_analysis['total_tool_calls']}")
for tool, stats in tool_analysis['stats'].items():
    print(f"  {tool}: {stats['count']} calls, {stats['total_ms']}ms total")
```

---

## Pattern 9: LLM Call Analysis

Analyze LLM calls in a trace.

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, List, Any

def analyze_llm_calls(trace: Trace) -> Dict[str, Any]:
    """Analyze LLM calls in a trace.

    Extracts model info, token usage, and latency.
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    # Find LLM/CHAT_MODEL spans
    llm_spans = [s for s in spans
                 if s.span_type in [SpanType.LLM, SpanType.CHAT_MODEL]]

    llm_calls = []
    for span in llm_spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6

        # Extract token info from attributes
        attributes = span.attributes or {}

        llm_calls.append({
            "name": span.name,
            "duration_ms": round(duration_ms, 2),
            "model": attributes.get("mlflow.chat_model.model") or attributes.get("llm.model_name"),
            "input_tokens": attributes.get("mlflow.chat_model.input_tokens"),
            "output_tokens": attributes.get("mlflow.chat_model.output_tokens"),
            "total_tokens": attributes.get("mlflow.chat_model.total_tokens"),
        })

    # Calculate totals
    total_input = sum(c["input_tokens"] or 0 for c in llm_calls)
    total_output = sum(c["output_tokens"] or 0 for c in llm_calls)
    total_latency = sum(c["duration_ms"] for c in llm_calls)

    return {
        "total_llm_calls": len(llm_calls),
        "total_latency_ms": round(total_latency, 2),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "calls": llm_calls
    }

# Usage
llm_analysis = analyze_llm_calls(trace)
print(f"LLM calls: {llm_analysis['total_llm_calls']}")
print(f"Total tokens: {llm_analysis['total_input_tokens']} in / {llm_analysis['total_output_tokens']} out")
print(f"LLM latency: {llm_analysis['total_latency_ms']}ms")
```

---

## Pattern 10: Trace Comparison

Compare multiple traces to identify patterns.

```python
from mlflow.entities import Trace
from typing import List, Dict, Any

def compare_traces(traces: List[Trace]) -> Dict[str, Any]:
    """Compare multiple traces to identify patterns.

    Useful for before/after comparisons or batch analysis.
    """
    trace_stats = []

    for trace in traces:
        spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

        # Get root span for total time
        root_spans = [s for s in spans if s.parent_id is None]
        total_ms = 0
        if root_spans:
            root = root_spans[0]
            total_ms = (root.end_time_ns - root.start_time_ns) / 1e6

        trace_stats.append({
            "trace_id": trace.info.trace_id,
            "total_ms": round(total_ms, 2),
            "span_count": len(spans),
            "status": str(trace.info.status)
        })

    # Calculate aggregates
    latencies = [t["total_ms"] for t in trace_stats]

    return {
        "trace_count": len(traces),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "min_latency_ms": round(min(latencies), 2) if latencies else 0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0,
        "p50_latency_ms": round(sorted(latencies)[len(latencies)//2], 2) if latencies else 0,
        "success_rate": sum(1 for t in trace_stats if "OK" in t["status"]) / len(trace_stats) if trace_stats else 0,
        "traces": trace_stats
    }

# Usage
comparison = compare_traces(traces)
print(f"Analyzed {comparison['trace_count']} traces")
print(f"Avg latency: {comparison['avg_latency_ms']}ms")
print(f"Success rate: {comparison['success_rate']:.1%}")
```

---

## Pattern 11: Generate Trace Analysis Report

Combine multiple analysis patterns into a comprehensive report.

```python
from mlflow.entities import Trace
from typing import Dict, Any

def generate_trace_report(trace: Trace) -> Dict[str, Any]:
    """Generate comprehensive trace analysis report.

    Combines hierarchy, latency, errors, and bottleneck analysis.
    """
    # Import analysis functions (from patterns above)
    hierarchy = analyze_span_hierarchy(trace)
    latency_by_type = latency_by_span_type(trace)
    bottlenecks = find_bottlenecks(trace, top_n=3)
    errors = detect_errors(trace)
    tool_analysis = analyze_tool_calls(trace)
    llm_analysis = analyze_llm_calls(trace)

    # Get root span info
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()
    root_spans = [s for s in spans if s.parent_id is None]
    total_ms = 0
    if root_spans:
        root = root_spans[0]
        total_ms = (root.end_time_ns - root.start_time_ns) / 1e6

    return {
        "summary": {
            "trace_id": trace.info.trace_id,
            "status": str(trace.info.status),
            "total_duration_ms": round(total_ms, 2),
            "total_spans": len(spans),
        },
        "hierarchy": hierarchy,
        "latency_by_type": latency_by_type,
        "bottlenecks": bottlenecks,
        "errors": errors,
        "tool_calls": tool_analysis,
        "llm_calls": llm_analysis,
        "recommendations": generate_recommendations(
            bottlenecks, errors, llm_analysis, total_ms
        )
    }

def generate_recommendations(
    bottlenecks: List[Dict],
    errors: Dict,
    llm_analysis: Dict,
    total_ms: float
) -> List[str]:
    """Generate actionable recommendations from analysis."""
    recommendations = []

    # Latency recommendations
    if bottlenecks and bottlenecks[0]["duration_ms"] > total_ms * 0.5:
        b = bottlenecks[0]
        recommendations.append(
            f"BOTTLENECK: '{b['name']}' takes {b['duration_ms']/total_ms*100:.0f}% of total time. "
            f"Consider optimizing this component."
        )

    # LLM recommendations
    if llm_analysis["total_llm_calls"] > 5:
        recommendations.append(
            f"HIGH LLM CALLS: {llm_analysis['total_llm_calls']} LLM calls detected. "
            f"Consider batching or reducing calls."
        )

    # Error recommendations
    if errors["failed_spans"]:
        recommendations.append(
            f"ERRORS: {len(errors['failed_spans'])} failed spans detected. "
            f"Review: {[e['name'] for e in errors['failed_spans'][:3]]}"
        )

    if not recommendations:
        recommendations.append("No major issues detected. Trace looks healthy.")

    return recommendations

# Usage
report = generate_trace_report(trace)
print(f"Trace {report['summary']['trace_id']}")
print(f"Duration: {report['summary']['total_duration_ms']}ms")
print(f"Spans: {report['summary']['total_spans']}")
print("\nRecommendations:")
for rec in report['recommendations']:
    print(f"  - {rec}")
```

---

## Pattern 12: Using MLflow MCP Server for Trace Analysis

Use the MLflow MCP server for quick trace lookups.

```python
# Via Claude Code, use MCP server tools:

# Search traces in an experiment
mcp__mlflow-mcp__search_traces(
    experiment_id="your_experiment_id",
    max_results=10,
    output="table"
)

# Get detailed trace info
mcp__mlflow-mcp__get_trace(
    trace_id="tr-abc123",
    extract_fields="info.trace_id,info.status,data.spans.*.name"
)

# Filter by status
mcp__mlflow-mcp__search_traces(
    experiment_id="123",
    filter_string="status = 'OK'",
    max_results=20
)
```

---

## Pattern 13: Architecture Detection

Auto-detect agent architecture from trace structure.

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, Any

def detect_architecture(trace: Trace) -> Dict[str, Any]:
    """Detect agent architecture from trace patterns.

    Returns architecture type and key characteristics.
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()
    span_names = [s.name.lower() for s in spans]
    span_types = [s.span_type for s in spans]

    # Architecture indicators
    indicators = {
        "dspy_multi_agent": any(
            p in " ".join(span_names)
            for p in ["classifier", "rewriter", "gatherer", "executor"]
        ),
        "langgraph": any(
            p in " ".join(span_names)
            for p in ["langgraph", "graph", "node", "state"]
        ),
        "rag": SpanType.RETRIEVER in span_types,
        "tool_calling": SpanType.TOOL in span_types,
        "simple_chat": len(set(span_types)) <= 2 and SpanType.CHAT_MODEL in span_types,
    }

    # Determine primary architecture
    if indicators["dspy_multi_agent"]:
        arch_type = "dspy_multi_agent"
    elif indicators["langgraph"]:
        arch_type = "langgraph"
    elif indicators["rag"] and indicators["tool_calling"]:
        arch_type = "rag_with_tools"
    elif indicators["rag"]:
        arch_type = "rag"
    elif indicators["tool_calling"]:
        arch_type = "tool_calling"
    else:
        arch_type = "simple_chat"

    return {
        "architecture": arch_type,
        "indicators": indicators,
        "span_type_distribution": {
            str(st): sum(1 for s in spans if s.span_type == st)
            for st in set(span_types)
        }
    }

# Usage
arch = detect_architecture(trace)
print(f"Detected architecture: {arch['architecture']}")
print(f"Span types: {arch['span_type_distribution']}")
```

---

## Best Practices

### 1. Always Handle Missing Data
```python
# Traces may have incomplete data
spans = trace.data.spans if hasattr(trace, 'data') else []
duration = (span.end_time_ns - span.start_time_ns) / 1e6 if span.end_time_ns else 0
```

### 2. Normalize Span Names
```python
# Handle fully qualified names (UC functions, etc.)
def normalize_name(name: str) -> str:
    return name.split(".")[-1] if "." in name else name
```

### 3. Use Appropriate Filters
```python
# Exclude wrapper spans for accurate bottleneck detection
exclude = ["forward", "predict", "__init__", "root"]
```

### 4. Cache Expensive Analysis
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_trace_analysis(trace_id: str):
    trace = client.get_trace(trace_id)
    return generate_trace_report(trace)
```

---

## Pattern 14: Using Assessments for Persistent Analysis

Store analysis findings directly in MLflow for later use. Use MCP tools during agent sessions.

### Log Analysis Feedback (via MCP)

```
# Store a finding during agent analysis
mcp__mlflow-mcp__log_feedback(
    trace_id="tr-abc123",
    name="bottleneck_detected",
    value="retriever",
    source_type="CODE",
    rationale="Retriever span accounts for 65% of total latency"
)
```

### Log Expected Behavior / Ground Truth (via MCP)

```
# When you know what the correct output should be
mcp__mlflow-mcp__log_expectation(
    trace_id="tr-abc123",
    name="expected_output",
    value='{"status": "success", "answer": "The quarterly revenue was $2.3M"}'
)
```

### Retrieve Assessments (via MCP)

```
mcp__mlflow-mcp__get_assessment(
    trace_id="tr-abc123",
    assessment_id="bottleneck_detected"
)
```

### Search Tagged Traces for Dataset Building (via MCP)

After tagging traces during analysis, search for them later:

```
# Find all traces tagged as evaluation candidates
mcp__mlflow-mcp__search_traces(
    experiment_id="123",
    filter_string="tags.eval_candidate = 'error_case'",
    extract_fields="info.trace_id,data.request,data.response"
)
```

### Convert Tagged Traces to Dataset (Python SDK)

When generating evaluation code, use Python SDK to build datasets:

```python
import mlflow

# Search for tagged traces
traces = mlflow.search_traces(
    filter_string="tags.eval_candidate = 'error_case'",
    max_results=100
)

# Convert to evaluation dataset format
eval_data = []
for _, trace in traces.iterrows():
    eval_data.append({
        "inputs": trace["request"],
        "outputs": trace["response"],
        "metadata": {"source_trace": trace["trace_id"]}
    })

# Use in evaluation
results = mlflow.genai.evaluate(
    data=eval_data,
    scorers=[...]
)
```
