# MCP Server Decommissioning Plan

## Executive Summary

This plan outlines removing `databricks-tools-core` and `databricks-mcp-server` from the main AI Dev Kit project, simplifying the installation to focus on **standalone skills only**.

## Current State Analysis

### What Exists Today

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| `databricks-tools-core/` | Python library with high-level Databricks functions | None (standalone) |
| `databricks-mcp-server/` | MCP server exposing 50+ tools | Depends on databricks-tools-core |
| `databricks-skills/` | Markdown skills + self-contained Python scripts | **None** (already standalone) |
| `databricks-builder-app/` | Full-stack web application | **Depends on BOTH** tools-core and mcp-server |

### Files Referencing MCP/Core

**Shell scripts:**
- `install.sh` (main installer) - lines 1071, 251, 657, etc.
- `databricks-mcp-server/setup.sh`
- `.claude-plugin/setup.sh`
- `databricks-builder-app/scripts/deploy.sh` (lines 193-195)
- `databricks-builder-app/scripts/start_local.sh` (lines 205-206)

**Documentation:**
- `README.md` - references both packages in "What's Included" and "Core Library" sections
- `SECURITY.md` - mentions packages in installation flow
- `CONTRIBUTING.md` - setup instructions reference mcp-server
- `databricks-builder-app/README.md` - architecture diagram includes mcp-server

## builder-app Refactoring (Much Simpler Than Expected!)

### Reference Implementation

A cleaner solution exists in `industry-demo-prompts/app/src/demo_prompt_generator/backend/services/agent.py`.

**Key insight:** MCP tools are NOT needed. Skills + standard SDK tools provide everything:

```python
# Note: MCP tools removed - ai-dev-kit now uses CLI tools via skills
allowed_tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"]
```

### Current builder-app Dependencies

| File | Import | Can Be Removed? |
|------|--------|----------------|
| `server/services/agent.py` | `databricks_tools_core.auth` | Yes - use `databricks.sdk.WorkspaceClient()` directly |
| `server/services/databricks_tools.py` | `databricks_mcp_server.*` | **DELETE ENTIRE FILE** |
| `server/services/clusters.py` | `databricks_tools_core.auth` | Yes - use SDK directly |
| `server/services/warehouses.py` | `databricks_tools_core.auth` | Yes - use SDK directly |
| `server/services/user.py` | `databricks_tools_core.identity` | Yes - inline constants |
| `server/db/database.py` | `databricks_tools_core.identity` | Yes - inline constants |
| `alembic/env.py` | `databricks_tools_core.identity` | Yes - inline constants |

### Refactoring Steps

1. **Delete `databricks_tools.py`** (433 lines) - No longer needed
2. **Simplify `agent.py`**:
   - Remove MCP server loading
   - Use standard SDK tools: `["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"]`
   - Add `setting_sources=["project"]` to enable skill discovery
   - Copy client pooling pattern from reference implementation
3. **Replace auth imports** - Use `databricks.sdk.WorkspaceClient()` directly
4. **Inline identity constants**:
   ```python
   # Instead of: from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION
   PRODUCT_NAME = "databricks-builder-app"
   PRODUCT_VERSION = "0.1.0"
   ```
5. **Update deploy.sh** - Remove package copying steps
6. **Update pyproject.toml** - Remove `databricks_tools_core*` and `databricks_mcp_server*` from includes

### Code Reduction

| File | Before | After |
|------|--------|-------|
| `databricks_tools.py` | 433 lines | **DELETED** |
| `agent.py` | ~400 lines | ~300 lines |
| `deploy.sh` | Complex pkg copy | Simple |

**Total: ~500+ lines removed, simpler architecture**

### Phase 2: Simplify Main Project

Once builder-app is self-contained:

#### 2.1 Delete Folders
```bash
rm -rf databricks-tools-core/
rm -rf databricks-mcp-server/
```

#### 2.2 Simplify install.sh

**Option A: Remove MCP entirely (Recommended)**

Replace the 1790-line `install.sh` with a simplified version that:
- Only installs skills (like `install_skills.sh` does)
- Removes all MCP configuration code
- Removes the Python venv creation for MCP

**Option B: Keep MCP as optional**

Keep `--skills-only` as default, make MCP opt-in via `--with-mcp`:
- Default behavior = skills only
- `--with-mcp` = old behavior

#### 2.3 Update Documentation

**README.md changes:**
- Remove "Core Library" section
- Remove "MCP Tools Only" from table
- Remove databricks-tools-core from "What's Included"
- Update architecture diagram (remove MCP layer)

**Files to update:**
- `README.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `databricks-builder-app/README.md`

#### 2.4 Update Other Files

- `.mcp.json` - Delete or update
- `.claude-plugin/setup.sh` - Remove core/mcp references
- `pyproject.toml` (if any) - Update dependencies

## Installation Flow Comparison

### Current Flow (install.sh)
```
1. Clone repo to ~/.ai-dev-kit
2. Create Python venv
3. pip install databricks-tools-core + databricks-mcp-server
4. Install skills to .claude/skills/
5. Write MCP config to claude_desktop_config.json, etc.
```

### Simplified Flow (after decommissioning)
```
1. Install skills to .claude/skills/ (directly from GitHub)
2. Done!
```

## Migration Guide for Users

Users who want MCP tools after decommissioning:

1. **Use databricks CLI directly** - Skills now guide users to use CLI commands
2. **Use databricks SDK** - Skills include Python SDK examples
3. **Fork the MCP server** - If they really need it, they can fork the repo at the commit before removal

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| builder-app breaks | Phase 1 must complete before Phase 2 |
| Users depend on MCP | Document migration path; skills cover same functionality |
| Lost test coverage | Move relevant tests to databricks-skills/.tests/ |

## File Deletion Summary

**Folders to delete:**
- `databricks-tools-core/` (~20 Python files, ~15K lines)
- `databricks-mcp-server/` (~15 Python files, ~10K lines)

**Files to heavily modify:**
- `install.sh` (reduce from 1790 lines to ~500)
- `README.md` (remove 4+ sections)
- `CONTRIBUTING.md` (remove MCP setup)
- `SECURITY.md` (update installation flow)

**Files to delete:**
- `.mcp.json` (MCP config example)

## Pre-requisite: Fix Skills Integration Tests

Before proceeding with decommissioning, fix the broken integration tests in `databricks-skills/.tests/`:

### Current Test Status

| Test File | Unit Tests | Integration Tests | Status |
|-----------|------------|-------------------|--------|
| `test_agent_bricks_manager.py` | 5 pass | 3 skip (no workspace) | OK |
| `test_pdf_generator.py` | 13 pass | 3 fail | **NEEDS FIX** |

### Failing Tests (test_pdf_generator.py)

```
FAILED test_pdf_generator.py::TestPDFGenerationIntegration::test_generate_and_upload_pdf
FAILED test_pdf_generator.py::TestPDFGenerationIntegration::test_generate_and_upload_pdf_with_folder
FAILED test_pdf_generator.py::TestPDFGenerationIntegration::test_generate_complex_pdf
```

**Root cause:** Test volume `ai_dev_kit.test_pdf_generation.raw_data` doesn't exist.

### Fix Required

Update `test_pdf_generator.py` to skip gracefully when test volume is unavailable:

```python
@pytest.fixture(autouse=True)
def skip_if_volume_missing(self, test_config):
    """Skip tests if the required volume doesn't exist."""
    error = _validate_volume_exists(
        test_config["catalog"],
        test_config["schema"],
        test_config["volume"]
    )
    if error:
        pytest.skip(f"Test volume not available: {error}")
```

### Additional Integration Tests Needed

For complete coverage, add integration tests for remaining skills with Python files:

| Skill | Python File | Test Status |
|-------|-------------|-------------|
| `databricks-agent-bricks` | `mas_manager.py` | Has tests |
| `databricks-unstructured-pdf-generation` | `pdf_generator.py` | Has tests (needs fix) |
| Other skills with .py files | Various | Need tests |

## Recommended Execution Order

### Phase 0: Fix Skills Tests
1. [ ] **Fix broken integration tests** (test_pdf_generator.py skip when volume missing)
2. [ ] Add integration tests for remaining skills with Python files

### Phase 1: Refactor builder-app (Much Simpler Now!)

**Reference implementation:** `../industry-demo-prompts/app/src/demo_prompt_generator/backend/services/agent.py`

3. [ ] Update `pyproject.toml`:
   - Bump `claude-agent-sdk>=0.1.50` (from 0.1.19)
   - Remove `databricks_tools_core*` and `databricks_mcp_server*` from includes
4. [ ] Delete `server/services/databricks_tools.py` entirely
5. [ ] Simplify `server/services/agent.py`:
   - Remove MCP imports and loading
   - Use standard tools: `["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"]`
   - Add `setting_sources=["project"]` for skill discovery
   - Adopt client pooling pattern from reference implementation
6. [ ] Replace `databricks_tools_core.auth` → `databricks.sdk.WorkspaceClient()`
7. [ ] Inline `PRODUCT_NAME`, `PRODUCT_VERSION` constants
8. [ ] Update `deploy.sh` - remove package copying
9. [ ] Test builder-app locally and deployed

### Phase 2: Simplify Main Project
10. [ ] Simplify `install.sh` to skills-only (remove MCP setup)
11. [ ] Update `install.ps1` (Windows) similarly
12. [ ] Update `README.md`
13. [ ] Update `CONTRIBUTING.md`
14. [ ] Update `SECURITY.md`

### Phase 3: Delete and Verify
15. [ ] Delete `databricks-tools-core/`
16. [ ] Delete `databricks-mcp-server/`
17. [ ] Delete `.mcp.json`
18. [ ] Delete `.claude-plugin/` (or update if needed)
19. [ ] Test full installation flow (skills-only)
20. [ ] Test builder-app deployment

## Questions to Resolve

1. **Should we archive MCP in a separate branch?** - For users who want to fork it
2. **What about install.ps1 (Windows)?** - Same changes needed
3. **Keep .claude-plugin/ ?** - This also references MCP
