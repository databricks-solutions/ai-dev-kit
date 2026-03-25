# Customization Guide: Steering Skill Optimization with `--focus`

## 1. Overview

The `--focus` flag lets you steer skill optimization with natural language. It uses an LLM to make targeted adjustments to `manifest.yaml` and `ground_truth.yaml` before GEPA runs, so the optimizer prioritizes what matters to you.

### Quick Start

```bash
# Single focus area
uv run python .test/scripts/optimize.py databricks-bundles \
  --focus "prefix all catalogs with customer_ prefix"

# Multiple focus areas
uv run python .test/scripts/optimize.py databricks-bundles \
  --focus "prefix all catalogs with customer_ prefix" \
  --focus "always use serverless compute"

# Focus areas from a file
uv run python .test/scripts/optimize.py databricks-bundles \
  --focus-file my_focus_areas.txt

# Dry run to see what would change
uv run python .test/scripts/optimize.py databricks-bundles \
  --focus "prefix all catalogs with customer_ prefix" --dry-run

# Combined with presets
uv run python .test/scripts/optimize.py databricks-bundles \
  --focus "use DLT for all pipeline examples" --preset quick
```

### What Happens

1. The LLM reads SKILL.md, `manifest.yaml`, and `ground_truth.yaml`
2. It adds `[FOCUS]`-prefixed guidelines to the manifest
3. It adjusts relevant existing test cases (expectations, patterns, guidelines)
4. It generates 2-3 new test cases targeting the focus area
5. GEPA optimization then runs with these enhanced evaluation criteria

---

## 2. How Each `ground_truth.yaml` Field Impacts Optimization

### `outputs.response` - Reference Answer

**What it is:** The ideal response the judge compares agent output against.

**How it steers optimization:** The quality judge uses this as the gold standard. If the reference response includes specific patterns (e.g., parameterized catalogs), the optimizer learns to produce those patterns.

**Example focus prompt:** `"All examples should use variable substitution for catalog names"`

**Before:**
```yaml
outputs:
  response: |
    catalog: my_catalog
```

**After:**
```yaml
outputs:
  response: |
    catalog: ${var.catalog_prefix}_catalog
```

### `expectations.expected_facts` - Substring Assertions

**What it is:** Exact substrings that must appear in the response. Checked deterministically (case-insensitive).

**How it steers optimization:** Failed facts tell the optimizer exactly what content is missing. Adding facts about your focus area forces the optimizer to include that content.

**Example focus prompt:** `"Must explain the MEASURE() function wrapping"`

**Before:**
```yaml
expected_facts:
  - "Defines variables with default values"
```

**After:**
```yaml
expected_facts:
  - "Defines variables with default values"
  - "All catalog values use ${var.catalog_prefix} variable"
```

### `expectations.expected_patterns` - Regex Patterns

**What it is:** Regular expressions checked with `re.findall(pattern, response, re.IGNORECASE)`. Each has a `min_count` (minimum number of matches required) and a `description`.

**How it steers optimization:** Pattern failures are binary and precise. Adding patterns for your focus area creates hard requirements the optimizer must satisfy.

**Example focus prompt:** `"Prefix all catalogs with a configurable prefix variable"`

**Before:**
```yaml
expected_patterns:
  - pattern: 'catalog:'
    min_count: 2
    description: Defines catalog variable
```

**After:**
```yaml
expected_patterns:
  - pattern: 'catalog:'
    min_count: 2
    description: Defines catalog variable
  - pattern: '\$\{var\.catalog_prefix\}'
    min_count: 1
    description: Uses catalog prefix variable
```

### `expectations.guidelines` - LLM Judge Rules

**What it is:** Natural-language evaluation criteria passed to the LLM judge. The judge scores how well the response follows each guideline.

**How it steers optimization:** Guidelines are the most flexible steering mechanism. They influence the guideline adherence score (15% of total) and the quality composite (20% of total, which averages correctness + completeness + guideline adherence).

**Example focus prompt:** `"Must parameterize catalog names with a prefix variable"`

**Before:**
```yaml
guidelines:
  - "Must define variables at root level with defaults"
```

**After:**
```yaml
guidelines:
  - "Must define variables at root level with defaults"
  - "Must parameterize catalog names with a prefix variable"
```

### `metadata.tags` - Categorization

**What it is:** Tags for organizing and filtering test cases. No direct impact on optimization scoring.

**How it steers optimization:** Tags help identify which test cases were generated or adjusted by focus. Focus-generated test cases get tags matching the focus area.

---

## 3. How Each `manifest.yaml` Field Impacts Optimization

### `scorers.default_guidelines` - Global Guidelines

**What it is:** Guidelines applied to ALL test cases that don't define their own guidelines. These are merged with per-test-case guidelines by the quality judge.

**How it steers optimization:** Adding `[FOCUS]` guidelines here affects every evaluation, not just specific test cases. This is the broadest way to steer optimization.

**What `--focus` does:** Prepends `[FOCUS]` to each new guideline and appends to the list. Duplicates are skipped.

**Before:**
```yaml
default_guidelines:
  - "Response must address the user's request completely"
  - "YAML examples must be valid and properly indented"
```

**After:**
```yaml
default_guidelines:
  - "Response must address the user's request completely"
  - "YAML examples must be valid and properly indented"
  - "[FOCUS] All catalog references must use a configurable prefix variable"
  - "[FOCUS] Variable substitution syntax ${var.prefix} must be demonstrated"
```

### `quality_gates` - Pass/Fail Thresholds

**What it is:** Minimum score thresholds for each scorer. If a score falls below the gate, the test case fails.

**How it steers optimization:** Higher thresholds make the optimizer work harder to satisfy that criterion. `--focus` can only make thresholds stricter (higher), never looser.

**Before:**
```yaml
quality_gates:
  pattern_adherence: 0.9
  execution_success: 0.8
```

**After (if focus demands stricter pattern checking):**
```yaml
quality_gates:
  pattern_adherence: 0.95
  execution_success: 0.8
```

---

## 4. Prompting Examples

### Scenario: Customer wants all catalogs prefixed

```bash
--focus "When creating DABs, prefix all catalogs and schemas with a customer-specific prefix using variables"
```

**What changes:**
- **manifest.yaml**: Adds `[FOCUS] All catalog/schema references must use ${var.prefix}_catalog pattern`
- **ground_truth.yaml**: Existing multi-env test cases get new `expected_patterns` for `${var.prefix}` syntax; 2-3 new test cases about prefix configuration

### Scenario: Customer wants DLT examples in DABs

```bash
--focus "Include Delta Live Tables (DLT) pipeline examples in all DABs configurations"
```

**What changes:**
- **manifest.yaml**: Adds `[FOCUS] DABs examples should include DLT pipeline resource definitions`
- **ground_truth.yaml**: Existing pipeline test cases get DLT-specific patterns; new test cases cover DLT pipeline YAML configuration

### Scenario: Customer wants stricter SQL validation

```bash
--focus "All SQL examples must use parameterized queries, never string interpolation"
```

**What changes:**
- **manifest.yaml**: Adds `[FOCUS] SQL examples must use parameterized queries with bind variables`
- **quality_gates**: `pattern_adherence` may increase (e.g., 0.9 -> 0.95)
- **ground_truth.yaml**: SQL-related test cases get patterns checking for parameterized syntax

---

## 5. Reviewing and Rolling Back Changes

### Identifying Focus-Generated Content

- **Guidelines**: Look for the `[FOCUS]` prefix in `manifest.yaml` `default_guidelines`
- **Test cases**: Check `metadata.source: generated_from_focus` in `ground_truth.yaml`
- **Adjusted responses**: Check `metadata._focus_original_response` for the pre-focus original

### Rolling Back

**Remove focus guidelines from manifest:**
```bash
# Edit manifest.yaml, delete lines starting with "[FOCUS]"
grep -v "^\s*- \"\[FOCUS\]" .test/skills/<skill>/manifest.yaml > tmp && mv tmp .test/skills/<skill>/manifest.yaml
```

**Remove focus-generated test cases:**
```python
# In Python
import yaml
with open(".test/skills/<skill>/ground_truth.yaml") as f:
    data = yaml.safe_load(f)
data["test_cases"] = [
    tc for tc in data["test_cases"]
    if tc.get("metadata", {}).get("source") != "generated_from_focus"
]
with open(".test/skills/<skill>/ground_truth.yaml", "w") as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False)
```

**Restore original responses (for adjusted test cases):**
```python
for tc in data["test_cases"]:
    original = tc.get("metadata", {}).pop("_focus_original_response", None)
    if original:
        tc["outputs"]["response"] = original
```

**Or use git:**
```bash
git checkout -- .test/skills/<skill>/manifest.yaml .test/skills/<skill>/ground_truth.yaml
```
