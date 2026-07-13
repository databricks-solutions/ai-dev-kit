# DEPRECATED — the `databricks-ai-dev-kit` Claude Code plugin

The **`databricks-ai-dev-kit`** Claude Code plugin published by *this repo* is
**deprecated and no longer published**. It has been removed from the marketplace
(`marketplace.json` lists no plugins) and `plugin.json` is marked
`"deprecated": true`. These files are kept only for historical reference.

> **This is not a move away from plugins.** Skills are still delivered as a plugin
> for the agents that support one — just the *official* `databricks` plugin managed
> by the Databricks CLI, not this repo's marketplace plugin. See "How skills install
> now" below.

## Why

- Skills are now delivered through the Databricks CLI: `databricks aitools install`
  (Databricks CLI v1.0.0+), backed by
  [github.com/databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills).
  The main installer (`install.sh` / `install.ps1`) already delegates to it.
- The CLI owns the install lifecycle (`install` / `update` / `uninstall` / `list`),
  so skills no longer need a repo-published marketplace plugin to be bundled and
  auto-loaded.

## How skills install now

`databricks aitools install` decides delivery per agent:

- **Claude Code, Codex, GitHub Copilot** — installs the official **`databricks`
  plugin** through each agent's own plugin CLI (a *different* plugin from the retired
  `databricks-ai-dev-kit` one).
- **Cursor, OpenCode, Antigravity** — writes **raw skill files** (no headless plugin
  install available).
- `--skills-only` forces raw skill files for every agent.

So on Claude Code you still get a plugin — the CLI-managed `databricks` plugin —
rather than the deprecated `databricks-ai-dev-kit` plugin.

## Migration for existing plugin users

Use either of the following to get the up-to-date skills:

- Run the installer:

  ```bash
  bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh)
  ```

- Or install directly via the Databricks CLI (v1.0.0+):

  ```bash
  databricks aitools install
  ```

## Notes

- The frozen historical copies of the bundled skills live at git tag `v0.1.13`.
- Files under `.claude-plugin/` remain in the repo for reference only; they are
  no longer installed or published.
