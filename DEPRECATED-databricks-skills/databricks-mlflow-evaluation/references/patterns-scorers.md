# MLflow 3 Scorer Patterns

Working code patterns for creating and using scorers in MLflow 3 GenAI.

## Table of Contents

| # | Pattern | Description |
|---|---------|-------------|
| 1 | [Built-in Guidelines Scorer](#pattern-1-built-in-guidelines-scorer) | Natural language criteria evaluation |
| 2 | [Correctness with Ground Truth](#pattern-2-correctness-scorer-with-ground-truth) | Expected answers/facts validation |
| 3 | [RAG with RetrievalGroundedness](#pattern-3-rag-evaluation-with-retrievalgroundedness) | Check responses grounded in context |
| 4 | [Simple Custom Scorer (Boolean)](#pattern-4-simple-custom-scorer-boolean) | Pass/fail checks |
| 5 | [Custom Scorer with Feedback](#pattern-5-custom-scorer-with-feedback-object) | Return rationale and custom names |
| 6 | [Multiple Metrics Scorer](#pattern-6-custom-scorer-with-multiple-metrics) | One scorer, multiple metrics |
| 7 | [Wrapping LLM Judge](#pattern-7-custom-scorer-wrapping-llm-judge) | Custom context for built-in judges |
| 8 | [Trace-Based Scorer](#pattern-8-trace-based-scorer) | Analyze execution details |
| 9 | [Class-Based Scorer](#pattern-9-class-based-scorer-with-configuration) | Configurable/stateful scorers |
| 10 | [Conditional Scoring](#pattern-10-conditional-scoring-based-on-input) | Different rules per input type |
| 11 | [Aggregations](#pattern-11-scorer-with-aggregations) | Numeric stats (mean, median, p90) |
| 12 | [Custom Make Judge](#pattern-12-custom-make-judge) | Complex multi-level evaluation |
| 13 | [Per-Stage Accuracy](#pattern-13-per-stagecomponent-accuracy-scorer) | Multi-agent component verification |
| 14 | [Tool Selection Accuracy](#pattern-14-tool-selection-accuracy-scorer) | Verify correct tools called |
| 15 | [Stage Latency Scorer](#pattern-15-stage-latency-scorer-multiple-metrics) | Per-stage latency metrics |
| 16 | [Component Accuracy Factory](#pattern-16-component-accuracy-factory) | Reusable scorer factory |

---

## Pattern 1: Built-in Guidelines Scorer

Use for evaluating against natural language criteria.

```python
from mlflow.genai.scorers import Guidelines
import mlflow

# Single guideline
tone_scorer = Guidelines(
    name="professional_tone",
    guidelines="The response must maintain a professional, helpful tone throughout"
)

# Multiple guidelines (evaluated together)
quality_scorer = Guidelines(
    name="response_quality",
    guidelines=[
        "The response must be concise and under 200 words",
        "The response must directly address the user's question",
        "The response must not include made-up information"
    ]
)

# With custom judge model
custom_scorer = Guidelines(
    name="custom_check",
    guidelines="Response must follow company policy",
    model="databricks:/databricks-gpt-oss-120b"
)

# Use in evaluation
results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=my_app,
    scorers=[tone_scorer, quality_scorer]
)
```

---

## Pattern 2: Correctness Scorer with Ground Truth

Use when you have expected answers or facts.

```python
from mlflow.genai.scorers import Correctness

# Dataset with expected facts
eval_data = [
    {
        "inputs": {"question": "What is MLflow?"},
        "expectations": {
            "expected_facts": [
                "MLflow is open-source",
                "MLflow manages the ML lifecycle",
                "MLflow includes experiment tracking"
            ]
        }
    },
    {
        "inputs": {"question": "Who created MLflow?"},
        "expectations": {
            "expected_response": "MLflow was created by Databricks and released in June 2018."
        }
    }
]

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[Correctness()]
)
```

---

## Pattern 3: RAG Evaluation with RetrievalGroundedness

Use for RAG applications to check if responses are grounded in retrieved context.

```python
from mlflow.genai.scorers import RetrievalGroundedness, RelevanceToQuery
import mlflow
from mlflow.entities import Document

# App must have RETRIEVER span type
@mlflow.trace(span_type="RETRIEVER")
def retrieve_docs(query: str) -> list[Document]:
    """Retrieval function marked with RETRIEVER span type."""
    # Your retrieval logic
    return [
        Document(
            id="doc1",
            page_content="Retrieved content here...",
            metadata={"source": "knowledge_base"}
        )
    ]

@mlflow.trace
def rag_app(query: str):
    docs = retrieve_docs(query)
    context = "\n".join([d.page_content for d in docs])
    
    response = generate_response(query, context)
    return {"response": response}

# Evaluate with RAG-specific scorers
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=rag_app,
    scorers=[
        RetrievalGroundedness(),  # Checks response vs retrieved docs
        RelevanceToQuery(),        # Checks if response addresses query
    ]
)
```

---

## Pattern 4: Simple Custom Scorer (Boolean)

Use for simple pass/fail checks.

```python
from mlflow.genai.scorers import scorer

@scorer
def contains_greeting(outputs):
    """Check if response contains a greeting."""
    response = outputs.get("response", "").lower()
    greetings = ["hello", "hi", "hey", "greetings"]
    return any(g in response for g in greetings)

@scorer
def response_not_empty(outputs):
    """Check if response is not empty."""
    return len(str(outputs.get("response", ""))) > 0

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[contains_greeting, response_not_empty]
)
```

---

## Pattern 5: Custom Scorer with Feedback Object

Use when you need rationale or custom names.

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

@scorer
def response_length_check(outputs):
    """Check if response length is appropriate."""
    response = str(outputs.get("response", ""))
    word_count = len(response.split())
    
    if word_count < 10:
        return Feedback(
            value="no",
            rationale=f"Response too short: {word_count} words (minimum 10)"
        )
    elif word_count > 500:
        return Feedback(
            value="no", 
            rationale=f"Response too long: {word_count} words (maximum 500)"
        )
    else:
        return Feedback(
            value="yes",
            rationale=f"Response length acceptable: {word_count} words"
        )
```

---

## Pattern 6: Custom Scorer with Multiple Metrics

Use when one scorer should produce multiple metrics.

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

@scorer
def comprehensive_check(inputs, outputs):
    """Return multiple metrics from one scorer."""
    response = str(outputs.get("response", ""))
    query = inputs.get("query", "")
    
    feedbacks = []
    
    # Check 1: Response exists
    feedbacks.append(Feedback(
        name="has_response",
        value=len(response) > 0,
        rationale="Response is present" if response else "No response"
    ))
    
    # Check 2: Word count
    word_count = len(response.split())
    feedbacks.append(Feedback(
        name="word_count",
        value=word_count,
        rationale=f"Response contains {word_count} words"
    ))
    
    # Check 3: Query terms in response
    query_terms = set(query.lower().split())
    response_terms = set(response.lower().split())
    overlap = len(query_terms & response_terms) / len(query_terms) if query_terms else 0
    feedbacks.append(Feedback(
        name="query_coverage",
        value=round(overlap, 2),
        rationale=f"{overlap*100:.0f}% of query terms found in response"
    ))
    
    return feedbacks
```

---

## Pattern 7: Custom Scorer Wrapping LLM Judge

Use when you need custom context for built-in judges.

```python
from mlflow.genai.scorers import scorer
from mlflow.genai.judges import meets_guidelines

@scorer
def custom_grounding_check(inputs, outputs, trace=None):
    """Check if response is grounded with custom context extraction."""
    
    # Extract what you need from inputs/outputs
    query = inputs.get("query", "")
    response = outputs.get("response", "")
    
    # Get retrieved docs from outputs (or extract from trace)
    retrieved_docs = outputs.get("retrieved_documents", [])
    
    # Call the judge with custom context
    return meets_guidelines(
        name="factual_grounding",
        guidelines=[
            "The response must only use facts from retrieved_documents",
            "The response must not make claims not supported by retrieved_documents"
        ],
        context={
            "request": query,
            "response": response,
            "retrieved_documents": retrieved_docs
        }
    )
```

---

## Pattern 8: Trace-Based Scorer

Use when you need to analyze execution details.

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace, SpanType

@scorer
def llm_latency_check(trace: Trace) -> Feedback:
    """Check if LLM response time is acceptable."""
    
    # Find LLM spans in trace
    llm_spans = trace.search_spans(span_type=SpanType.CHAT_MODEL)
    
    if not llm_spans:
        return Feedback(
            value="no",
            rationale="No LLM calls found in trace"
        )
    
    # Calculate total LLM time
    total_llm_time = 0
    for span in llm_spans:
        duration = (span.end_time_ns - span.start_time_ns) / 1e9
        total_llm_time += duration
    
    max_acceptable = 5.0  # seconds
    
    if total_llm_time <= max_acceptable:
        return Feedback(
            value="yes",
            rationale=f"LLM latency {total_llm_time:.2f}s within {max_acceptable}s limit"
        )
    else:
        return Feedback(
            value="no",
            rationale=f"LLM latency {total_llm_time:.2f}s exceeds {max_acceptable}s limit"
        )

@scorer  
def tool_usage_check(trace: Trace) -> Feedback:
    """Check if appropriate tools were called."""
    
    tool_spans = trace.search_spans(span_type=SpanType.TOOL)
    
    tool_names = [span.name for span in tool_spans]
    
    return Feedback(
        value=len(tool_spans) > 0,
        rationale=f"Tools called: {tool_names}" if tool_names else "No tools called"
    )
```

---

## Pattern 9: Class-Based Scorer with Configuration

Use when scorer needs persistent state or configuration.

```python
from mlflow.genai.scorers import Scorer
from mlflow.entities import Feedback
from typing import Optional, List

class KeywordRequirementScorer(Scorer):
    """Configurable scorer that checks for required keywords."""
    
    name: str = "keyword_requirement"
    required_keywords: List[str] = []
    case_sensitive: bool = False
    
    def __call__(self, outputs) -> Feedback:
        response = str(outputs.get("response", ""))
        
        if not self.case_sensitive:
            response = response.lower()
            keywords = [k.lower() for k in self.required_keywords]
        else:
            keywords = self.required_keywords
        
        missing = [k for k in keywords if k not in response]
        
        if not missing:
            return Feedback(
                value="yes",
                rationale=f"All required keywords present: {self.required_keywords}"
            )
        else:
            return Feedback(
                value="no",
                rationale=f"Missing keywords: {missing}"
            )

# Use with different configurations
product_scorer = KeywordRequirementScorer(
    name="product_mentions",
    required_keywords=["MLflow", "Databricks"],
    case_sensitive=False
)

compliance_scorer = KeywordRequirementScorer(
    name="compliance_terms",
    required_keywords=["Terms of Service", "Privacy Policy"],
    case_sensitive=True
)

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[product_scorer, compliance_scorer]
)
```

---

## Pattern 10: Conditional Scoring Based on Input

Use when different inputs need different evaluation.

```python
from mlflow.genai.scorers import scorer, Guidelines

@scorer
def conditional_scorer(inputs, outputs):
    """Apply different guidelines based on query type."""
    
    query = inputs.get("query", "").lower()
    
    if "technical" in query or "how to" in query:
        # Technical queries need detailed responses
        judge = Guidelines(
            name="technical_quality",
            guidelines=[
                "Response must include step-by-step instructions",
                "Response must include code examples where relevant"
            ]
        )
    elif "price" in query or "cost" in query:
        # Pricing queries need specific info
        judge = Guidelines(
            name="pricing_quality",
            guidelines=[
                "Response must include specific pricing information",
                "Response must mention any conditions or limitations"
            ]
        )
    else:
        # General queries
        judge = Guidelines(
            name="general_quality",
            guidelines=[
                "Response must directly address the question",
                "Response must be clear and concise"
            ]
        )
    
    return judge(inputs=inputs, outputs=outputs)
```

---

## Pattern 11: Scorer with Aggregations

Use for numeric scorers that need aggregate statistics.

```python
from mlflow.genai.scorers import scorer

@scorer(aggregations=["mean", "min", "max", "median", "p90"])
def response_latency(outputs) -> float:
    """Return response generation time."""
    return outputs.get("latency_ms", 0) / 1000.0  # Convert to seconds

@scorer(aggregations=["mean", "min", "max"])
def token_count(outputs) -> int:
    """Return token count from response."""
    response = str(outputs.get("response", ""))
    # Rough token estimate
    return len(response.split())

# Valid aggregations: min, max, mean, median, variance, p90
# NOTE: p50, p99, sum are NOT valid - use median instead of p50
```

---

## Pattern 12: Custom Make Judge

Use for complex multi-level evaluation with custom instructions.

```python
from mlflow.genai.judges import make_judge

# Issue resolution judge with multiple outcomes
resolution_judge = make_judge(
    name="issue_resolution",
    instructions="""
    Evaluate if the customer's issue was resolved.
    
    User's messages: {{ inputs }}
    Agent's responses: {{ outputs }}
    
    Assess the resolution status and respond with exactly one of:
    - 'fully_resolved': Issue completely addressed with clear solution
    - 'partially_resolved': Some help provided but not fully solved  
    - 'needs_follow_up': Issue not adequately addressed
    
    Your response must be exactly one of these three values.
    """,
    model="databricks:/databricks-gpt-5-mini"  # Optional
)

# Use in evaluation
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=support_agent,
    scorers=[resolution_judge]
)
```

---

## Combining Multiple Scorer Types

```python
from mlflow.genai.scorers import (
    Guidelines, Safety, Correctness,
    RelevanceToQuery, scorer
)
from mlflow.entities import Feedback

# Built-in scorers
safety = Safety()
relevance = RelevanceToQuery()

# Guidelines scorers
tone = Guidelines(name="tone", guidelines="Must be professional")
format_check = Guidelines(name="format", guidelines="Must use bullet points for lists")

# Custom code scorer
@scorer
def has_cta(outputs):
    """Check for call-to-action."""
    response = outputs.get("response", "").lower()
    ctas = ["contact us", "learn more", "get started", "sign up"]
    return any(cta in response for cta in ctas)

# Combine all
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[
        safety,
        relevance,
        tone,
        format_check,
        has_cta
    ]
)
```

---

## Pattern 13: Per-Stage/Component Accuracy Scorer

Use for multi-agent or multi-stage pipelines to verify each component works correctly.

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace
from typing import Dict, Any

@scorer
def classifier_accuracy(
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    expectations: Dict[str, Any],
    trace: Trace
) -> Feedback:
    """Check if classifier correctly identified the query type."""

    expected_type = expectations.get("expected_query_type")

    if expected_type is None:
        return Feedback(
            name="classifier_accuracy",
            value="skip",
            rationale="No expected_query_type in expectations"
        )

    # Find classifier span in trace by name pattern
    classifier_spans = [
        span for span in trace.search_spans()
        if "classifier" in span.name.lower()
    ]

    if not classifier_spans:
        return Feedback(
            name="classifier_accuracy",
            value="no",
            rationale="No classifier span found in trace"
        )

    # Extract actual value from span outputs
    span_outputs = classifier_spans[0].outputs or {}
    actual_type = span_outputs.get("query_type") if isinstance(span_outputs, dict) else None

    if actual_type is None:
        return Feedback(
            name="classifier_accuracy",
            value="no",
            rationale=f"No query_type in classifier outputs"
        )

    is_correct = actual_type == expected_type

    return Feedback(
        name="classifier_accuracy",
        value="yes" if is_correct else "no",
        rationale=f"Expected '{expected_type}', got '{actual_type}'"
    )
```

---

## Pattern 14: Tool Selection Accuracy Scorer

Check if the correct tools were called during agent execution.

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace, SpanType
from typing import Dict, Any, List

@scorer
def tool_selection_accuracy(
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    expectations: Dict[str, Any],
    trace: Trace
) -> Feedback:
    """Check if the correct tools were called."""

    expected_tools = expectations.get("expected_tools", [])

    if not expected_tools:
        return Feedback(
            name="tool_selection_accuracy",
            value="skip",
            rationale="No expected_tools in expectations"
        )

    # Get actual tool calls from TOOL spans
    tool_spans = trace.search_spans(span_type=SpanType.TOOL)
    actual_tools = {span.name for span in tool_spans}

    # Normalize names (handle fully qualified names like "catalog.schema.func")
    def normalize(name: str) -> str:
        return name.split(".")[-1] if "." in name else name

    expected_normalized = {normalize(t) for t in expected_tools}
    actual_normalized = {normalize(t) for t in actual_tools}

    # Check if all expected tools were called
    missing = expected_normalized - actual_normalized
    extra = actual_normalized - expected_normalized

    all_expected_called = len(missing) == 0

    rationale = f"Expected: {list(expected_normalized)}, Actual: {list(actual_normalized)}"
    if missing:
        rationale += f" | Missing: {list(missing)}"

    return Feedback(
        name="tool_selection_accuracy",
        value="yes" if all_expected_called else "no",
        rationale=rationale
    )
```

---

## Pattern 15: Stage Latency Scorer (Multiple Metrics)

Measure latency per pipeline stage and identify bottlenecks.

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace
from typing import List

@scorer
def stage_latency_scorer(trace: Trace) -> List[Feedback]:
    """Measure latency for each pipeline stage."""

    feedbacks = []
    all_spans = trace.search_spans()

    # Total trace time
    root_spans = [s for s in all_spans if s.parent_id is None]
    if root_spans:
        root = root_spans[0]
        total_ms = (root.end_time_ns - root.start_time_ns) / 1e6
        feedbacks.append(Feedback(
            name="total_latency_ms",
            value=round(total_ms, 2),
            rationale=f"Total execution time: {total_ms:.2f}ms"
        ))

    # Per-stage latency (customize patterns for your pipeline)
    stage_patterns = ["classifier", "rewriter", "executor", "retriever"]
    stage_times = {}

    for span in all_spans:
        span_name_lower = span.name.lower()
        for pattern in stage_patterns:
            if pattern in span_name_lower:
                duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
                stage_times[pattern] = stage_times.get(pattern, 0) + duration_ms
                break

    for stage, time_ms in stage_times.items():
        feedbacks.append(Feedback(
            name=f"{stage}_latency_ms",
            value=round(time_ms, 2),
            rationale=f"Stage '{stage}' took {time_ms:.2f}ms"
        ))

    # Identify bottleneck
    if stage_times:
        bottleneck = max(stage_times, key=stage_times.get)
        feedbacks.append(Feedback(
            name="bottleneck_stage",
            value=bottleneck,
            rationale=f"Slowest stage: '{bottleneck}' at {stage_times[bottleneck]:.2f}ms"
        ))

    return feedbacks
```

---

## Pattern 16: Component Accuracy Factory

Create reusable scorers for any component/field combination.

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace
from typing import Dict, Any

def component_accuracy(
    component_name: str,
    output_field: str,
    expected_key: str = None
):
    """Factory for component-specific accuracy scorers.

    Args:
        component_name: Pattern to match span names (e.g., "classifier")
        output_field: Field to check in span outputs (e.g., "query_type")
        expected_key: Key in expectations (defaults to f"expected_{output_field}")

    Example:
        router_accuracy = component_accuracy("router", "route", "expected_route")
    """
    if expected_key is None:
        expected_key = f"expected_{output_field}"

    @scorer
    def _scorer(
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        expectations: Dict[str, Any],
        trace: Trace
    ) -> Feedback:
        expected = expectations.get(expected_key)

        if expected is None:
            return Feedback(
                name=f"{component_name}_{output_field}_accuracy",
                value="skip",
                rationale=f"No {expected_key} in expectations"
            )

        # Find component span
        spans = [
            s for s in trace.search_spans()
            if component_name.lower() in s.name.lower()
        ]

        if not spans:
            return Feedback(
                name=f"{component_name}_{output_field}_accuracy",
                value="no",
                rationale=f"No {component_name} span found"
            )

        actual = spans[0].outputs.get(output_field) if isinstance(spans[0].outputs, dict) else None

        return Feedback(
            name=f"{component_name}_{output_field}_accuracy",
            value="yes" if actual == expected else "no",
            rationale=f"Expected '{expected}', got '{actual}'"
        )

    return _scorer

# Usage examples:
classifier_accuracy = component_accuracy("classifier", "query_type", "expected_query_type")
router_accuracy = component_accuracy("router", "route", "expected_route")
intent_accuracy = component_accuracy("intent", "intent_type", "expected_intent")
```
