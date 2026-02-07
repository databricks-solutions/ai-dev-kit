package installer

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
)

// httpClient is a shared HTTP client with timeout
var httpClient = &http.Client{
	Timeout: 30 * time.Second,
}

// InstallSkills installs Databricks and MLflow skills for selected tools
func InstallSkills(cfg *Config) error {
	// Determine unique target directories
	dirs := getSkillsDirectories(cfg)

	for _, dir := range dirs {
		// Create directory
		if err := os.MkdirAll(dir, 0755); err != nil {
			return fmt.Errorf("failed to create skills directory: %w", err)
		}

		// Install Databricks skills from repo
		if err := installDatabricksSkills(cfg, dir); err != nil {
			return err
		}
		fmt.Println(ui.RenderSuccess(fmt.Sprintf("Databricks skills → %s", DisplayPath(dir))))

		// Install MLflow skills from remote
		if err := installMLflowSkills(dir); err != nil {
			// MLflow skills are optional, just warn on failure
			fmt.Println(ui.RenderWarning(fmt.Sprintf("Some MLflow skills failed to install: %v", err)))
		} else {
			fmt.Println(ui.RenderSuccess(fmt.Sprintf("MLflow skills → %s", DisplayPath(dir))))
		}
	}

	return nil
}

// getSkillsDirectories returns unique directories for skills installation
func getSkillsDirectories(cfg *Config) []string {
	dirMap := make(map[string]bool)
	var dirs []string

	for _, tool := range cfg.Tools {
		var dir string
		switch tool {
		case "claude":
			dir = cfg.GetSkillsDir("claude")
		case "cursor":
			// Cursor shares with Claude if Claude is also selected
			if !containsTool(cfg.Tools, "claude") {
				dir = cfg.GetSkillsDir("cursor")
			}
		case "copilot":
			dir = cfg.GetSkillsDir("copilot")
		case "codex":
			dir = cfg.GetSkillsDir("codex")
		}

		if dir != "" && !dirMap[dir] {
			dirMap[dir] = true
			dirs = append(dirs, dir)
		}
	}

	return dirs
}

// containsTool checks if a tool is in the list
func containsTool(tools []string, tool string) bool {
	for _, t := range tools {
		if t == tool {
			return true
		}
	}
	return false
}

// installDatabricksSkills copies skills from the cloned repository
func installDatabricksSkills(cfg *Config, targetDir string) error {
	skillsSourceDir := filepath.Join(cfg.RepoDir, "databricks-skills")

	for _, skill := range DatabricksSkills {
		srcDir := filepath.Join(skillsSourceDir, skill)

		// Skip if source doesn't exist
		if !pathExists(srcDir) {
			continue
		}

		destDir := filepath.Join(targetDir, skill)

		// Remove existing
		os.RemoveAll(destDir)

		// Copy skill directory
		if err := copyDir(srcDir, destDir); err != nil {
			return fmt.Errorf("failed to copy skill %s: %w", skill, err)
		}
	}

	return nil
}

// installMLflowSkills fetches MLflow skills from the remote repository
func installMLflowSkills(targetDir string) error {
	var lastErr error

	for _, skill := range MLflowSkills {
		destDir := filepath.Join(targetDir, skill)

		// Create skill directory
		if err := os.MkdirAll(destDir, 0755); err != nil {
			lastErr = err
			continue
		}

		// Fetch SKILL.md (required)
		skillURL := fmt.Sprintf("%s/%s/SKILL.md", MLflowURL, skill)
		destFile := filepath.Join(destDir, "SKILL.md")

		if err := downloadFile(skillURL, destFile); err != nil {
			// Remove the directory if we can't get the main file
			os.RemoveAll(destDir)
			lastErr = err
			continue
		}

		// Try to fetch optional reference files
		optionalFiles := []string{"reference.md", "examples.md", "api.md"}
		for _, refFile := range optionalFiles {
			refURL := fmt.Sprintf("%s/%s/%s", MLflowURL, skill, refFile)
			refDest := filepath.Join(destDir, refFile)
			downloadFile(refURL, refDest) // Ignore errors for optional files
		}
	}

	return lastErr
}

// downloadFile downloads a file from a URL to a local path with timeout
func downloadFile(url, destPath string) error {
	resp, err := httpClient.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	// Create file with temp extension first to avoid partial writes
	tempPath := destPath + ".tmp"
	out, err := os.Create(tempPath)
	if err != nil {
		return err
	}

	_, err = io.Copy(out, resp.Body)
	out.Close()
	if err != nil {
		os.Remove(tempPath)
		return err
	}

	// Rename temp file to final destination
	return os.Rename(tempPath, destPath)
}

// copyDir recursively copies a directory
func copyDir(src, dst string) error {
	srcInfo, err := os.Stat(src)
	if err != nil {
		return err
	}

	if err := os.MkdirAll(dst, srcInfo.Mode()); err != nil {
		return err
	}

	entries, err := os.ReadDir(src)
	if err != nil {
		return err
	}

	for _, entry := range entries {
		srcPath := filepath.Join(src, entry.Name())
		dstPath := filepath.Join(dst, entry.Name())

		if entry.IsDir() {
			if err := copyDir(srcPath, dstPath); err != nil {
				return err
			}
		} else {
			if err := copyFile(srcPath, dstPath); err != nil {
				return err
			}
		}
	}

	return nil
}

// SkillsDirectoryDescription returns a human-readable description of where skills are installed
func SkillsDirectoryDescription(tools []string, baseDir string) string {
	var dirs []string
	for _, tool := range tools {
		switch tool {
		case "claude":
			dirs = append(dirs, ".claude/skills")
		case "cursor":
			if !containsTool(tools, "claude") {
				dirs = append(dirs, ".cursor/skills")
			}
		case "copilot":
			dirs = append(dirs, ".github/skills")
		case "codex":
			dirs = append(dirs, ".agents/skills")
		}
	}

	if len(dirs) == 0 {
		return "none"
	}

	return strings.Join(dirs, ", ")
}

