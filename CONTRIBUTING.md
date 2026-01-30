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

When adding a new skill to `databricks-skills/`:

1. Create a directory with a descriptive name
2. Include a `SKILL.md` file that defines:
   - Trigger conditions (when the skill activates)
   - Core patterns and best practices
   - Code examples
3. Add supporting documentation files as needed
4. Update the skills table in the main README.md

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
