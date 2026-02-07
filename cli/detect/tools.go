// Package detect provides tool and profile detection functionality
package detect

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

// Tool represents a development tool that can be configured
type Tool struct {
	Name     string
	Value    string
	Detected bool
	Hint     string
}

// DetectTools checks which development tools are installed on the system
func DetectTools() []Tool {
	tools := []Tool{
		{Name: "Claude Code", Value: "claude", Detected: false, Hint: "not found"},
		{Name: "Cursor", Value: "cursor", Detected: false, Hint: "not found"},
		{Name: "GitHub Copilot", Value: "copilot", Detected: false, Hint: "not found"},
		{Name: "OpenAI Codex", Value: "codex", Detected: false, Hint: "not found"},
		{Name: "Google Gemini", Value: "gemini", Detected: false, Hint: "not found"},
	}

	// Check Claude
	if commandExists("claude") {
		tools[0].Detected = true
		tools[0].Hint = "detected"
	}

	// Check Cursor
	if detectCursor() {
		tools[1].Detected = true
		tools[1].Hint = "detected"
	}

	// Check VS Code / Copilot
	if detectVSCode() {
		tools[2].Detected = true
		tools[2].Hint = "detected"
	}

	// Check Codex
	if commandExists("codex") {
		tools[3].Detected = true
		tools[3].Hint = "detected"
	}

	// Check Gemini
	if commandExists("gemini") {
		tools[4].Detected = true
		tools[4].Hint = "detected"
	}

	// If nothing detected, default Claude to true
	anyDetected := false
	for _, t := range tools {
		if t.Detected {
			anyDetected = true
			break
		}
	}
	if !anyDetected {
		tools[0].Detected = true
		tools[0].Hint = "default"
	}

	return tools
}

// commandExists checks if a command is available in PATH
func commandExists(cmd string) bool {
	_, err := exec.LookPath(cmd)
	return err == nil
}

// detectCursor checks for Cursor installation
func detectCursor() bool {
	// Check command in PATH
	if commandExists("cursor") {
		return true
	}

	// Check common installation paths
	switch runtime.GOOS {
	case "darwin":
		if pathExists("/Applications/Cursor.app") {
			return true
		}
	case "windows":
		// Check common Windows paths
		localAppData := os.Getenv("LOCALAPPDATA")
		if localAppData != "" {
			if pathExists(filepath.Join(localAppData, "Programs", "cursor", "Cursor.exe")) {
				return true
			}
		}
	case "linux":
		// Check common Linux paths
		homeDir, _ := os.UserHomeDir()
		if pathExists(filepath.Join(homeDir, ".local", "share", "cursor", "cursor")) {
			return true
		}
		if pathExists("/usr/share/cursor/cursor") {
			return true
		}
	}

	return false
}

// detectVSCode checks for VS Code installation (indicates potential Copilot)
func detectVSCode() bool {
	// Check command in PATH
	if commandExists("code") {
		return true
	}

	// Check common installation paths
	switch runtime.GOOS {
	case "darwin":
		if pathExists("/Applications/Visual Studio Code.app") {
			return true
		}
	case "windows":
		localAppData := os.Getenv("LOCALAPPDATA")
		if localAppData != "" {
			if pathExists(filepath.Join(localAppData, "Programs", "Microsoft VS Code", "Code.exe")) {
				return true
			}
		}
	case "linux":
		if pathExists("/usr/share/code/code") {
			return true
		}
		homeDir, _ := os.UserHomeDir()
		if pathExists(filepath.Join(homeDir, ".local", "share", "code", "code")) {
			return true
		}
	}

	return false
}

// pathExists checks if a path exists
func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// GetToolByValue finds a tool by its value
func GetToolByValue(tools []Tool, value string) *Tool {
	for i := range tools {
		if tools[i].Value == value {
			return &tools[i]
		}
	}
	return nil
}

// FilterSelected returns only detected tools from the list
func FilterSelected(tools []Tool) []string {
	var selected []string
	for _, t := range tools {
		if t.Detected {
			selected = append(selected, t.Value)
		}
	}
	return selected
}

