// Package cmd provides CLI commands using Cobra
package cmd

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
	"github.com/spf13/cobra"
)

// Version is set at build time via ldflags
var Version = "dev"

// Verbose enables detailed output
var Verbose bool

var rootCmd = &cobra.Command{
	Use:   "aidevkit",
	Short: "Databricks AI Dev Kit CLI",
	Long: `Databricks AI Dev Kit CLI - Install and configure the AI Dev Kit
for Claude Code, Cursor, GitHub Copilot, and OpenAI Codex.

The CLI provides an interactive installer that:
  • Detects installed development tools
  • Configures Databricks MCP server
  • Installs Databricks and MLflow skills
  • Sets up tool-specific configurations`,
	Version: Version,
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		// Check for updates (non-blocking, silent on error)
		checkForUpdates()
	},
	CompletionOptions: cobra.CompletionOptions{
		DisableDefaultCmd: true,
	},
}

// Execute runs the root command
func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}

func init() {
	// Global flags
	rootCmd.PersistentFlags().BoolVarP(&Verbose, "verbose", "v", false, "Enable verbose output")

	// Commands
	rootCmd.AddCommand(installCmd)
	rootCmd.AddCommand(versionCmd)
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print the version number",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("aidevkit version %s\n", Version)

		// Check for latest version
		if latest, err := getLatestVersion(); err == nil && latest != "" && latest != Version {
			fmt.Println()
			fmt.Printf("  %s A new version is available: %s\n",
				ui.InfoStyle.Render("→"),
				ui.SuccessStyle.Render(latest))
			fmt.Printf("  %s Update with: %s\n",
				ui.DimStyle.Render(" "),
				ui.DimStyle.Render("Download from GitHub releases"))
		}
	},
}

// checkForUpdates is a no-op placeholder for future update notification
// Update checking is handled by the 'version' command
func checkForUpdates() {
	// Update checking is performed by the version command
	// Background checks during other commands were removed as they
	// couldn't reliably display notifications during command execution
}

// getLatestVersion fetches the latest version from GitHub
func getLatestVersion() (string, error) {
	client := &http.Client{Timeout: 3 * time.Second}

	resp, err := client.Get("https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/VERSION")
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	version := strings.TrimSpace(string(data))

	// Validate version doesn't contain error text
	if strings.Contains(version, "404") || strings.Contains(version, "Not Found") {
		return "", fmt.Errorf("invalid version")
	}

	return version, nil
}

// LogVerbose prints a message only if verbose mode is enabled
func LogVerbose(format string, args ...interface{}) {
	if Verbose {
		fmt.Printf("  "+ui.DimStyle.Render("[verbose]")+" "+format+"\n", args...)
	}
}

// LogDebug prints debug information
func LogDebug(format string, args ...interface{}) {
	if Verbose {
		fmt.Printf("  "+ui.DimStyle.Render("[debug]")+" "+format+"\n", args...)
	}
}
