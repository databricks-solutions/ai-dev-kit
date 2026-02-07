package installer

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
)

// MCPServerConfig represents the MCP server configuration
type MCPServerConfig struct {
	Command string            `json:"command"`
	Args    []string          `json:"args"`
	Env     map[string]string `json:"env,omitempty"`
}

// MCPConfig represents the MCP configuration file format (Claude/Cursor)
type MCPConfig struct {
	MCPServers map[string]MCPServerConfig `json:"mcpServers"`
}

// CopilotMCPConfig represents the Copilot MCP configuration format
type CopilotMCPConfig struct {
	Servers map[string]MCPServerConfig `json:"servers"`
}

// SetupMCPServer installs the MCP server and creates a virtual environment
func SetupMCPServer(cfg *Config, pkgMgr *PythonPackageManager) error {
	// Ensure install directory exists
	if err := os.MkdirAll(cfg.InstallDir, 0755); err != nil {
		return fmt.Errorf("failed to create install directory: %w", err)
	}

	// Clone or update repository
	if err := setupRepository(cfg); err != nil {
		return err
	}

	// Install Python dependencies
	if err := installPythonDeps(cfg, pkgMgr); err != nil {
		return err
	}

	// Verify installation
	if err := verifyMCPInstall(cfg); err != nil {
		return err
	}

	return nil
}

// setupRepository clones or updates the repository
func setupRepository(cfg *Config) error {
	gitDir := filepath.Join(cfg.RepoDir, ".git")

	if pathExists(gitDir) {
		// Try to pull updates
		err := RunGitPull(cfg.RepoDir)
		if err != nil {
			// If pull fails, remove and re-clone
			os.RemoveAll(cfg.RepoDir)
			return RunGitClone(RepoURL, cfg.RepoDir)
		}
		return nil
	}

	// Fresh clone
	return RunGitClone(RepoURL, cfg.RepoDir)
}

// installPythonDeps installs Python dependencies in a virtual environment
func installPythonDeps(cfg *Config, pkgMgr *PythonPackageManager) error {
	toolsCoreDir := filepath.Join(cfg.RepoDir, "databricks-tools-core")
	mcpServerDir := filepath.Join(cfg.RepoDir, "databricks-mcp-server")

	if pkgMgr.Name == "uv" {
		// Create venv with uv
		cmd := exec.Command("uv", "venv", "--python", "3.11", "--allow-existing", cfg.VenvDir, "-q")
		if err := cmd.Run(); err != nil {
			// Try without specifying Python version
			cmd = exec.Command("uv", "venv", "--allow-existing", cfg.VenvDir, "-q")
			if err := cmd.Run(); err != nil {
				return fmt.Errorf("failed to create venv: %w", err)
			}
		}

		// Install packages with uv
		cmd = exec.Command("uv", "pip", "install", "--python", cfg.VenvPython,
			"-e", toolsCoreDir,
			"-e", mcpServerDir,
			"-q")
		if err := cmd.Run(); err != nil {
			return fmt.Errorf("failed to install packages: %w", err)
		}
	} else {
		// Create venv with python
		if !pathExists(cfg.VenvDir) {
			cmd := exec.Command("python3", "-m", "venv", cfg.VenvDir)
			if err := cmd.Run(); err != nil {
				return fmt.Errorf("failed to create venv: %w", err)
			}
		}

		// Install packages with pip
		cmd := exec.Command(cfg.VenvPython, "-m", "pip", "install", "-q",
			"-e", toolsCoreDir,
			"-e", mcpServerDir)
		if err := cmd.Run(); err != nil {
			return fmt.Errorf("failed to install packages: %w", err)
		}
	}

	return nil
}

// verifyMCPInstall verifies the MCP server was installed correctly
func verifyMCPInstall(cfg *Config) error {
	cmd := exec.Command(cfg.VenvPython, "-c", "import databricks_mcp_server")
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("MCP server verification failed: %w", err)
	}
	return nil
}

// WriteMCPConfigs writes MCP configuration files for all selected tools
func WriteMCPConfigs(cfg *Config) error {
	for _, tool := range cfg.Tools {
		if err := writeMCPConfig(cfg, tool); err != nil {
			return err
		}
	}
	return nil
}

// writeMCPConfig writes MCP config for a specific tool
func writeMCPConfig(cfg *Config, tool string) error {
	switch tool {
	case "claude":
		return writeMCPJSON(cfg, tool)
	case "cursor":
		if cfg.Scope == "global" {
			fmt.Println(ui.RenderWarning("Cursor global: configure in Settings > MCP"))
			fmt.Printf("  Command: %s | Args: %s\n", cfg.VenvPython, cfg.McpEntry)
			return nil
		}
		return writeMCPJSON(cfg, tool)
	case "copilot":
		if cfg.Scope == "global" {
			fmt.Println(ui.RenderWarning("Copilot global: configure MCP in VS Code settings"))
			fmt.Printf("  Command: %s | Args: %s\n", cfg.VenvPython, cfg.McpEntry)
			return nil
		}
		return writeCopilotMCPJSON(cfg)
	case "codex":
		return writeMCPTOML(cfg)
	}
	return nil
}

// writeMCPJSON writes the MCP JSON config file (for Claude/Cursor)
func writeMCPJSON(cfg *Config, tool string) error {
	configPath := cfg.GetMCPConfigPath(tool)
	if configPath == "" {
		return nil
	}

	// Ensure directory exists
	if err := os.MkdirAll(filepath.Dir(configPath), 0755); err != nil {
		return err
	}

	// Backup existing file
	if pathExists(configPath) {
		backupPath := configPath + ".bak"
		if err := copyFile(configPath, backupPath); err == nil {
			fmt.Println("  " + ui.DimStyle.Render(fmt.Sprintf("Backed up %s → %s.bak", filepath.Base(configPath), filepath.Base(configPath))))
		}
	}

	// Read existing config or create new
	var config MCPConfig
	if pathExists(configPath) {
		data, err := os.ReadFile(configPath)
		if err == nil {
			if err := json.Unmarshal(data, &config); err != nil {
				fmt.Println(ui.RenderWarning(fmt.Sprintf("Warning: could not parse existing %s, creating new config", filepath.Base(configPath))))
			}
		}
	}
	if config.MCPServers == nil {
		config.MCPServers = make(map[string]MCPServerConfig)
	}

	// Add/update databricks server config
	// Use forward slashes for cross-platform compatibility
	pythonPath := toForwardSlash(cfg.VenvPython)
	mcpEntry := toForwardSlash(cfg.McpEntry)

	config.MCPServers["databricks"] = MCPServerConfig{
		Command: pythonPath,
		Args:    []string{mcpEntry},
		Env:     map[string]string{"DATABRICKS_CONFIG_PROFILE": cfg.Profile},
	}

	// Write config
	data, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(configPath, append(data, '\n'), 0644)
}

// writeCopilotMCPJSON writes the Copilot MCP JSON config file
func writeCopilotMCPJSON(cfg *Config) error {
	configPath := cfg.GetMCPConfigPath("copilot")
	if configPath == "" {
		return nil
	}

	// Ensure directory exists
	if err := os.MkdirAll(filepath.Dir(configPath), 0755); err != nil {
		return err
	}

	// Backup existing file
	if pathExists(configPath) {
		backupPath := configPath + ".bak"
		if err := copyFile(configPath, backupPath); err == nil {
			fmt.Println("  " + ui.DimStyle.Render(fmt.Sprintf("Backed up %s → %s.bak", filepath.Base(configPath), filepath.Base(configPath))))
		}
	}

	// Read existing config or create new
	var config CopilotMCPConfig
	if pathExists(configPath) {
		data, err := os.ReadFile(configPath)
		if err == nil {
			if err := json.Unmarshal(data, &config); err != nil {
				fmt.Println(ui.RenderWarning(fmt.Sprintf("Warning: could not parse existing %s, creating new config", filepath.Base(configPath))))
			}
		}
	}
	if config.Servers == nil {
		config.Servers = make(map[string]MCPServerConfig)
	}

	// Add/update databricks server config
	pythonPath := toForwardSlash(cfg.VenvPython)
	mcpEntry := toForwardSlash(cfg.McpEntry)

	config.Servers["databricks"] = MCPServerConfig{
		Command: pythonPath,
		Args:    []string{mcpEntry},
		Env:     map[string]string{"DATABRICKS_CONFIG_PROFILE": cfg.Profile},
	}

	// Write config
	data, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(configPath, append(data, '\n'), 0644)
}

// CodexMCPConfig represents the Codex TOML config structure
type CodexMCPConfig struct {
	MCPServers map[string]CodexServerConfig `toml:"mcp_servers"`
}

// CodexServerConfig represents a single MCP server in Codex config
type CodexServerConfig struct {
	Command string   `toml:"command"`
	Args    []string `toml:"args"`
}

// writeMCPTOML writes the MCP TOML config file (for Codex)
func writeMCPTOML(cfg *Config) error {
	configPath := cfg.GetMCPConfigPath("codex")
	if configPath == "" {
		return nil
	}

	// Ensure directory exists
	if err := os.MkdirAll(filepath.Dir(configPath), 0755); err != nil {
		return err
	}

	// Check if databricks config already exists
	if pathExists(configPath) {
		data, _ := os.ReadFile(configPath)
		if strings.Contains(string(data), "mcp_servers.databricks") {
			return nil // Already configured
		}
		// Backup existing file
		backupPath := configPath + ".bak"
		if err := copyFile(configPath, backupPath); err == nil {
			fmt.Println("  " + ui.DimStyle.Render(fmt.Sprintf("Backed up %s → %s.bak", filepath.Base(configPath), filepath.Base(configPath))))
		}
	}

	// Append databricks config
	pythonPath := toForwardSlash(cfg.VenvPython)
	mcpEntry := toForwardSlash(cfg.McpEntry)

	tomlBlock := fmt.Sprintf(`
[mcp_servers.databricks]
command = "%s"
args = ["%s"]
`, pythonPath, mcpEntry)

	f, err := os.OpenFile(configPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = f.WriteString(tomlBlock)
	return err
}

// PrintMCPInstructions prints tool-specific MCP instructions
func PrintMCPInstructions(tool string) {
	switch tool {
	case "cursor":
		fmt.Println(ui.RenderWarning("Cursor: MCP servers are disabled by default."))
		fmt.Println("  Enable in: " + ui.TextStyle.Render("Cursor → Settings → Cursor Settings → Tools & MCP → Toggle 'databricks'"))
	case "copilot":
		fmt.Println(ui.RenderWarning("Copilot: MCP servers must be enabled manually."))
		fmt.Println("  In Copilot Chat, click " + ui.TextStyle.Render("Configure Tools") + " (tool icon, bottom-right) and enable " + ui.TextStyle.Render("databricks"))
	}
}

// toForwardSlash converts Windows backslashes to forward slashes for JSON compatibility
func toForwardSlash(path string) string {
	if runtime.GOOS == "windows" {
		return strings.ReplaceAll(path, "\\", "/")
	}
	return path
}

// pathExists checks if a path exists
func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// copyFile copies a file from src to dst
func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0644)
}


