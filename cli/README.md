# Databricks AI Dev Kit CLI

A cross-platform CLI for installing and managing the Databricks AI Dev Kit. Supports Claude Code, Cursor, GitHub Copilot, and OpenAI Codex.

## Installation

Download the latest binary for your platform from [GitHub Releases](https://github.com/databricks-solutions/ai-dev-kit/releases) or use the bootstrap script:

```bash
# Using uv (recommended)
curl -LsSf https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.py | uv run -

# Or download directly
# macOS (Intel + Apple Silicon)
curl -LO https://github.com/databricks-solutions/ai-dev-kit/releases/latest/download/macos/aidevkit

# Linux (amd64)
curl -LO https://github.com/databricks-solutions/ai-dev-kit/releases/latest/download/linux/amd64/aidevkit

# Make executable
chmod +x aidevkit
```

## Commands

| Command | Description |
|---------|-------------|
| `aidevkit install` | Install the AI Dev Kit (MCP server + skills) |
| `aidevkit uninstall` | Remove installed components |
| `aidevkit update` | Update CLI to the latest version |
| `aidevkit status` | Show installation status |
| `aidevkit doctor` | Diagnose installation issues |
| `aidevkit version` | Print version information |

### install

```bash
aidevkit install [flags]

Flags:
  -p, --profile string   Databricks profile (default "DEFAULT")
  -g, --global           Install globally for all projects
      --skills-only      Skip MCP server setup
      --mcp-only         Skip skills installation
      --mcp-path string  Custom MCP installation path
      --tools string     Comma-separated: claude,cursor,copilot,codex
  -f, --force            Force reinstall
      --silent           Non-interactive mode
```

**Examples:**
```bash
aidevkit install                          # Interactive installation
aidevkit install --silent                 # Non-interactive with defaults
aidevkit install --tools cursor,copilot   # Specific tools only
aidevkit install --global --profile PROD  # Global install with custom profile
```

### uninstall

```bash
aidevkit uninstall [flags]

Flags:
  -g, --global   Also remove global installation (MCP server, venv)
  -f, --force    Skip confirmation prompt
```

### update

```bash
aidevkit update [flags]

Flags:
  -c, --check   Only check for updates, don't install
  -f, --force   Force update even if on latest version
```

---

## Development

All development uses containerized builds via Podman (or Docker). No local Go installation required.

### Prerequisites

- [Podman](https://podman.io/getting-started/installation) or Docker

### Quick Start

```bash
cd cli

# Run the installer interactively
make dev

# Run with specific arguments
make run ARGS="install --help"

# Open a shell in the dev container
make shell
```

### Build Commands

| Command | Description |
|---------|-------------|
| `make build` | Build for current platform → `dist/aidevkit` |
| `make build-all` | Build all platforms → `build/{platform}/{arch}/aidevkit` |
| `make build-darwin` | Build macOS universal binary |

### Test Commands

| Command | Description |
|---------|-------------|
| `make test` | Run all tests with coverage |
| `make test-short` | Run tests without coverage (faster) |
| `make test-coverage` | Generate HTML coverage report |

### Other Commands

| Command | Description |
|---------|-------------|
| `make fmt` | Format Go code |
| `make lint` | Run linter |
| `make clean` | Remove build artifacts |
| `make help` | Show all available commands |

### Using Docker Instead of Podman

```bash
make build CONTAINER_RUNTIME=docker
```

### Project Structure

```
cli/
├── main.go             # Entry point
├── cmd/                # CLI commands (Cobra)
├── ui/                 # TUI components (Bubbletea + Lipgloss)
├── detect/             # Tool and profile detection
├── installer/          # Installation logic
├── Dockerfile          # Multi-stage build
└── Makefile            # Build automation
```

---

## Third-Party Packages

| Package | License | Description |
|---------|---------|-------------|
| [spf13/cobra](https://github.com/spf13/cobra) | Apache-2.0 | CLI framework |
| [charmbracelet/bubbletea](https://github.com/charmbracelet/bubbletea) | MIT | TUI framework |
| [charmbracelet/bubbles](https://github.com/charmbracelet/bubbles) | MIT | TUI components |
| [charmbracelet/lipgloss](https://github.com/charmbracelet/lipgloss) | MIT | Terminal styling |
| [BurntSushi/toml](https://github.com/BurntSushi/toml) | MIT | TOML parser |

All dependencies are compatible with the project's [DB License](../LICENSE.md).
