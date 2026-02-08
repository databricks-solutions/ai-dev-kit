package cmd

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/databricks-solutions/ai-dev-kit/cli/signal"
	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
	"github.com/spf13/cobra"
)

const (
	githubRepo    = "databricks-solutions/ai-dev-kit"
	versionURL    = "https://raw.githubusercontent.com/" + githubRepo + "/main/VERSION"
	releaseURLFmt = "https://github.com/" + githubRepo + "/releases/latest/download/%s"
)

var (
	updateForce bool
	updateCheck bool
)

var updateCmd = &cobra.Command{
	Use:   "update",
	Short: "Update aidevkit to the latest version",
	Long: `Check for and install the latest version of aidevkit.

The update command will:
  • Check the latest version from GitHub
  • Download the appropriate binary for your platform
  • Replace the current binary with the new version

Use --check to only check for updates without installing.`,
	Run: runUpdate,
}

func init() {
	updateCmd.Flags().BoolVarP(&updateForce, "force", "f", false, "Force update even if already on latest version")
	updateCmd.Flags().BoolVarP(&updateCheck, "check", "c", false, "Only check for updates, don't install")
	// TODO: Re-enable once update infrastructure is ready (VERSION file + release URL)
	// rootCmd.AddCommand(updateCmd)
}

func runUpdate(cmd *cobra.Command, args []string) {
	ui.ClearScreen()
	ui.PrintLogo()

	fmt.Println()
	fmt.Println(ui.RenderStep("Update AI Dev Kit CLI"))
	fmt.Println()

	// Get current version
	currentVersion := Version
	fmt.Printf("  Current version: %s\n", ui.InfoStyle.Render(currentVersion))

	// Check latest version
	fmt.Printf("  Checking for updates...")
	latestVersion, err := fetchLatestVersion()
	if err != nil {
		fmt.Println()
		fmt.Println(ui.RenderError(fmt.Sprintf("Failed to check for updates: %v", err)))
		os.Exit(1)
	}
	fmt.Printf("\r  Latest version:  %s\n", ui.SuccessStyle.Render(latestVersion))

	// Compare versions
	if currentVersion == latestVersion && !updateForce {
		fmt.Println()
		fmt.Println(ui.RenderSuccess("You're already on the latest version!"))
		return
	}

	if currentVersion == "dev" {
		fmt.Println()
		fmt.Println(ui.RenderWarning("Running development version — use --force to update anyway"))
		if !updateForce {
			return
		}
	}

	// Check-only mode
	if updateCheck {
		fmt.Println()
		if currentVersion != latestVersion {
			fmt.Printf("  %s Update available: %s → %s\n",
				ui.InfoStyle.Render("→"),
				ui.DimStyle.Render(currentVersion),
				ui.SuccessStyle.Render(latestVersion))
			fmt.Println()
			fmt.Println("  Run " + ui.InfoStyle.Render("aidevkit update") + " to install the update.")
		}
		return
	}

	// Check for interrupt before proceeding with download
	if signal.IsInterrupted() {
		fmt.Println()
		fmt.Println(ui.RenderWarning("Update cancelled by user"))
		os.Exit(130)
		return
	}

	// Determine platform and binary name
	binaryName, err := getBinaryName()
	if err != nil {
		fmt.Println(ui.RenderError(err.Error()))
		os.Exit(1)
	}

	downloadURL := fmt.Sprintf(releaseURLFmt, binaryName)
	fmt.Println()
	fmt.Printf("  Platform: %s/%s\n", runtime.GOOS, runtime.GOARCH)
	fmt.Printf("  Binary:   %s\n", ui.DimStyle.Render(binaryName))

	// Get current executable path
	execPath, err := os.Executable()
	if err != nil {
		fmt.Println(ui.RenderError(fmt.Sprintf("Failed to get executable path: %v", err)))
		os.Exit(1)
	}
	execPath, err = filepath.EvalSymlinks(execPath)
	if err != nil {
		fmt.Println(ui.RenderError(fmt.Sprintf("Failed to resolve executable path: %v", err)))
		os.Exit(1)
	}

	fmt.Println()
	fmt.Println(ui.RenderStep("Downloading update"))
	fmt.Println()

	// Download to temp file
	tmpFile, err := os.CreateTemp("", "aidevkit-update-*")
	if err != nil {
		fmt.Println(ui.RenderError(fmt.Sprintf("Failed to create temp file: %v", err)))
		os.Exit(1)
	}
	tmpPath := tmpFile.Name()
	defer os.Remove(tmpPath) // Clean up on failure

	fmt.Printf("  Downloading from GitHub...")
	err = downloadBinary(downloadURL, tmpFile)
	tmpFile.Close()
	if err != nil {
		fmt.Println()
		fmt.Println(ui.RenderError(fmt.Sprintf("Failed to download: %v", err)))
		os.Exit(1)
	}
	fmt.Println(" " + ui.SuccessStyle.Render("✓"))

	// Make executable (Unix)
	if runtime.GOOS != "windows" {
		if err := os.Chmod(tmpPath, 0755); err != nil {
			fmt.Println(ui.RenderError(fmt.Sprintf("Failed to set permissions: %v", err)))
			os.Exit(1)
		}
	}

	// Check for interrupt before replacing binary
	if signal.IsInterrupted() {
		fmt.Println()
		fmt.Println(ui.RenderWarning("Update cancelled by user"))
		fmt.Println("  " + ui.DimStyle.Render("No changes were made to your installation."))
		os.Exit(130)
		return
	}

	// Replace current binary
	fmt.Printf("  Installing update...")

	// On Windows, we need to rename the old binary first
	if runtime.GOOS == "windows" {
		oldPath := execPath + ".old"
		os.Remove(oldPath) // Remove any previous .old file
		if err := os.Rename(execPath, oldPath); err != nil {
			fmt.Println()
			fmt.Println(ui.RenderError(fmt.Sprintf("Failed to backup old binary: %v", err)))
			os.Exit(1)
		}
		defer os.Remove(oldPath) // Clean up old binary
	}

	// Move new binary into place
	if err := moveFile(tmpPath, execPath); err != nil {
		fmt.Println()
		fmt.Println(ui.RenderError(fmt.Sprintf("Failed to install update: %v", err)))
		fmt.Println("  " + ui.DimStyle.Render("You may need to run with elevated permissions (sudo)"))
		os.Exit(1)
	}
	fmt.Println(" " + ui.SuccessStyle.Render("✓"))

	fmt.Println()
	fmt.Println(ui.RenderSuccess(fmt.Sprintf("Updated to version %s!", latestVersion)))
	fmt.Println()
	fmt.Println("  Run " + ui.InfoStyle.Render("aidevkit version") + " to verify.")
}

// fetchLatestVersion gets the latest version from GitHub
func fetchLatestVersion() (string, error) {
	client := &http.Client{Timeout: 10 * time.Second}

	resp, err := client.Get(versionURL)
	if err != nil {
		return "", fmt.Errorf("network error: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP %d from version check", resp.StatusCode)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read response: %w", err)
	}

	version := strings.TrimSpace(string(data))
	if version == "" || strings.Contains(version, "404") {
		return "", fmt.Errorf("invalid version response")
	}

	return version, nil
}

// getBinaryName returns the binary name for the current platform
func getBinaryName() (string, error) {
	var platform string
	var arch string

	switch runtime.GOOS {
	case "darwin":
		platform = "macos"
		// Universal binary - no arch needed
		return platform + "/aidevkit", nil
	case "linux":
		platform = "linux"
	case "windows":
		platform = "windows"
	default:
		return "", fmt.Errorf("unsupported operating system: %s", runtime.GOOS)
	}

	switch runtime.GOARCH {
	case "amd64":
		arch = "amd64"
	case "arm64":
		arch = "arm64"
	default:
		return "", fmt.Errorf("unsupported architecture: %s", runtime.GOARCH)
	}

	name := fmt.Sprintf("%s/%s/aidevkit", platform, arch)
	if runtime.GOOS == "windows" {
		name += ".exe"
	}

	return name, nil
}

// downloadBinary downloads a file from URL to the given writer
func downloadBinary(url string, dest *os.File) error {
	client := &http.Client{
		Timeout: 5 * time.Minute, // Large timeout for big files
	}

	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("binary not found at %s - release may not exist yet", url)
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	_, err = io.Copy(dest, resp.Body)
	return err
}

// moveFile moves a file, falling back to copy+delete if rename fails (cross-device)
func moveFile(src, dst string) error {
	// Try simple rename first
	err := os.Rename(src, dst)
	if err == nil {
		return nil
	}

	// Rename failed, try copy + delete (for cross-device moves)
	srcFile, err := os.Open(src)
	if err != nil {
		return err
	}
	defer srcFile.Close()

	dstFile, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0755)
	if err != nil {
		return err
	}
	defer dstFile.Close()

	if _, err := io.Copy(dstFile, srcFile); err != nil {
		return err
	}

	// Close files before removing source
	srcFile.Close()
	dstFile.Close()

	return os.Remove(src)
}

