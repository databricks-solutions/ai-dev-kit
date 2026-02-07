package ui

import (
	"errors"
	"strings"
	"testing"
)

func TestCLIError(t *testing.T) {
	err := NewCLIError("test error")

	if err.Message != "test error" {
		t.Errorf("Expected message 'test error', got '%s'", err.Message)
	}

	if err.Error() != "test error" {
		t.Errorf("Error() should return message")
	}
}

func TestCLIErrorChaining(t *testing.T) {
	err := NewCLIError("main error").
		WithDetails("some details").
		WithCause("cause 1").
		WithCause("cause 2").
		WithSuggestion("suggestion 1").
		WithSuggestion("suggestion 2")

	if err.Details != "some details" {
		t.Errorf("Expected details 'some details', got '%s'", err.Details)
	}

	if len(err.Causes) != 2 {
		t.Errorf("Expected 2 causes, got %d", len(err.Causes))
	}

	if len(err.Suggestions) != 2 {
		t.Errorf("Expected 2 suggestions, got %d", len(err.Suggestions))
	}
}

func TestErrGitNotFound(t *testing.T) {
	err := ErrGitNotFound()

	if !strings.Contains(err.Message, "Git") {
		t.Error("Error should mention Git")
	}

	if len(err.Suggestions) == 0 {
		t.Error("Should have suggestions")
	}
}

func TestErrPythonNotFound(t *testing.T) {
	err := ErrPythonNotFound()

	if !strings.Contains(err.Message, "Python") {
		t.Error("Error should mention Python")
	}

	if len(err.Suggestions) == 0 {
		t.Error("Should have suggestions")
	}
}

func TestErrPipNotFound(t *testing.T) {
	err := ErrPipNotFound()

	if !strings.Contains(err.Details, "uv") || !strings.Contains(err.Details, "pip") {
		t.Error("Error should mention uv and pip")
	}

	if len(err.Suggestions) == 0 {
		t.Error("Should have suggestions")
	}
}

func TestErrNetworkError(t *testing.T) {
	originalErr := errors.New("connection refused")
	err := ErrNetworkError("https://example.com", originalErr)

	if !strings.Contains(err.Message, "Network") {
		t.Error("Error should mention Network")
	}

	if !strings.Contains(err.Details, "example.com") {
		t.Error("Details should contain the URL")
	}

	if !strings.Contains(err.Details, "connection refused") {
		t.Error("Details should contain original error")
	}
}

func TestErrGitCloneFailed(t *testing.T) {
	originalErr := errors.New("timeout")
	err := ErrGitCloneFailed("https://github.com/repo.git", originalErr)

	if !strings.Contains(err.Message, "clone") {
		t.Error("Error should mention clone")
	}

	if !strings.Contains(err.Details, "github.com") {
		t.Error("Details should contain the URL")
	}
}

func TestErrAuthNotConfigured(t *testing.T) {
	err := ErrAuthNotConfigured("test-profile")

	if !strings.Contains(err.Message, "authentication") {
		t.Error("Error should mention authentication")
	}

	if !strings.Contains(err.Details, "test-profile") {
		t.Error("Details should contain profile name")
	}

	// Should suggest databricks auth login
	hasSuggestion := false
	for _, s := range err.Suggestions {
		if strings.Contains(s, "databricks auth login") {
			hasSuggestion = true
			break
		}
	}
	if !hasSuggestion {
		t.Error("Should suggest databricks auth login")
	}
}

func TestErrMCPInstallFailed(t *testing.T) {
	originalErr := errors.New("pip install failed")
	err := ErrMCPInstallFailed(originalErr)

	if !strings.Contains(err.Message, "MCP") {
		t.Error("Error should mention MCP")
	}

	if err.Details != "pip install failed" {
		t.Errorf("Details should be original error, got '%s'", err.Details)
	}

	// Should suggest aidevkit doctor
	hasSuggestion := false
	for _, s := range err.Suggestions {
		if strings.Contains(s, "aidevkit doctor") {
			hasSuggestion = true
			break
		}
	}
	if !hasSuggestion {
		t.Error("Should suggest aidevkit doctor")
	}
}

func TestWrapError(t *testing.T) {
	// Test with nil error
	if WrapError(nil, "context") != nil {
		t.Error("WrapError(nil) should return nil")
	}

	// Test network error detection
	networkErr := errors.New("connection refused")
	wrapped := WrapError(networkErr, "failed to connect")
	if len(wrapped.Causes) == 0 || !strings.Contains(wrapped.Causes[0], "Network") {
		t.Error("Should detect network error")
	}

	// Test permission error detection
	permErr := errors.New("permission denied")
	wrapped = WrapError(permErr, "failed to write")
	hasCause := false
	for _, c := range wrapped.Causes {
		if strings.Contains(c, "permission") {
			hasCause = true
			break
		}
	}
	if !hasCause {
		t.Error("Should detect permission error")
	}

	// Test not found error detection
	notFoundErr := errors.New("file not found")
	wrapped = WrapError(notFoundErr, "")
	hasCause = false
	for _, c := range wrapped.Causes {
		if strings.Contains(c, "not found") {
			hasCause = true
			break
		}
	}
	if !hasCause {
		t.Error("Should detect not found error")
	}
}

func TestWrapErrorDefaultMessage(t *testing.T) {
	err := WrapError(errors.New("some error"), "")
	if err.Message != "An error occurred" {
		t.Errorf("Expected default message, got '%s'", err.Message)
	}
}

func TestUserCancelledError(t *testing.T) {
	err := &UserCancelledError{}
	expected := "operation cancelled by user"
	if err.Error() != expected {
		t.Errorf("Expected '%s', got '%s'", expected, err.Error())
	}
}

func TestIsUserCancelled(t *testing.T) {
	if !IsUserCancelled(ErrUserCancelled) {
		t.Error("Should recognize ErrUserCancelled")
	}

	if !IsUserCancelled(&UserCancelledError{}) {
		t.Error("Should recognize new UserCancelledError")
	}

	regularErr := errors.New("some error")
	if IsUserCancelled(regularErr) {
		t.Error("Should not recognize regular error as user cancelled")
	}
}

