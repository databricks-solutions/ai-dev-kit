package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/databricks-solutions/ai-dev-kit/cli/installer"
	"github.com/databricks-solutions/ai-dev-kit/cli/signal"
	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
	"github.com/spf13/cobra"
)

var (
	uninstallGlobal bool
	uninstallForce  bool
)

var uninstallCmd = &cobra.Command{
	Use:   "uninstall",
	Short: "Uninstall the Databricks AI Dev Kit",
	Long: `Uninstall the Databricks AI Dev Kit components.

By default, removes project-level items from the current directory:
  • Skills directories (.claude/skills, .cursor/skills, etc.)
  • MCP configuration files (.mcp.json, .cursor/mcp.json, etc.)
  • Project version marker (.ai-dev-kit/)

With --global flag, also removes globally installed items:
  • MCP server runtime (~/.ai-dev-kit/)
  • Global configuration files`,
	Run: runUninstall,
}

func init() {
	uninstallCmd.Flags().BoolVarP(&uninstallGlobal, "global", "g", false, "Also remove global installation (MCP server, venv)")
	uninstallCmd.Flags().BoolVarP(&uninstallForce, "force", "f", false, "Skip confirmation prompt")
	rootCmd.AddCommand(uninstallCmd)
}

func runUninstall(cmd *cobra.Command, args []string) {
	cfg := installer.NewConfig()
	cfg.UpdateBaseDir()

	// Clear screen and show logo
	ui.ClearScreen()
	ui.PrintLogo()

	fmt.Println()
	fmt.Println(ui.RenderStep("Uninstall AI Dev Kit"))
	fmt.Println()

	// Collect items to remove
	var projectItems []uninstallItem
	var globalItems []uninstallItem

	// Project-level items
	cwd, _ := os.Getwd()

	// Skills directories
	skillsDirs := []struct {
		tool string
		path string
	}{
		{"Claude", filepath.Join(cwd, ".claude", "skills")},
		{"Cursor", filepath.Join(cwd, ".cursor", "skills")},
		{"Copilot", filepath.Join(cwd, ".github", "skills")},
		{"Codex", filepath.Join(cwd, ".agents", "skills")},
		{"Gemini", filepath.Join(cwd, ".gemini", "skills")},
	}

	for _, sd := range skillsDirs {
		if pathExists(sd.path) {
			projectItems = append(projectItems, uninstallItem{
				name:        fmt.Sprintf("%s skills", sd.tool),
				path:        sd.path,
				description: installer.DisplayPath(sd.path),
			})
		}
	}

	// MCP config files (project scope)
	mcpConfigs := []struct {
		tool string
		path string
	}{
		{"Claude", filepath.Join(cwd, ".mcp.json")},
		{"Cursor", filepath.Join(cwd, ".cursor", "mcp.json")},
		{"Copilot", filepath.Join(cwd, ".vscode", "mcp.json")},
		{"Codex", filepath.Join(cwd, ".codex", "config.toml")},
		{"Gemini", filepath.Join(cwd, ".gemini", "settings.json")},
	}

	for _, mc := range mcpConfigs {
		if pathExists(mc.path) {
			projectItems = append(projectItems, uninstallItem{
				name:        fmt.Sprintf("%s MCP config", mc.tool),
				path:        mc.path,
				description: installer.DisplayPath(mc.path),
				isFile:      true,
			})
		}
	}

	// Project version marker
	projectVersionDir := filepath.Join(cwd, ".ai-dev-kit")
	if pathExists(projectVersionDir) {
		projectItems = append(projectItems, uninstallItem{
			name:        "Project version marker",
			path:        projectVersionDir,
			description: ".ai-dev-kit/",
		})
	}

	// Global items (only if --global flag)
	if uninstallGlobal {
		homeDir := getHomeDir()

		// Main installation directory
		installDir := cfg.InstallDir
		if pathExists(installDir) {
			globalItems = append(globalItems, uninstallItem{
				name:        "MCP server & runtime",
				path:        installDir,
				description: installer.DisplayPath(installDir) + " (repo, venv, version)",
			})
		}

		// Global MCP configs
		globalConfigs := []struct {
			tool string
			path string
		}{
			{"Claude", filepath.Join(homeDir, ".claude", "mcp.json")},
			{"Codex", filepath.Join(homeDir, ".codex", "config.toml")},
			{"Gemini", filepath.Join(homeDir, ".gemini", "settings.json")},
		}

		for _, gc := range globalConfigs {
			if pathExists(gc.path) {
				// Check if it contains databricks config
				if containsDatabricksConfig(gc.path) {
					globalItems = append(globalItems, uninstallItem{
						name:        fmt.Sprintf("%s global MCP config", gc.tool),
						path:        gc.path,
						description: installer.DisplayPath(gc.path),
						isFile:      true,
						needsClean:  true, // Only remove databricks entry, not whole file
					})
				}
			}
		}
	}

	// Check if anything to uninstall
	totalItems := len(projectItems) + len(globalItems)
	if totalItems == 0 {
		fmt.Println(ui.RenderSuccess("Nothing to uninstall — AI Dev Kit is not installed here"))
		return
	}

	// Display what will be removed
	fmt.Println("  The following items will be removed:")
	fmt.Println()

	if len(projectItems) > 0 {
		fmt.Println("  " + ui.SubtitleStyle.Render("Project items (current directory):"))
		for _, item := range projectItems {
			fmt.Printf("    %s %s\n", ui.WarningStyle.Render("•"), item.name)
			fmt.Printf("      %s\n", ui.DimStyle.Render(item.description))
		}
		fmt.Println()
	}

	if len(globalItems) > 0 {
		fmt.Println("  " + ui.SubtitleStyle.Render("Global items:"))
		for _, item := range globalItems {
			fmt.Printf("    %s %s\n", ui.ErrorStyle.Render("•"), item.name)
			fmt.Printf("      %s\n", ui.DimStyle.Render(item.description))
		}
		fmt.Println()
	}

	// Confirmation
	if !uninstallForce {
		fmt.Println()
		response := ui.SimplePrompt("Are you sure you want to uninstall? (y/n)", "n")
		if response != "y" && response != "Y" && response != "yes" {
			fmt.Println("\n  Uninstall cancelled.")
			return
		}
	}

	// Check for interrupt after confirmation
	if signal.IsInterrupted() {
		fmt.Println()
		fmt.Println(ui.RenderWarning("Uninstall cancelled by user"))
		os.Exit(130)
		return
	}

	fmt.Println()
	fmt.Println(ui.RenderStep("Removing items"))
	fmt.Println()

	// Remove project items
	var errors []string
	for _, item := range projectItems {
		// Check for interrupt before each removal
		if signal.IsInterrupted() {
			fmt.Println()
			fmt.Println(ui.RenderWarning("Uninstall cancelled by user"))
			os.Exit(130)
			return
		}
		if err := removeItem(item); err != nil {
			errors = append(errors, fmt.Sprintf("%s: %v", item.name, err))
			fmt.Printf("  %s %s\n", ui.ErrorStyle.Render("✗"), item.name)
		} else {
			fmt.Printf("  %s %s\n", ui.SuccessStyle.Render("✓"), item.name)
		}
	}

	// Remove global items
	for _, item := range globalItems {
		// Check for interrupt before each removal
		if signal.IsInterrupted() {
			fmt.Println()
			fmt.Println(ui.RenderWarning("Uninstall cancelled by user"))
			os.Exit(130)
			return
		}
		if err := removeItem(item); err != nil {
			errors = append(errors, fmt.Sprintf("%s: %v", item.name, err))
			fmt.Printf("  %s %s\n", ui.ErrorStyle.Render("✗"), item.name)
		} else {
			fmt.Printf("  %s %s\n", ui.SuccessStyle.Render("✓"), item.name)
		}
	}

	// Summary
	fmt.Println()
	if len(errors) > 0 {
		fmt.Println(ui.RenderWarning(fmt.Sprintf("Uninstall completed with %d error(s):", len(errors))))
		for _, e := range errors {
			fmt.Printf("  %s %s\n", ui.ErrorStyle.Render("•"), e)
		}
	} else {
		fmt.Println(ui.RenderSuccess("AI Dev Kit successfully uninstalled"))
	}

	if !uninstallGlobal && len(globalItems) == 0 {
		fmt.Println()
		fmt.Println("  " + ui.DimStyle.Render("Note: Global installation (~/.ai-dev-kit) was preserved."))
		fmt.Println("  " + ui.DimStyle.Render("Use --global flag to also remove the MCP server runtime."))
	}
}

type uninstallItem struct {
	name        string
	path        string
	description string
	isFile      bool
	needsClean  bool // If true, only remove databricks entry from config
}

func removeItem(item uninstallItem) error {
	if item.needsClean {
		return cleanDatabricksFromConfig(item.path)
	}

	if item.isFile {
		return os.Remove(item.path)
	}

	return os.RemoveAll(item.path)
}

// cleanDatabricksFromConfig removes the databricks entry from MCP config files
func cleanDatabricksFromConfig(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	content := string(data)

	// Check file type by extension
	if strings.HasSuffix(path, ".json") {
		// For JSON files, we need to be careful not to break the structure
		// Simple approach: if the file only contains databricks config, remove it
		// Otherwise, leave it (user should manually clean)
		if strings.Contains(content, `"databricks"`) {
			// Try to parse and remove databricks entry
			cleaned, removed := removeDatabricksFromJSON(content)
			if removed {
				return os.WriteFile(path, []byte(cleaned), 0644)
			}
		}
	} else if strings.HasSuffix(path, ".toml") {
		// For TOML files, remove [mcp_servers.databricks] section
		if strings.Contains(content, "[mcp_servers.databricks]") {
			cleaned := removeDatabricksFromTOML(content)
			return os.WriteFile(path, []byte(cleaned), 0644)
		}
	}

	return nil
}

// removeDatabricksFromJSON removes databricks entry from MCP JSON config
func removeDatabricksFromJSON(content string) (string, bool) {
	// Simple regex-like removal for common patterns
	// This handles both mcpServers and servers formats

	// Pattern 1: "databricks": { ... }
	start := strings.Index(content, `"databricks"`)
	if start == -1 {
		return content, false
	}

	// Find the opening brace after "databricks":
	braceStart := strings.Index(content[start:], "{")
	if braceStart == -1 {
		return content, false
	}
	braceStart += start

	// Find matching closing brace
	depth := 1
	braceEnd := braceStart + 1
	for braceEnd < len(content) && depth > 0 {
		if content[braceEnd] == '{' {
			depth++
		} else if content[braceEnd] == '}' {
			depth--
		}
		braceEnd++
	}

	// Find the start of the entry (including preceding comma or following comma)
	entryStart := start
	for entryStart > 0 && (content[entryStart-1] == ' ' || content[entryStart-1] == '\t' || content[entryStart-1] == '\n' || content[entryStart-1] == ',') {
		entryStart--
	}

	// Check for trailing comma
	entryEnd := braceEnd
	for entryEnd < len(content) && (content[entryEnd] == ' ' || content[entryEnd] == '\t' || content[entryEnd] == '\n') {
		entryEnd++
	}
	if entryEnd < len(content) && content[entryEnd] == ',' {
		entryEnd++
	}

	// Remove the entry
	cleaned := content[:entryStart] + content[entryEnd:]

	// Clean up any double commas or trailing commas before }
	cleaned = strings.ReplaceAll(cleaned, ",,", ",")
	cleaned = strings.ReplaceAll(cleaned, ",\n}", "\n}")
	cleaned = strings.ReplaceAll(cleaned, ", }", " }")

	return cleaned, true
}

// removeDatabricksFromTOML removes databricks section from TOML config
func removeDatabricksFromTOML(content string) string {
	lines := strings.Split(content, "\n")
	var result []string
	inDatabricksSection := false

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)

		// Check if entering databricks section
		if trimmed == "[mcp_servers.databricks]" {
			inDatabricksSection = true
			continue
		}

		// Check if entering a different section (end of databricks section)
		if inDatabricksSection && strings.HasPrefix(trimmed, "[") {
			inDatabricksSection = false
		}

		// Skip lines in databricks section
		if inDatabricksSection {
			continue
		}

		result = append(result, line)
	}

	return strings.Join(result, "\n")
}

// containsDatabricksConfig checks if a config file contains databricks configuration
func containsDatabricksConfig(path string) bool {
	data, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	content := string(data)
	return strings.Contains(content, "databricks")
}

// getHomeDir returns the user's home directory
func getHomeDir() string {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		if h := os.Getenv("HOME"); h != "" {
			return h
		}
		if h := os.Getenv("USERPROFILE"); h != "" {
			return h
		}
		return "/tmp"
	}
	return homeDir
}

