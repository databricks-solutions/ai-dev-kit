# Test Format Specification

Reference for ai-dev-kit's skill testing formats: `ground_truth.yaml`, `manifest.yaml`, and routing tests.

All test files live at the repository root under `.test/skills/`, not relative to the skill directory.

## File Locations

```
.test/skills/
├── _routing/
│   └── ground_truth.yaml          # Routing tests (shared across all skills)
├── {skill-name}/
│   ├── ground_truth.yaml          # Skill-specific test cases
│   ├── candidates.yaml            # Pending test cases for review
│   └── manifest.yaml              # Evaluation configuration
```

## Manifest (`manifest.yaml`)

Defines skill metadata, evaluation datasets, scorers, and quality gates.

```yaml
skill:
  name: "{skill-name}"                              # Must match directory name
  source_path: "databricks-skills/{skill-name}"      # Path to skill source
  description: "{Short description of what's being tested}"

evaluation:
  datasets:
    - path: ground_truth.yaml
      type: yaml

  scorers:
    tier1:                    # Deterministic (fast, run first)
      - python_syntax         # AST parsing of Python code blocks
      - sql_syntax            # Structural SQL validation
      - pattern_adherence     # Regex pattern matching
      - no_hallucinated_apis  # Check for deprecated/incorrect APIs
    tier2:                    # Execution-based
      - code_executes         # Validates generated code runs
    tier3:                    # LLM Judge (slowest, run last)
      - Guidelines            # Semantic evaluation against guidelines

  quality_gates:
    tier1_pass_rate: 1.0      # 100% — syntax and patterns must always pass
    tier2_pass_rate: 0.8      # 80% — some execution failures acceptable
    tier3_pass_rate: 0.85     # 85% — LLM judge threshold
```

### Available Scorers

**Tier 1 (Deterministic):**
| Scorer | Input | What It Checks |
|--------|-------|----------------|
| `python_syntax` | `outputs.response` | All Python code blocks parse via AST |
| `sql_syntax` | `outputs.response` | SQL statements are structurally valid |
| `pattern_adherence` | `outputs.response` + `expectations.expected_patterns` | Required regex patterns present |
| `no_hallucinated_apis` | `outputs.response` | No deprecated APIs (`@dlt.table`, `PARTITION BY`, etc.) |
| `expected_facts_present` | `outputs.response` + `expectations.expected_facts` | Required facts mentioned |

**Tier 2 (Execution):**
| Scorer | Input | What It Checks |
|--------|-------|----------------|
| `code_executes` | `outputs.execution_success` | Generated code runs successfully |

**Tier 3 (LLM Judge):**
| Scorer | Input | What It Checks |
|--------|-------|----------------|
| `Guidelines` | `expectations.guidelines` | Semantic adherence judged by LLM |

**Choose scorers based on your skill:**
- Python-only skill: include `python_syntax`, drop `sql_syntax`
- SQL-only skill: include `sql_syntax`, drop `python_syntax`
- Both: include both
- Always include: `pattern_adherence`, `no_hallucinated_apis`
- Include `Guidelines` for nuanced quality checks

## Ground Truth (`ground_truth.yaml`)

Test cases with inputs, expected outputs, expectations, and metadata.

```yaml
test_cases:
  - id: "{skill-name}_{category}_{number}"    # Unique identifier

    inputs:
      prompt: |
        {Natural language prompt as a user would write it.
        Be specific and realistic — avoid generic "do X" prompts.}

    outputs:
      response: |
        {Complete expected response including code blocks, explanations,
        and any other content the skill should produce.}
      execution_success: true                   # Optional: did the code run?

    expectations:
      expected_facts:                           # Tier 1: must be mentioned
        - "Uses STREAMING TABLE for incremental ingestion"
        - "Includes CLUSTER BY instead of PARTITION BY"

      expected_patterns:                        # Tier 1: regex patterns
        - pattern: "CREATE OR REFRESH STREAMING TABLE"
          min_count: 1
        - pattern: "CLUSTER BY"
          min_count: 1
        - pattern: "PARTITION BY"              # Negative check
          max_count: 0
          min_count: 0

      guidelines:                               # Tier 3: LLM judge criteria
        - "Must use modern SDP syntax, not legacy DLT"
        - "Should include metadata columns for lineage"

    metadata:
      category: "happy_path"                    # happy_path | edge_case | error_handling | boundary
      difficulty: "easy"                        # easy | medium | hard
      source: "manual"                          # manual | generated | trace
      tags: ["bronze", "ingestion"]             # Searchable tags
```

### Test Case Design Guidelines

**Minimum: 3-5 test cases per skill:**

1. **Happy path (easy)** — The most common, straightforward use case. If a user asks the simplest possible question about this skill, does it respond correctly?

2. **Happy path (medium)** — A realistic use case with some complexity (multiple parameters, configuration choices).

3. **Edge case** — Unusual input, boundary condition, or a request that tests the limits of the skill's knowledge.

4. **Error/boundary case** — Something the skill should gracefully handle or refuse (e.g., a request for a deprecated pattern).

5. **Multi-step (optional)** — A complex request requiring the skill to produce multiple code blocks or make architectural decisions.

**Writing good prompts:**
- Write as a real user would — natural language, not formal
- Include context: "I have a Delta table at catalog.schema.table with columns x, y, z..."
- Be specific enough that there's a clear "correct" answer
- Vary complexity across test cases

**Writing good expected responses:**
- Must be complete and correct — these are the gold standard
- Include all code blocks with language tags
- Use current APIs (not deprecated ones)
- Include brief explanations where a user would expect them

### Pattern Specification

Patterns support both simple strings and structured objects:

```yaml
expected_patterns:
  # Simple: just a regex string (min_count defaults to 1)
  - "WorkspaceClient"

  # Structured: full control
  - pattern: "CREATE OR REFRESH STREAMING TABLE"
    min_count: 1                # Minimum matches required (default: 1)
    max_count: 3                # Maximum matches allowed (optional)
    description: "Uses streaming table syntax"

  # Negative check: pattern must NOT appear
  - pattern: "@dlt\\.table"
    min_count: 0
    max_count: 0
    description: "Must not use deprecated DLT syntax"
```

## Routing Tests (`_routing/ground_truth.yaml`)

Shared across all skills. Tests whether prompts trigger the correct skill(s).

```yaml
test_cases:
  # Should trigger (single skill)
  - id: "routing_{skill-name}_001"
    inputs:
      prompt: "{Prompt that should clearly trigger this skill}"
    expectations:
      expected_skills: ["{skill-name}"]
      is_multi_skill: false
    metadata:
      category: "single_skill"
      difficulty: "easy"
      reasoning: "{Why this should trigger — which keyword/phrase matches}"

  # Should trigger (multi-skill)
  - id: "routing_{skill-name}_multi_001"
    inputs:
      prompt: "{Prompt that should trigger this skill AND another}"
    expectations:
      expected_skills: ["{skill-name}", "{other-skill}"]
      is_multi_skill: true
    metadata:
      category: "multi_skill"
      difficulty: "medium"
      reasoning: "{Why both skills should activate}"

  # Should NOT trigger (false positive guard)
  - id: "routing_{skill-name}_neg_001"
    inputs:
      prompt: "{Prompt that sounds related but should NOT trigger}"
    expectations:
      expected_skills: []
      is_multi_skill: false
    metadata:
      category: "no_match"
      difficulty: "medium"
      reasoning: "{Why this should NOT trigger despite seeming related}"
```

### Routing Test Guidelines

**Minimum per skill: 5 routing test cases:**
- 3 should-trigger (easy, medium, hard difficulty)
- 2 should-NOT-trigger (plausible false positives)

**Difficulty levels:**
- **Easy**: Contains explicit keywords from the skill description (e.g., "streaming table" for SDP)
- **Medium**: Uses domain language without exact keywords (e.g., "incremental ingestion pipeline")
- **Hard**: Ambiguous prompt that could match multiple skills but should match this one

**False positive guards:**
- Prompts that use related terminology but belong to a different skill
- Generic prompts that shouldn't trigger any skill (e.g., "What's the weather?")

## Initializing Test Scaffolding

Use the test framework to create template files:

```bash
# Via script
uv run python .test/scripts/init_skill.py {skill-name}

# Via slash command
/skill-test {skill-name} init
```

This creates:
- `.test/skills/{skill-name}/manifest.yaml` — with default scorers
- `.test/skills/{skill-name}/ground_truth.yaml` — empty template
- `.test/skills/{skill-name}/candidates.yaml` — empty template

## Running Tests

```bash
# Quick evaluation
uv run python .test/scripts/run_eval.py {skill-name}

# MLflow evaluation with LLM judges
uv run python .test/scripts/mlflow_eval.py {skill-name}

# Routing accuracy
uv run python .test/scripts/routing_eval.py _routing

# Compare against baseline
uv run python .test/scripts/regression.py {skill-name}

# Save current results as baseline
uv run python .test/scripts/baseline.py {skill-name}
```
