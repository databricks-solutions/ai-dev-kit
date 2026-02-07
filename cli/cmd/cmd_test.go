package cmd

import (
	"bytes"
	"os"
	"strings"
	"testing"

	"github.com/spf13/cobra"
)

// executeCommand executes a cobra command with the given args and returns output
func executeCommand(root *cobra.Command, args ...string) (output string, err error) {
	buf := new(bytes.Buffer)
	root.SetOut(buf)
	root.SetErr(buf)
	root.SetArgs(args)

	err = root.Execute()
	return buf.String(), err
}

func TestRootCommand(t *testing.T) {
	// Test that root command shows help without error
	output, err := executeCommand(rootCmd, "--help")
	if err != nil {
		t.Fatalf("Root command failed: %v", err)
	}

	expectedStrings := []string{
		"Databricks AI Dev Kit",
		"install",
		"--help",
	}

	for _, s := range expectedStrings {
		if !strings.Contains(output, s) {
			t.Errorf("Help output should contain %q", s)
		}
	}
}

func TestVersionCommand(t *testing.T) {
	// The version command prints directly to stdout, not to cmd.OutOrStdout()
	// So we just verify the command executes without error
	originalVersion := Version
	Version = "test-version"
	defer func() { Version = originalVersion }()

	// Capture stdout
	oldStdout := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	_, err := executeCommand(rootCmd, "version")

	w.Close()
	os.Stdout = oldStdout

	var buf bytes.Buffer
	buf.ReadFrom(r)
	output := buf.String()

	if err != nil {
		t.Fatalf("Version command failed: %v", err)
	}

	if !strings.Contains(output, "test-version") {
		t.Errorf("Version output should contain version string, got: %s", output)
	}
}

func TestInstallCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "install", "--help")
	if err != nil {
		t.Fatalf("Install help failed: %v", err)
	}

	expectedStrings := []string{
		"Install",
		"--profile",
		"--global",
		"--silent",
		"--force",
		"--tools",
	}

	for _, s := range expectedStrings {
		if !strings.Contains(output, s) {
			t.Errorf("Install help should contain %q", s)
		}
	}
}

func TestStatusCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "status", "--help")
	if err != nil {
		t.Fatalf("Status help failed: %v", err)
	}

	if !strings.Contains(output, "status") {
		t.Error("Status help should contain 'status'")
	}
}

func TestDoctorCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "doctor", "--help")
	if err != nil {
		t.Fatalf("Doctor help failed: %v", err)
	}

	if !strings.Contains(output, "doctor") {
		t.Error("Doctor help should contain 'doctor'")
	}
}

func TestVerboseFlag(t *testing.T) {
	// Test that verbose flag exists
	cmd := rootCmd
	flag := cmd.PersistentFlags().Lookup("verbose")
	if flag == nil {
		t.Error("verbose flag should exist")
	}

	shorthand := flag.Shorthand
	if shorthand != "v" {
		t.Errorf("verbose shorthand should be 'v', got '%s'", shorthand)
	}
}

func TestInstallFlags(t *testing.T) {
	flags := []struct {
		name      string
		shorthand string
	}{
		{"profile", "p"},
		{"global", "g"},
		{"force", "f"},
		{"silent", ""},
		{"skills-only", ""},
		{"mcp-only", ""},
		{"mcp-path", ""},
		{"tools", ""},
	}

	for _, f := range flags {
		t.Run(f.name, func(t *testing.T) {
			flag := installCmd.Flags().Lookup(f.name)
			if flag == nil {
				t.Errorf("Flag --%s should exist", f.name)
				return
			}
			if f.shorthand != "" && flag.Shorthand != f.shorthand {
				t.Errorf("Flag --%s shorthand should be '%s', got '%s'",
					f.name, f.shorthand, flag.Shorthand)
			}
		})
	}
}

func TestLogVerbose(t *testing.T) {
	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	// Test with verbose disabled
	Verbose = false
	LogVerbose("test message")

	w.Close()
	os.Stdout = old

	var buf bytes.Buffer
	buf.ReadFrom(r)
	output := buf.String()

	if strings.Contains(output, "test message") {
		t.Error("LogVerbose should not output when verbose is disabled")
	}

	// Test with verbose enabled
	r, w, _ = os.Pipe()
	os.Stdout = w

	Verbose = true
	LogVerbose("test message")

	w.Close()
	os.Stdout = old

	buf.Reset()
	buf.ReadFrom(r)
	output = buf.String()

	if !strings.Contains(output, "test message") {
		t.Error("LogVerbose should output when verbose is enabled")
	}

	// Reset
	Verbose = false
}

func TestToolDisplayName(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"claude", "Claude"},
		{"cursor", "Cursor"},
		{"copilot", "Copilot"},
		{"codex", "Codex"},
		{"unknown", "unknown"},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := toolDisplayName(tt.input)
			if got != tt.expected {
				t.Errorf("toolDisplayName(%s) = %s, want %s", tt.input, got, tt.expected)
			}
		})
	}
}

func TestPathExists(t *testing.T) {
	// Test existing path
	if !pathExists(".") {
		t.Error("pathExists should return true for current directory")
	}

	// Test non-existing path
	if pathExists("/nonexistent/path/12345") {
		t.Error("pathExists should return false for non-existing path")
	}
}

func TestCheckForUpdates(t *testing.T) {
	// Just verify it doesn't panic
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("checkForUpdates panicked: %v", r)
		}
	}()

	checkForUpdates()
}

func TestGetLatestVersion(t *testing.T) {
	// This test may fail in CI without network access
	// Just verify it doesn't panic and handles errors gracefully
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("getLatestVersion panicked: %v", r)
		}
	}()

	version, err := getLatestVersion()
	// Don't fail on network errors, just log
	if err != nil {
		t.Logf("getLatestVersion returned error (may be expected in isolated test): %v", err)
	} else if version != "" {
		t.Logf("getLatestVersion returned: %s", version)
	}
}

func TestUninstallCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "uninstall", "--help")
	if err != nil {
		t.Fatalf("Uninstall help failed: %v", err)
	}

	expectedStrings := []string{
		"Uninstall",
		"--global",
		"--force",
		"Skills directories",
		"MCP configuration",
	}

	for _, s := range expectedStrings {
		if !strings.Contains(output, s) {
			t.Errorf("Uninstall help should contain %q", s)
		}
	}
}

func TestUninstallFlags(t *testing.T) {
	flags := []struct {
		name      string
		shorthand string
	}{
		{"global", "g"},
		{"force", "f"},
	}

	for _, f := range flags {
		t.Run(f.name, func(t *testing.T) {
			flag := uninstallCmd.Flags().Lookup(f.name)
			if flag == nil {
				t.Errorf("Flag --%s should exist", f.name)
				return
			}
			if f.shorthand != "" && flag.Shorthand != f.shorthand {
				t.Errorf("Flag --%s shorthand should be '%s', got '%s'",
					f.name, f.shorthand, flag.Shorthand)
			}
		})
	}
}

func TestRemoveDatabricksFromJSON(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
		removed  bool
	}{
		{
			name: "single entry",
			input: `{
  "mcpServers": {
    "databricks": {
      "command": "python",
      "args": ["-m", "server"]
    }
  }
}`,
			expected: `{
  "mcpServers": {
  }
}`,
			removed: true,
		},
		{
			name: "multiple entries",
			input: `{
  "mcpServers": {
    "other": {"command": "other"},
    "databricks": {
      "command": "python",
      "args": ["-m", "server"]
    }
  }
}`,
			removed: true,
		},
		{
			name:     "no databricks entry",
			input:    `{"mcpServers": {"other": {"command": "other"}}}`,
			expected: `{"mcpServers": {"other": {"command": "other"}}}`,
			removed:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, removed := removeDatabricksFromJSON(tt.input)
			if removed != tt.removed {
				t.Errorf("removed = %v, want %v", removed, tt.removed)
			}
			if removed && !strings.Contains(result, "other") && strings.Contains(tt.input, "other") {
				t.Error("Should preserve other entries")
			}
			if removed && strings.Contains(result, `"databricks"`) {
				t.Error("Should remove databricks entry")
			}
		})
	}
}

func TestRemoveDatabricksFromTOML(t *testing.T) {
	input := `[general]
setting = "value"

[mcp_servers.databricks]
command = "python"
args = ["-m", "server"]

[mcp_servers.other]
command = "other"
`
	result := removeDatabricksFromTOML(input)

	if strings.Contains(result, "[mcp_servers.databricks]") {
		t.Error("Should remove databricks section")
	}
	if !strings.Contains(result, "[mcp_servers.other]") {
		t.Error("Should preserve other sections")
	}
	if !strings.Contains(result, "[general]") {
		t.Error("Should preserve general section")
	}
}

func TestGetHomeDir(t *testing.T) {
	home := getHomeDir()
	if home == "" {
		t.Error("getHomeDir should return non-empty string")
	}
	// Should return a valid path
	if _, err := os.Stat(home); os.IsNotExist(err) {
		t.Errorf("getHomeDir returned non-existent path: %s", home)
	}
}

func TestUpdateCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "update", "--help")
	if err != nil {
		t.Fatalf("Update help failed: %v", err)
	}

	expectedStrings := []string{
		"update",
		"--check",
		"--force",
		"latest version",
	}

	for _, s := range expectedStrings {
		if !strings.Contains(output, s) {
			t.Errorf("Update help should contain %q, got: %s", s, output)
		}
	}
}

func TestUpdateFlags(t *testing.T) {
	flags := []struct {
		name      string
		shorthand string
	}{
		{"force", "f"},
		{"check", "c"},
	}

	for _, f := range flags {
		t.Run(f.name, func(t *testing.T) {
			flag := updateCmd.Flags().Lookup(f.name)
			if flag == nil {
				t.Errorf("Flag --%s should exist", f.name)
				return
			}
			if f.shorthand != "" && flag.Shorthand != f.shorthand {
				t.Errorf("Flag --%s shorthand should be '%s', got '%s'",
					f.name, f.shorthand, flag.Shorthand)
			}
		})
	}
}

func TestGetBinaryName(t *testing.T) {
	name, err := getBinaryName()
	if err != nil {
		t.Fatalf("getBinaryName failed: %v", err)
	}

	// Should contain platform info
	if name == "" {
		t.Error("getBinaryName returned empty string")
	}

	// Should contain aidevkit
	if !strings.Contains(name, "aidevkit") {
		t.Errorf("getBinaryName should contain 'aidevkit', got: %s", name)
	}
}

func TestFetchLatestVersion(t *testing.T) {
	// This test may fail in CI without network access
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("fetchLatestVersion panicked: %v", r)
		}
	}()

	version, err := fetchLatestVersion()
	if err != nil {
		t.Logf("fetchLatestVersion returned error (may be expected in isolated test): %v", err)
		return
	}

	if version == "" {
		t.Error("fetchLatestVersion returned empty version")
	}

	// Version should look like a version number (e.g., "0.0.1")
	if !strings.Contains(version, ".") {
		t.Errorf("fetchLatestVersion returned unexpected format: %s", version)
	}
}

