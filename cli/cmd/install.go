package cmd

import (
	"fmt"
	"os"
	"strings"

	"github.com/databricks-solutions/ai-dev-kit/cli/detect"
	"github.com/databricks-solutions/ai-dev-kit/cli/installer"
	"github.com/databricks-solutions/ai-dev-kit/cli/signal"
	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
	"github.com/spf13/cobra"
)

var (
	flagProfile    string
	flagGlobal     bool
	flagSkillsOnly bool
	flagMCPOnly    bool
	flagMCPPath    string
	flagTools      string
	flagForce      bool
	flagSilent     bool
)

var installCmd = &cobra.Command{
	Use:   "install",
	Short: "Install the Databricks AI Dev Kit",
	Long: `Install the Databricks AI Dev Kit including:
  • MCP tools for AI assistant integration with Databricks
  • Databricks skills for Claude, Cursor, Copilot, Codex, and Gemini
  • Tool-specific configuration files

The installer auto-detects installed tools and guides you through
profile selection and configuration.`,
	Run: runInstall,
}

func init() {
	installCmd.Flags().StringVarP(&flagProfile, "profile", "p", "DEFAULT", "Databricks profile name")
	installCmd.Flags().BoolVarP(&flagGlobal, "global", "g", false, "Install globally for all projects")
	installCmd.Flags().BoolVar(&flagSkillsOnly, "skills-only", false, "Skip MCP tools setup")
	installCmd.Flags().BoolVar(&flagMCPOnly, "mcp-only", false, "Skip skills installation")
	installCmd.Flags().StringVar(&flagMCPPath, "mcp-path", "", "Custom MCP installation path")
	installCmd.Flags().StringVar(&flagTools, "tools", "", "Comma-separated tools: claude,cursor,copilot,codex,gemini")
	installCmd.Flags().BoolVarP(&flagForce, "force", "f", false, "Force reinstall")
	installCmd.Flags().BoolVar(&flagSilent, "silent", false, "Silent mode (no interactive prompts)")
}

func runInstall(cmd *cobra.Command, args []string) {
	// Initialize configuration
	cfg := installer.NewConfig()

	// Apply flags
	cfg.Profile = flagProfile
	cfg.Force = flagForce
	cfg.Silent = flagSilent
	cfg.InstallMCP = !flagSkillsOnly
	cfg.InstallSkills = !flagMCPOnly

	if flagGlobal {
		cfg.SetScope("global")
	} else {
		cfg.SetScope("project")
		cfg.UpdateBaseDir()
	}

	if flagMCPPath != "" {
		cfg.SetInstallDir(flagMCPPath)
	}

	// Clear screen and show logo
	if !cfg.Silent {
		ui.ClearScreen()
		ui.PrintLogo()
	}

	// Step 0: Select installation mode (if not specified via flags)
	if !cfg.Silent && !flagSkillsOnly && !flagMCPOnly {
		installMCP, installSkills, err := selectInstallMode()
		if err != nil {
			handleInstallError(err, cfg.Silent)
			return
		}
		cfg.InstallMCP = installMCP
		cfg.InstallSkills = installSkills
	}

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 1: Check dependencies
	printStep("Checking prerequisites", cfg.Silent)
	deps, pkgMgr, err := installer.CheckDependencies(cfg.InstallMCP)
	if err != nil {
		handleInstallError(err, cfg.Silent)
		return
	}
	installer.PrintDependencyStatus(deps, pkgMgr, cfg.Silent)

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 2: Tool selection
	printStep("Selecting tools", cfg.Silent)
	tools, err := selectTools(cfg)
	if err != nil {
		handleInstallError(err, cfg.Silent)
		return
	}
	cfg.Tools = tools
	if !cfg.Silent {
		fmt.Println(ui.RenderSuccess("Selected: " + strings.Join(tools, ", ")))
	}

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 3: Profile selection
	printStep("Databricks profile", cfg.Silent)
	profile, err := selectProfile(cfg)
	if err != nil {
		handleInstallError(err, cfg.Silent)
		return
	}
	cfg.Profile = profile
	if !cfg.Silent {
		fmt.Println(ui.RenderSuccess("Profile: " + profile))
	}

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 4: MCP path selection (if installing MCP)
	if cfg.InstallMCP && flagMCPPath == "" {
		printStep("MCP tools location", cfg.Silent)
		mcpPath, err := selectMCPPath(cfg)
		if err != nil {
			handleInstallError(err, cfg.Silent)
			return
		}
		cfg.SetInstallDir(mcpPath)
		if !cfg.Silent {
			fmt.Println(ui.RenderSuccess("MCP path: " + installer.DisplayPath(cfg.InstallDir)))
		}
	}

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 5: Confirmation
	if !cfg.Silent {
		confirmed, err := showSummary(cfg)
		if err != nil {
			handleInstallError(err, cfg.Silent)
			return
		}
		if !confirmed {
			fmt.Println("\n  Installation cancelled.")
			os.Exit(0)
		}
	}

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 6: Version check
	needsUpdate, localVer, _, _ := installer.CheckVersion(cfg)
	if !needsUpdate {
		fmt.Println(ui.RenderSuccess(fmt.Sprintf("Already up to date (v%s)", localVer)))
		fmt.Println("  " + ui.DimStyle.Render("Use --force to reinstall"))
		os.Exit(0)
	}

	// Step 7: Setup MCP tools
	if cfg.InstallMCP {
		printStep("Setting up MCP tools", cfg.Silent)

		// Check for interrupt before long operation
		if checkInterrupt(cfg.Silent) {
			return
		}

		// Clone repository
		fmt.Println("  Cloning repository...")
		if err := installer.SetupMCPServer(cfg, pkgMgr); err != nil {
			handleInstallError(err, cfg.Silent)
			return
		}
		fmt.Println(ui.RenderSuccess("MCP tools ready"))
	} else if !pathExists(cfg.RepoDir) {
		// Need to clone repo for skills even if not installing MCP
		printStep("Downloading sources", cfg.Silent)

		// Check for interrupt before long operation
		if checkInterrupt(cfg.Silent) {
			return
		}

		if err := installer.RunGitClone(installer.RepoURL, cfg.RepoDir); err != nil {
			handleInstallError(err, cfg.Silent)
			return
		}
		fmt.Println(ui.RenderSuccess("Repository cloned"))
	}

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 8: Install skills
	if cfg.InstallSkills {
		printStep("Installing skills", cfg.Silent)
		if err := installer.InstallSkills(cfg); err != nil {
			handleInstallError(err, cfg.Silent)
			return
		}
	}

	// Check for interrupt
	if checkInterrupt(cfg.Silent) {
		return
	}

	// Step 9: Write MCP configs
	if cfg.InstallMCP {
		printStep("Configuring MCP", cfg.Silent)
		if err := installer.WriteMCPConfigs(cfg); err != nil {
			handleInstallError(err, cfg.Silent)
			return
		}

		// Print tool-specific configs
		for _, tool := range cfg.Tools {
			configPath := cfg.GetMCPConfigPath(tool)
			if configPath != "" {
				fmt.Println(ui.RenderSuccess(fmt.Sprintf("%s MCP config", toolDisplayName(tool))))
			}
			installer.PrintMCPInstructions(tool)
		}
	}

	// Step 10: Save version
	installer.SaveVersion(cfg)

	// Step 11: Print completion message
	ui.PrintCompletionMessage(cfg.Profile, cfg.Tools, cfg.InstallDir)

	// Step 12: Prompt for auth (if interactive)
	if !cfg.Silent {
		promptAuth(cfg)
	}
}

// checkInterrupt checks if an interrupt signal was received and handles graceful shutdown
func checkInterrupt(silent bool) bool {
	if signal.IsInterrupted() {
		if !silent {
			fmt.Println()
			fmt.Println(ui.RenderWarning("Installation cancelled by user"))
			fmt.Println("  " + ui.DimStyle.Render("No changes have been applied. Run 'aidevkit install' to try again."))
		}
		os.Exit(130) // Standard exit code for SIGINT
		return true
	}
	return false
}

// handleInstallError handles errors during installation, with special handling for interrupts
func handleInstallError(err error, silent bool) {
	if signal.IsInterruptError(err) || signal.IsInterrupted() || ui.IsUserCancelled(err) {
		if !silent {
			fmt.Println()
			fmt.Println(ui.RenderWarning("Installation cancelled by user"))
		}
		os.Exit(130)
		return
	}
	fmt.Println(ui.RenderError(err.Error()))
	os.Exit(1)
}

// selectTools handles tool selection via flags or interactive UI
func selectTools(cfg *installer.Config) ([]string, error) {
	// If tools provided via flag, use those
	if flagTools != "" {
		tools := strings.Split(flagTools, ",")
		for i := range tools {
			tools[i] = strings.TrimSpace(tools[i])
		}
		return tools, nil
	}

	// Detect installed tools
	detectedTools := detect.DetectTools()

	// In silent mode, use detected tools
	if cfg.Silent {
		return detect.FilterSelected(detectedTools), nil
	}

	// Build checkbox items
	items := make([]ui.CheckboxItem, len(detectedTools))
	for i, t := range detectedTools {
		items[i] = ui.CheckboxItem{
			Label:   t.Name,
			Value:   t.Value,
			Checked: t.Detected,
			Hint:    t.Hint,
		}
	}

	// Run interactive selection
	selected, err := ui.RunCheckbox("Select tools to install for:", items)
	if err != nil {
		return nil, err
	}

	// Default to claude if nothing selected
	if len(selected) == 0 {
		fmt.Println(ui.RenderWarning("No tools selected, defaulting to Claude Code"))
		return []string{"claude"}, nil
	}

	return selected, nil
}

// selectProfile handles profile selection via flags or interactive UI
func selectProfile(cfg *installer.Config) (string, error) {
	// If profile was explicitly set via flag (not default), use it
	if flagProfile != "DEFAULT" {
		return flagProfile, nil
	}

	// In silent mode, use default
	if cfg.Silent {
		return "DEFAULT", nil
	}

	// Detect available profiles
	profiles, err := detect.DetectProfiles()
	if err != nil || len(profiles) == 0 {
		// No profiles found - show simple prompt
		fmt.Println("  " + ui.DimStyle.Render("No ~/.databrickscfg found. You can authenticate after install."))
		fmt.Println()
		return ui.SimplePrompt("Profile name", "DEFAULT"), nil
	}

	// Build radio items
	items := make([]ui.RadioItem, len(profiles))
	defaultIdx := 0
	for i, p := range profiles {
		hint := ""
		selected := false
		if p.Name == "DEFAULT" {
			hint = "default"
			selected = true
			defaultIdx = i
		}
		items[i] = ui.RadioItem{
			Label:    p.Name,
			Value:    p.Name,
			Selected: selected,
			Hint:     hint,
		}
	}

	// If no DEFAULT profile, select first one
	if !hasDefaultProfile(profiles) && len(items) > 0 {
		items[0].Selected = true
		defaultIdx = 0
	}
	_ = defaultIdx // suppress unused warning

	// Run interactive selection
	return ui.RunRadio("Select Databricks profile", items)
}

// hasDefaultProfile checks if DEFAULT profile exists
func hasDefaultProfile(profiles []detect.Profile) bool {
	for _, p := range profiles {
		if p.Name == "DEFAULT" {
			return true
		}
	}
	return false
}

// selectInstallMode lets user choose what to install
func selectInstallMode() (installMCP bool, installSkills bool, err error) {
	items := []ui.RadioItem{
		{
			Label:    "Everything",
			Value:    "all",
			Hint:     "MCP tools + Skills",
			Selected: true,
		},
		{
			Label: "Skills only",
			Value: "skills",
			Hint:  "Databricks & MLflow skills for AI assistants",
		},
		{
			Label: "MCP tools only",
			Value: "mcp",
			Hint:  "Model Context Protocol tools for Databricks",
		},
	}

	fmt.Println()
	fmt.Println(ui.RenderStep("Installation mode"))
	fmt.Println()
	fmt.Println("  " + ui.DimStyle.Render("Choose what to install:"))
	fmt.Println("  " + ui.DimStyle.Render("• Skills: Markdown files that enhance AI assistant capabilities"))
	fmt.Println("  " + ui.DimStyle.Render("• MCP tools: Enable AI assistants to interact with Databricks APIs"))
	fmt.Println()

	selected, err := ui.RunRadio("What would you like to install?", items)
	if err != nil {
		return false, false, err
	}

	switch selected {
	case "all":
		return true, true, nil
	case "skills":
		return false, true, nil
	case "mcp":
		return true, false, nil
	default:
		return true, true, nil
	}
}

// selectMCPPath handles MCP path selection
func selectMCPPath(cfg *installer.Config) (string, error) {
	if cfg.Silent {
		return cfg.InstallDir, nil
	}

	fmt.Println("  " + ui.DimStyle.Render("The MCP tools runtime (Python venv + source) will be installed here."))
	fmt.Println("  " + ui.DimStyle.Render("Shared across all your projects — only the config files are per-project."))
	fmt.Println()

	return ui.SimplePrompt("Install path", cfg.InstallDir), nil
}

// showSummary displays installation summary and asks for confirmation
func showSummary(cfg *installer.Config) (bool, error) {
	// Determine install mode for display
	installMode := "Everything"
	if cfg.InstallMCP && !cfg.InstallSkills {
		installMode = "MCP tools only"
	} else if !cfg.InstallMCP && cfg.InstallSkills {
		installMode = "Skills only"
	}

	items := []ui.SummaryItem{
		{Key: "Mode", Value: installMode},
		{Key: "Tools", Value: strings.Join(cfg.Tools, ", ")},
		{Key: "Profile", Value: cfg.Profile},
		{Key: "Scope", Value: cfg.Scope},
	}

	if cfg.InstallMCP {
		items = append(items, ui.SummaryItem{Key: "MCP path", Value: installer.DisplayPath(cfg.InstallDir)})
	}

	return ui.RunSummary("Summary", items)
}

// promptAuth prompts user to run databricks auth
func promptAuth(cfg *installer.Config) {
	// Check if already authenticated (supports OAuth, Service Principal, and PAT tokens)
	if detect.ProfileIsAuthenticated(cfg.Profile) {
		fmt.Println(ui.RenderSuccess(fmt.Sprintf("Profile %s is already authenticated — skipping auth", cfg.Profile)))
		return
	}

	if detect.IsTokenSet() {
		fmt.Println(ui.RenderSuccess("DATABRICKS_TOKEN is set — skipping auth"))
		return
	}

	// Check if databricks CLI is available
	deps, _, _ := installer.CheckDependencies(false)
	databricksFound := false
	for _, d := range deps {
		if d.Name == "databricks" && d.Found {
			databricksFound = true
			break
		}
	}

	if !databricksFound {
		fmt.Println(ui.RenderWarning("Databricks CLI not installed — cannot run OAuth login"))
		fmt.Printf("  Install it, then run: %s\n", ui.InfoStyle.Render(fmt.Sprintf("databricks auth login --profile %s", cfg.Profile)))
		return
	}

	fmt.Println()
	fmt.Println("  " + ui.SubtitleStyle.Render("Authentication"))
	fmt.Printf("  This will run OAuth login for profile %s\n", ui.InfoStyle.Render(cfg.Profile))
	fmt.Println("  " + ui.DimStyle.Render("A browser window will open for you to authenticate with your Databricks workspace."))
	fmt.Println()

	response := ui.SimplePrompt(fmt.Sprintf("Run databricks auth login --profile %s now? (y/n)", cfg.Profile), "y")
	if response == "y" || response == "Y" || response == "yes" {
		fmt.Println()
		installer.RunDatabricksAuth(cfg.Profile)
	}
}


// printStep prints a step header
func printStep(title string, silent bool) {
	if silent {
		return
	}
	fmt.Println()
	fmt.Println(ui.RenderStep(title))
}

// toolDisplayName returns a display-friendly name for a tool
func toolDisplayName(tool string) string {
	switch tool {
	case "claude":
		return "Claude"
	case "cursor":
		return "Cursor"
	case "copilot":
		return "Copilot"
	case "codex":
		return "Codex"
	case "gemini":
		return "Gemini"
	default:
		return tool
	}
}

// pathExists checks if a path exists
func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

