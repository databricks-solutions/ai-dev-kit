// Databricks AI Dev Kit CLI
//
// A terminal user interface for installing and configuring the Databricks
// AI Dev Kit for Claude Code, Cursor, GitHub Copilot, and OpenAI Codex.
//
// Usage:
//
//	aidevkit install              # Interactive installation
//	aidevkit install --silent     # Non-interactive with defaults
//	aidevkit install --global     # Install globally for all projects
//	aidevkit install --tools cursor,copilot  # Specify tools
//	aidevkit version              # Show version
//
// Build:
//
//	make build                    # Build for current platform
//	make release                  # Cross-compile all platforms
package main

import (
	"github.com/databricks-solutions/ai-dev-kit/cli/cmd"
	"github.com/databricks-solutions/ai-dev-kit/cli/signal"
)

// Version is set at build time via -ldflags
var Version = "dev"

func main() {
	// Setup signal handling for graceful shutdown
	signal.Setup()

	// Set version from build-time variable
	cmd.Version = Version
	cmd.Execute()
}

