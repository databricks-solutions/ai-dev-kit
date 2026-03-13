---
name: databricks-reusable-ip
description: "Production-ready Databricks reference implementations (agent deployment, model serving, CI/CD, Genie Spaces, Lakebase, DABs, A/B testing, Claude Code). TRIGGER: when implementing a new Databricks pattern or porting a reference implementation. ACTION: fetch llms.txt index first, then fetch only relevant files."
---

# Reusable IP — Databricks Reference Implementations

## When to Use

When implementing a new Databricks pattern or porting a reference implementation, check this repo
for existing solutions. Covers: agent deployment, model serving (concurrent PyFunc), CI/CD,
Genie Spaces, Lakebase, Databricks Asset Bundles (DABs), A/B testing, and Claude Code
integration.

## JIT Fetch Protocol

**Step 1: Always fetch the index first**
```bash
gh api repos/databricks-field-eng/reusable-ip-ai/contents/llms.txt \
  --jq '.content' | base64 -d
```

If this command fails (authentication error, access denied, or file not found), stop and inform
the user that the reusable-ip-ai repo is inaccessible. Do not proceed with this skill.

**Step 2: Identify relevant files** from the descriptions (not filenames alone).
If nothing is relevant, proceed without fetching further.

**Step 3: Fetch only the files you need**
```bash
gh api repos/databricks-field-eng/reusable-ip-ai/contents/PATH/TO/FILE \
  --jq '.content' | base64 -d
```

**Rules:**
- Always fetch `llms.txt` first — do not guess file paths
- Fetch MINIMUM files (1–3). Fetch additional files incrementally only if needed
- Do not dump the full directory tree
