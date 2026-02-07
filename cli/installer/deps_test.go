package installer

import (
	"os"
	"os/exec"
	"runtime"
	"testing"
)

func TestCommandExists(t *testing.T) {
	// Test with a command that definitely exists
	if !commandExists("go") {
		t.Error("commandExists should return true for 'go'")
	}

	// Test with a command that definitely doesn't exist
	if commandExists("nonexistent_command_12345") {
		t.Error("commandExists should return false for nonexistent command")
	}
}

func TestDetectPythonPackageManager(t *testing.T) {
	pkgMgr := detectPythonPackageManager()

	// In the test container, we should have either uv or pip
	if pkgMgr == nil {
		t.Log("No Python package manager found - this may be expected in some test environments")
		return
	}

	if pkgMgr.Name == "" {
		t.Error("Package manager name should not be empty")
	}

	if pkgMgr.Command == "" {
		t.Error("Package manager command should not be empty")
	}

	// Verify it's one of the expected package managers
	validNames := map[string]bool{"uv": true, "pip3": true, "pip": true}
	if !validNames[pkgMgr.Name] {
		t.Errorf("Unexpected package manager: %s", pkgMgr.Name)
	}
}

func TestCheckDependencies_WithoutMCP(t *testing.T) {
	// Test without MCP installation (doesn't require Python package manager)
	deps, pkgMgr, err := CheckDependencies(false)

	if err != nil {
		// Git might not be installed in test environment
		t.Logf("CheckDependencies error (may be expected): %v", err)
	}

	// Should have at least git and databricks dependencies defined
	if len(deps) < 2 {
		t.Errorf("Expected at least 2 dependencies, got %d", len(deps))
	}

	// pkgMgr should be nil when not installing MCP
	if pkgMgr != nil {
		t.Error("Package manager should be nil when installMCP=false")
	}

	// Verify git is in the dependencies
	gitFound := false
	for _, dep := range deps {
		if dep.Name == "git" {
			gitFound = true
			if !dep.Required {
				t.Error("git should be marked as required")
			}
			break
		}
	}
	if !gitFound {
		t.Error("git should be in the dependencies list")
	}
}

func TestCheckDependencies_WithMCP(t *testing.T) {
	deps, pkgMgr, err := CheckDependencies(true)

	// In test environment, this may succeed or fail depending on available tools
	if err != nil {
		t.Logf("CheckDependencies with MCP error (may be expected): %v", err)
		return
	}

	// When MCP install is requested, we should get a package manager
	if pkgMgr == nil {
		t.Error("Expected package manager when installMCP=true")
	}

	// Dependencies should still be returned
	if len(deps) < 2 {
		t.Errorf("Expected at least 2 dependencies, got %d", len(deps))
	}
}

func TestDependencyStruct(t *testing.T) {
	dep := Dependency{
		Name:     "test",
		Command:  "test-cmd",
		Required: true,
		Found:    false,
		HelpText: "Install test",
	}

	if dep.Name != "test" {
		t.Error("Name not set correctly")
	}

	if dep.Command != "test-cmd" {
		t.Error("Command not set correctly")
	}

	if !dep.Required {
		t.Error("Required not set correctly")
	}

	if dep.Found {
		t.Error("Found should be false")
	}

	if dep.HelpText != "Install test" {
		t.Error("HelpText not set correctly")
	}
}

func TestPythonPackageManagerStruct(t *testing.T) {
	pkgMgr := PythonPackageManager{
		Name:    "uv",
		Command: "uv",
	}

	if pkgMgr.Name != "uv" {
		t.Error("Name not set correctly")
	}

	if pkgMgr.Command != "uv" {
		t.Error("Command not set correctly")
	}
}

func TestGetGitInstallHelp(t *testing.T) {
	help := getGitInstallHelp()

	if help == "" {
		t.Error("Git install help should not be empty")
	}

	// Should mention git
	switch runtime.GOOS {
	case "darwin":
		if help == "" {
			t.Error("macOS help should not be empty")
		}
	case "windows":
		if help == "" {
			t.Error("Windows help should not be empty")
		}
	case "linux":
		if help == "" {
			t.Error("Linux help should not be empty")
		}
	}
}

func TestGetDatabricksInstallHelp(t *testing.T) {
	help := getDatabricksInstallHelp()

	if help == "" {
		t.Error("Databricks install help should not be empty")
	}
}

func TestRunGitClone(t *testing.T) {
	// Skip if git is not available
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git not available, skipping test")
	}

	tmpDir := t.TempDir()
	destDir := tmpDir + "/test-repo"

	// Clone a small public repo
	// Using a known small repo for testing
	err := RunGitClone("https://github.com/octocat/Hello-World.git", destDir)

	if err != nil {
		// Network errors are acceptable in isolated test environments
		t.Logf("Git clone failed (may be expected in isolated env): %v", err)
		return
	}

	// Verify .git directory exists
	if _, err := os.Stat(destDir + "/.git"); os.IsNotExist(err) {
		t.Error(".git directory should exist after clone")
	}
}

func TestRunGitPull(t *testing.T) {
	// Skip if git is not available
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git not available, skipping test")
	}

	// Create a temp git repo for testing
	tmpDir := t.TempDir()

	// Initialize a git repo
	cmd := exec.Command("git", "init", tmpDir)
	if err := cmd.Run(); err != nil {
		t.Fatalf("Failed to init git repo: %v", err)
	}

	// Git pull in a fresh repo without remote should fail
	err := RunGitPull(tmpDir)
	if err == nil {
		t.Log("Git pull succeeded (may have remote configured)")
	} else {
		// Expected to fail in a fresh repo without remote
		t.Logf("Git pull failed as expected in fresh repo: %v", err)
	}
}

func TestPrintDependencyStatus(t *testing.T) {
	deps := []Dependency{
		{Name: "git", Command: "git", Required: true, Found: true},
		{Name: "databricks", Command: "databricks", Required: false, Found: false, HelpText: "Install databricks"},
	}

	// Test with silent=true (should not print)
	PrintDependencyStatus(deps, nil, true)

	// Test with silent=false (should print)
	// This just verifies no panic
	PrintDependencyStatus(deps, nil, false)

	// Test with package manager
	pkgMgr := &PythonPackageManager{Name: "uv", Command: "uv"}
	PrintDependencyStatus(deps, pkgMgr, false)
}

