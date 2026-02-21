# gskill: Auto-Generate Optimized Skills for Your Repository

`gskill` uses [GEPA](https://github.com/databricks/gepa) to automatically generate optimized SKILL.md files that teach Claude Code how to work with your specific Databricks project patterns.

## What It Does

1. **Scans your repository** for Databricks patterns (SDK usage, SQL, notebooks, configs)
2. **Generates a SKILL.md** optimized for AI agent consumption
3. **Validates quality** using the skill-test evaluation framework
4. **Outputs to `.claude/skills/`** so Claude Code automatically picks it up

## Quick Start

### Prerequisites

```bash
# Install GEPA
pip install gepa>=0.1.0

# Set up LLM API keys (for GEPA reflection)
export OPENAI_API_KEY=your-key-here
```

### Generate a Skill

```bash
# From the ai-dev-kit repository
cd /path/to/ai-dev-kit

# Generate a skill for your project repo
uv run python -c "
from skill_test.optimize.gskill import run_gskill
result = run_gskill('/path/to/your/databricks-project')
print(f'Generated: {result[\"skill_path\"]}')
"
```

### Using with Claude Code

Once generated, the skill is automatically available to Claude Code:

```
your-repo/
├── .claude/
│   └── skills/
│       └── your-repo/
│           └── SKILL.md    # <- Generated skill
├── src/
│   └── ...
```

Claude Code reads `.claude/skills/*/SKILL.md` files and uses them as context when helping with your code.

## Configuration

### Presets

| Preset | Iterations | Best For |
|--------|-----------|----------|
| `quick` | 15 | Initial generation, small repos |
| `standard` | 50 | Most repos (default) |
| `thorough` | 150 | Large repos, production quality |

### Custom Context

Provide additional files for gskill to consider:

```python
from skill_test.optimize.gskill import run_gskill

result = run_gskill(
    repo_path="/path/to/your/repo",
    preset="standard",
    context_files=[
        "docs/architecture.md",
        "README.md",
        "src/config.py",
    ],
)
```

## Evaluating Generated Skills

Use the ai-dev-kit evaluation framework to validate generated skills:

```bash
# 1. Add test cases for the generated skill
uv run python .test/scripts/init_skill.py your-skill-name

# 2. Add ground truth test cases
uv run python .test/scripts/add.py your-skill-name

# 3. Run evaluation
uv run python .test/scripts/run_eval.py your-skill-name

# 4. Optimize further with GEPA
uv run python .test/scripts/optimize.py your-skill-name
```

## How It Works

```
Your Repository
     │
     ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Scan for │ --> │ Generate │ --> │ Validate │ --> SKILL.md
│ patterns │     │ SKILL.md │     │ quality  │
└──────────┘     └──────────┘     └──────────┘
                      │
                      ▼
               GEPA optimize_anything
               (reflects on quality,
                iterates to improve)
```

GEPA's `optimize_anything` treats the SKILL.md as the artifact to optimize. It:
- Starts with patterns found in your repo as the seed
- Uses GEPA's reflection LM to propose improvements
- Scores each iteration for quality, correctness, and conciseness
- Selects the best candidate via Pareto frontier optimization

## Tips

- **Keep skills focused**: One skill per domain (e.g., separate skills for "data pipeline" and "model serving")
- **Add test cases**: Skills with ground truth test cases optimize much better than bootstrap mode
- **Iterate**: Run `optimize.py` after adding test cases for incremental improvement
- **Token budget**: Skills should be as concise as possible -- every token consumed is agent context window budget
