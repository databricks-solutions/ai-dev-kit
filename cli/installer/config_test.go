package installer

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestNewConfig(t *testing.T) {
	cfg := NewConfig()

	if cfg == nil {
		t.Fatal("NewConfig() returned nil")
	}

	// Check defaults
	if cfg.Profile != "DEFAULT" {
		t.Errorf("Expected Profile=DEFAULT, got %s", cfg.Profile)
	}

	if cfg.Scope != "project" {
		t.Errorf("Expected Scope=project, got %s", cfg.Scope)
	}

	if !cfg.InstallMCP {
		t.Error("Expected InstallMCP=true")
	}

	if !cfg.InstallSkills {
		t.Error("Expected InstallSkills=true")
	}

	if cfg.Force {
		t.Error("Expected Force=false")
	}

	if cfg.Silent {
		t.Error("Expected Silent=false")
	}

	// Check that paths are set
	if cfg.InstallDir == "" {
		t.Error("InstallDir should not be empty")
	}

	if cfg.RepoDir == "" {
		t.Error("RepoDir should not be empty")
	}

	if cfg.VenvDir == "" {
		t.Error("VenvDir should not be empty")
	}

	if cfg.VenvPython == "" {
		t.Error("VenvPython should not be empty")
	}
}

func TestSetInstallDir(t *testing.T) {
	cfg := NewConfig()

	// Test absolute path
	cfg.SetInstallDir("/custom/path")
	if cfg.InstallDir != "/custom/path" {
		t.Errorf("Expected /custom/path, got %s", cfg.InstallDir)
	}

	// Check derived paths are updated
	if !strings.HasPrefix(cfg.RepoDir, "/custom/path") {
		t.Errorf("RepoDir should start with /custom/path, got %s", cfg.RepoDir)
	}

	// Test tilde expansion
	cfg.SetInstallDir("~/test-dir")
	if strings.HasPrefix(cfg.InstallDir, "~") {
		t.Error("Tilde should be expanded")
	}
}

func TestSetScope(t *testing.T) {
	cfg := NewConfig()

	// Test project scope
	cfg.SetScope("project")
	if cfg.Scope != "project" {
		t.Errorf("Expected Scope=project, got %s", cfg.Scope)
	}

	// Test global scope
	cfg.SetScope("global")
	if cfg.Scope != "global" {
		t.Errorf("Expected Scope=global, got %s", cfg.Scope)
	}

	// BaseDir should be home dir for global
	homeDir := getHomeDir()
	if cfg.BaseDir != homeDir {
		t.Errorf("Expected BaseDir=%s for global scope, got %s", homeDir, cfg.BaseDir)
	}
}

func TestUpdatePaths(t *testing.T) {
	cfg := NewConfig()
	cfg.InstallDir = "/test/install"
	cfg.updatePaths()

	expectedRepoDir := filepath.Join("/test/install", "repo")
	if cfg.RepoDir != expectedRepoDir {
		t.Errorf("Expected RepoDir=%s, got %s", expectedRepoDir, cfg.RepoDir)
	}

	expectedVenvDir := filepath.Join("/test/install", ".venv")
	if cfg.VenvDir != expectedVenvDir {
		t.Errorf("Expected VenvDir=%s, got %s", expectedVenvDir, cfg.VenvDir)
	}

	// Check platform-specific Python path
	if runtime.GOOS == "windows" {
		if !strings.HasSuffix(cfg.VenvPython, "Scripts\\python.exe") &&
			!strings.HasSuffix(cfg.VenvPython, "Scripts/python.exe") {
			t.Errorf("Windows VenvPython should end with Scripts/python.exe, got %s", cfg.VenvPython)
		}
	} else {
		if !strings.HasSuffix(cfg.VenvPython, "bin/python") {
			t.Errorf("Unix VenvPython should end with bin/python, got %s", cfg.VenvPython)
		}
	}
}

func TestGetSkillsDir(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = "/project"

	tests := []struct {
		tool     string
		expected string
	}{
		{"claude", filepath.Join("/project", ".claude", "skills")},
		{"cursor", filepath.Join("/project", ".cursor", "skills")},
		{"copilot", filepath.Join("/project", ".github", "skills")},
		{"codex", filepath.Join("/project", ".agents", "skills")},
		{"unknown", ""},
	}

	for _, tt := range tests {
		t.Run(tt.tool, func(t *testing.T) {
			got := cfg.GetSkillsDir(tt.tool)
			if got != tt.expected {
				t.Errorf("GetSkillsDir(%s) = %s, want %s", tt.tool, got, tt.expected)
			}
		})
	}
}

func TestGetMCPConfigPath(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = "/project"
	cfg.Scope = "project"

	// Test project scope
	tests := []struct {
		tool     string
		expected string
	}{
		{"claude", filepath.Join("/project", ".mcp.json")},
		{"cursor", filepath.Join("/project", ".cursor", "mcp.json")},
		{"copilot", filepath.Join("/project", ".vscode", "mcp.json")},
		{"codex", filepath.Join("/project", ".codex", "config.toml")},
		{"unknown", ""},
	}

	for _, tt := range tests {
		t.Run(tt.tool+"_project", func(t *testing.T) {
			got := cfg.GetMCPConfigPath(tt.tool)
			if got != tt.expected {
				t.Errorf("GetMCPConfigPath(%s) = %s, want %s", tt.tool, got, tt.expected)
			}
		})
	}

	// Test global scope - some tools return empty
	cfg.Scope = "global"
	if got := cfg.GetMCPConfigPath("cursor"); got != "" {
		t.Errorf("Cursor global should return empty, got %s", got)
	}
	if got := cfg.GetMCPConfigPath("copilot"); got != "" {
		t.Errorf("Copilot global should return empty, got %s", got)
	}
}

func TestDisplayPath(t *testing.T) {
	homeDir := getHomeDir()

	tests := []struct {
		input    string
		expected string
	}{
		{filepath.Join(homeDir, "test", "path"), "~/test/path"},
		{"/other/path", "/other/path"},
		// Note: homeDir exactly returns unchanged because the logic checks len(path) > len(homeDir)
		{homeDir, homeDir},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := DisplayPath(tt.input)
			if got != tt.expected {
				t.Errorf("DisplayPath(%s) = %s, want %s", tt.input, got, tt.expected)
			}
		})
	}
}

func TestVersionFile(t *testing.T) {
	cfg := NewConfig()
	cfg.InstallDir = "/test/install"

	expected := filepath.Join("/test/install", "version")
	got := cfg.VersionFile()
	if got != expected {
		t.Errorf("VersionFile() = %s, want %s", got, expected)
	}
}

func TestProjectVersionFile(t *testing.T) {
	cfg := NewConfig()

	expected := filepath.Join(".ai-dev-kit", "version")
	got := cfg.ProjectVersionFile()
	if got != expected {
		t.Errorf("ProjectVersionFile() = %s, want %s", got, expected)
	}
}

func TestGetHomeDir(t *testing.T) {
	homeDir := getHomeDir()

	if homeDir == "" {
		t.Error("getHomeDir() should not return empty string")
	}

	if homeDir == "/tmp" {
		// This is the fallback, which means HOME is not set
		t.Log("Warning: getHomeDir() returned fallback /tmp")
	}
}

func TestGetInstallDir(t *testing.T) {
	// Test with AIDEVKIT_HOME set
	original := os.Getenv("AIDEVKIT_HOME")
	defer os.Setenv("AIDEVKIT_HOME", original)

	os.Setenv("AIDEVKIT_HOME", "/custom/aidevkit")
	got := getInstallDir("/home/user")
	if got != "/custom/aidevkit" {
		t.Errorf("Expected /custom/aidevkit when AIDEVKIT_HOME set, got %s", got)
	}

	// Test without AIDEVKIT_HOME
	os.Unsetenv("AIDEVKIT_HOME")
	got = getInstallDir("/home/user")
	expected := filepath.Join("/home/user", DefaultDir)
	if got != expected {
		t.Errorf("Expected %s, got %s", expected, got)
	}
}

