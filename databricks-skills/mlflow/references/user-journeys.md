# User Journey Guides

Step-by-step workflows for common evaluation scenarios.

---

## Journey 0: Strategy Alignment (ALWAYS START HERE)

**Starting Point**: You need to evaluate an agent
**Goal**: Align on what to evaluate before writing any code

**PRIORITY:** Before writing evaluation code, complete strategy alignment. This ensures evaluations measure what matters and provide actionable insights.

### Step 1: Understand the Agent

Before evaluating, gather context about what you're evaluating:

**Questions to ask (or investigate in the codebase):**
1. **What does this agent do?** (data analysis, RAG, multi-turn chat, task automation)
2. **What tools does it use?** (UC functions, vector search, external APIs)
3. **What is the input/output format?** (messages format, structured output)
4. **What is the current state?** (prototype, production, needs improvement)

**Actions to take:**
- Read the agent's main code file (e.g., `agent.py`)
- Review the config file for system prompts and tool definitions
- Check existing tests or evaluation scripts
- Look at CLAUDE.md or README for project context

### Step 2: Align on What to Evaluate

**Evaluation dimensions to consider:**

| Dimension | When to Use | Example Scorer |
|-----------|-------------|----------------|
| **Safety** | Always (table stakes) | `Safety()` |
| **Correctness** | When ground truth exists | `Correctness()` |
| **Relevance** | When responses should address queries | `RelevanceToQuery()` |
| **Groundedness** | RAG systems with retrieved context | `RetrievalGroundedness()` |
| **Domain Guidelines** | Domain-specific requirements | `Guidelines(name="...", guidelines="...")` |
| **Format/Structure** | Structured output requirements | Custom scorer |
| **Tool Usage** | Agents with tool calls | Custom scorer checking tool selection |

**Questions to ask the user:**
1. What are the **must-have** quality criteria? (safety, accuracy, relevance)
2. What are the **nice-to-have** criteria? (conciseness, tone, format)
3. Are there **specific failure modes** you've seen or worry about?
4. Do you have **ground truth** or expected answers for test cases?

### Step 3: Define User Scenarios (Evaluation Dataset)

**Types of test cases to include:**

| Category | Purpose | Example |
|----------|---------|---------|
| **Happy Path** | Core functionality works | Typical user questions |
| **Edge Cases** | Boundary conditions | Empty inputs, very long queries |
| **Adversarial** | Robustness testing | Prompt injection, off-topic |
| **Multi-turn** | Conversation handling | Follow-up questions, context recall |
| **Domain-specific** | Business logic | Industry terminology, specific formats |

**Questions to ask the user:**
1. What are the **most common** questions users ask?
2. What are **challenging** questions the agent should handle?
3. Are there questions it should **refuse** to answer?
4. Do you have **existing test cases** or production traces to start from?

### Step 4: Establish Success Criteria

**Define quality gates before running evaluation:**

```python
QUALITY_GATES = {
    "safety": 1.0,           # 100% - non-negotiable
    "correctness": 0.9,      # 90% - high bar for accuracy
    "relevance": 0.85,       # 85% - good relevance
    "concise": 0.8,          # 80% - nice to have
}
```

**Questions to ask the user:**
1. What pass rates are **acceptable** for each dimension?
2. Which metrics are **blocking** vs **informational**?
3. How will evaluation results **inform decisions**? (ship/no-ship, iterate, investigate)

### Strategy Alignment Checklist

Before implementing evaluation, confirm:
- [ ] Agent purpose and architecture understood
- [ ] Evaluation dimensions agreed upon
- [ ] Test case categories identified
- [ ] Success criteria defined
- [ ] Data source identified (new, traces, existing dataset)

---

## Journey 3: "Something Broke" - Regression Detection

**Starting Point**: You made changes to your agent and suspect something regressed
**Goal**: Identify what broke and verify the fix

### Steps

1. **Establish baseline metrics**
   ```bash
   # Run evaluation on the previous version (or use saved baseline)
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   Record key metrics: `classifier_accuracy`, `tool_selection_accuracy`, `follows_instructions`

2. **Run evaluation on current version**
   ```bash
   python run_quick_eval.py
   ```

3. **Compare metrics**
   ```python
   from evaluation.optimization_history import OptimizationHistory

   history = OptimizationHistory()
   print(history.compare_iterations(-2, -1))  # Compare last two
   ```

4. **Identify regression source**
   - If `classifier_accuracy` dropped → Check ClassifierSignature changes
   - If `tool_selection_accuracy` dropped → Check tool descriptions, required_tools field
   - If `follows_instructions` dropped → Check ExecutorSignature output format

5. **Analyze failing traces**
   ```
   /eval:analyze-traces [experiment-id]
   ```
   Look for:
   - Error patterns in specific test categories
   - Tool call failures
   - Unexpected outputs

6. **Fix and re-evaluate**
   - Revert problematic changes or apply targeted fix
   - Re-run evaluation
   - Verify metrics restored

### Commands Used
- `python run_quick_eval.py` - Run evaluation
- `/eval:analyze-traces` - Deep trace analysis
- `OptimizationHistory.compare_iterations()` - Metric comparison

### Success Indicators
- Metrics return to baseline or improve
- No new failing test cases
- Trace analysis shows expected behavior

---

## Journey 7: "My Multi-Agent is Slow" - Performance Optimization

**Starting Point**: Your agent responses are too slow
**Goal**: Identify bottlenecks and reduce latency

### Steps

1. **Run evaluation with latency scoring**
   ```bash
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   Note the latency metrics:
   - `classifier_latency_ms`
   - `rewriter_latency_ms`
   - `executor_latency_ms`
   - `total_latency_ms`

2. **Identify the bottleneck stage**
   | Latency | Typical Range | If High, Check |
   |---------|---------------|----------------|
   | classifier_latency | <5s | ClassifierSignature verbosity |
   | rewriter_latency | <10s | QueryRewriterSignature complexity |
   | executor_latency | <30s | Tool call count, response generation |

3. **Analyze traces for slow stages**
   ```
   /eval:analyze-traces [experiment-id]
   ```
   Focus on:
   - Span durations by stage
   - Number of LLM calls per stage
   - Tool execution times

4. **Run signature analysis**
   ```bash
   python -m evaluation.analyze_signatures
   ```
   Look for:
   - High total description chars (>2000)
   - Verbose OutputField descriptions
   - Missing examples (causes more retries)

5. **Apply optimizations**

   **For high classifier latency:**
   - Simplify ClassifierSignature docstring
   - Add concrete examples to reduce ambiguity

   **For high executor latency:**
   - Simplify ExecutorSignature.answer format
   - Reduce output format requirements
   - Consider caching repeated tool calls

   **For high total latency:**
   - Review if all stages are necessary
   - Consider parallel execution where possible

6. **Re-evaluate and compare**
   ```bash
   python run_quick_eval.py
   ```
   Use `OptimizationHistory.compare_iterations()` to verify improvement

### Commands Used
- `python run_quick_eval.py` - Run evaluation with latency scoring
- `/eval:analyze-traces` - Trace analysis with timing breakdown
- `python -m evaluation.analyze_signatures` - Signature verbosity analysis

### Success Indicators
- Target latencies: classifier <5s, executor <30s, total <60s
- No regression in accuracy metrics
- Consistent improvement across test categories

---

## Journey 8: "Improve My Prompts" - Systematic Prompt Optimization

**Starting Point**: Your agent works but could be more accurate
**Goal**: Systematically improve prompt quality through evaluation

### Steps

1. **Establish baseline**
   ```bash
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   Record all metrics in `optimization_history.json`

2. **Run signature analysis**
   ```bash
   python -m evaluation.analyze_signatures
   ```
   Review the report for:
   - Metric correlations (which signatures affect which metrics)
   - Specific issues flagged per signature

3. **Prioritize fixes by metric impact**

   | Metric | Primary Signature | Common Issues |
   |--------|-------------------|---------------|
   | follows_instructions | ExecutorSignature | Verbose answer format, unclear structure |
   | tool_selection_accuracy | ClassifierSignature | No examples, ambiguous tool descriptions |
   | classifier_accuracy | ClassifierSignature | Verbose docstring, unclear query_type mapping |

4. **Apply ONE fix at a time**
   - Make a single, targeted change
   - Document the change in your commit message
   - Track in optimization_history.json

5. **Re-evaluate immediately**
   ```bash
   python run_quick_eval.py
   ```
   - If improved → Keep change, move to next fix
   - If regressed → Revert and try different approach
   - If unchanged → Consider if fix was necessary

6. **Iterate until targets met**

   | Metric | Target |
   |--------|--------|
   | classifier_accuracy | 95%+ |
   | tool_selection_accuracy | 90%+ |
   | follows_instructions | 80%+ |

7. **Document successful optimizations**
   ```python
   from evaluation.optimization_history import OptimizationHistory

   history = OptimizationHistory()
   print(history.summary())
   ```

### Commands Used
- `python run_quick_eval.py` - Run evaluation
- `python -m evaluation.analyze_signatures` - Identify prompt issues
- `/optimize:context --quick` - Full optimization loop (when endpoint available)

### Success Indicators
- All target metrics met
- No regressions from baseline
- Clear documentation of what changed and why
- Optimization history shows positive trend

---

## Quick Reference

### Which Journey Am I On?

| Symptom | Journey |
|---------|---------|
| "It was working before" | Journey 3 (Regression) |
| "It's too slow" | Journey 7 (Performance) |
| "It's not accurate enough" | Journey 8 (Prompt Optimization) |

### Common Tools Across Journeys

| Tool | Purpose |
|------|---------|
| `run_quick_eval.py` | Fast evaluation (8 test cases) |
| `run_full_eval.py` | Full evaluation (23 test cases) |
| `analyze_signatures.py` | Signature/prompt analysis |
| `OptimizationHistory` | Track iterations |
| `/eval:analyze-traces` | Deep trace analysis |
| `/optimize:context` | Full optimization loop |

### Metric Targets

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| classifier_accuracy | 95%+ | <80% |
| tool_selection_accuracy | 90%+ | <70% |
| follows_instructions | 80%+ | <50% |
| executor_latency | <30s | >60s |
