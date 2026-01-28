# Skill Testing Framework

Test Databricks skills with real execution on serverless compute.

**Note:** This framework is for contributors only and is not distributed via install_skills.sh.

## Prerequisites

```bash
uv pip install -e ".test/[dev]"
```

Requires a Databricks workspace with serverless SQL/compute enabled.

## Installation

The skill-test skill must be installed to `.claude/skills/` for Claude Code to discover it:

```bash
# Sync skill files from .test/ to .claude/skills/skill-test/
.test/install_skill_test.sh
```

This copies:
- `SKILL.md` - Skill instructions for Claude
- `scripts/` - Wrapper scripts Claude executes
- `references/` - YAML schemas and scorer documentation

## Quick Start
Start a new Claude Code session from within the project root folder - `ai-dev-kit`. Then run the desired steps below.

### 1. Test an Existing Skill

```
/skill-test spark-declarative-pipelines
```

This runs all test cases in `skills/spark-declarative-pipelines/ground_truth.yaml` and reports pass/fail for each code block.

### 2. Add a New Test Case

```
/skill-test spark-declarative-pipelines add
```

Claude will:
1. Ask for your test prompt
2. Invoke the skill to generate a response
3. Execute code blocks on Databricks
4. Auto-save passing tests to `ground_truth.yaml`
5. Save failing tests to `candidates.yaml` for review

### 3. Create a Regression Baseline

```
/skill-test spark-declarative-pipelines baseline
```

Saves current metrics to `baselines/spark-declarative-pipelines/baseline.yaml`.

### 4. Check for Regressions

```
/skill-test spark-declarative-pipelines regression
```

Compares current pass rate against the saved baseline.

### 5. Run MLflow Evaluation with LLM Judges

```
/skill-test spark-declarative-pipelines mlflow
```

Runs full evaluation with:
- Deterministic scorers (syntax, patterns, facts)
- LLM-based scorers (Safety, Guidelines)
- Logs results to Databricks MLflow

### 6. View Scorer Configuration

```
/skill-test spark-declarative-pipelines scorers
```

Shows enabled scorers, LLM scorers, and default guidelines for the skill.

### 7. Update Scorer Configuration

```
/skill-test spark-declarative-pipelines scorers update --add-guideline "Must use CLUSTER BY"
```

Modifies the manifest.yaml to add/remove scorers or update guidelines.

## Test a New Skill

```
/skill-test my-new-skill init
```

Creates scaffolding:
```
skills/my-new-skill/
├── ground_truth.yaml   # Verified test cases
├── candidates.yaml     # Pending review
└── manifest.yaml       # Skill metadata
```

## Test Case Format

```yaml
test_cases:
  - id: "sdp_bronze_001"
    inputs:
      prompt: "Create a bronze ingestion pipeline for JSON files"
    outputs:
      response: |
        ```sql
        CREATE OR REFRESH STREAMING TABLE bronze_events
        AS SELECT * FROM STREAM read_files('/data/events/*.json')
        ```
      execution_success: true
    expectations:
      expected_facts:
        - "STREAMING TABLE"
      guidelines:
        - "Must use modern SDP syntax"
```

## Directory Structure

```
.test/                            # Source of truth
├── SKILL.md                      # Skill instructions (synced to .claude/)
├── install_skill_test.sh         # Sync script
├── pyproject.toml                # Package config
├── README.md                     # This file
├── scripts/                      # Wrapper scripts (synced to .claude/)
│   ├── mlflow_eval.py
│   ├── run_eval.py
│   ├── baseline.py
│   ├── regression.py
│   └── init_skill.py
├── src/skill_test/               # Python package
│   ├── cli/                      # CLI commands
│   ├── fixtures/                 # Test fixture setup
│   ├── grp/                      # Generate-Review-Promote pipeline
│   ├── runners/                  # Evaluation runners
│   └── scorers/                  # Evaluation scorers
├── skills/                       # Test definitions per skill
│   └── {skill-name}/
│       ├── ground_truth.yaml     # Verified tests
│       ├── candidates.yaml       # Pending review
│       └── manifest.yaml         # Scorer configuration
├── baselines/                    # Regression baselines
├── references/                   # Documentation (synced to .claude/)
│   ├── yaml-schemas.md
│   └── scorers.md
└── tests/                        # Unit tests
```

After running `install_skill_test.sh`:

```
.claude/skills/skill-test/        # Installed skill
├── SKILL.md                      # Skill instructions
├── scripts/                      # Wrapper scripts
│   ├── mlflow_eval.py
│   ├── run_eval.py
│   ├── baseline.py
│   ├── regression.py
│   └── init_skill.py
└── references/                   # Documentation
    ├── yaml-schemas.md
    └── scorers.md
```

## Subcommands

| Command | Description |
|---------|-------------|
| `run` | Execute tests against ground truth (default) |
| `add` | Interactively add a new test case |
| `baseline` | Save current results as regression baseline |
| `regression` | Compare against baseline |
| `mlflow` | Run MLflow evaluation with LLM judges |
| `scorers` | List configured scorers for a skill |
| `scorers update` | Add/remove scorers or update default guidelines |
| `init` | Create scaffolding for a new skill |
| `sync` | Sync YAML to Unity Catalog (Phase 2 - not yet implemented) |

### Subcommand Details

#### `run` (default)
```
/skill-test spark-declarative-pipelines
/skill-test spark-declarative-pipelines run
```
Executes code blocks from ground truth test cases and reports pass/fail. Uses Databricks serverless by default, falls back to local syntax validation if unavailable.

#### `mlflow`
```
/skill-test spark-declarative-pipelines mlflow
```
Runs full MLflow evaluation including:
- **Deterministic scorers**: `python_syntax`, `sql_syntax`, `pattern_adherence`, `no_hallucinated_apis`, `expected_facts_present`
- **LLM scorers**: `Safety`, `guidelines_from_expectations`
- Logs metrics and results to Databricks MLflow experiment

#### `scorers`
```
/skill-test spark-declarative-pipelines scorers
```
Displays the scorer configuration from `manifest.yaml`:
- Enabled deterministic scorers
- LLM-based scorers
- Default guidelines for evaluation

#### `scorers update`
```
/skill-test spark-declarative-pipelines scorers update --add-guideline "Must include CLUSTER BY"
/skill-test spark-declarative-pipelines scorers update --remove-scorer no_hallucinated_apis
/skill-test spark-declarative-pipelines scorers update --add-scorer python_syntax
```
Modifies scorer configuration in `manifest.yaml`. Supports:
- `--add-guideline` / `--remove-guideline`: Modify default guidelines
- `--add-scorer` / `--remove-scorer`: Enable/disable scorers
- `--set-guidelines`: Replace all guidelines

#### `baseline`
```
/skill-test spark-declarative-pipelines baseline
```
Saves current evaluation metrics to `baselines/{skill}/baseline.yaml` for regression comparison.

#### `regression`
```
/skill-test spark-declarative-pipelines regression
```
Compares current pass rate against saved baseline. Reports regressions (lower scores) and improvements (higher scores).

#### `add`
```
/skill-test spark-declarative-pipelines add
```
Interactive workflow:
1. Prompts for test input
2. Invokes the skill to generate response
3. Executes code blocks on Databricks
4. Auto-saves passing tests to `ground_truth.yaml`
5. Saves failing tests to `candidates.yaml` for GRP review

#### `init`
```
/skill-test my-new-skill init
```
Creates test scaffolding for a new skill with template files.

## Usage

### Contributors (local development)

```bash
# One-time setup
pip install -e ".test/[dev]"
.test/install_skill_test.sh

# Use Claude Code slash command
/skill-test spark-declarative-pipelines run

# Or run scripts directly
python .claude/skills/skill-test/scripts/run_eval.py spark-declarative-pipelines

# Or Python CLI
skill-test spark-declarative-pipelines run
python -m skill_test spark-declarative-pipelines run
```

### CI/CD (GitHub Actions)

```bash
pip install -e ".test/"
pytest .test/tests/
python .test/scripts/regression.py spark-declarative-pipelines
```

## Development Workflow

1. **Edit** files in `.test/` (source of truth)
2. **Sync** by running `.test/install_skill_test.sh`
3. **Test** using `/skill-test` command in Claude Code

To see what would be synced without making changes:

```bash
.test/install_skill_test.sh --dry-run
```
