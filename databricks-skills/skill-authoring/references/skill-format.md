# Skill Format Specification

Complete reference for ai-dev-kit skill format, frontmatter rules, and structural conventions.

## Directory Layout

```
databricks-skills/{skill-name}/
├── SKILL.md                    # Required — main skill instructions
├── {reference}.md              # Optional — deep reference content
└── ...                         # Additional reference files as needed
```

- Directory name must exactly match the `name` field in SKILL.md frontmatter
- Use lowercase letters, numbers, and hyphens only
- Prefix with `databricks-` for Databricks platform skills (convention, not enforced)

## Frontmatter Specification

SKILL.md must begin with YAML frontmatter delimited by `---`:

```yaml
---
name: "{skill-name}"
description: "{skill-description}"
---
```

### `name` (required)

| Constraint | Rule |
|------------|------|
| Format | Lowercase letters, numbers, hyphens only (`^[a-z0-9]+(-[a-z0-9]+)*$`) |
| Max length | 64 characters |
| Reserved words | Must not contain "anthropic" or "claude" |
| XML tags | Must not contain XML/HTML tags |
| Match | Must match the directory name |

### `description` (required)

| Constraint | Rule |
|------------|------|
| Min length | Non-empty |
| Max length | 1024 characters |
| XML tags | Must not contain XML/HTML tags |
| Trigger phrases | Should contain "Use when" with specific scenarios |

**Writing effective descriptions:**

The description is the primary mechanism Claude uses to decide whether to activate a skill. It is always loaded in context (~100 words). Make it count.

1. **Lead with action**: "Creates, configures, and manages..."
2. **Include explicit triggers**: "Use when building X, working with Y, or when the user mentions Z."
3. **List keywords**: Include domain-specific terms that should activate the skill
4. **Be assertive**: "Use when" not "Can be used when" — Claude under-triggers by default

**Good example:**
```
"Creates, configures, and updates Databricks Lakeflow Spark Declarative Pipelines (SDP/LDP)
using serverless compute. Handles streaming tables, materialized views, CDC, SCD Type 2, and
Auto Loader ingestion patterns. Use when building data pipelines, working with Delta Live Tables,
ingesting streaming data, implementing change data capture, or when the user mentions SDP, LDP,
DLT, Lakeflow pipelines, streaming tables, or bronze/silver/gold medallion architectures."
```

**Bad example:**
```
"A skill for Databricks pipelines."
```

## Progressive Disclosure Model

Content is structured in three tiers to manage context window usage:

| Tier | Location | When Loaded | Budget |
|------|----------|-------------|--------|
| **1. Metadata** | Frontmatter (name + description) | Always in context | ~100 words |
| **2. Body** | SKILL.md content below frontmatter | When skill triggers | <500 lines |
| **3. References** | Separate .md files in same directory | When Claude reads them on demand | Unlimited |

### Tier 1: Metadata
- Always in Claude's context window
- Must be information-dense — every word earns its place
- The description is the skill's "elevator pitch" AND its routing signal

### Tier 2: Body (SKILL.md)
- Loaded when the skill triggers based on description match
- Target: under 500 lines for the full body
- Should handle 80% of user requests without needing reference files
- Include working code examples, common patterns, and critical rules

### Tier 3: References
- Loaded only when Claude specifically reads them (via `Read` tool)
- Use for: exhaustive API references, parameter lists, migration guides, advanced patterns
- No line limit, but keep individual files focused on one topic
- Reference them from SKILL.md: `See [API Reference](api-reference.md) for details.`

## Body Section Conventions

Based on analysis of the best existing skills (databricks-vector-search, databricks-spark-declarative-pipelines, databricks-python-sdk):

### Recommended Sections (in order)

1. **Title** (`# {Skill Name}`) — Brief summary paragraph
2. **Critical Rules** — Only if the domain has rules that MUST always be followed. Use bold, imperative language. Place before all other sections.
3. **When to Use** — Bulleted list of specific scenarios. Reinforces description triggers.
4. **Overview** — Conceptual summary. Tables work well for comparing options (types, methods, approaches).
5. **Quick Start** — The simplest, most common use case. Complete, working, copy-pasteable code.
6. **Common Patterns** — 2-5 patterns for frequent use cases. Each has a heading, code example, and brief explanation.
7. **Reference Files** — Links to reference .md files with descriptions of what each covers.
8. **Common Issues** — Table of known gotchas, error messages, and fixes.

### Section Guidelines

- **Critical Rules**: Not every skill needs this. Only include when there are hard requirements (e.g., "MUST use serverless", "NEVER use deprecated syntax"). Example from databricks-spark-declarative-pipelines:
  ```markdown
  ## Critical Rules (always follow)
  - **MUST** confirm language as Python or SQL
  - **MUST** create serverless pipelines by default
  ```

- **Quick Start**: This is the most important section. It should be a single, complete example that works out of the box. Include imports, setup, and realistic values.

- **Common Patterns**: Each pattern should have:
  - A descriptive heading (`### Pattern 2: Hybrid Search with Filters`)
  - Working code (with language tag)
  - 1-2 sentences explaining when/why to use this pattern

- **Common Issues**: Use a table format for scannability:
  ```markdown
  | Issue | Solution |
  |-------|----------|
  | **`PERMISSION_DENIED` on endpoint** | Grant `USE ENDPOINT` via Unity Catalog |
  ```

## Code Example Standards

- All code blocks MUST have a language tag: ```python, ```sql, ```yaml, ```bash
- Use realistic values (catalog names, table names, paths) — not "foo", "bar", "example"
- Include imports and setup code — examples should be copy-pasteable
- Use current Databricks APIs only:
  - `@dp.table` not `@dlt.table`
  - `CLUSTER BY` not `PARTITION BY`
  - `mlflow.genai.evaluate` not `mlflow.evaluate`
  - `from databricks.sdk import WorkspaceClient` for SDK examples
- Show the most common/recommended approach first, alternatives second

## Registration

After creating a skill, it must be registered in three places:

1. **`databricks-skills/install_skills.sh`**: Add to `DATABRICKS_SKILLS` variable
2. **`install.sh` / `install.ps1`**: Add to the appropriate profile (data-engineer, analyst, ai-ml-engineer, app-developer)
3. **`databricks-skills/README.md`**: Add to the skills table

The CI validator (`validate_skills.py`) cross-references directories against `install_skills.sh` and will fail if a skill directory exists without registration.
