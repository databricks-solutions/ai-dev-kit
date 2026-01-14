# Databricks Python App Skill

Claude Agent skill for building Python-based Databricks applications with various frameworks.

## Structure

```
databricks-app-python/
├── SKILL.md           # Main skill file with core patterns
├── dash.md            # Dash framework specific guide
├── streamlit.md       # Streamlit guide (coming soon)
├── flask.md           # Flask guide (coming soon)
└── README.md          # This file
```

## Overview

This skill provides comprehensive guidance for building Python applications for Databricks, including:

### Core Components (SKILL.md)
- Architecture patterns
- Pydantic data models
- Mock and real backend patterns
- Databricks connectivity
- Unity Catalog integration
- Environment configuration
- Best practices

### Framework-Specific Guides

#### Dash (dash.md)
- Complete Dash application structure
- Component patterns (cards, tables, charts, modals)
- Callback patterns and best practices
- Plotly chart examples
- Bootstrap styling
- Common pitfalls and solutions

#### Coming Soon
- **streamlit.md** - Streamlit patterns for rapid prototyping
- **flask.md** - Flask patterns for custom web apps
- **gradio.md** - Gradio for ML model interfaces

## Usage

When user requests a Python app for Databricks:

1. **SKILL.md** provides the foundation:
   - Data model design
   - Backend architecture (mock + real)
   - Databricks connectivity patterns
   - Database setup

2. **Framework-specific file** provides implementation:
   - UI component patterns
   - Framework-specific callbacks/routing
   - Styling and theming
   - Deployment configuration

## Design Philosophy

### Separation of Concerns
- **Core patterns** (SKILL.md) - Framework-agnostic
- **Framework details** (dash.md, etc.) - Implementation specifics

### Progressive Complexity
- Start with mock backend (rapid development)
- Add real backend (production ready)
- Scale with Unity Catalog

### Consistent Architecture
All apps follow same pattern:
```
models.py           → Data definitions
backend_mock.py     → Sample data
backend_real.py     → Databricks SQL
{framework}_app.py  → UI implementation
setup_database.py   → Schema initialization
```

## Example Applications

### Order Management (Dash)
Location: `/example-app-dash/`

Features:
- Dashboard with statistics and charts
- Filterable orders table
- Customer and product management
- Order details modal
- Mock and real backend support

To run:
```bash
cd example-app-dash
uv pip install -r requirements.txt
USE_MOCK_BACKEND=true uv run python dash_app.py
```

## Adding New Frameworks

To add support for a new framework:

1. Create `{framework}.md` in this directory
2. Follow the structure of `dash.md`:
   - When to use
   - Dependencies
   - Project structure
   - Component patterns
   - Best practices
   - Common pitfalls
   - Example code

3. Update `SKILL.md` to reference new framework
4. Create example app in `/example-app-{framework}/`

## Contributing

When updating this skill:

1. **SKILL.md changes**: Update if affecting all frameworks
   - New backend patterns
   - Database connectivity
   - Environment configuration
   - Pydantic model patterns

2. **Framework-specific changes**: Update individual files
   - New component patterns
   - Framework version updates
   - Best practices
   - Bug fixes

3. Keep example apps in sync with documentation

## Testing

Before committing changes:

1. Test example apps run without errors
2. Verify all code examples are syntactically correct
3. Check cross-references between files work
4. Ensure new patterns follow existing conventions

## Related Skills

- **databricks-app-apx** - APX framework (FastAPI + React)
- **databricks-dev** - General Databricks development
- **python-dev** - Python development standards
- **asset-bundles** - Databricks Asset Bundles

## Support

For issues or questions:
1. Check framework-specific documentation
2. Review example applications
3. Consult Databricks documentation
4. Check framework-specific communities
