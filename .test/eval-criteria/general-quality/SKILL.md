---
name: general-quality
description: >
  General response quality evaluation. Always applicable regardless of
  domain. Covers response structure, actionability, clarity, and
  hallucination detection.
metadata:
  category: evaluation
  version: "1.0"
  applies_to: []
---

## General Quality Rubric

When evaluating any Claude Code agent trace, check these dimensions:

### 1. Actionable Output
- Can the user directly use the response (copy-paste code, follow steps)?
- Are code examples complete and runnable, not fragments?
- Are file paths, table names, and API references concrete?

### 2. Structured Response
- Code is in fenced code blocks with correct language tags
- Steps are numbered or bulleted for multi-step tasks
- Explanations are concise — answer first, context after

### 3. No Hallucination
- All referenced APIs, functions, and parameters must actually exist
- Databricks features must be current (not deprecated)
- Tool names in traces must match real MCP tool names
- No invented catalog/schema/table names unless the user specified them

### 4. Conciseness
- Answers the question without excessive preamble or disclaimers
- Doesn't repeat the question back
- Doesn't explain basic concepts the user didn't ask about

### 5. Error Handling
- If the agent encountered errors during execution, did it recover?
- Did it explain errors to the user when relevant?
- Did it avoid silently swallowing failures?
