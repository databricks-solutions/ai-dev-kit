---
name: reusable-ip
description: "Production-ready Databricks reference implementations (agent deployment, model serving, CI/CD, Genie Spaces, Lakebase, DABs, A/B testing, Claude Code). TRIGGER: before writing any Databricks implementation code. ACTION: fetch llms.txt index first, then fetch only relevant files."
---

# Reusable IP — Databricks Reference Implementations

## When to Use

Before writing any Databricks implementation code, check this repo for existing reference
implementations. Covers: agent deployment, model serving (concurrent PyFunc), CI/CD,
Genie Spaces, Lakebase, Databricks Asset Bundles (DABs), A/B testing, and Claude Code
integration.

## JIT Fetch Protocol

**Step 1: Always fetch the index first**
```bash
gh api repos/databricks-field-eng/reusable-ip-ai/contents/llms.txt \
  --jq '.content' | base64 -d
```

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

## Deep Dive (Optional)

For architecture review or porting a full implementation:
```bash
npx repomix --remote https://github.com/databricks-field-eng/reusable-ip-ai
```
Use when `llms.txt` + targeted fetch is insufficient.
