package installer

import (
	"os"
	"path/filepath"
	"testing"
)

func TestValidateRepoLayout(t *testing.T) {
	// Test with non-existent directory
	layout := validateRepoLayout("/nonexistent/path")
	if layout != nil {
		t.Error("validateRepoLayout should return nil for non-existent path")
	}

	// Test with empty directory
	tmpDir := t.TempDir()
	layout = validateRepoLayout(tmpDir)
	if layout != nil {
		t.Error("validateRepoLayout should return nil for empty directory")
	}

	// Create a mock repo structure
	dirs := []string{
		"ai-dev-project",
		"databricks-builder-app",
		"databricks-mcp-server",
		"databricks-tools-core",
		"databricks-skills",
	}
	for _, dir := range dirs {
		os.MkdirAll(filepath.Join(tmpDir, dir), 0755)
	}

	layout = validateRepoLayout(tmpDir)
	if layout == nil {
		t.Error("validateRepoLayout should return layout for valid repo structure")
	}

	if layout != nil {
		if layout.RootDir != tmpDir {
			t.Errorf("RootDir should be %s, got %s", tmpDir, layout.RootDir)
		}
		if layout.StarterProject != filepath.Join(tmpDir, "ai-dev-project") {
			t.Error("StarterProject path incorrect")
		}
		if layout.BuilderApp != filepath.Join(tmpDir, "databricks-builder-app") {
			t.Error("BuilderApp path incorrect")
		}
	}
}

func TestFindRepoFromPath(t *testing.T) {
	// Create a mock repo structure
	tmpDir := t.TempDir()
	dirs := []string{
		"ai-dev-project",
		"databricks-builder-app",
		"databricks-mcp-server",
		"databricks-tools-core",
		"databricks-skills",
	}
	for _, dir := range dirs {
		os.MkdirAll(filepath.Join(tmpDir, dir), 0755)
	}

	// Test from root
	layout := findRepoFromPath(tmpDir)
	if layout == nil {
		t.Error("Should find repo from root directory")
	}

	// Test from subdirectory
	subDir := filepath.Join(tmpDir, "ai-dev-project")
	layout = findRepoFromPath(subDir)
	if layout == nil {
		t.Error("Should find repo from subdirectory")
	}
	if layout != nil && layout.RootDir != tmpDir {
		t.Errorf("Should return parent as root, got %s", layout.RootDir)
	}

	// Test from non-repo directory
	layout = findRepoFromPath("/tmp")
	if layout != nil {
		t.Error("Should not find repo from unrelated directory")
	}
}

func TestRepoLayout_ValidateStarterProject(t *testing.T) {
	tmpDir := t.TempDir()
	layout := &RepoLayout{
		RootDir:        tmpDir,
		StarterProject: filepath.Join(tmpDir, "ai-dev-project"),
	}

	// Should fail without setup.sh
	os.MkdirAll(layout.StarterProject, 0755)
	err := layout.ValidateStarterProject()
	if err == nil {
		t.Error("Should fail without setup.sh")
	}

	// Create setup.sh
	setupPath := filepath.Join(layout.StarterProject, "setup.sh")
	os.WriteFile(setupPath, []byte("#!/bin/bash\n"), 0755)

	err = layout.ValidateStarterProject()
	if err != nil {
		t.Errorf("Should pass with setup.sh: %v", err)
	}
}

func TestRepoLayout_ValidateBuilderApp(t *testing.T) {
	tmpDir := t.TempDir()
	layout := &RepoLayout{
		RootDir:    tmpDir,
		BuilderApp: filepath.Join(tmpDir, "databricks-builder-app"),
	}

	// Should fail without required files
	os.MkdirAll(layout.BuilderApp, 0755)
	err := layout.ValidateBuilderApp()
	if err == nil {
		t.Error("Should fail without required files")
	}

	// Create required files
	requiredFiles := []string{
		"scripts/start_dev.sh",
		"scripts/deploy.sh",
		"server/app.py",
		"client/package.json",
	}
	for _, file := range requiredFiles {
		path := filepath.Join(layout.BuilderApp, file)
		os.MkdirAll(filepath.Dir(path), 0755)
		os.WriteFile(path, []byte(""), 0644)
	}

	err = layout.ValidateBuilderApp()
	if err != nil {
		t.Errorf("Should pass with all required files: %v", err)
	}
}

func TestCopyDirectory(t *testing.T) {
	// Create source directory with files
	srcDir := t.TempDir()
	os.WriteFile(filepath.Join(srcDir, "file1.txt"), []byte("content1"), 0644)
	os.MkdirAll(filepath.Join(srcDir, "subdir"), 0755)
	os.WriteFile(filepath.Join(srcDir, "subdir", "file2.txt"), []byte("content2"), 0644)

	// Create destination
	dstDir := filepath.Join(t.TempDir(), "dest")

	// Copy
	err := CopyDirectory(srcDir, dstDir)
	if err != nil {
		t.Fatalf("CopyDirectory failed: %v", err)
	}

	// Verify files
	content1, err := os.ReadFile(filepath.Join(dstDir, "file1.txt"))
	if err != nil || string(content1) != "content1" {
		t.Error("file1.txt not copied correctly")
	}

	content2, err := os.ReadFile(filepath.Join(dstDir, "subdir", "file2.txt"))
	if err != nil || string(content2) != "content2" {
		t.Error("subdir/file2.txt not copied correctly")
	}
}

func TestCopyDirectory_SkipsNodeModules(t *testing.T) {
	srcDir := t.TempDir()

	// Create node_modules directory (should be skipped)
	os.MkdirAll(filepath.Join(srcDir, "node_modules", "package"), 0755)
	os.WriteFile(filepath.Join(srcDir, "node_modules", "package", "index.js"), []byte(""), 0644)

	// Create regular file
	os.WriteFile(filepath.Join(srcDir, "index.js"), []byte("main"), 0644)

	dstDir := filepath.Join(t.TempDir(), "dest")

	err := CopyDirectory(srcDir, dstDir)
	if err != nil {
		t.Fatalf("CopyDirectory failed: %v", err)
	}

	// node_modules should not exist
	if _, err := os.Stat(filepath.Join(dstDir, "node_modules")); !os.IsNotExist(err) {
		t.Error("node_modules should be skipped")
	}

	// Regular file should exist
	if _, err := os.Stat(filepath.Join(dstDir, "index.js")); os.IsNotExist(err) {
		t.Error("index.js should be copied")
	}
}

func TestMakeExecutable(t *testing.T) {
	tmpDir := t.TempDir()
	filePath := filepath.Join(tmpDir, "script.sh")

	// Create file without execute permission
	os.WriteFile(filePath, []byte("#!/bin/bash\n"), 0644)

	err := MakeExecutable(filePath)
	if err != nil {
		t.Fatalf("MakeExecutable failed: %v", err)
	}

	info, _ := os.Stat(filePath)
	mode := info.Mode()
	if mode&0100 == 0 {
		t.Error("File should have owner execute permission")
	}
}

