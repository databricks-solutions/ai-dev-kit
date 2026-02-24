# MLflow Evaluation Scorers Guide

Complete guide for selecting and creating scorers to evaluate agent quality.

## Table of Contents

1. [Understanding Scorers](#understanding-scorers)
2. [Built-in Scorers](#built-in-scorers)
3. [Model Selection for Scorers](#model-selection-for-scorers)
4. [Custom Scorer Design](#custom-scorer-design)
5. [Scorer Registration](#scorer-registration)
6. [Testing Scorers](#testing-scorers)

## Understanding Scorers

### What are Scorers?

Scorers (also called "judges" or "LLM-as-a-judge") are evaluation criteria that assess the quality of agent responses. They:

- Take as input single-turn inputs&outputs, or multi-turn conversations, or traces
- Apply quality criteria (relevance, accuracy, completeness, etc.)
- Return a structured assessment (pass/fail or numeric) along with a rationale
- Can be built-in (provided by MLflow) or custom (defined by you)

### Types of Scorers

**1. Reference-Free Scorers**

- Don't require ground truth or expected outputs
- **Easiest to use** - work with any dataset

**2. Ground-Truth Scorers**

- Require expectations in the dataset
- Compare agent response to ground truth
- Require datasets with `expectations` field

## Built-in Scorers

MLflow provides several built-in scorers for common evaluation criteria.

```python
uv run mlflow scorers list -b
```

Detailed documentation for builtin-scorers can be found at `https://mlflow.org/docs/latest/api_reference/python_api/mlflow.genai.html`

### Important: Trace Structure Assumptions

**CRITICAL**: Built-in scorers make assumptions about trace structure.

Before using a built-in scorer:

1. **Read its documentation** to understand required inputs
2. **Check trace structure** matches expectations
3. **Verify it works** with a test trace before full evaluation

Read `troubleshooting.md` for some common issues with built-in scorers.

## Model Selection for Scorers

Scorers require an LLM to judge quality. The `model=` parameter accepts MLflow model URIs.

### Default Model Behavior

When `model=None` (default), MLflow selects based on tracking URI:
- **Databricks tracking URI**: Uses `"databricks"` managed judge (no API key needed)
- **Local/other tracking URI**: Uses `"openai:/gpt-4.1-mini"` (requires `OPENAI_API_KEY`)

#### Testing whether the default model works

```python
from mlflow.genai.judges import make_judge

test_judge = make_judge(name="test", instructions="Test whether {{inputs}} is in english")
test_judge(inputs="hello")  # Should return a valid Feedback object if default model works
```

### If default model does not work

#### MLflow Model URI Format

MLflow uses the format `<provider>:/<model-name>`. Examples:

| URI | Description |
|-----|-------------|
| `databricks` | Databricks managed judge (good default if there is a databricks connection) |
| `databricks:/<endpoint>` | Databricks serving endpoint |
| `openai:/<model>` | OpenAI (e.g., `openai:/gpt-4`) |
| `anthropic:/<model>` | Anthropic |

#### Reusing the Agent's LLM

If the agent uses a working LLM, reuse it for scorers to avoid credential issues:

1. **Find agent's model config** - Look for settings/config module
2. **Check environment** - `LLM_MODEL` or provider-specific env vars
3. **Convert to MLflow URI** - If agent uses LiteLLM format, convert:
   - `"gpt-4o"` → `"openai:/gpt-4o"`
   - `"databricks/endpoint"` → `"databricks:/endpoint"`

## Custom Scorer Design

Create custom scorers when:

- Built-in scorers don't match your criteria
- You need domain-specific evaluation
- Your agent has unique requirements
- Trace structure doesn't match built-in assumptions

### MLflow Judge Constraints

⚠️ **The MLflow CLI has specific requirements for custom scorers.**

Before creating custom scorers, read the complete constraints guide:

- See `references/scorers-constraints.md` for detailed requirements

**Key constraints:**

1. `{{trace}}` variable cannot be mixed with `{{inputs}}` or `{{outputs}}`
2. CLI requires "yes"/"no" return values (not "pass"/"fail")
3. Instructions must include at least one template variable

---

### Design Process

**Step 1: Define Quality Criterion Clearly**

What specific aspect of quality are you judging?

**Examples**:

- "Response uses appropriate tools for the query"
- "Response is factually accurate based on available data"
- "Response follows the expected format"
- "Response appropriately handles ambiguous queries"

**Step 2: Determine Required Inputs**

What information does the scorer need?

**Common inputs**:

- `query`: The user's question
- `response`: The agent's answer
- `trace`: Full trace with tool calls, LLM calls, etc.
- `context`: Retrieved documents or context (if applicable)

**Step 3: Write Evaluation Instructions**

Clear instructions for the LLM judge:

```
You are evaluating whether an agent used appropriate tools for a query.

Given:
- Query: {query}
- Response: {response}
- Trace: {trace} (contains tool calls)

Criteria: The agent should use tools when needed (e.g., search for factual queries)
and should not use tools unnecessarily (e.g., for greetings).

Evaluate whether appropriate tools were used. Return "yes" if tools were used
appropriately, "no" if not.
```

**Step 4: Choose Output Format**

Use yes/no format as required by the CLI (see CRITICAL CONSTRAINTS above).

### Example Custom Scorers

**Example 1: Tool Usage Appropriateness**

```
Scorer Name: ToolUsageAppropriate

Definition: Judges whether the agent used appropriate tools for the query.

Instructions:
You are evaluating tool usage by an AI agent.

Given a query and trace showing tool calls, determine if:
1. Tools were used when needed (factual questions, searches, lookups)
2. Tools were NOT used unnecessarily (greetings, simple questions)
3. The RIGHT tools were chosen for the task

Return "yes" if tool usage was appropriate, "no" if not.

Variables: query, response, trace
Output: yes/no
```

**Example 2: Factual Accuracy**

```
Scorer Name: FactualAccuracy

Definition: Judges whether the response is factually accurate.

Instructions:
You are evaluating the factual accuracy of an AI agent's response.

Review the agent's response and determine if the information provided is
factually correct based on the context and your knowledge.

Return "yes" if the response is factually accurate, "no" if it contains
incorrect information or makes unsupported claims.

Variables: query, response, context (optional)
Output: yes/no
```

## Scorer Registration

*IMPORTANT: All scorers (built-in and custom) must be registered so that they can be reused in future runs*

### Registering built-in scorers

```python
from mlflow.genai.scorers import <scorer_name>

scorer=<scorer_name>(...)
scorer.register()
```

### Registering custom scorers

#### Check CLI Help First

Run `--help` to verify parameter names:

```bash
uv run mlflow scorers register-llm-judge --help
```

#### Correct CLI Parameters

#### Registration Example - All Requirements Met

```bash
# ✅ CORRECT - Has variable, uses yes/no, correct parameters
uv run mlflow scorers register-llm-judge \
  -n "RelevanceCheck" \
  -d "Checks if response addresses the query" \
  -i "Given the response {{ outputs }}, determine if it directly addresses the query. Return 'yes' if relevant, 'no' if not."
```

```bash
# ✅ CORRECT - Uses {{trace}} only (no other variables), yes/no, correct parameters
uv run mlflow scorers register-llm-judge \
  -n "ToolUsageCheck" \
  -d "Evaluates tool selection quality" \
  -i "Examine the trace {{ trace }}. Did the agent use appropriate tools for the query? Return 'yes' if appropriate, 'no' if not."
```

#### Programmatic registration (for advanced use cases):

```python
from mlflow.genai.judges import make_judge
from typing import Literal

scorer = make_judge(
    name="ToolUsageAppropriate",
    description="Judges whether appropriate tools were used",
    instructions="""
    You are evaluating tool usage by an AI agent.

    Given a trace: {{ trace }}

    Determine if appropriate tools were used.
    Return "yes" if tool usage was appropriate, "no" if not.
    """,
    feedback_value_type=Literal["yes", "no"],
)

# Register the scorer
registered_scorer = scorer.register()
```

**When to use**:

- `mlflow scorers register-llm-judge` fails with an obscure error
- Need programmatic control
- Integration with existing code

**Important**: The `make_judge()` API follows the same constraints documented in the CRITICAL CONSTRAINTS section above. 

### Best Practices

**1. Use default model** unless you have specific needs:

- Default is usually sufficient and cost-effective
- Specify model only for specialized evaluation

**2. Register both built-in and custom scorers for version control and team collaboration**

**3. Test before full evaluation**:

- Test on single trace first
- Verify output format is correct
- Check that instructions are clear

**4. Version your scorers**:

- Include version in name if criteria change: `ToolUsageAppropriate_v2`
- Document what changed between versions

## Testing Scorers

**Always test a scorer** before using it on your full evaluation dataset.

### Quick Single-Trace Test

```bash
# Get a sample trace ID (from previous agent run)
export TRACE_ID="<sample_trace_id>"

# Test scorer on single trace
uv run mlflow traces evaluate \
  --output json \
  --scorers ToolUsageAppropriate \
  --trace-ids $TRACE_ID
```

### Verify Scorer Behavior

**Check 1: No Errors**

- Scorer executes without errors
- No null or empty outputs

**Check 2: Output Format**

- For yes/no: Returns "yes" or "no"
- For numeric: Returns number in expected range

**Check 3: Makes Sense**

- Review the trace
- Manually judge if scorer output is reasonable
- If scorer is wrong, refine instructions

**Check 4: Trace Coverage**

- Test on diverse traces (different query types)
- Ensure scorer handles all cases
- Check edge cases

### Iteration Workflow

1. **Register scorer** with initial instructions
2. **Test on single trace** with known expected outcome
3. **Review output** - does it match your judgment?
4. **If wrong**: Refine instructions, re-register, test again
5. **Test on diverse traces** (3-5 different types)
6. **Deploy to full evaluation** once confident

### Example Test Session

```bash
# Test ToolUsageAppropriate scorer

# Test 1: Query that should use tools (expect: yes)
uv run mlflow traces evaluate \
  --scorers ToolUsageAppropriate \
  --trace-ids <trace_with_tool_use> \
  --output json

# Test 2: Greeting that shouldn't use tools (expect: yes)
uv run mlflow traces evaluate \
  --scorers ToolUsageAppropriate \
  --trace-ids <trace_greeting> \
  --output json

# Test 3: Query that should use tools but didn't (expect: no)
uv run mlflow traces evaluate \
  --scorers ToolUsageAppropriate \
  --trace-ids <trace_missing_tools> \
  --output json
```

Review each output to verify scorer behaves as expected.

---

**For troubleshooting scorer issues**, see `references/troubleshooting.md`
