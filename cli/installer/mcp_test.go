package installer

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestMCPConfigJSON(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = t.TempDir()
	cfg.Scope = "project"
	cfg.Profile = "test-profile"
	cfg.VenvPython = "/path/to/python"
	cfg.McpEntry = "/path/to/mcp/entry.py"
	cfg.Tools = []string{"claude"}

	// Write MCP config
	err := WriteMCPConfigs(cfg)
	if err != nil {
		t.Fatalf("WriteMCPConfigs failed: %v", err)
	}

	// Read and verify
	configPath := cfg.GetMCPConfigPath("claude")
	data, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatalf("Failed to read config: %v", err)
	}

	var config MCPConfig
	if err := json.Unmarshal(data, &config); err != nil {
		t.Fatalf("Failed to parse config: %v", err)
	}

	// Verify databricks server config
	dbServer, ok := config.MCPServers["databricks"]
	if !ok {
		t.Fatal("databricks server not found in config")
	}

	if dbServer.Command != "/path/to/python" {
		t.Errorf("Unexpected command: %s", dbServer.Command)
	}

	if len(dbServer.Args) != 1 || dbServer.Args[0] != "/path/to/mcp/entry.py" {
		t.Errorf("Unexpected args: %v", dbServer.Args)
	}

	if dbServer.Env["DATABRICKS_CONFIG_PROFILE"] != "test-profile" {
		t.Errorf("Unexpected profile: %s", dbServer.Env["DATABRICKS_CONFIG_PROFILE"])
	}
}

func TestMCPConfigPreservesExisting(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = t.TempDir()
	cfg.Scope = "project"
	cfg.Profile = "test-profile"
	cfg.VenvPython = "/path/to/python"
	cfg.McpEntry = "/path/to/mcp/entry.py"
	cfg.Tools = []string{"claude"}

	configPath := cfg.GetMCPConfigPath("claude")

	// Create existing config with another server
	existingConfig := MCPConfig{
		MCPServers: map[string]MCPServerConfig{
			"other-server": {
				Command: "/other/command",
				Args:    []string{"--arg"},
			},
		},
	}
	if err := os.MkdirAll(filepath.Dir(configPath), 0755); err != nil {
		t.Fatalf("Failed to create dir: %v", err)
	}
	data, _ := json.MarshalIndent(existingConfig, "", "  ")
	if err := os.WriteFile(configPath, data, 0644); err != nil {
		t.Fatalf("Failed to write existing config: %v", err)
	}

	// Write MCP config (should merge)
	err := WriteMCPConfigs(cfg)
	if err != nil {
		t.Fatalf("WriteMCPConfigs failed: %v", err)
	}

	// Read and verify both servers exist
	data, _ = os.ReadFile(configPath)
	var config MCPConfig
	json.Unmarshal(data, &config)

	if _, ok := config.MCPServers["other-server"]; !ok {
		t.Error("Existing server was not preserved")
	}

	if _, ok := config.MCPServers["databricks"]; !ok {
		t.Error("Databricks server was not added")
	}
}

func TestMCPConfigBackup(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = t.TempDir()
	cfg.Scope = "project"
	cfg.Profile = "test-profile"
	cfg.VenvPython = "/path/to/python"
	cfg.McpEntry = "/path/to/mcp/entry.py"
	cfg.Tools = []string{"claude"}

	configPath := cfg.GetMCPConfigPath("claude")

	// Create existing config
	if err := os.MkdirAll(filepath.Dir(configPath), 0755); err != nil {
		t.Fatalf("Failed to create dir: %v", err)
	}
	originalContent := `{"mcpServers": {"original": {}}}`
	if err := os.WriteFile(configPath, []byte(originalContent), 0644); err != nil {
		t.Fatalf("Failed to write existing config: %v", err)
	}

	// Write MCP config (should create backup)
	err := WriteMCPConfigs(cfg)
	if err != nil {
		t.Fatalf("WriteMCPConfigs failed: %v", err)
	}

	// Check backup exists
	backupPath := configPath + ".bak"
	if _, err := os.Stat(backupPath); os.IsNotExist(err) {
		t.Error("Backup file was not created")
	}
}

func TestCopilotMCPConfig(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = t.TempDir()
	cfg.Scope = "project"
	cfg.Profile = "test-profile"
	cfg.VenvPython = "/path/to/python"
	cfg.McpEntry = "/path/to/mcp/entry.py"
	cfg.Tools = []string{"copilot"}

	// Write MCP config
	err := WriteMCPConfigs(cfg)
	if err != nil {
		t.Fatalf("WriteMCPConfigs failed: %v", err)
	}

	// Read and verify (Copilot uses different format)
	configPath := cfg.GetMCPConfigPath("copilot")
	data, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatalf("Failed to read config: %v", err)
	}

	var config CopilotMCPConfig
	if err := json.Unmarshal(data, &config); err != nil {
		t.Fatalf("Failed to parse config: %v", err)
	}

	// Verify databricks server config (uses "servers" key, not "mcpServers")
	if _, ok := config.Servers["databricks"]; !ok {
		t.Fatal("databricks server not found in Copilot config")
	}
}

func TestCodexMCPConfig(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = t.TempDir()
	cfg.Scope = "project"
	cfg.Profile = "test-profile"
	cfg.VenvPython = "/path/to/python"
	cfg.McpEntry = "/path/to/mcp/entry.py"
	cfg.Tools = []string{"codex"}

	// Write MCP config
	err := WriteMCPConfigs(cfg)
	if err != nil {
		t.Fatalf("WriteMCPConfigs failed: %v", err)
	}

	// Read and verify TOML format
	configPath := cfg.GetMCPConfigPath("codex")
	data, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatalf("Failed to read config: %v", err)
	}

	content := string(data)
	if !strings.Contains(content, "[mcp_servers.databricks]") {
		t.Error("TOML config should contain [mcp_servers.databricks] section")
	}

	if !strings.Contains(content, "command = ") {
		t.Error("TOML config should contain command")
	}
}

func TestToForwardSlash(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"/unix/path", "/unix/path"},
		{"relative/path", "relative/path"},
		{"", ""},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := toForwardSlash(tt.input)
			// On non-Windows, should return unchanged
			if got != tt.expected {
				t.Errorf("toForwardSlash(%s) = %s, want %s", tt.input, got, tt.expected)
			}
		})
	}
}

func TestPathExists(t *testing.T) {
	tmpDir := t.TempDir()

	// Test existing path
	if !pathExists(tmpDir) {
		t.Error("pathExists should return true for existing directory")
	}

	// Test existing file
	tmpFile := filepath.Join(tmpDir, "test.txt")
	os.WriteFile(tmpFile, []byte("test"), 0644)
	if !pathExists(tmpFile) {
		t.Error("pathExists should return true for existing file")
	}

	// Test non-existing path
	if pathExists(filepath.Join(tmpDir, "nonexistent")) {
		t.Error("pathExists should return false for non-existing path")
	}
}

func TestCopyFile(t *testing.T) {
	tmpDir := t.TempDir()

	src := filepath.Join(tmpDir, "source.txt")
	dst := filepath.Join(tmpDir, "dest.txt")
	content := "test content"

	// Create source file
	if err := os.WriteFile(src, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to create source file: %v", err)
	}

	// Copy file
	if err := copyFile(src, dst); err != nil {
		t.Fatalf("copyFile failed: %v", err)
	}

	// Verify content
	data, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("Failed to read destination: %v", err)
	}

	if string(data) != content {
		t.Errorf("Content mismatch: got %s, want %s", string(data), content)
	}
}

