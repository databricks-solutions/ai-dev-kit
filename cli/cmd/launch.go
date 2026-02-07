package cmd

import (
	"github.com/spf13/cobra"
)

var launchCmd = &cobra.Command{
	Use:   "launch",
	Short: "Launch standalone AI Dev Kit projects",
	Long: `Launch standalone AI Dev Kit projects.

Available projects:

  starter   AI Dev Project - A template for creating new projects
            configured with Databricks AI Dev Kit for Claude Code or Cursor.
            Use this to experiment with skills and MCP tools.

  builder   Visual Builder App - A web application that provides a
            Claude Code agent interface with integrated Databricks tools.
            Includes React frontend and FastAPI backend.

Examples:
  # Launch the starter kit in-place (within the repo)
  aidevkit launch starter

  # Copy starter kit to a new project directory
  aidevkit launch starter --copy-to ~/projects/my-project

  # Start the builder app development servers
  aidevkit launch builder

  # Deploy builder app to Databricks Apps
  aidevkit launch builder --deploy my-app-name`,
}

func init() {
	// Subcommands are added in their respective files
}

