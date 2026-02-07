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
	builderCopyTo   string
	builderDeploy   string
	builderSkipBuild bool
)

var launchBuilderCmd = &cobra.Command{
	Use:   "builder",
	Short: "Launch the Visual Builder App",
	Long: `Launch the Visual Builder App - a web application that provides a
Claude Code agent interface with integrated Databricks tools.

Features:
  • React frontend with chat interface
  • FastAPI backend with Claude Code agent
  • Integrated Databricks MCP tools
  • Project and conversation persistence

By default, starts the development servers locally.
Use --deploy to deploy to Databricks Apps platform.

Examples:
  # Start development servers (backend + frontend)
  aidevkit launch builder

  # Copy project to a new directory
  aidevkit launch builder --copy-to ~/projects/my-builder

  # Deploy to Databricks Apps
  aidevkit launch builder --deploy my-builder-app

  # Deploy without rebuilding frontend
  aidevkit launch builder --deploy my-builder-app --skip-build`,
	Run: runLaunchBuilder,
}

func init() {
	launchBuilderCmd.Flags().StringVar(&builderCopyTo, "copy-to", "", "Copy project to a new directory")
	launchBuilderCmd.Flags().StringVar(&builderDeploy, "deploy", "", "Deploy to Databricks Apps with this app name")
	launchBuilderCmd.Flags().BoolVar(&builderSkipBuild, "skip-build", false, "Skip frontend build when deploying")
	launchCmd.AddCommand(launchBuilderCmd)
}

func runLaunchBuilder(cmd *cobra.Command, args []string) {
	ui.ClearScreen()
	ui.PrintLogo()

	fmt.Println()
	fmt.Println(ui.RenderStep("Launch Visual Builder App"))
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

	// Validate builder app exists
	if err := repo.ValidateBuilderApp(); err != nil {
		fmt.Println(ui.RenderError(err.Error()))
		os.Exit(1)
	}

	// Check dependencies based on mode
	fmt.Println()
	fmt.Println(ui.RenderStep("Checking prerequisites"))
	fmt.Println()

	if builderDeploy != "" {
		deps, err := installer.CheckDeployDependencies()
		if err != nil {
			fmt.Println(ui.RenderError(err.Error()))
			os.Exit(1)
		}
		installer.PrintDependencyStatus(deps, nil, false)
	} else {
		deps, pkgMgr, err := installer.CheckBuilderDependencies()
		if err != nil {
			fmt.Println(ui.RenderError(err.Error()))
			os.Exit(1)
		}
		installer.PrintDependencyStatus(deps, pkgMgr, false)
	}

	// Check for interrupt
	if signal.IsInterrupted() {
		fmt.Println(ui.RenderWarning("\nOperation cancelled by user"))
		os.Exit(130)
	}

	// Determine working directory
	workDir := repo.BuilderApp
	if builderCopyTo != "" {
		workDir, err = copyBuilderProject(repo, builderCopyTo)
		if err != nil {
			fmt.Println(ui.RenderError(err.Error()))
			os.Exit(1)
		}
	}

	// Check for interrupt
	if signal.IsInterrupted() {
		fmt.Println(ui.RenderWarning("\nOperation cancelled by user"))
		os.Exit(130)
	}

	// Run deploy or start dev
	if builderDeploy != "" {
		runBuilderDeploy(workDir, builderDeploy, builderSkipBuild)
	} else {
		runBuilderDev(workDir, repo.RootDir)
	}
}

func copyBuilderProject(repo *installer.RepoLayout, copyTo string) (string, error) {
	fmt.Println()
	fmt.Println(ui.RenderStep("Copying project"))
	fmt.Println()

	// Expand path
	targetDir := copyTo
	if targetDir[0] == '~' {
		homeDir, _ := os.UserHomeDir()
		targetDir = filepath.Join(homeDir, targetDir[1:])
	}
	targetDir, _ = filepath.Abs(targetDir)

	// Check if target exists
	if _, err := os.Stat(targetDir); err == nil {
		return "", fmt.Errorf("directory already exists: %s", targetDir)
	}

	fmt.Printf("  Copying builder app to %s...\n", installer.DisplayPath(targetDir))

	// Create target directory
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create directory: %v", err)
	}

	// Copy builder app
	if err := installer.CopyDirectory(repo.BuilderApp, targetDir); err != nil {
		return "", fmt.Errorf("failed to copy builder app: %v", err)
	}

	// Create packages directory and copy sibling packages
	packagesDir := filepath.Join(targetDir, "packages")
	if err := os.MkdirAll(packagesDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create packages directory: %v", err)
	}

	// Copy databricks-tools-core
	fmt.Println("  Copying databricks-tools-core...")
	toolsCoreDir := filepath.Join(packagesDir, "databricks_tools_core")
	if err := os.MkdirAll(toolsCoreDir, 0755); err != nil {
		return "", err
	}
	srcToolsCore := filepath.Join(repo.ToolsCore, "databricks_tools_core")
	if err := installer.CopyDirectory(srcToolsCore, toolsCoreDir); err != nil {
		return "", fmt.Errorf("failed to copy databricks-tools-core: %v", err)
	}

	// Copy databricks-mcp-server
	fmt.Println("  Copying databricks-mcp-server...")
	mcpServerDir := filepath.Join(packagesDir, "databricks_mcp_server")
	if err := os.MkdirAll(mcpServerDir, 0755); err != nil {
		return "", err
	}
	srcMCPServer := filepath.Join(repo.MCPServer, "databricks_mcp_server")
	if err := installer.CopyDirectory(srcMCPServer, mcpServerDir); err != nil {
		return "", fmt.Errorf("failed to copy databricks-mcp-server: %v", err)
	}

	// Copy skills
	fmt.Println("  Copying skills...")
	skillsDir := filepath.Join(targetDir, "skills")
	if err := copySkills(repo.Skills, skillsDir); err != nil {
		return "", fmt.Errorf("failed to copy skills: %v", err)
	}

	// Make scripts executable
	scripts := []string{"scripts/start_dev.sh", "scripts/deploy.sh"}
	for _, script := range scripts {
		scriptPath := filepath.Join(targetDir, script)
		if err := installer.MakeExecutable(scriptPath); err != nil {
			// Non-fatal, just warn
			fmt.Println(ui.RenderWarning(fmt.Sprintf("Could not make %s executable", script)))
		}
	}

	fmt.Println(ui.RenderSuccess("Project copied successfully"))

	fmt.Println()
	fmt.Println("  " + ui.DimStyle.Render("The project now includes all required packages."))
	fmt.Println("  " + ui.DimStyle.Render("Update packages/ if you need the latest versions."))

	return targetDir, nil
}

func copySkills(srcDir, dstDir string) error {
	if err := os.MkdirAll(dstDir, 0755); err != nil {
		return err
	}

	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return err
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		skillName := entry.Name()
		// Skip template and non-skill directories
		if skillName == "TEMPLATE" {
			continue
		}

		// Check if it has a SKILL.md
		skillMd := filepath.Join(srcDir, skillName, "SKILL.md")
		if _, err := os.Stat(skillMd); os.IsNotExist(err) {
			continue
		}

		// Copy skill directory
		srcSkill := filepath.Join(srcDir, skillName)
		dstSkill := filepath.Join(dstDir, skillName)
		if err := installer.CopyDirectory(srcSkill, dstSkill); err != nil {
			return err
		}
	}

	return nil
}

func runBuilderDeploy(workDir, appName string, skipBuild bool) {
	fmt.Println()
	fmt.Println(ui.RenderStep("Deploying to Databricks Apps"))
	fmt.Println()

	fmt.Printf("  App name: %s\n", ui.InfoStyle.Render(appName))
	fmt.Printf("  Source:   %s\n", installer.DisplayPath(workDir))
	fmt.Println()

	// Build command arguments
	deployScript := filepath.Join(workDir, "scripts", "deploy.sh")
	cmdArgs := []string{deployScript, appName}
	if skipBuild {
		cmdArgs = append(cmdArgs, "--skip-build")
	}

	execCmd := exec.Command("bash", cmdArgs...)
	execCmd.Dir = workDir
	execCmd.Stdin = os.Stdin
	execCmd.Stdout = os.Stdout
	execCmd.Stderr = os.Stderr

	if err := execCmd.Run(); err != nil {
		if signal.IsInterrupted() {
			fmt.Println()
			fmt.Println(ui.RenderWarning("Deployment interrupted by user"))
			os.Exit(130)
		}
		fmt.Println()
		fmt.Println(ui.RenderError(fmt.Sprintf("Deployment failed: %v", err)))
		os.Exit(1)
	}
}

func runBuilderDev(workDir, repoRoot string) {
	fmt.Println()
	fmt.Println(ui.RenderStep("Starting development servers"))
	fmt.Println()

	fmt.Println("  " + ui.DimStyle.Render("Backend:  http://localhost:8000"))
	fmt.Println("  " + ui.DimStyle.Render("Frontend: http://localhost:3000"))
	fmt.Println()
	fmt.Println("  " + ui.DimStyle.Render("Press Ctrl+C to stop both servers"))
	fmt.Println()

	// Run start_dev.sh
	startScript := filepath.Join(workDir, "scripts", "start_dev.sh")

	execCmd := exec.Command("bash", startScript)
	execCmd.Dir = workDir
	execCmd.Stdin = os.Stdin
	execCmd.Stdout = os.Stdout
	execCmd.Stderr = os.Stderr

	// Set environment for finding sibling packages
	execCmd.Env = append(os.Environ(), fmt.Sprintf("AI_DEV_KIT_PATH=%s", repoRoot))

	if err := execCmd.Run(); err != nil {
		if signal.IsInterrupted() {
			fmt.Println()
			fmt.Println(ui.RenderWarning("Servers stopped by user"))
			os.Exit(0) // Clean exit for Ctrl+C
		}
		fmt.Println()
		fmt.Println(ui.RenderError(fmt.Sprintf("Development server error: %v", err)))
		os.Exit(1)
	}
}

