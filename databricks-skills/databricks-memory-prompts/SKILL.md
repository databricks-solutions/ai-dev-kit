---
name: databricks-memory-prompts
description: >
  Persistent memory for AI applications using RAG + RLM (Recursive Language Modeling).
  Store decisions, patterns, and feedback in Unity Catalog. Retrieve relevant context
  before prompt construction. Learn from production feedback automatically.
  
  Based on the architecture from soul.py (github.com/menonpg/soul.py).
---

# Memory-Aware Prompts

Extend your AI applications with persistent memory that learns from experience.

> Contributed by [ThinkCreate.AI](https://thinkcreateai.com)  
> Based on [soul.py](https://github.com/menonpg/soul.py) — RAG + RLM memory architecture

---

## The Problem

You deploy a PII redaction prompt. Users report bugs:
- "It missed phone extensions like 555-1234 x789"
- "It redacted 'Boston General Hospital' but that's not patient PII"
- "Family member names in clinical notes weren't caught"

You fix the prompt. A month later, a colleague deploys a similar prompt — same bugs. Your learnings were in your head, not in the system.

**This skill solves that problem.**

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                         THE MEMORY LOOP                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. USER REPORTS ISSUE                                          │
│     "555-1234 x789 wasn't redacted"                             │
│                           │                                      │
│                           ▼                                      │
│  2. YOU LOG THE PATTERN                                         │
│     INSERT INTO patterns (pattern, evidence, task_scope)        │
│     VALUES ('Phone extensions need special handling',            │
│             'Ticket #4521', 'pii_redaction')                    │
│                           │                                      │
│                           ▼                                      │
│  3. NEXT PROMPT BUILD                                           │
│     SELECT pattern FROM patterns WHERE task_scope = 'pii'       │
│     → Returns: "Phone extensions need special handling"         │
│                           │                                      │
│                           ▼                                      │
│  4. ENHANCED PROMPT                                             │
│     Base prompt + "Watch for: Phone extensions..."              │
│     → LLM now handles the edge case                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

1. **Unity Catalog** — You need a catalog where you can create tables
2. **CREATE TABLE permission** — In the schema where you'll store memory
3. **Serverless SQL Warehouse** or cluster with DBR 15.1+ — For `ai_query()`

**Important:** You must manually create the memory tables (Step 1 below) before using this pattern. They are not auto-created.

---

## Quick Start

### Step 1: Create Memory Tables

Run this SQL in a Databricks notebook. Replace `my_catalog` with your catalog name.

```sql
-- Run in any Databricks notebook
CREATE SCHEMA IF NOT EXISTS my_catalog.memory;

-- Patterns: Things you learned from production
CREATE TABLE IF NOT EXISTS my_catalog.memory.patterns (
    id STRING DEFAULT uuid(),
    pattern TEXT NOT NULL,
    evidence TEXT,
    task_scope STRING,
    frequency INT DEFAULT 1,
    confidence DOUBLE DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT current_timestamp()
);

-- Decisions: Explicit choices you made
CREATE TABLE IF NOT EXISTS my_catalog.memory.decisions (
    id STRING DEFAULT uuid(),
    decision TEXT NOT NULL,
    rationale TEXT,
    task_scope STRING,
    created_at TIMESTAMP DEFAULT current_timestamp()
);

-- Feedback: Raw user corrections (input for pattern extraction)
CREATE TABLE IF NOT EXISTS my_catalog.memory.feedback (
    id STRING DEFAULT uuid(),
    input_text TEXT,
    output_text TEXT,
    correction TEXT,
    task_scope STRING,
    created_at TIMESTAMP DEFAULT current_timestamp()
);
```

### Step 2: Log What You Learn

When you discover something from production:

```sql
-- A pattern you learned from a bug
INSERT INTO my_catalog.memory.patterns (pattern, evidence, task_scope)
VALUES (
    'Phone numbers with extensions (x1234) require explicit handling',
    'Ticket #4521: User reported 555-1234 x789 was not redacted',
    'pii_redaction'
);

-- A decision you made deliberately
INSERT INTO my_catalog.memory.decisions (decision, rationale, task_scope)
VALUES (
    'Use typed tags [NAME], [SSN], [PHONE] instead of generic [REDACTED]',
    'Typed tags enable downstream compliance audits and selective reveal',
    'pii_redaction'
);
```

### Step 3: Build Enhanced Prompts

```python
def build_prompt_with_memory(base_prompt: str, task_scope: str) -> str:
    """Enhance a prompt with relevant patterns and decisions from memory."""
    
    # Retrieve patterns
    patterns_df = spark.sql(f"""
        SELECT pattern FROM my_catalog.memory.patterns
        WHERE task_scope = '{task_scope}'
        ORDER BY confidence DESC, created_at DESC
        LIMIT 5
    """)
    patterns = [row.pattern for row in patterns_df.collect()]
    
    # Retrieve decisions  
    decisions_df = spark.sql(f"""
        SELECT decision FROM my_catalog.memory.decisions
        WHERE task_scope = '{task_scope}'
        ORDER BY created_at DESC
        LIMIT 3
    """)
    decisions = [row.decision for row in decisions_df.collect()]
    
    # Build enhanced prompt
    enhanced = base_prompt
    
    if decisions:
        enhanced += "\n\n## Design Decisions (follow these)\n"
        for d in decisions:
            enhanced += f"- {d}\n"
    
    if patterns:
        enhanced += "\n## Learned Patterns (watch for these)\n"
        for p in patterns:
            enhanced += f"- {p}\n"
    
    return enhanced
```

### Step 4: Use It

```python
# Your base prompt
base_prompt = """You are a PII redaction system for healthcare data.
Replace personally identifiable information with typed tags like [NAME], [SSN], [PHONE]."""

# Enhance with memory
enhanced_prompt = build_prompt_with_memory(base_prompt, task_scope="pii_redaction")

# Call the LLM
result = spark.sql(f"""
    SELECT ai_query(
        'databricks-meta-llama-3-3-70b-instruct',
        concat('{enhanced_prompt}', '

Text to redact:
', clinical_notes)
    ) AS redacted
    FROM patient_records
    LIMIT 10
""")
```

**What the LLM actually sees:**

```
You are a PII redaction system for healthcare data.
Replace personally identifiable information with typed tags like [NAME], [SSN], [PHONE].

## Design Decisions (follow these)
- Use typed tags [NAME], [SSN], [PHONE] instead of generic [REDACTED]

## Learned Patterns (watch for these)
- Phone numbers with extensions (x1234) require explicit handling

Text to redact:
Patient John Smith called from 555-1234 x789 regarding his prescription...
```

---

## The RAG + RLM Architecture

This skill uses the same memory architecture as [soul.py](https://github.com/menonpg/soul.py):

**RAG (Retrieval-Augmented Generation):**
- Store memories in Unity Catalog tables
- Retrieve relevant context via SQL or Vector Search
- Inject into prompts before generation

**RLM (Recursive Language Modeling):**
- Accumulate raw feedback over time
- Periodically distill feedback into high-confidence patterns
- Patterns with high frequency/confidence surface first

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG + RLM MEMORY STACK                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Feedback   │ →  │  Patterns   │ →  │  Decisions  │         │
│  │  (raw)      │    │  (distilled)│    │  (explicit) │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│        ↑                   ↑                   ↑                │
│   User reports       Auto-extracted       You document          │
│   bugs/corrections   from feedback        deliberately          │
│                                                                  │
│  Low confidence ←────────────────────────→ High confidence      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Going Further

| Feature | Description | Reference |
|---------|-------------|-----------|
| **Full Schema** | Production DDL with indexes, retention, confidence decay | [1-memory-schema.md](1-memory-schema.md) |
| **Vector Search** | Semantic retrieval (find by meaning, not just task_scope) | [2-vector-search-setup.md](2-vector-search-setup.md) |
| **Learning Pipeline** | Auto-extract patterns from feedback using Lakeflow | [3-learning-pipeline.md](3-learning-pipeline.md) |
| **MLflow Integration** | Track which memories shaped each prompt version | [4-mlflow-integration.md](4-mlflow-integration.md) |

---

## Common Issues

| Problem | Solution |
|---------|----------|
| Prompt gets too long | Limit to 3-5 patterns. Use `LIMIT 5` and `ORDER BY confidence DESC` |
| Old patterns conflict with new | Add `superseded_by` column; filter out superseded patterns |
| Need semantic search | Set up Vector Search index (see reference file) |
| Want automatic pattern extraction | Deploy the learning pipeline (see reference file) |

---

## Why This Matters

> "MLflow tracks what you deployed. Memory tracks what you learned."

Without memory:
- Session 1: You fix a bug
- Session 10: Someone else hits the same bug
- Session 50: The fix is folklore, not code

With memory:
- Session 1: You fix a bug, log the pattern
- Session 10: Pattern surfaces automatically
- Session 50: The system has learned 50 sessions worth of patterns

**The learning compounds.**
