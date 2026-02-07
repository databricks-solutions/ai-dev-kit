// Package installer provides core installation functionality
package installer

import (
	"os"
	"path/filepath"
	"runtime"
)

// getHomeDir returns the user's home directory with fallback
func getHomeDir() string {
	homeDir, err := os.UserHomeDir()
	if err != nil || homeDir == "" {
		// Fallback to environment variables
		if h := os.Getenv("HOME"); h != "" {
			return h
		}
		if h := os.Getenv("USERPROFILE"); h != "" {
			return h
		}
		// Last resort fallback
		return "/tmp"
	}
	return homeDir
}

// Configuration constants
const (
	RepoURL    = "https://github.com/databricks-solutions/ai-dev-kit.git"
	RawURL     = "https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main"
	MLflowURL  = "https://raw.githubusercontent.com/mlflow/skills/main"
	DefaultDir = ".ai-dev-kit"
)

// Databricks skills bundled in the repo
var DatabricksSkills = []string{
	"agent-bricks",
	"aibi-dashboards",
	"asset-bundles",
	"databricks-app-apx",
	"databricks-app-python",
	"databricks-config",
	"databricks-docs",
	"databricks-genie",
	"databricks-jobs",
	"databricks-python-sdk",
	"databricks-unity-catalog",
	"lakebase-provisioned",
	"model-serving",
	"spark-declarative-pipelines",
	"synthetic-data-generation",
	"unstructured-pdf-generation",
}

// MLflow skills fetched from mlflow/skills repo
var MLflowSkills = []string{
	"agent-evaluation",
	"analyze-mlflow-chat-session",
	"analyze-mlflow-trace",
	"instrumenting-with-mlflow-tracing",
	"mlflow-onboarding",
	"querying-mlflow-metrics",
	"retrieving-mlflow-traces",
	"searching-mlflow-docs",
}

// Config holds all installation configuration
type Config struct {
	// Paths
	InstallDir string // Base installation directory (~/.ai-dev-kit)
	RepoDir    string // Repository directory
	VenvDir    string // Python virtual environment
	VenvPython string // Path to Python in venv
	McpEntry   string // Path to MCP server entry point

	// Options
	Profile       string   // Databricks profile name
	Scope         string   // "project" or "global"
	InstallMCP    bool     // Whether to install MCP server
	InstallSkills bool     // Whether to install skills
	Force         bool     // Force reinstall
	Silent        bool     // Silent mode
	Tools         []string // Selected tools

	// Derived from Scope
	BaseDir string // Base directory for config files
}

// NewConfig creates a new configuration with defaults
func NewConfig() *Config {
	homeDir := getHomeDir()
	installDir := getInstallDir(homeDir)

	cfg := &Config{
		InstallDir:    installDir,
		Profile:       "DEFAULT",
		Scope:         "project",
		InstallMCP:    true,
		InstallSkills: true,
		Force:         false,
		Silent:        false,
		Tools:         []string{},
	}

	cfg.updatePaths()
	return cfg
}

// SetInstallDir updates the installation directory and derived paths
func (c *Config) SetInstallDir(dir string) {
	// Expand ~ to home directory
	if len(dir) > 0 && dir[0] == '~' {
		dir = filepath.Join(getHomeDir(), dir[1:])
	}
	c.InstallDir = dir
	c.updatePaths()
}

// updatePaths recalculates derived paths
func (c *Config) updatePaths() {
	c.RepoDir = filepath.Join(c.InstallDir, "repo")
	c.VenvDir = filepath.Join(c.InstallDir, ".venv")
	c.McpEntry = filepath.Join(c.RepoDir, "databricks-mcp-server", "run_server.py")

	// Platform-specific Python path
	if runtime.GOOS == "windows" {
		c.VenvPython = filepath.Join(c.VenvDir, "Scripts", "python.exe")
	} else {
		c.VenvPython = filepath.Join(c.VenvDir, "bin", "python")
	}
}

// SetScope sets the installation scope and updates BaseDir
func (c *Config) SetScope(scope string) {
	c.Scope = scope
	c.UpdateBaseDir()
}

// UpdateBaseDir updates BaseDir based on current scope
func (c *Config) UpdateBaseDir() {
	if c.Scope == "global" {
		c.BaseDir = getHomeDir()
	} else {
		cwd, err := os.Getwd()
		if err != nil {
			c.BaseDir = "."
		} else {
			c.BaseDir = cwd
		}
	}
}

// getInstallDir returns the installation directory, respecting AIDEVKIT_HOME
func getInstallDir(homeDir string) string {
	if envDir := os.Getenv("AIDEVKIT_HOME"); envDir != "" {
		return envDir
	}
	return filepath.Join(homeDir, DefaultDir)
}

// VersionFile returns the path to the version file
func (c *Config) VersionFile() string {
	return filepath.Join(c.InstallDir, "version")
}

// ProjectVersionFile returns the path to the project-specific version file
func (c *Config) ProjectVersionFile() string {
	return filepath.Join(".ai-dev-kit", "version")
}

// GetSkillsDir returns the skills directory for a given tool
func (c *Config) GetSkillsDir(tool string) string {
	switch tool {
	case "claude":
		return filepath.Join(c.BaseDir, ".claude", "skills")
	case "cursor":
		return filepath.Join(c.BaseDir, ".cursor", "skills")
	case "copilot":
		return filepath.Join(c.BaseDir, ".github", "skills")
	case "codex":
		return filepath.Join(c.BaseDir, ".agents", "skills")
	case "gemini":
		return filepath.Join(c.BaseDir, ".gemini", "skills")
	default:
		return ""
	}
}

// GetMCPConfigPath returns the MCP config file path for a given tool
func (c *Config) GetMCPConfigPath(tool string) string {
	homeDir := getHomeDir()
	switch tool {
	case "claude":
		if c.Scope == "global" {
			return filepath.Join(homeDir, ".claude", "mcp.json")
		}
		return filepath.Join(c.BaseDir, ".mcp.json")
	case "cursor":
		if c.Scope == "global" {
			return "" // Cursor global requires manual configuration
		}
		return filepath.Join(c.BaseDir, ".cursor", "mcp.json")
	case "copilot":
		if c.Scope == "global" {
			return "" // Copilot global requires manual configuration
		}
		return filepath.Join(c.BaseDir, ".vscode", "mcp.json")
	case "codex":
		if c.Scope == "global" {
			return filepath.Join(homeDir, ".codex", "config.toml")
		}
		return filepath.Join(c.BaseDir, ".codex", "config.toml")
	case "gemini":
		if c.Scope == "global" {
			return filepath.Join(homeDir, ".gemini", "settings.json")
		}
		return filepath.Join(c.BaseDir, ".gemini", "settings.json")
	default:
		return ""
	}
}

// DisplayPath returns a path with ~ substitution for display
func DisplayPath(path string) string {
	homeDir := getHomeDir()
	if len(path) > len(homeDir) && path[:len(homeDir)] == homeDir {
		return "~" + path[len(homeDir):]
	}
	return path
}

