# Plan: Add Unity Catalog ABAC Policy Governance Skill

## Context

The `abac_ai_dev_kit` (forked from `databricks-solutions/ai-dev-kit`) provides Claude Code skills for Databricks. The existing `databricks-unity-catalog` skill covers system tables and volumes but has **no ABAC policy governance content**.

The UCABAC companion repo (`/Users/sreeramreddy.thoom/Documents/ClaudeCodeRepo/UCABAC`) implements a full ABAC governance agent with:
- Python SDK code for ABAC policy CRUD (`w.policies.list_policies/create_policy/update_policy/delete_policy`)
- SQL generation for `CREATE POLICY`, `DROP POLICY`, `SET TAG`, masking UDFs
- MCP tools for policy management (12 tools)
- Human-in-the-loop governance workflow (Analyze > Recommend > Preview > Approve > Execute > Verify)
- Policy conflict detection, drift scanning, compliance reporting
- Multi-agent architecture (Supervisor + 4 specialist agents)

**Goal**: Extract the ABAC governance knowledge from UCABAC into a new skill (`uc-abac-governance`) in the ai-dev-kit, add Python SDK examples, and produce a `DEV_CHANGELOG.md`.

---

## Architecture Overview (UCABAC)

```
UCABAC/
├── ucabac/                        # Main package (v0.2.0)
│   ├── core/policy_manager.py     # GovernancePolicyManager facade
│   ├── sql_gen/                   # Pure SQL generation (no state)
│   │   ├── _base.py              # Enums: PIIType, MaskingStrategy, PolicyScope
│   │   ├── tag_skills.py         # SET/UNSET TAG SQL
│   │   ├── udf_skills.py         # CREATE FUNCTION (masking UDFs)
│   │   ├── policy_skills.py      # CREATE/DROP POLICY SQL
│   │   ├── discovery_skills.py   # SHOW/DESCRIBE SQL
│   │   └── compliance_skills.py  # Compliance query SQL
│   ├── mcp/
│   │   ├── policy_api_tools.py   # 12 MCP tools for ABAC CRUD via SDK
│   │   ├── server.py             # MCP server (40+ tools)
│   │   └── sql_executor.py       # SQL Warehouse execution
│   ├── services/
│   │   ├── unity_catalog_client.py  # UC client with REST API wrappers
│   │   ├── abac_policy_sync.py     # Sync policies to Postgres cache
│   │   ├── drift_detector.py       # Policy drift detection
│   │   └── policy_conflict_checker.py # Conflict validation
│   ├── agents/                    # Multi-agent system (Claude-powered)
│   │   ├── supervisor_agent.py    # Task decomposition + delegation
│   │   ├── governance_agent.py    # Governance policy specialist
│   │   ├── pii_agent.py          # PII detection specialist
│   │   ├── compliance_agent.py   # Compliance reporting specialist
│   │   └── query_agent.py        # Query assistant specialist
│   └── database/                  # Lakebase Postgres persistence
├── app/api/                       # FastAPI REST + SSE backend
├── frontend/                      # React + TypeScript SPA
├── skills/governance-policy/      # Existing skill docs (reference)
└── tests/                         # 283 unit tests
```

---

## Changes to Make

### 1. New Skill: `databricks-skills/uc-abac-governance/`

Create a new skill directory following the TEMPLATE pattern:

| File | Content Source |
|------|--------------|
| `SKILL.md` | ABAC overview, governed tags, tag assignments, masking UDFs, CREATE POLICY syntax, human-in-the-loop workflow, policy quotas, invalid SQL warnings, common errors. Derived from `ucabac/skills/governance-policy/SKILL.md` |
| `sql-generation.md` | Pure SQL patterns: SET/UNSET TAG, CREATE FUNCTION, CREATE/DROP POLICY, discovery queries. Derived from `ucabac/sql_gen/` modules |
| `python-sdk-patterns.md` | Databricks Python SDK examples: `w.policies.list_policies()`, `create_policy()`, `update_policy()`, `delete_policy()`, `get_policy()`. Derived from `ucabac/mcp/policy_api_tools.py` and `ucabac/services/` |
| `mcp-tools-reference.md` | MCP tool reference for 12 policy API tools: list, get, create, update, delete, preview. Derived from `ucabac/mcp/policy_api_tools.py` |

### 2. Install into `.claude/skills/uc-abac-governance/`

Copy the 4 skill files to `.claude/skills/uc-abac-governance/` (matching how other skills are installed).

### 3. Update `databricks-skills/install_skills.sh`

- Add `uc-abac-governance` to `DATABRICKS_SKILLS` list (line 45)
- Add `"uc-abac-governance") echo "ABAC policy governance - tags, UDFs, column masks, row filters"` in `get_skill_description()`
- Add `"uc-abac-governance") echo "sql-generation.md python-sdk-patterns.md mcp-tools-reference.md"` in `get_skill_extra_files()`

### 4. New SDK Example: `databricks-skills/databricks-python-sdk/examples/6-abac-policies.py`

Following the pattern of existing examples (1-authentication.py through 5-serving-and-vector-search.py), add a new example demonstrating ABAC policy operations:
- List policies on catalog/schema/table
- Create column mask policy with tag matching
- Create row filter policy
- Update policy principals
- Delete policy
- Preview policy changes before execution

### 5. Update `databricks-python-sdk` Skill

- Add ABAC policies section to `databricks-skills/databricks-python-sdk/SKILL.md`
- Update `get_skill_extra_files()` to include `examples/6-abac-policies.py`

### 6. Create `DEV_CHANGELOG.md` in Project Root

---

## Key Patterns to Preserve

### SQL That Does NOT Exist in Databricks
- `SHOW POLICIES` / `DESCRIBE POLICY` -- use REST API instead
- `ALTER POLICY` -- drop and recreate
- `information_schema.column_masks` / `.row_filters` -- for old-style masking, NOT ABAC
- `ALTER USER SET ATTRIBUTES` / `SHOW USER ATTRIBUTES` -- use SCIM API

### Automatic `gov_admin` Exception
Every ABAC policy MUST include `EXCEPT \`gov_admin\`` to protect administrator access. Enforced at 3 levels: system prompt, tool-level injection, SQL interception.

### Policy Quotas
- Max 10 policies per catalog
- Max 10 policies per schema
- Max 5 policies per table

### Human-in-the-Loop Workflow
```
ANALYZE → RECOMMEND → PREVIEW → APPROVE → EXECUTE → VERIFY
```

---

## Files to Create/Modify

| Action | File |
|--------|------|
| CREATE | `databricks-skills/uc-abac-governance/SKILL.md` |
| CREATE | `databricks-skills/uc-abac-governance/sql-generation.md` |
| CREATE | `databricks-skills/uc-abac-governance/python-sdk-patterns.md` |
| CREATE | `databricks-skills/uc-abac-governance/mcp-tools-reference.md` |
| CREATE | `.claude/skills/uc-abac-governance/SKILL.md` |
| CREATE | `.claude/skills/uc-abac-governance/sql-generation.md` |
| CREATE | `.claude/skills/uc-abac-governance/python-sdk-patterns.md` |
| CREATE | `.claude/skills/uc-abac-governance/mcp-tools-reference.md` |
| MODIFY | `databricks-skills/install_skills.sh` |
| CREATE | `databricks-skills/databricks-python-sdk/examples/6-abac-policies.py` |
| MODIFY | `databricks-skills/databricks-python-sdk/SKILL.md` |
| CREATE | `DEV_CHANGELOG.md` |

---

## Verification

1. `./databricks-skills/install_skills.sh --list` -- confirm `uc-abac-governance` appears with description
2. `./databricks-skills/install_skills.sh uc-abac-governance --local` -- confirm all 4 files install to `.claude/skills/`
3. `python -c "import ast; ast.parse(open('databricks-skills/databricks-python-sdk/examples/6-abac-policies.py').read())"` -- syntax check
4. Verify SKILL.md frontmatter matches naming conventions
5. Cross-reference SQL patterns against Databricks ABAC docs
