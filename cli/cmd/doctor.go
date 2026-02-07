package cmd

import (
	"fmt"
	"net/http"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/databricks-solutions/ai-dev-kit/cli/detect"
	"github.com/databricks-solutions/ai-dev-kit/cli/installer"
	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
	"github.com/spf13/cobra"
)

var doctorCmd = &cobra.Command{
	Use:   "doctor",
	Short: "Diagnose installation issues",
	Long: `Check your system for potential issues with the Databricks AI Dev Kit.
This command verifies dependencies, configuration, and connectivity.`,
	Run: runDoctor,
}

func init() {
	rootCmd.AddCommand(doctorCmd)
}

func runDoctor(cmd *cobra.Command, args []string) {
	cfg := installer.NewConfig()
	cfg.UpdateBaseDir()

	fmt.Println()
	fmt.Println("  " + ui.TitleStyle.Render("Databricks AI Dev Kit Doctor"))
	fmt.Println("  " + strings.Repeat("─", 50))
	fmt.Println()

	issues := 0

	// System checks
	fmt.Println(ui.SubtitleStyle.Render("  System Dependencies"))
	fmt.Println()

	// Check Git
	if version, ok := getCommandVersion("git", "--version"); ok {
		fmt.Printf("    %s git %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("("+version+")"))
	} else {
		fmt.Printf("    %s git %s\n", ui.ErrorStyle.Render("✗"), ui.ErrorStyle.Render("not found"))
		printSuggestion("Install git: https://git-scm.com/downloads")
		issues++
	}

	// Check Python
	pythonCmd := "python3"
	if runtime.GOOS == "windows" {
		pythonCmd = "python"
	}
	if version, ok := getCommandVersion(pythonCmd, "--version"); ok {
		fmt.Printf("    %s python %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("("+version+")"))
	} else {
		fmt.Printf("    %s python %s\n", ui.ErrorStyle.Render("✗"), ui.ErrorStyle.Render("not found"))
		printSuggestion("Install Python 3.9+: https://python.org")
		issues++
	}

	// Check uv or pip
	if version, ok := getCommandVersion("uv", "--version"); ok {
		fmt.Printf("    %s uv %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("("+version+")"))
	} else if version, ok := getCommandVersion("pip3", "--version"); ok {
		fmt.Printf("    %s pip3 %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("("+version+")"))
	} else if version, ok := getCommandVersion("pip", "--version"); ok {
		fmt.Printf("    %s pip %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("("+version+")"))
	} else {
		fmt.Printf("    %s pip/uv %s\n", ui.WarningStyle.Render("!"), ui.WarningStyle.Render("not found"))
		printSuggestion("Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
		issues++
	}

	// Check Databricks CLI
	if version, ok := getCommandVersion("databricks", "--version"); ok {
		fmt.Printf("    %s databricks CLI %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("("+version+")"))
	} else {
		fmt.Printf("    %s databricks CLI %s\n", ui.WarningStyle.Render("!"), ui.WarningStyle.Render("not found"))
		printSuggestion("Install: curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh")
	}
	fmt.Println()

	// Connectivity checks
	fmt.Println(ui.SubtitleStyle.Render("  Connectivity"))
	fmt.Println()

	// Check GitHub
	if checkURL("https://github.com") {
		fmt.Printf("    %s GitHub %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("reachable"))
	} else {
		fmt.Printf("    %s GitHub %s\n", ui.ErrorStyle.Render("✗"), ui.ErrorStyle.Render("unreachable"))
		printSuggestion("Check your internet connection or firewall settings")
		issues++
	}

	// Check PyPI
	if checkURL("https://pypi.org") {
		fmt.Printf("    %s PyPI %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("reachable"))
	} else {
		fmt.Printf("    %s PyPI %s\n", ui.WarningStyle.Render("!"), ui.WarningStyle.Render("unreachable"))
		printSuggestion("Python packages may fail to install")
	}
	fmt.Println()

	// Installation checks
	fmt.Println(ui.SubtitleStyle.Render("  Installation"))
	fmt.Println()

	// Check install directory
	if pathExists(cfg.InstallDir) {
		fmt.Printf("    %s Install directory exists\n", ui.SuccessStyle.Render("✓"))
	} else {
		fmt.Printf("    %s Install directory %s\n", ui.MutedStyle.Render("○"), ui.DimStyle.Render("not created yet"))
	}

	// Check repo
	if pathExists(filepath.Join(cfg.RepoDir, ".git")) {
		fmt.Printf("    %s Repository cloned\n", ui.SuccessStyle.Render("✓"))
	} else {
		fmt.Printf("    %s Repository %s\n", ui.MutedStyle.Render("○"), ui.DimStyle.Render("not cloned yet"))
	}

	// Check venv
	if pathExists(cfg.VenvPython) {
		fmt.Printf("    %s Python venv ready\n", ui.SuccessStyle.Render("✓"))

		// Check MCP server import
		cmd := exec.Command(cfg.VenvPython, "-c", "import databricks_mcp_server")
		if err := cmd.Run(); err == nil {
			fmt.Printf("    %s MCP server installed\n", ui.SuccessStyle.Render("✓"))
		} else {
			fmt.Printf("    %s MCP server %s\n", ui.ErrorStyle.Render("✗"), ui.ErrorStyle.Render("import failed"))
			printSuggestion("Run: aidevkit install --force")
			issues++
		}
	} else {
		fmt.Printf("    %s Python venv %s\n", ui.MutedStyle.Render("○"), ui.DimStyle.Render("not created yet"))
	}
	fmt.Println()

	// Configuration checks
	fmt.Println(ui.SubtitleStyle.Render("  Configuration"))
	fmt.Println()

	// Check Databricks auth
	profiles, _ := detect.DetectProfiles()
	hasAuth := false
	authMethod := ""
	for _, p := range profiles {
		if p.IsAuthenticated() {
			hasAuth = true
			if p.HasOAuth {
				authMethod = "OAuth"
			} else if p.HasServicePrinc {
				authMethod = "Service Principal"
			} else if p.HasToken {
				authMethod = "PAT Token"
			}
			break
		}
	}

	if detect.IsTokenSet() {
		fmt.Printf("    %s DATABRICKS_TOKEN set\n", ui.SuccessStyle.Render("✓"))
		hasAuth = true
	} else if hasAuth {
		if authMethod != "" {
			fmt.Printf("    %s Databricks authentication configured %s\n", ui.SuccessStyle.Render("✓"), ui.DimStyle.Render("("+authMethod+")"))
		} else {
			fmt.Printf("    %s Databricks profile configured\n", ui.SuccessStyle.Render("✓"))
		}
	} else {
		fmt.Printf("    %s Databricks authentication %s\n", ui.WarningStyle.Render("!"), ui.WarningStyle.Render("not configured"))
		printSuggestion("Run: databricks auth login --profile DEFAULT")
	}

	// Check tool configs
	toolConfigs := []struct {
		name string
		path string
	}{
		{"Claude", filepath.Join(cfg.BaseDir, ".mcp.json")},
		{"Cursor", filepath.Join(cfg.BaseDir, ".cursor", "mcp.json")},
		{"Copilot", filepath.Join(cfg.BaseDir, ".vscode", "mcp.json")},
		{"Codex", filepath.Join(cfg.BaseDir, ".codex", "config.toml")},
	}

	configuredTools := 0
	for _, tc := range toolConfigs {
		if pathExists(tc.path) && hasDatabricksConfig(tc.path) {
			configuredTools++
		}
	}

	if configuredTools > 0 {
		fmt.Printf("    %s %d tool(s) configured\n", ui.SuccessStyle.Render("✓"), configuredTools)
	} else {
		fmt.Printf("    %s No tools configured %s\n", ui.MutedStyle.Render("○"), ui.DimStyle.Render("run: aidevkit install"))
	}
	fmt.Println()

	// Summary
	fmt.Println("  " + strings.Repeat("─", 50))
	if issues == 0 {
		fmt.Println()
		fmt.Println("  " + ui.SuccessStyle.Render("✓ No issues found!"))
	} else {
		fmt.Println()
		fmt.Printf("  %s %d issue(s) found\n", ui.WarningStyle.Render("!"), issues)
	}
	fmt.Println()
}

// getCommandVersion runs a command and extracts version info
func getCommandVersion(name string, args ...string) (string, bool) {
	cmd := exec.Command(name, args...)
	output, err := cmd.Output()
	if err != nil {
		return "", false
	}
	// Extract version from output (take first line, clean it up)
	version := strings.TrimSpace(string(output))
	if idx := strings.Index(version, "\n"); idx > 0 {
		version = version[:idx]
	}
	// Try to extract just the version number
	parts := strings.Fields(version)
	for _, p := range parts {
		if len(p) > 0 && (p[0] >= '0' && p[0] <= '9') {
			return p, true
		}
	}
	return version, true
}

// checkURL tests if a URL is reachable
func checkURL(url string) bool {
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Head(url)
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode < 400
}

// printSuggestion prints a formatted suggestion
func printSuggestion(text string) {
	fmt.Printf("      %s %s\n", ui.DimStyle.Render("→"), ui.DimStyle.Render(text))
}

