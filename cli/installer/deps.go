package installer

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"

	"github.com/databricks-solutions/ai-dev-kit/cli/ui"
)

// Dependency represents a required dependency
type Dependency struct {
	Name     string
	Command  string
	Required bool
	Found    bool
	HelpText string
}

// PythonPackageManager holds info about the available Python package manager
type PythonPackageManager struct {
	Name    string
	Command string
}

// CheckDependencies verifies all required dependencies are installed
func CheckDependencies(installMCP bool) ([]Dependency, *PythonPackageManager, error) {
	deps := []Dependency{
		{
			Name:     "git",
			Command:  "git",
			Required: true,
			HelpText: getGitInstallHelp(),
		},
		{
			Name:     "databricks",
			Command:  "databricks",
			Required: false,
			HelpText: getDatabricksInstallHelp(),
		},
	}

	// Check each dependency
	for i := range deps {
		deps[i].Found = commandExists(deps[i].Command)
	}

	// Check for Python package manager if MCP installation is needed
	var pkgMgr *PythonPackageManager
	if installMCP {
		pkgMgr = detectPythonPackageManager()
		if pkgMgr == nil {
			return deps, nil, fmt.Errorf("Python package manager required. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
		}
	}

	// Check for required dependencies
	for _, dep := range deps {
		if dep.Required && !dep.Found {
			return deps, pkgMgr, fmt.Errorf("%s is required but not found. %s", dep.Name, dep.HelpText)
		}
	}

	return deps, pkgMgr, nil
}

// detectPythonPackageManager finds the best available Python package manager
func detectPythonPackageManager() *PythonPackageManager {
	// Prefer uv
	if commandExists("uv") {
		return &PythonPackageManager{Name: "uv", Command: "uv"}
	}
	// Fall back to pip3
	if commandExists("pip3") {
		return &PythonPackageManager{Name: "pip3", Command: "pip3"}
	}
	// Fall back to pip
	if commandExists("pip") {
		return &PythonPackageManager{Name: "pip", Command: "pip"}
	}
	return nil
}

// commandExists checks if a command is available in PATH
func commandExists(cmd string) bool {
	_, err := exec.LookPath(cmd)
	return err == nil
}

// PrintDependencyStatus prints the status of all dependencies
func PrintDependencyStatus(deps []Dependency, pkgMgr *PythonPackageManager, silent bool) {
	if silent {
		return
	}

	for _, dep := range deps {
		if dep.Found {
			fmt.Println(ui.RenderSuccess(dep.Name))
		} else if dep.Required {
			fmt.Println(ui.RenderError(dep.Name + " (required)"))
		} else {
			fmt.Println(ui.RenderWarning(dep.Name + " not found"))
			fmt.Println("  " + ui.DimStyle.Render(dep.HelpText))
		}
	}

	if pkgMgr != nil {
		fmt.Println(ui.RenderSuccess(pkgMgr.Name))
	}
}

// getGitInstallHelp returns platform-specific git installation instructions
func getGitInstallHelp() string {
	switch runtime.GOOS {
	case "darwin":
		return "Install with: xcode-select --install or brew install git"
	case "windows":
		return "Install with: winget install Git.Git or choco install git"
	case "linux":
		return "Install with: apt install git or yum install git"
	default:
		return "Install git from https://git-scm.com"
	}
}

// getDatabricksInstallHelp returns platform-specific Databricks CLI installation instructions
func getDatabricksInstallHelp() string {
	switch runtime.GOOS {
	case "darwin", "linux":
		return "Install: curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"
	case "windows":
		return "Install: winget install Databricks.DatabricksCLI"
	default:
		return "Install from https://docs.databricks.com/dev-tools/cli/install.html"
	}
}

// RunGitClone clones a repository
func RunGitClone(url, destDir string) error {
	cmd := exec.Command("git", "clone", "-q", "--depth", "1", url, destDir)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("git clone failed: %s - %w", strings.TrimSpace(string(output)), err)
	}
	return nil
}

// RunGitPull pulls latest changes in a repository
func RunGitPull(repoDir string) error {
	cmd := exec.Command("git", "-C", repoDir, "pull", "-q")
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("git pull failed: %s - %w", strings.TrimSpace(string(output)), err)
	}
	return nil
}

// RunDatabricksAuth runs databricks auth login interactively
func RunDatabricksAuth(profile string) error {
	cmd := exec.Command("databricks", "auth", "login", "--profile", profile)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return cmd.Run()
}

