---
name: skill-authoring
description: "Guided workflow for creating new Databricks skills for ai-dev-kit. Use when a contributor wants to create a new skill, draft a SKILL.md, generate test cases, or improve an existing skill's structure. Triggers on 'create skill', 'new skill', 'author skill', 'draft skill', 'skill template', or 'write a skill for'."
---

# Databricks Skill Authoring Guide

Conversational workflow for creating high-quality Databricks skills in ai-dev-kit. Adapted from [Anthropic's skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) (Apache 2.0) for ai-dev-kit conventions.

## References

- [Skill Format Specification](references/skill-format.md) — Frontmatter rules, progressive disclosure, section conventions
- [Test Format Specification](references/test-format.md) — ground_truth.yaml and manifest.yaml schemas

## Workflow Overview

Follow these phases in order. Do not skip phases — each builds on the previous.

```
Phase 1: Capture Intent ──► Phase 2: Interview & Research ──► Phase 3: Write SKILL.md
    │                                                              │
    │                                                              ▼
    │                                                     Phase 4: Write Test Cases
    │                                                              │
    │                                                              ▼
    │                                                     Phase 5: Validate & Register
    │                                                              │
    │                                                              ▼
    └──────────────────────────────────────────────────── Phase 6: Evaluate & Improve
```

---

## Phase 1: Capture Intent

Ask the contributor these questions before writing anything:

1. **What Databricks feature or domain does this skill cover?**
   - e.g., "Unity Catalog metric views", "Lakebase autoscaling", "Model Serving endpoints"

2. **Who is the target user?**
   - Data engineers, data scientists, ML engineers, analysts, app developers?

3. **What are 3-5 specific tasks a user would ask Claude to do with this skill?**
   - These become the seed for test cases later.

4. **Does this overlap with an existing skill?**
   - Check `databricks-skills/` for related skills. If overlap exists, clarify the boundary.

5. **What language(s) should code examples use?**
   - Python, SQL, YAML (for bundles), or a mix?

**Output**: A short summary paragraph capturing the skill's purpose, audience, and scope. Save this — it becomes the seed for the description.

---

## Phase 2: Interview & Research

Dig deeper into the domain. Ask the contributor (or research from Databricks docs):

### Domain Questions
- What are the **critical rules** a user must always follow? (e.g., "always use serverless", "never use deprecated DLT syntax")
- What are the **common mistakes** or deprecated patterns to avoid?
- What **API versions or SDK methods** are relevant? Verify they exist in the current Databricks SDK.
- Are there **multiple approaches** to the same task? (e.g., Python SDK vs. SQL vs. CLI) — document the recommended one first.

### Scope Questions
- What should this skill **NOT** cover? (Explicit exclusions prevent scope creep)
- Are there **prerequisite skills** the user should know about? (e.g., databricks-unity-catalog for permissions)
- Should the skill reference any **MCP tools** from `databricks-mcp-server/`? If so, verify the tool names exist as `@mcp.tool` functions.

### Structure Questions
- Is the content **small enough for a single SKILL.md** (<500 lines)?
- If not, what content should go into **reference files**? (Deep API references, exhaustive parameter lists, migration guides)

**Output**: A structured outline of sections and reference files.

---

## Phase 3: Write SKILL.md

Create the skill directory and SKILL.md following ai-dev-kit conventions.

### 3.1 Directory Structure

```
databricks-skills/{skill-name}/
├── SKILL.md                    # Required — main skill file
├── {reference1}.md             # Optional — deep reference content
├── {reference2}.md             # Optional — additional patterns
└── ...
```

The directory name MUST match the `name` field in frontmatter.

### 3.2 Frontmatter

```yaml
---
name: {skill-name}
description: "{One paragraph, max 1024 chars. Must include 'Use when' trigger phrases. Be specific and pushy — Claude tends to under-trigger skills, so make the description assertive about when to activate.}"
---
```

**Frontmatter rules** (enforced by CI):
- `name`: Required. Lowercase letters, numbers, hyphens only. Max 64 chars. Must not contain "anthropic" or "claude".
- `description`: Required. Non-empty. Max 1024 chars. No XML tags. Must contain "Use when" with specific trigger scenarios.

**Writing effective descriptions:**
- Lead with what the skill does: "Creates, configures, and manages X..."
- Include explicit trigger phrases: "Use when building X, working with Y, or when the user mentions Z."
- List specific keywords that should activate the skill
- Be assertive — "Use when" not "Can be used when"
- Example from a good skill:
  ```
  "Patterns for Databricks Vector Search: create endpoints and indexes, query with filters, manage embeddings. Use when building RAG applications, semantic search, or similarity matching. Covers both storage-optimized and standard endpoints."
  ```

### 3.3 Progressive Disclosure Architecture

Structure content in three tiers:

| Tier | What | When Loaded | Budget |
|------|------|-------------|--------|
| **Metadata** | name + description in frontmatter | Always in context | ~100 words |
| **Body** | SKILL.md content below frontmatter | When skill triggers | <500 lines ideal |
| **References** | Separate .md files | When Claude reads them | Unlimited |

**Key principle**: Keep SKILL.md lean. Move deep reference material (exhaustive API docs, parameter lists, migration guides) into reference files. The body should contain enough to handle 80% of requests; reference files cover the remaining 20%.

### 3.4 Recommended Body Sections

Based on patterns from the best existing skills:

```markdown
# {Skill Title}

{One-paragraph summary + critical rules if any}

## When to Use

Use this skill when:
- {Specific scenario 1}
- {Specific scenario 2}
- {Specific scenario 3}

## Overview

{Component table or conceptual summary — help the user understand the landscape before diving into code}

## Quick Start

{The simplest, most common use case. Working code example the user can copy.}

## Common Patterns

### Pattern 1: {Descriptive Name}
{Code example + brief explanation}

### Pattern 2: {Descriptive Name}
{Code example + brief explanation}

## Reference Files

- [{reference1}.md]({reference1}.md) - {What this covers}
- [{reference2}.md]({reference2}.md) - {What this covers}

## Common Issues

| Issue | Solution |
|-------|----------|
| **{Problem}** | {Fix} |
| **{Problem}** | {Fix} |
```

**Section guidelines:**
- **Critical Rules**: If the domain has rules that MUST always be followed (like "always use serverless"), put them right after the title, before any other section. Use bold and imperative language.
- **When to Use**: Reinforces the description triggers. Helps Claude decide if the skill applies.
- **Overview**: Tables work well for comparing options (endpoint types, index types, SDK methods).
- **Quick Start**: Must be a complete, working example — not pseudocode. This is the most important section.
- **Common Patterns**: 2-5 patterns covering the most frequent use cases. Each should have a real code example.
- **Reference Files**: Only include if SKILL.md would exceed ~400 lines without them.
- **Common Issues**: Known gotchas, error messages, and their fixes.

### 3.5 Reference File Conventions

Reference files follow the same markdown format without frontmatter:

```markdown
# {Pattern/Topic Name}

## When to Use
{Specific scenario this reference covers}

## Code Example
{Working code with explanations}

## Explanation
{Why this approach, tradeoffs, alternatives}

## Common Variations
{Modifications for different scenarios}
```

### 3.6 Code Example Standards

- All code blocks MUST have a language tag (```python, ```sql, ```yaml, ```bash)
- Use realistic values, not "foo/bar" placeholders
- Include imports and setup — examples should be copy-pasteable
- Use current APIs only — no deprecated patterns (e.g., `@dp.table` not `@dlt.table`)
- Prefer the Databricks SDK (`from databricks.sdk import WorkspaceClient`) for Python examples

---

## Phase 4: Write Test Cases

Generate test scaffolding using the existing test framework.

### 4.1 Initialize Test Scaffolding

Run:
```bash
uv run python .test/scripts/init_skill.py {skill-name}
```

Or use the `/skill-test` command:
```
/skill-test {skill-name} init
```

This creates the test directory at `.test/skills/{skill-name}/` with template files.

### 4.2 Write Ground Truth

Create `.test/skills/{skill-name}/ground_truth.yaml` with 3-5 test cases. Use the tasks from Phase 1 as seeds.

See [Test Format Specification](references/test-format.md) for the full schema.

**Test case guidelines:**
- Include at least one "happy path" (straightforward use case)
- Include at least one "edge case" (unusual input, boundary condition)
- Include at least one that tests the skill's boundaries (what it should NOT do)
- Use realistic prompts — write them as a user would naturally phrase the request
- Expected responses should be complete and correct — they become the reference standard

### 4.3 Write Routing Tests

Add entries to `.test/skills/_routing/ground_truth.yaml`:

```yaml
# Should trigger
- id: "routing_{skill-name}_001"
  inputs:
    prompt: "{A prompt that should trigger this skill}"
  expectations:
    expected_skills: ["{skill-name}"]
    is_multi_skill: false
  metadata:
    category: "single_skill"
    difficulty: "easy"
    reasoning: "{Why this should trigger the skill}"

# Should NOT trigger
- id: "routing_{skill-name}_neg_001"
  inputs:
    prompt: "{A prompt that sounds related but should NOT trigger}"
  expectations:
    expected_skills: []
    is_multi_skill: false
  metadata:
    category: "no_match"
    difficulty: "medium"
    reasoning: "{Why this should NOT trigger despite seeming related}"
```

Include at minimum:
- 3 should-trigger prompts (easy, medium, hard)
- 2 should-NOT-trigger prompts (plausible false positives)

### 4.4 Configure Manifest

Edit `.test/skills/{skill-name}/manifest.yaml`:

```yaml
skill:
  name: "{skill-name}"
  source_path: "databricks-skills/{skill-name}"
  description: "{Short description}"

evaluation:
  datasets:
    - path: ground_truth.yaml
      type: yaml

  scorers:
    tier1:
      - python_syntax      # If skill produces Python
      - sql_syntax          # If skill produces SQL
      - pattern_adherence
      - no_hallucinated_apis
    tier2:
      - code_executes       # If execution can be verified
    tier3:
      - Guidelines

  quality_gates:
    tier1_pass_rate: 1.0
    tier2_pass_rate: 0.8
    tier3_pass_rate: 0.85
```

Remove scorers that don't apply (e.g., drop `sql_syntax` if the skill only produces Python).

---

## Phase 5: Validate & Register

### 5.1 Run CI Validation

```bash
python .github/scripts/validate_skills.py
```

This checks:
- SKILL.md exists with valid frontmatter
- name/description meet constraints
- Skill is registered in install_skills.sh

### 5.2 Register in Install Script

Add the skill name to the appropriate variable in `databricks-skills/install_skills.sh`:

1. Add to `DATABRICKS_SKILLS` (the main skill list)
2. Add to the appropriate profile in `install.sh` and `install.ps1` (data-engineer, analyst, ai-ml-engineer, or app-developer)
3. If the skill has extra files beyond SKILL.md, add entries to the `get_skill_extra_files()` function

### 5.3 Update README

Add the skill to the skills table in `databricks-skills/README.md`.

---

## Phase 6: Evaluate & Improve

Use the existing test framework to measure and improve quality.

### 6.1 Run Evaluation

```bash
# Quick evaluation against ground truth
uv run python .test/scripts/run_eval.py {skill-name}

# Full MLflow evaluation with LLM judges
uv run python .test/scripts/mlflow_eval.py {skill-name}

# Routing accuracy check
uv run python .test/scripts/routing_eval.py _routing
```

### 6.2 Save Baseline

Once results are acceptable:
```bash
uv run python .test/scripts/baseline.py {skill-name}
```

### 6.3 Optimize (Advanced)

For description optimization and skill improvement, use the GEPA framework:
```bash
uv run python .test/scripts/optimize.py {skill-name} --preset quick
```

Presets: `quick` (15 iterations), `standard` (50), `thorough` (150).

### 6.4 Iteration Loop

After evaluation, improve the skill by:
1. **Reviewing failures**: Read the evaluation output for failed test cases
2. **Identifying patterns**: Are failures concentrated in one area (e.g., SQL syntax, missing facts)?
3. **Updating SKILL.md**: Add missing patterns, fix incorrect examples, clarify ambiguous instructions
4. **Re-running evaluation**: Verify improvements and check for regressions

Repeat until quality gates are met:
- Tier 1 (syntax/patterns): 100% pass rate
- Tier 2 (execution): 80% pass rate
- Tier 3 (LLM judge): 85% pass rate

---

## Checklist

Before submitting a PR, verify:

- [ ] `SKILL.md` has valid frontmatter (name, description with "Use when" triggers)
- [ ] Description is assertive and includes specific trigger keywords
- [ ] Body is under 500 lines (reference files used for overflow)
- [ ] All code blocks have language tags
- [ ] Code examples use current APIs (no deprecated patterns)
- [ ] Quick Start example is complete and copy-pasteable
- [ ] Common Issues section covers known gotchas
- [ ] Test scaffolding exists at `.test/skills/{skill-name}/`
- [ ] At least 3 ground truth test cases written
- [ ] At least 5 routing test cases (3 positive, 2 negative) added
- [ ] `validate_skills.py` passes
- [ ] Skill registered in `install_skills.sh`
- [ ] Skill added to appropriate profile in `install.sh`/`install.ps1`
- [ ] Skills table updated in `databricks-skills/README.md`

---

## Attribution

This skill's authoring workflow is adapted from [Anthropic's skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator), licensed under Apache License 2.0.
