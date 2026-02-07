package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/databricks-solutions/ai-dev-kit/cli/installer"
	"github.com/databricks-solutions/ai-dev-kit/cli/signal"
	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
	"github.com/spf13/cobra"
)

var (
	starterCopyTo  string
	starterProfile string
)

var launchStarterCmd = &cobra.Command{
	Use:   "starter",
	Short: "Launch the AI Dev Project (Starter Kit)",
	Long: `Launch the AI Dev Project - a template for creating new projects
configured with Databricks AI Dev Kit for Claude Code or Cursor.

This starter kit includes:
  • Pre-configured MCP server setup
  • Databricks skills installation
  • Ready-to-use CLAUDE.md project context
  • MCP configuration for both Claude Code and Cursor

By default, runs setup in-place within the ai-dev-kit repository.
Use --copy-to to create a standalone project in a new directory.

Examples:
  # Run setup in-place (from within the repo)
  aidevkit launch starter

  # Copy to a new project directory
  aidevkit launch starter --copy-to ~/projects/my-databricks-project

  # Specify a Databricks profile
  aidevkit launch starter --profile my-workspace`,
	Run: runLaunchStarter,
}

func init() {
	launchStarterCmd.Flags().StringVar(&starterCopyTo, "copy-to", "", "Copy project to a new directory before setup")
	launchStarterCmd.Flags().StringVarP(&starterProfile, "profile", "p", "", "Databricks profile to use")
	launchCmd.AddCommand(launchStarterCmd)
}

func runLaunchStarter(cmd *cobra.Command, args []string) {
	ui.ClearScreen()
	ui.PrintLogo()

	fmt.Println()
	fmt.Println(ui.RenderStep("Launch AI Dev Project (Starter Kit)"))
	fmt.Println()

	// Find the repository
	fmt.Println("  Locating ai-dev-kit repository...")
	repo, err := installer.FindRepository()
	if err != nil {
		fmt.Println(ui.RenderError(err.Error()))
		fmt.Println()
		fmt.Println("  " + ui.DimStyle.Render("Set AI_DEV_KIT_PATH environment variable or run from within the repository."))
		os.Exit(1)
	}
	fmt.Println(ui.RenderSuccess(fmt.Sprintf("Found repository at %s", installer.DisplayPath(repo.RootDir))))

	// Check for interrupt
	if signal.IsInterrupted() {
		fmt.Println(ui.RenderWarning("\nOperation cancelled by user"))
		os.Exit(130)
	}

	// Validate starter project exists
	if err := repo.ValidateStarterProject(); err != nil {
		fmt.Println(ui.RenderError(err.Error()))
		os.Exit(1)
	}

	// Determine working directory
	workDir := repo.StarterProject
	if starterCopyTo != "" {
		fmt.Println()
		fmt.Println(ui.RenderStep("Copying project template"))
		fmt.Println()

		// Expand path
		targetDir := starterCopyTo
		if targetDir[0] == '~' {
			homeDir, _ := os.UserHomeDir()
			targetDir = filepath.Join(homeDir, targetDir[1:])
		}
		targetDir, _ = filepath.Abs(targetDir)

		// Check if target exists
		if _, err := os.Stat(targetDir); err == nil {
			fmt.Println(ui.RenderError(fmt.Sprintf("Directory already exists: %s", targetDir)))
			fmt.Println("  " + ui.DimStyle.Render("Choose a different path or remove the existing directory."))
			os.Exit(1)
		}

		// Check for interrupt
		if signal.IsInterrupted() {
			fmt.Println(ui.RenderWarning("\nOperation cancelled by user"))
			os.Exit(130)
		}

		fmt.Printf("  Copying to %s...\n", installer.DisplayPath(targetDir))

		// Create target directory
		if err := os.MkdirAll(targetDir, 0755); err != nil {
			fmt.Println(ui.RenderError(fmt.Sprintf("Failed to create directory: %v", err)))
			os.Exit(1)
		}

		// Copy starter project
		if err := installer.CopyDirectory(repo.StarterProject, targetDir); err != nil {
			fmt.Println(ui.RenderError(fmt.Sprintf("Failed to copy project: %v", err)))
			os.Exit(1)
		}

		// Make setup.sh executable
		setupScript := filepath.Join(targetDir, "setup.sh")
		if err := installer.MakeExecutable(setupScript); err != nil {
			fmt.Println(ui.RenderWarning(fmt.Sprintf("Could not make setup.sh executable: %v", err)))
		}

		fmt.Println(ui.RenderSuccess("Project copied successfully"))
		workDir = targetDir

		// Update the setup.sh to point to the original repo
		fmt.Println()
		fmt.Println("  " + ui.DimStyle.Render("Note: The copied project references the original ai-dev-kit repository."))
		fmt.Println("  " + ui.DimStyle.Render("Ensure AI_DEV_KIT_PATH is set if you move the repository."))
	}

	// Check for interrupt
	if signal.IsInterrupted() {
		fmt.Println(ui.RenderWarning("\nOperation cancelled by user"))
		os.Exit(130)
	}

	fmt.Println()
	fmt.Println(ui.RenderStep("Running setup"))
	fmt.Println()

	// Run setup.sh
	setupScript := filepath.Join(workDir, "setup.sh")
	cmdArgs := []string{setupScript}
	if starterProfile != "" {
		cmdArgs = append(cmdArgs, "--profile", starterProfile)
	}

	execCmd := exec.Command("bash", cmdArgs...)
	execCmd.Dir = workDir
	execCmd.Stdin = os.Stdin
	execCmd.Stdout = os.Stdout
	execCmd.Stderr = os.Stderr

	// Set AI_DEV_KIT_PATH for the script to find sibling directories
	execCmd.Env = append(os.Environ(), fmt.Sprintf("AI_DEV_KIT_PATH=%s", repo.RootDir))

	if err := execCmd.Run(); err != nil {
		if signal.IsInterrupted() {
			fmt.Println()
			fmt.Println(ui.RenderWarning("Setup interrupted by user"))
			os.Exit(130)
		}
		fmt.Println()
		fmt.Println(ui.RenderError(fmt.Sprintf("Setup failed: %v", err)))
		os.Exit(1)
	}

	// Print success message
	fmt.Println()
	fmt.Println(ui.RenderSuccess("Starter kit is ready!"))
	fmt.Println()
	fmt.Println("  " + ui.SubtitleStyle.Render("Next steps:"))
	fmt.Println()
	fmt.Printf("  1. %s\n", ui.DimStyle.Render(fmt.Sprintf("cd %s", installer.DisplayPath(workDir))))
	fmt.Printf("  2. %s\n", ui.DimStyle.Render("Set DATABRICKS_HOST and DATABRICKS_TOKEN (or use a profile)"))
	fmt.Printf("  3. %s\n", ui.DimStyle.Render("Run: claude"))
	fmt.Println()
}

