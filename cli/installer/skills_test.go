package installer

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestGetSkillsDirectories(t *testing.T) {
	cfg := NewConfig()
	cfg.BaseDir = "/test/project"

	tests := []struct {
		name     string
		tools    []string
		expected int
	}{
		{
			name:     "Single tool - claude",
			tools:    []string{"claude"},
			expected: 1,
		},
		{
			name:     "Single tool - cursor",
			tools:    []string{"cursor"},
			expected: 1,
		},
		{
			name:     "Claude and cursor - cursor shares with claude",
			tools:    []string{"claude", "cursor"},
			expected: 1, // cursor shares with claude
		},
		{
			name:     "All tools",
			tools:    []string{"claude", "cursor", "copilot", "codex"},
			expected: 3, // claude, copilot, codex (cursor shares with claude)
		},
		{
			name:     "Copilot and codex",
			tools:    []string{"copilot", "codex"},
			expected: 2,
		},
		{
			name:     "Empty tools",
			tools:    []string{},
			expected: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg.Tools = tt.tools
			dirs := getSkillsDirectories(cfg)
			if len(dirs) != tt.expected {
				t.Errorf("getSkillsDirectories() returned %d dirs, want %d", len(dirs), tt.expected)
			}
		})
	}
}

func TestContainsTool(t *testing.T) {
	tools := []string{"claude", "cursor", "copilot"}

	tests := []struct {
		tool     string
		expected bool
	}{
		{"claude", true},
		{"cursor", true},
		{"copilot", true},
		{"codex", false},
		{"unknown", false},
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.tool, func(t *testing.T) {
			got := containsTool(tools, tt.tool)
			if got != tt.expected {
				t.Errorf("containsTool(%q) = %v, want %v", tt.tool, got, tt.expected)
			}
		})
	}
}

func TestCopyDir(t *testing.T) {
	srcDir := t.TempDir()
	dstDir := filepath.Join(t.TempDir(), "dest")

	// Create source structure
	subDir := filepath.Join(srcDir, "subdir")
	os.MkdirAll(subDir, 0755)

	// Create files
	os.WriteFile(filepath.Join(srcDir, "file1.txt"), []byte("content1"), 0644)
	os.WriteFile(filepath.Join(subDir, "file2.txt"), []byte("content2"), 0644)

	// Copy
	err := copyDir(srcDir, dstDir)
	if err != nil {
		t.Fatalf("copyDir failed: %v", err)
	}

	// Verify
	if _, err := os.Stat(filepath.Join(dstDir, "file1.txt")); os.IsNotExist(err) {
		t.Error("file1.txt should exist in destination")
	}

	if _, err := os.Stat(filepath.Join(dstDir, "subdir", "file2.txt")); os.IsNotExist(err) {
		t.Error("subdir/file2.txt should exist in destination")
	}

	// Verify content
	content, _ := os.ReadFile(filepath.Join(dstDir, "file1.txt"))
	if string(content) != "content1" {
		t.Errorf("file1.txt content mismatch: got %s", content)
	}
}

func TestDownloadFile(t *testing.T) {
	// Create a test HTTP server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/success" {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("test content"))
		} else if r.URL.Path == "/notfound" {
			w.WriteHeader(http.StatusNotFound)
		} else {
			w.WriteHeader(http.StatusInternalServerError)
		}
	}))
	defer server.Close()

	tmpDir := t.TempDir()

	// Test successful download
	destPath := filepath.Join(tmpDir, "downloaded.txt")
	err := downloadFile(server.URL+"/success", destPath)
	if err != nil {
		t.Errorf("downloadFile should succeed: %v", err)
	}

	content, _ := os.ReadFile(destPath)
	if string(content) != "test content" {
		t.Errorf("Downloaded content mismatch: got %s", content)
	}

	// Test 404
	err = downloadFile(server.URL+"/notfound", filepath.Join(tmpDir, "notfound.txt"))
	if err == nil {
		t.Error("downloadFile should fail for 404")
	}

	// Test server error
	err = downloadFile(server.URL+"/error", filepath.Join(tmpDir, "error.txt"))
	if err == nil {
		t.Error("downloadFile should fail for server error")
	}
}

func TestDownloadFile_AtomicWrite(t *testing.T) {
	// Create a test HTTP server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("test content"))
	}))
	defer server.Close()

	tmpDir := t.TempDir()
	destPath := filepath.Join(tmpDir, "atomic.txt")

	err := downloadFile(server.URL+"/", destPath)
	if err != nil {
		t.Fatalf("downloadFile failed: %v", err)
	}

	// Verify temp file is not left behind
	tempPath := destPath + ".tmp"
	if _, err := os.Stat(tempPath); !os.IsNotExist(err) {
		t.Error("Temp file should not exist after successful download")
	}

	// Verify final file exists
	if _, err := os.Stat(destPath); os.IsNotExist(err) {
		t.Error("Final file should exist")
	}
}

func TestInstallDatabricksSkills(t *testing.T) {
	cfg := NewConfig()
	cfg.InstallDir = t.TempDir()
	cfg.updatePaths()

	// Create mock repo with skills
	skillsDir := filepath.Join(cfg.RepoDir, "databricks-skills")
	os.MkdirAll(skillsDir, 0755)

	// Create a test skill
	testSkillDir := filepath.Join(skillsDir, "databricks-docs")
	os.MkdirAll(testSkillDir, 0755)
	os.WriteFile(filepath.Join(testSkillDir, "SKILL.md"), []byte("# Test Skill"), 0644)

	// Create target directory
	targetDir := t.TempDir()

	// Install skills
	err := installDatabricksSkills(cfg, targetDir)
	if err != nil {
		t.Fatalf("installDatabricksSkills failed: %v", err)
	}

	// Verify skill was copied
	copiedSkill := filepath.Join(targetDir, "databricks-docs", "SKILL.md")
	if _, err := os.Stat(copiedSkill); os.IsNotExist(err) {
		t.Error("Skill should be copied to target directory")
	}
}

func TestInstallDatabricksSkills_MissingSource(t *testing.T) {
	cfg := NewConfig()
	cfg.InstallDir = t.TempDir()
	cfg.updatePaths()

	// Don't create the skills source directory
	targetDir := t.TempDir()

	// Should not error, just skip missing skills
	err := installDatabricksSkills(cfg, targetDir)
	if err != nil {
		t.Errorf("Should not error for missing source: %v", err)
	}
}

func TestSkillsDirectoryDescription(t *testing.T) {
	tests := []struct {
		name     string
		tools    []string
		expected string
	}{
		{
			name:     "Claude only",
			tools:    []string{"claude"},
			expected: ".claude/skills",
		},
		{
			name:     "Cursor only",
			tools:    []string{"cursor"},
			expected: ".cursor/skills",
		},
		{
			name:     "Claude and Cursor",
			tools:    []string{"claude", "cursor"},
			expected: ".claude/skills", // cursor shares with claude
		},
		{
			name:     "Copilot",
			tools:    []string{"copilot"},
			expected: ".github/skills",
		},
		{
			name:     "Codex",
			tools:    []string{"codex"},
			expected: ".agents/skills",
		},
		{
			name:     "Empty",
			tools:    []string{},
			expected: "none",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := SkillsDirectoryDescription(tt.tools, "/base")
			if got != tt.expected {
				t.Errorf("SkillsDirectoryDescription(%v) = %s, want %s", tt.tools, got, tt.expected)
			}
		})
	}
}

func TestDatabricksSkillsList(t *testing.T) {
	// Verify the skills list is populated
	if len(DatabricksSkills) == 0 {
		t.Error("DatabricksSkills should not be empty")
	}

	// Check for some expected skills
	expectedSkills := []string{
		"databricks-docs",
		"databricks-unity-catalog",
		"asset-bundles",
	}

	for _, expected := range expectedSkills {
		found := false
		for _, skill := range DatabricksSkills {
			if skill == expected {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("Expected skill %s not found in DatabricksSkills", expected)
		}
	}
}

func TestMLflowSkillsList(t *testing.T) {
	// Verify the skills list is populated
	if len(MLflowSkills) == 0 {
		t.Error("MLflowSkills should not be empty")
	}

	// Check for some expected skills
	expectedSkills := []string{
		"mlflow-onboarding",
		"agent-evaluation",
	}

	for _, expected := range expectedSkills {
		found := false
		for _, skill := range MLflowSkills {
			if skill == expected {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("Expected skill %s not found in MLflowSkills", expected)
		}
	}
}

func TestInstallSkills(t *testing.T) {
	cfg := NewConfig()
	cfg.InstallDir = t.TempDir()
	cfg.BaseDir = t.TempDir()
	cfg.Tools = []string{"claude"}
	cfg.updatePaths()

	// Create mock repo with skills
	skillsDir := filepath.Join(cfg.RepoDir, "databricks-skills")
	os.MkdirAll(skillsDir, 0755)

	// Create a minimal test skill
	testSkillDir := filepath.Join(skillsDir, "databricks-docs")
	os.MkdirAll(testSkillDir, 0755)
	os.WriteFile(filepath.Join(testSkillDir, "SKILL.md"), []byte("# Test"), 0644)

	// This will try to install and may fail on MLflow (network), but should not panic
	err := InstallSkills(cfg)
	// We don't check for error since MLflow download may fail in test env
	_ = err

	// Verify local skills were installed
	localSkillPath := filepath.Join(cfg.GetSkillsDir("claude"), "databricks-docs", "SKILL.md")
	if _, err := os.Stat(localSkillPath); os.IsNotExist(err) {
		t.Error("Local skill should be installed")
	}
}

func TestHttpClientTimeout(t *testing.T) {
	// Verify httpClient has a timeout set
	if httpClient.Timeout == 0 {
		t.Error("httpClient should have a timeout set")
	}

	// Should be 30 seconds
	if httpClient.Timeout.Seconds() != 30 {
		t.Errorf("httpClient timeout should be 30s, got %v", httpClient.Timeout)
	}
}

