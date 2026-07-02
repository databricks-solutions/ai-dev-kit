# DEPRECATED — AI Dev Kit Claude Code plugin

The AI Dev Kit Claude Code plugin is **deprecated and no longer published**. It
has been removed from the marketplace (`marketplace.json` lists no plugins) and
`plugin.json` is marked `"deprecated": true`. These files are kept only for
historical reference.

## Why

- Skills are now delivered through the Databricks CLI: `databricks aitools install`
  (Databricks CLI v1.0.0+), backed by
  [github.com/databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills).
  The main installer (`install.sh` / `install.ps1`) already delegates to it.
- MCP and skills installs are now standalone rather than being bundled and
  auto-loaded through a Claude Code plugin.

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

- The frozen historical copies of the bundled skills live at git tag `v0.1.12`.
- Files under `.claude-plugin/` remain in the repo for reference only; they are
  no longer installed or published.
