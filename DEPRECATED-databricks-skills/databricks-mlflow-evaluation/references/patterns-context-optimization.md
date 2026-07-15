# Context Optimization Strategies

A guide to managing context windows effectively in agentic systems. These strategies apply across architectures and help maintain quality while reducing token usage.

## Table of Contents

- [Why Context Optimization Matters](#why-context-optimization-matters)
- [Strategy 1: Tool Result Management](#strategy-1-tool-result-management)
- [Strategy 2: Message History Compression](#strategy-2-message-history-compression)
- [Strategy 3: Structured State vs. Message History](#strategy-3-structured-state-vs-message-history)
- [Strategy 4: Prompt Engineering for Context Efficiency](#strategy-4-prompt-engineering-for-context-efficiency)
- [Strategy 5: Intelligent Caching](#strategy-5-intelligent-caching)
- [Strategy 6: Compression Triggers](#strategy-6-compression-triggers)
- [Strategy 7: Architecture-Specific Patterns](#strategy-7-architecture-specific-patterns)
- [Metrics for Context Optimization](#metrics-for-context-optimization)
- [Common Pitfalls](#common-pitfalls)
- [Implementation Priority](#implementation-priority)

---

## Why Context Optimization Matters

Context windows are finite and expensive. Poor context management leads to:
- **Token bloat**: Paying for redundant or low-value tokens
- **Lost context**: Important information pushed out by verbose content
- **Quality degradation**: Model attention diluted across irrelevant content
- **Latency**: Larger contexts = slower inference

---

## Strategy 1: Tool Result Management

Tool calls often return verbose JSON that quickly fills context windows.

### Problem
A single tool call might return 5,000+ tokens of JSON data, but only 50 tokens are actually needed for the agent's response.

### Solutions

**Selective Field Extraction**
- Before returning tool results to the agent, extract only the fields needed
- Define "essential fields" per tool type (e.g., for a search tool: title, snippet, url)
- Discard metadata, debugging info, and redundant fields

**Result Truncation**
- Limit array results to top N items (e.g., top 10 search results, not 100)
- Truncate long text fields to first N characters
- Summarize large datasets into aggregates (counts, averages, ranges)

**Structured Summaries**
- Convert raw tool output to natural language summaries
- "Found 47 results. Top 3: [Company A] (45% growth), [Company B] (32% growth), [Company C] (28% growth)"
- Preserves key facts, drops JSON verbosity

### When to Apply
- Immediately after tool execution, before adding to context
- More aggressive for older tool results, preserve detail for recent ones

---

## Strategy 2: Message History Compression

Conversation history grows with each turn. Managing it is critical for multi-turn agents.

### Tier 1: Sliding Window
Keep only the last N messages, drop older ones.

| Pros | Cons |
|------|------|
| Simple to implement | Loses historical context |
| Predictable context size | May break conversation continuity |
| No additional latency | User references to old content fail |

**Best for**: Simple chat agents, short conversations, stateless interactions

### Tier 2: Filter + Summarize
Filter verbose messages, create summaries of older content.

| Pros | Cons |
|------|------|
| Preserves key information | Requires extraction logic |
| Good compression (50-70%) | Some detail loss |
| Maintains continuity | Added complexity |

**Best for**: Tool-calling agents, multi-step tasks, medium-length conversations

### Tier 3: Semantic Compression
Use an LLM to summarize older conversation segments.

| Pros | Cons |
|------|------|
| Highest compression (70-85%) | Adds latency (LLM call) |
| Preserves meaning well | Costs tokens for summary |
| Handles complex context | May lose fine details |

**Best for**: Very long conversations, periodic checkpoints, complex multi-agent workflows

### Hybrid Approach
Combine tiers based on message age:
- **Recent (last 5-10 messages)**: Keep verbatim
- **Medium (10-30 messages back)**: Tier 2 filtering
- **Old (30+ messages)**: Tier 3 semantic summary

---

## Strategy 3: Structured State vs. Message History

Instead of passing full message history, maintain structured state that captures conversation semantics.

### Message History Approach
```
[Message 1: User asks about X]
[Message 2: Assistant responds]
[Message 3: Tool call result - 2000 tokens of JSON]
[Message 4: Assistant analyzes]
[Message 5: User follow-up about Y]
...
```
Grows linearly, contains redundancy.

### Structured State Approach
```
{
  "topic": "X analysis",
  "entities_discussed": ["Company A", "Company B"],
  "filters_applied": {"time_range": "Q3 2024"},
  "key_findings": ["Finding 1", "Finding 2"],
  "last_query": "Y follow-up"
}
```
Fixed size, captures semantics.

### Trade-offs

| Aspect | Message History | Structured State |
|--------|-----------------|------------------|
| Size growth | Linear | Bounded |
| Context richness | High | Medium |
| Implementation | Simple | Complex |
| Error recovery | Easy (replay) | Harder |
| Multi-turn coherence | Natural | Requires design |

### Recommendation
Use structured state for:
- Long-running conversations (10+ turns)
- Multi-agent systems (state passed between agents)
- Streaming contexts (state can be serialized/resumed)

Use message history for:
- Short interactions (< 10 turns)
- Simple Q&A agents
- When full conversation context is genuinely needed

---

## Strategy 4: Prompt Engineering for Context Efficiency

The system prompt itself can bloat context. Optimize it.

### Avoid Redundancy
- Don't repeat instructions that are implicit in examples
- Don't include examples that cover the same case
- Reference external docs rather than inlining them

### Use Hierarchical Instructions
```
## Core Rules (always apply)
- Rule 1
- Rule 2

## Situational Rules (apply when relevant)
- If X, then Y
- If A, then B
```
Agent can skip irrelevant sections mentally.

### Dynamic Prompt Assembly
Instead of a monolithic system prompt, assemble based on context:
- Base instructions (always included)
- Tool-specific guidance (only when tools are bound)
- Domain context (only when relevant to query)

### Measure Prompt Token Cost
Track tokens used by:
- System prompt (fixed cost per request)
- Few-shot examples (fixed cost)
- Conversation history (variable)
- Tool results (variable, often largest)

---

## Strategy 5: Intelligent Caching

Avoid redundant computation and token usage through caching.

### Result Caching
- Cache tool results for identical queries
- Set TTL based on data freshness requirements
- Invalidate on relevant state changes

### Summary Caching
- Cache computed summaries of conversation segments
- Reuse when that segment hasn't changed
- Particularly valuable for Tier 3 semantic summaries

### Prompt Caching (Model-Level)
Some providers cache prompt prefixes:
- Anthropic: Automatic prefix caching for repeated prompts
- OpenAI: Prompt caching for identical prefix sequences

Structure prompts to maximize cache hits:
- Put stable content (system prompt, examples) first
- Put variable content (conversation, tool results) last

---

## Strategy 6: Compression Triggers

Don't compress on every turn—compress when needed.

### Signal-Based Triggers
- **Token count**: Compress when estimated tokens > threshold
- **Message count**: Compress when messages > threshold
- **Turn count**: Compress every N turns
- **Time-based**: Compress after N minutes of conversation

### Threshold Guidelines

| Agent Type | Token Trigger | Message Trigger |
|------------|---------------|-----------------|
| Simple Chat | 80K | 30 messages |
| RAG Agent | 40K | 15 messages |
| Tool-Calling | 50K | 20 messages |
| Multi-Agent | 30K | 10 messages |

### Avoid Over-Compression
- Don't compress before you have meaningful content to compress
- Keep recent context intact (last 5-10 messages)
- Verify compression doesn't break agent behavior (test with evals)

---

## Strategy 7: Architecture-Specific Patterns

### For Multi-Agent Pipelines
- Each agent should receive only the context it needs
- Pass structured summaries between stages, not full history
- The final "executor" stage may need more context than the "classifier"

### For RAG Agents
- Retrieved documents often dominate context
- Limit chunks returned (top 3-5, not 10+)
- Summarize retrieved content before adding to context
- Consider relevance filtering before retrieval

### For Streaming Agents
- Context must be serializable for resume
- Prefer structured state over message history
- Compress before serialization checkpoints

---

## Metrics for Context Optimization

Track these to measure optimization effectiveness:

| Metric | What It Measures | Target |
|--------|------------------|--------|
| Tokens per request | Context efficiency | Minimize |
| Compression ratio | Before/after tokens | 0.3-0.7 |
| Eval score post-compression | Quality maintenance | No regression |
| Latency impact | Compression overhead | < 100ms |
| Cache hit rate | Redundant computation avoided | > 50% |

---

## Common Pitfalls

### 1. Compressing Too Aggressively
**Symptom**: Agent can't answer follow-up questions
**Fix**: Preserve recent messages, test with multi-turn evals

### 2. Ignoring Tool Result Size
**Symptom**: Single tool call fills context window
**Fix**: Truncate/summarize tool results immediately

### 3. Redundant Context Across Agents
**Symptom**: Multi-agent system passes same content to every stage
**Fix**: Tailor context per agent role

### 4. No Compression Testing
**Symptom**: Compression breaks edge cases
**Fix**: Include compression scenarios in evaluation dataset

### 5. Static Thresholds
**Symptom**: Works for some queries, fails for others
**Fix**: Use multi-signal triggers (tokens AND messages AND time)

---

## Implementation Priority

When implementing context optimization:

1. **Start with tool results** - Often the biggest win with lowest effort
2. **Add sliding window** - Simple message limit prevents runaway growth
3. **Implement structured extraction** - Capture key facts before filtering
4. **Add compression triggers** - Compress only when needed
5. **Consider semantic summarization** - For complex, long-running conversations

---

## References

- Anthropic prompt caching: Automatic prefix caching for repeated prompts
- Token estimation: ~4 characters per token heuristic for English text
- Context window limits vary by model—check provider documentation
