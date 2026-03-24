# Contributing to AI Dev Kit

This repository is maintained by Databricks and intended for contributions from Databricks Field Engineers. While the repository is public and meant to help anyone developing projects that use Databricks, external contributions are not currently accepted. Feel free to open an issue with requests or suggestions.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/databricks-solutions/ai-dev-kit.git
   cd ai-dev-kit
   ```

2. Set up the MCP server (includes databricks-tools-core):
   ```bash
   ./databricks-mcp-server/setup.sh
   ```

3. Configure authentication:
   ```bash
   export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
   export DATABRICKS_TOKEN="your-token"
   ```
   or
      ```bash
   export DATABRICKS_CONFIG_PROFILE="your-profile"
   ```

## Code Standards

- **Python**: Follow PEP 8 conventions
- **Documentation**: Update relevant SKILL.md files when adding or modifying functionality
- **Type hints**: Include type annotations for public functions
- **Naming**: Use lowercase with hyphens for directories (e.g., `databricks-tools-core`)

## Linting

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting. Run these before submitting a PR:

```bash
# Check for linting errors
uvx ruff@0.11.0 check \
  --select=E,F,B,PIE \
  --ignore=E401,E402,F401,F403,B017,B904,ANN,TCH \
  --line-length=120 \
  --target-version=py311 \
  databricks-tools-core/ databricks-mcp-server/

# Auto-fix linting errors where possible
uvx ruff@0.11.0 check --fix \
  --select=E,F,B,PIE \
  --ignore=E401,E402,F401,F403,B017,B904,ANN,TCH \
  --line-length=120 \
  --target-version=py311 \
  databricks-tools-core/ databricks-mcp-server/

# Check formatting
uvx ruff@0.11.0 format --check \
  --line-length=120 \
  --target-version=py311 \
  databricks-tools-core/ databricks-mcp-server/

# Auto-format code
uvx ruff@0.11.0 format \
  --line-length=120 \
  --target-version=py311 \
  databricks-tools-core/ databricks-mcp-server/
```

## Testing

Run integration tests before submitting changes:

```bash
cd databricks-tools-core
uv run pytest tests/integration/ -v
```

Ensure your changes work with a live Databricks workspace.

## Pull Request Process

1. Create a feature branch from `main` (fork repo is necessary)
2. Make your changes with clear, descriptive commits
3. Test your changes against a Databricks workspace
4. Open a PR with:
   - Brief description of the change
   - Any relevant context or motivation
   - Testing performed
5. Address review feedback

## Adding New Skills

### Recommended: Use the Authoring Skill

The fastest way to create a high-quality skill is with the `skill-authoring` skill (available in `.skill-authoring/` when you clone the repo). Ask Claude:

> "Help me create a new skill for [Databricks feature]"

This walks you through a structured workflow: interview, draft, test, validate, register.

### Manual Workflow

If you prefer to work manually:

1. **Copy the template:**
   ```bash
   cp -r databricks-skills/TEMPLATE databricks-skills/your-skill-name
   ```

2. **Write SKILL.md** with valid frontmatter and content:
   ```yaml
   ---
   name: your-skill-name
   description: "What it does. Use when [scenario1], [scenario2], or when the user mentions [keywords]."
   ---
   ```

3. **Generate test scaffolding:**
   ```bash
   /skill-test your-skill-name init
   ```

4. **Write test cases** in `.test/skills/your-skill-name/ground_truth.yaml` (minimum 3 cases)

5. **Add routing tests** to `.test/skills/_routing/ground_truth.yaml` (minimum 3 positive, 2 negative)

6. **Register the skill:**
   - Add to `DATABRICKS_SKILLS` in `databricks-skills/install_skills.sh`
   - Add to appropriate profile in `install.sh` and `install.ps1`
   - Add to skills table in `databricks-skills/README.md`

7. **Validate:**
   ```bash
   python .github/scripts/validate_skills.py
   ```

### Quality Checklist

Before submitting a PR for a new skill, verify:

- [ ] **Frontmatter**: `name` (kebab-case, <=64 chars) and `description` (<=1024 chars, includes "Use when" triggers)
- [ ] **Description is assertive**: Uses "Use when" with specific triggers and domain keywords
- [ ] **Body under 500 lines**: Reference files used for overflow content
- [ ] **Code blocks have language tags**: ```python, ```sql, ```yaml, ```bash
- [ ] **Code examples are current**: No deprecated APIs (`@dlt.table`, `PARTITION BY`, `mlflow.evaluate`)
- [ ] **Quick Start is complete**: Copy-pasteable with imports and realistic values
- [ ] **Common Issues documented**: Known gotchas with solutions
- [ ] **Test scaffolding exists**: `.test/skills/your-skill-name/` with ground_truth.yaml and manifest.yaml
- [ ] **Routing tests added**: At least 5 entries (3 positive, 2 negative) in `_routing/ground_truth.yaml`
- [ ] **CI validation passes**: `python .github/scripts/validate_skills.py`
- [ ] **Registered in install scripts**: `install_skills.sh`, `install.sh`, `install.ps1`
- [ ] **README updated**: Skill added to `databricks-skills/README.md`

### Skill Format Reference

For detailed format specifications, see:
- `.skill-authoring/references/skill-format.md` — Frontmatter rules, progressive disclosure, section conventions
- `.skill-authoring/references/test-format.md` — ground_truth.yaml and manifest.yaml schemas

### Evaluation & Optimization

After creating a skill, measure and improve quality:

```bash
# Quick trigger smoke test
uv run python .test/scripts/quick_trigger.py your-skill-name

# Evaluation against ground truth
uv run python .test/scripts/run_eval.py your-skill-name

# Full MLflow evaluation with LLM judges
uv run python .test/scripts/mlflow_eval.py your-skill-name

# Description optimization (GEPA framework)
uv run python .test/scripts/optimize.py your-skill-name --preset quick
```

Quality gates to meet:
- **Tier 1** (syntax/patterns): 100% pass rate
- **Tier 2** (execution): 80% pass rate
- **Tier 3** (LLM judge): 85% pass rate

## Updating Existing Skills

The `main` branch install script clones the latest release, so even after a skill PR update is merged, the latest content will not be installed until a new release is produced.

## Security

- Never commit credentials, tokens, or sensitive data
- Use synthetic data for examples and tests
- Review changes for potential security issues before submitting

## License

By submitting a contribution, you agree that your contributions will be licensed under the same terms as the project (see [LICENSE.md](LICENSE.md)).

You certify that:
- You have the right to submit the contribution
- Your contribution does not include confidential or proprietary information
- You grant Databricks the right to use, modify, and distribute your contribution
