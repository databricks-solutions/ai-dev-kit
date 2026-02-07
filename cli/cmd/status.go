package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/databricks-solutions/ai-dev-kit/cli/detect"
	"github.com/databricks-solutions/ai-dev-kit/cli/installer"
	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
	"github.com/spf13/cobra"
)

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show installation status",
	Long: `Display the current status of the Databricks AI Dev Kit installation,
including configured tools, profiles, and installed components.`,
	Run: runStatus,
}

func init() {
	rootCmd.AddCommand(statusCmd)
}

func runStatus(cmd *cobra.Command, args []string) {
	cfg := installer.NewConfig()
	cfg.UpdateBaseDir()

	// Header
	fmt.Println()
	fmt.Printf("  %s v%s\n", ui.TitleStyle.Render("Databricks AI Dev Kit"), Version)
	fmt.Println("  " + strings.Repeat("─", 50))
	fmt.Println()

	// Installation info
	fmt.Println(ui.SubtitleStyle.Render("  Installation"))
	fmt.Println()

	if pathExists(cfg.InstallDir) {
		fmt.Printf("    Location:  %s\n", ui.ActiveStyle.Render(installer.DisplayPath(cfg.InstallDir)))
		version := installer.GetCurrentVersion(cfg)
		fmt.Printf("    Version:   %s\n", ui.ActiveStyle.Render(version))
	} else {
		fmt.Printf("    Location:  %s\n", ui.MutedStyle.Render("not installed"))
	}

	// Check MCP server
	if pathExists(cfg.VenvPython) {
		fmt.Printf("    MCP Server: %s\n", ui.SuccessStyle.Render("installed"))
	} else {
		fmt.Printf("    MCP Server: %s\n", ui.MutedStyle.Render("not installed"))
	}
	fmt.Println()

	// Profile info
	fmt.Println(ui.SubtitleStyle.Render("  Databricks Profile"))
	fmt.Println()

	// Determine selected profile
	selectedProfile := os.Getenv("DATABRICKS_CONFIG_PROFILE")
	if selectedProfile == "" {
		selectedProfile = "DEFAULT"
	}

	profiles, _ := detect.DetectProfiles()
	if len(profiles) > 0 {
		for _, p := range profiles {
			// Determine auth status
			status := ui.MutedStyle.Render("○")
			authMethod := ""
			if p.IsAuthenticated() {
				status = ui.SuccessStyle.Render("●")
				if p.HasOAuth {
					authMethod = "OAuth"
				} else if p.HasServicePrinc {
					authMethod = "Service Principal"
				} else if p.HasToken {
					authMethod = "PAT"
				}
			}

			// Build hint text
			hints := []string{}
			if p.Name == selectedProfile {
				hints = append(hints, "selected")
			}
			if authMethod != "" {
				hints = append(hints, authMethod)
			}

			hint := ""
			if len(hints) > 0 {
				hint = ui.DimStyle.Render(" (" + strings.Join(hints, ", ") + ")")
			}

			// Highlight selected profile
			name := p.Name
			if p.Name == selectedProfile {
				name = ui.ActiveStyle.Render(p.Name)
			}

			fmt.Printf("    %s %s%s\n", status, name, hint)
		}
	} else {
		fmt.Printf("    %s\n", ui.MutedStyle.Render("No profiles found in ~/.databrickscfg"))
	}

	// Show env var override if set
	if envProfile := os.Getenv("DATABRICKS_CONFIG_PROFILE"); envProfile != "" {
		fmt.Printf("    %s DATABRICKS_CONFIG_PROFILE=%s\n", ui.DimStyle.Render("→"), ui.ActiveStyle.Render(envProfile))
	}

	if detect.IsTokenSet() {
		fmt.Printf("    %s %s\n", ui.SuccessStyle.Render("●"), "DATABRICKS_TOKEN env var set")
	}
	fmt.Println()

	// Tools status
	fmt.Println(ui.SubtitleStyle.Render("  Configured Tools"))
	fmt.Println()

	tools := []struct {
		name       string
		value      string
		configPath string
	}{
		{"Claude Code", "claude", filepath.Join(cfg.BaseDir, ".mcp.json")},
		{"Cursor", "cursor", filepath.Join(cfg.BaseDir, ".cursor", "mcp.json")},
		{"GitHub Copilot", "copilot", filepath.Join(cfg.BaseDir, ".vscode", "mcp.json")},
		{"OpenAI Codex", "codex", filepath.Join(cfg.BaseDir, ".codex", "config.toml")},
	}

	for _, tool := range tools {
		if pathExists(tool.configPath) && hasDatabricksConfig(tool.configPath) {
			fmt.Printf("    %s %-16s %s\n",
				ui.SuccessStyle.Render("✓"),
				tool.name,
				ui.DimStyle.Render(installer.DisplayPath(tool.configPath)))
		} else {
			fmt.Printf("    %s %-16s %s\n",
				ui.MutedStyle.Render("○"),
				tool.name,
				ui.DimStyle.Render("not configured"))
		}
	}
	fmt.Println()

	// Skills count
	fmt.Println(ui.SubtitleStyle.Render("  Installed Skills"))
	fmt.Println()

	skillsDirs := []string{
		filepath.Join(cfg.BaseDir, ".claude", "skills"),
		filepath.Join(cfg.BaseDir, ".cursor", "skills"),
		filepath.Join(cfg.BaseDir, ".github", "skills"),
		filepath.Join(cfg.BaseDir, ".agents", "skills"),
	}

	totalSkills := 0
	for _, dir := range skillsDirs {
		if entries, err := os.ReadDir(dir); err == nil {
			for _, e := range entries {
				if e.IsDir() {
					totalSkills++
				}
			}
			if len(entries) > 0 {
				fmt.Printf("    %s %d skills in %s\n",
					ui.SuccessStyle.Render("✓"),
					countDirs(entries),
					ui.DimStyle.Render(installer.DisplayPath(dir)))
			}
		}
	}

	if totalSkills == 0 {
		fmt.Printf("    %s\n", ui.MutedStyle.Render("No skills installed"))
	}
	fmt.Println()
}

// hasDatabricksConfig checks if a config file has databricks configuration
func hasDatabricksConfig(path string) bool {
	data, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	content := string(data)
	return strings.Contains(content, "databricks")
}

// countDirs counts directories in a slice of DirEntry
func countDirs(entries []os.DirEntry) int {
	count := 0
	for _, e := range entries {
		if e.IsDir() {
			count++
		}
	}
	return count
}

