# Databricks AI Dev Kit CLI

A cross-platform CLI for installing and managing the Databricks AI Dev Kit. Supports Claude Code, Cursor, GitHub Copilot, OpenAI Codex, and Google Gemini.

## Installation

Pre-built binaries are available in the `cli/build/` folder, or use the bootstrap script:

```bash
# Using uv (recommended)
curl -LsSf https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.py | uv run -
```

### Download Binary

Clone the repo and use the pre-built binaries:

| Platform | Binary |
|----------|--------|
| macOS (Intel + Apple Silicon) | `cli/build/macos/aidevkit` |
| Linux x64 | `cli/build/linux/amd64/aidevkit` |
| Linux ARM64 | `cli/build/linux/arm64/aidevkit` |
| Windows x64 | `cli/build/windows/amd64/aidevkit.exe` |
| Windows ARM64 | `cli/build/windows/arm64/aidevkit.exe` |

```bash
# Clone the repo
git clone https://github.com/databricks-solutions/ai-dev-kit.git
cd ai-dev-kit

# Make executable and run (macOS example)
chmod +x cli/build/macos/aidevkit
./cli/build/macos/aidevkit install
```

## Commands

| Command | Description |
|---------|-------------|
| `aidevkit install` | Install the AI Dev Kit (MCP tools + skills) |
| `aidevkit uninstall` | Remove installed components |
| `aidevkit update` | Update CLI to the latest version |
| `aidevkit launch` | Launch standalone projects (starter kit, builder app) |
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
      --tools string     Comma-separated: claude,cursor,copilot,codex,gemini
  -f, --force            Force reinstall
      --silent           Non-interactive mode
```

**Examples:**
```bash
aidevkit install                          # Interactive installation
aidevkit install --silent                 # Non-interactive with defaults
aidevkit install --tools cursor,gemini    # Specific tools only
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

### launch

Launch standalone AI Dev Kit projects. These are separate from the main install flow.

```bash
aidevkit launch starter [flags]   # Launch AI Dev Project (Starter Kit)
aidevkit launch builder [flags]   # Launch Visual Builder App
```

#### launch starter

Set up the AI Dev Project template - a sandbox for experimenting with Databricks skills and MCP tools.

```bash
aidevkit launch starter [flags]

Flags:
      --copy-to string   Copy project to a new directory before setup
  -p, --profile string   Databricks profile to use
```

**Examples:**
```bash
aidevkit launch starter                                    # Run in-place
aidevkit launch starter --copy-to ~/projects/my-project    # Copy to new location
aidevkit launch starter --profile PROD                     # Use specific profile
```

#### launch builder

Launch the Visual Builder App - a web application with Claude Code agent interface and Databricks tools integration.

```bash
aidevkit launch builder [flags]

Flags:
      --copy-to string    Copy project to a new directory
      --deploy string     Deploy to Databricks Apps with this app name
      --skip-build        Skip frontend build when deploying
```

**Examples:**
```bash
aidevkit launch builder                              # Start dev servers (localhost:3000 + :8000)
aidevkit launch builder --copy-to ~/my-builder       # Copy for customization
aidevkit launch builder --deploy my-app              # Deploy to Databricks Apps
aidevkit launch builder --deploy my-app --skip-build # Deploy without rebuilding
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
