# Deprecated: Bundled Databricks Skills (frozen)

> **These skill copies are deprecated and no longer maintained.**

The skill folders under `databricks-skills/deprecated/` are frozen, historical copies
of the Databricks skills that used to ship in this repository. They are kept only so
that existing tooling (and anyone who copied them directly) does not break. They will
**not** receive updates.

## Use the supported path instead

Skills are now installed and maintained through the Databricks CLI:

```bash
databricks aitools install
```

This requires Databricks CLI **v1.0.0+** and pulls the current, maintained skills from
[github.com/databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills).
The AI Dev Kit installer (`install.sh` / `install.ps1`) already delegates to it, so a normal
install gets you the up-to-date skills with no manual copying.

## Getting the exact historical content

If you specifically need the files exactly as they were bundled, check out the last release
that shipped them:

```bash
git checkout v0.1.13 -- databricks-skills
```

## Migration notes

- Some skills were **renamed** when they moved to `databricks-agent-skills`. The mapping and
  other breaking changes are documented in the root [`README.md`](../../README.md) "breaking change" note.
- APX skills has been removed in favor of other app skills (see the root README).

## Genie Code (workspace upload)
Genie Code already has coverage for most skills available publicly and we will continue to sync improvements
whenever possible. The one flow `databricks aitools install` does not fully cover is uploading skills to a
Databricks workspace for **Genie Code**. Keep that simple — do not clone this tree to copy files:

- **Recommended:** run the notebook uploader
  [`../install_genie_code_skills.py`](../install_genie_code_skills.py) in your workspace. It
  downloads skills from GitHub (pinned to release `v0.1.13`) and uploads them via the SDK — no
  local clone needed.
- **Fallback:** [`../install_skills.sh --install-to-genie`](../install_skills.sh) downloads the
  skills from the last release that shipped them (`v0.1.13`) and uploads them. Use this when the
  notebook path is not available. (Add `--local` to source from this `deprecated/` folder instead
  of downloading, e.g. when working fully offline.)
