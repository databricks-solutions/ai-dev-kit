package ui

import (
	"fmt"
	"strings"
)

// CLIError represents an error with context and suggestions
type CLIError struct {
	Message     string
	Details     string
	Causes      []string
	Suggestions []string
}

// Error implements the error interface
func (e *CLIError) Error() string {
	return e.Message
}

// Print displays the error with full formatting
func (e *CLIError) Print() {
	fmt.Println()
	fmt.Println("  " + ErrorStyle.Render("✗ "+e.Message))

	if e.Details != "" {
		fmt.Println()
		fmt.Println("  " + DimStyle.Render(e.Details))
	}

	if len(e.Causes) > 0 {
		fmt.Println()
		fmt.Println("  " + SubtitleStyle.Render("Possible causes:"))
		for _, cause := range e.Causes {
			fmt.Println("    " + DimStyle.Render("• "+cause))
		}
	}

	if len(e.Suggestions) > 0 {
		fmt.Println()
		fmt.Println("  " + SubtitleStyle.Render("Try:"))
		for _, suggestion := range e.Suggestions {
			fmt.Println("    " + InfoStyle.Render("→ ") + suggestion)
		}
	}

	fmt.Println()
}

// NewCLIError creates a new CLI error
func NewCLIError(message string) *CLIError {
	return &CLIError{Message: message}
}

// WithDetails adds details to the error
func (e *CLIError) WithDetails(details string) *CLIError {
	e.Details = details
	return e
}

// WithCause adds a possible cause
func (e *CLIError) WithCause(cause string) *CLIError {
	e.Causes = append(e.Causes, cause)
	return e
}

// WithSuggestion adds a suggestion
func (e *CLIError) WithSuggestion(suggestion string) *CLIError {
	e.Suggestions = append(e.Suggestions, suggestion)
	return e
}

// Common errors with helpful context

// ErrUserCancelled is returned when the user cancels an operation (Ctrl+C)
var ErrUserCancelled = &UserCancelledError{}

// UserCancelledError represents a user-initiated cancellation
type UserCancelledError struct{}

func (e *UserCancelledError) Error() string {
	return "operation cancelled by user"
}

// IsUserCancelled checks if an error is a user cancellation
func IsUserCancelled(err error) bool {
	_, ok := err.(*UserCancelledError)
	return ok
}

// ErrGitNotFound returns an error for missing git
func ErrGitNotFound() *CLIError {
	return NewCLIError("Git is not installed").
		WithCause("Git executable not found in PATH").
		WithSuggestion("Install Git from https://git-scm.com/downloads").
		WithSuggestion("On macOS: xcode-select --install").
		WithSuggestion("On Ubuntu: sudo apt install git")
}

// ErrPythonNotFound returns an error for missing Python
func ErrPythonNotFound() *CLIError {
	return NewCLIError("Python is not installed").
		WithCause("Python 3.9+ is required but not found").
		WithSuggestion("Install Python from https://python.org").
		WithSuggestion("On macOS: brew install python@3.11").
		WithSuggestion("On Ubuntu: sudo apt install python3")
}

// ErrPipNotFound returns an error for missing pip/uv
func ErrPipNotFound() *CLIError {
	return NewCLIError("No Python package manager found").
		WithDetails("Either uv or pip is required to install dependencies").
		WithSuggestion("Install uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh").
		WithSuggestion("Or ensure pip is installed with Python")
}

// ErrNetworkError returns a network connectivity error
func ErrNetworkError(url string, err error) *CLIError {
	cliErr := NewCLIError("Network error").
		WithDetails(fmt.Sprintf("Failed to connect to %s", url)).
		WithCause("No internet connection").
		WithCause("Firewall blocking the connection").
		WithCause("DNS resolution failure").
		WithSuggestion("Check your internet connection").
		WithSuggestion("Try again in a few moments")

	if err != nil {
		cliErr.Details += fmt.Sprintf("\n  Error: %v", err)
	}

	return cliErr
}

// ErrGitCloneFailed returns an error for git clone failures
func ErrGitCloneFailed(url string, err error) *CLIError {
	return NewCLIError("Failed to clone repository").
		WithDetails(fmt.Sprintf("Could not clone %s", url)).
		WithCause("No internet connection").
		WithCause("Repository URL changed").
		WithCause("GitHub is temporarily unavailable").
		WithSuggestion("Check your internet connection").
		WithSuggestion("Run with --verbose for more details").
		WithSuggestion("Try again later")
}

// ErrAuthNotConfigured returns an error for missing Databricks auth
func ErrAuthNotConfigured(profile string) *CLIError {
	return NewCLIError("Databricks authentication not configured").
		WithDetails(fmt.Sprintf("No credentials found for profile '%s'", profile)).
		WithCause("Profile not configured in ~/.databrickscfg").
		WithCause("Token not set in profile").
		WithSuggestion(fmt.Sprintf("Run: databricks auth login --profile %s", profile)).
		WithSuggestion("Or set DATABRICKS_HOST and DATABRICKS_TOKEN environment variables")
}

// ErrMCPInstallFailed returns an error for MCP server installation failure
func ErrMCPInstallFailed(err error) *CLIError {
	cliErr := NewCLIError("MCP server installation failed").
		WithCause("Python dependencies failed to install").
		WithCause("Incompatible Python version").
		WithCause("Disk space issue").
		WithSuggestion("Ensure Python 3.9+ is installed").
		WithSuggestion("Run: aidevkit doctor").
		WithSuggestion("Run: aidevkit install --force")

	if err != nil {
		cliErr.Details = err.Error()
	}

	return cliErr
}

// PrintSimpleError prints a simple error message
func PrintSimpleError(message string) {
	fmt.Println("  " + ErrorStyle.Render("✗ "+message))
}

// PrintErrorWithHelp prints an error with a help hint
func PrintErrorWithHelp(message string, helpCommand string) {
	fmt.Println("  " + ErrorStyle.Render("✗ "+message))
	fmt.Println("  " + DimStyle.Render("Run '"+helpCommand+"' for more information"))
}

// WrapError wraps a standard error with CLI formatting
func WrapError(err error, context string) *CLIError {
	if err == nil {
		return nil
	}

	message := context
	if context == "" {
		message = "An error occurred"
	}

	cliErr := NewCLIError(message)

	// Try to provide helpful context based on error content
	errStr := strings.ToLower(err.Error())

	if strings.Contains(errStr, "connection refused") ||
		strings.Contains(errStr, "no such host") ||
		strings.Contains(errStr, "network") {
		cliErr.WithCause("Network connectivity issue")
		cliErr.WithSuggestion("Check your internet connection")
	}

	if strings.Contains(errStr, "permission denied") {
		cliErr.WithCause("Insufficient permissions")
		cliErr.WithSuggestion("Check file/directory permissions")
	}

	if strings.Contains(errStr, "not found") ||
		strings.Contains(errStr, "no such file") {
		cliErr.WithCause("Required file or command not found")
	}

	cliErr.Details = err.Error()

	return cliErr
}

