package installer

import (
	"fmt"
	"os"
	"path/filepath"
)

// RepoLayout defines the expected structure of the ai-dev-kit repository
type RepoLayout struct {
	RootDir          string
	StarterProject   string
	BuilderApp       string
	MCPServer        string
	ToolsCore        string
	Skills           string
}

// FindRepository locates the ai-dev-kit repository
// It checks multiple locations in order:
// 1. If running from within the repo (check for key files)
// 2. The global install directory (~/.ai-dev-kit)
// 3. Environment variable AI_DEV_KIT_PATH
func FindRepository() (*RepoLayout, error) {
	// Check environment variable first
	if envPath := os.Getenv("AI_DEV_KIT_PATH"); envPath != "" {
		if layout := validateRepoLayout(envPath); layout != nil {
			return layout, nil
		}
	}

	// Check if we're running from within the repo
	// Try to find repo root by looking for key markers
	cwd, err := os.Getwd()
	if err == nil {
		if layout := findRepoFromPath(cwd); layout != nil {
			return layout, nil
		}
	}

	// Check global install directory
	homeDir := getHomeDir()
	globalInstall := filepath.Join(homeDir, ".ai-dev-kit")
	if layout := validateRepoLayout(globalInstall); layout != nil {
		return layout, nil
	}

	// Check if repo is cloned in global install
	repoClone := filepath.Join(globalInstall, "repo")
	if layout := validateRepoLayout(repoClone); layout != nil {
		return layout, nil
	}

	return nil, fmt.Errorf("ai-dev-kit repository not found. Set AI_DEV_KIT_PATH or run from within the repository")
}

// findRepoFromPath walks up the directory tree to find the repo root
func findRepoFromPath(startPath string) *RepoLayout {
	path := startPath
	for {
		if layout := validateRepoLayout(path); layout != nil {
			return layout
		}

		parent := filepath.Dir(path)
		if parent == path {
			// Reached root
			break
		}
		path = parent
	}
	return nil
}

// validateRepoLayout checks if a directory contains the ai-dev-kit repository
func validateRepoLayout(rootDir string) *RepoLayout {
	// Check for key directories/files that indicate this is the repo
	markers := []string{
		"ai-dev-project",
		"databricks-builder-app",
		"databricks-mcp-server",
		"databricks-tools-core",
		"databricks-skills",
	}

	for _, marker := range markers {
		path := filepath.Join(rootDir, marker)
		if _, err := os.Stat(path); os.IsNotExist(err) {
			return nil
		}
	}

	return &RepoLayout{
		RootDir:        rootDir,
		StarterProject: filepath.Join(rootDir, "ai-dev-project"),
		BuilderApp:     filepath.Join(rootDir, "databricks-builder-app"),
		MCPServer:      filepath.Join(rootDir, "databricks-mcp-server"),
		ToolsCore:      filepath.Join(rootDir, "databricks-tools-core"),
		Skills:         filepath.Join(rootDir, "databricks-skills"),
	}
}

// ValidateStarterProject checks if the starter project is valid
func (r *RepoLayout) ValidateStarterProject() error {
	setupScript := filepath.Join(r.StarterProject, "setup.sh")
	if _, err := os.Stat(setupScript); os.IsNotExist(err) {
		return fmt.Errorf("setup.sh not found in %s", r.StarterProject)
	}
	return nil
}

// ValidateBuilderApp checks if the builder app is valid
func (r *RepoLayout) ValidateBuilderApp() error {
	// Check for key files
	requiredFiles := []string{
		"scripts/start_dev.sh",
		"scripts/deploy.sh",
		"server/app.py",
		"client/package.json",
	}

	for _, file := range requiredFiles {
		path := filepath.Join(r.BuilderApp, file)
		if _, err := os.Stat(path); os.IsNotExist(err) {
			return fmt.Errorf("%s not found in builder app", file)
		}
	}
	return nil
}

// CopyDirectory copies a directory recursively
func CopyDirectory(src, dst string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		// Calculate relative path
		relPath, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}

		// Skip hidden files/directories except .claude, .cursor, .vscode, .github
		baseName := filepath.Base(path)
		if baseName != "." && baseName[0] == '.' {
			// Allow specific hidden directories
			allowedHidden := map[string]bool{
				".claude":  true,
				".cursor":  true,
				".vscode":  true,
				".github":  true,
				".gitignore": true,
				".env.example": true,
			}
			if !allowedHidden[baseName] {
				if info.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}
		}

		// Skip certain directories
		skipDirs := map[string]bool{
			"node_modules": true,
			"__pycache__":  true,
			".venv":        true,
			"venv":         true,
			".git":         true,
			"dist":         true,
			"build":        true,
			"out":          true,
		}
		if info.IsDir() && skipDirs[baseName] {
			return filepath.SkipDir
		}

		dstPath := filepath.Join(dst, relPath)

		if info.IsDir() {
			return os.MkdirAll(dstPath, info.Mode())
		}

		return copyFileWithMode(path, dstPath)
	})
}

// copyFileWithMode copies a single file preserving its mode
func copyFileWithMode(src, dst string) error {
	// Ensure parent directory exists
	if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
		return err
	}

	// Read source file
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}

	// Get source file mode
	info, err := os.Stat(src)
	if err != nil {
		return err
	}

	// Write destination file
	return os.WriteFile(dst, data, info.Mode())
}

// MakeExecutable makes a file executable (chmod +x)
func MakeExecutable(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	// Add execute permission for owner
	return os.Chmod(path, info.Mode()|0100)
}

