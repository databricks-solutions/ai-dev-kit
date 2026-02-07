package ui

import (
	"bytes"
	"os"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestNewPrompt(t *testing.T) {
	model := NewPrompt("Test Title", "Test Description", "default-value")

	if model.Title != "Test Title" {
		t.Errorf("Expected title 'Test Title', got %s", model.Title)
	}

	if model.Description != "Test Description" {
		t.Errorf("Expected description 'Test Description', got %s", model.Description)
	}

	if model.Default != "default-value" {
		t.Errorf("Expected default 'default-value', got %s", model.Default)
	}

	if model.finished {
		t.Error("Should not be finished initially")
	}
}

func TestPromptModel_Init(t *testing.T) {
	model := NewPrompt("Test", "", "default")
	cmd := model.Init()

	// Init should return textinput.Blink command
	if cmd == nil {
		t.Error("Init should return a command for text input blinking")
	}
}

func TestPromptModel_Update_Enter(t *testing.T) {
	model := NewPrompt("Test", "", "default")

	// Simulate typing
	model.textInput.SetValue("custom-value")

	// Press enter
	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model = newModel.(PromptModel)

	if !model.finished {
		t.Error("Should be finished after enter")
	}

	if model.value != "custom-value" {
		t.Errorf("Value should be 'custom-value', got %s", model.value)
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestPromptModel_Update_EnterWithDefault(t *testing.T) {
	model := NewPrompt("Test", "", "default-value")

	// Press enter without typing (use default)
	newModel, _ := model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model = newModel.(PromptModel)

	if model.value != "default-value" {
		t.Errorf("Value should be 'default-value', got %s", model.value)
	}
}

func TestPromptModel_Update_CtrlC(t *testing.T) {
	model := NewPrompt("Test", "", "default")

	_, cmd := model.Update(tea.KeyMsg{Type: tea.KeyCtrlC})

	if cmd == nil {
		t.Error("ctrl+c should return quit command")
	}
}

func TestPromptModel_View(t *testing.T) {
	model := NewPrompt("Test Title", "Test Description", "default-value")
	view := model.View()

	// Should contain title
	if !strings.Contains(view, "Test Title") {
		t.Error("View should contain title")
	}

	// Should contain description
	if !strings.Contains(view, "Test Description") {
		t.Error("View should contain description")
	}

	// Should contain default hint
	if !strings.Contains(view, "default-value") {
		t.Error("View should contain default value hint")
	}

	// When finished, view should be empty
	model.finished = true
	view = model.View()
	if view != "" {
		t.Error("View should be empty when finished")
	}
}

func TestPromptModel_View_NoDescription(t *testing.T) {
	model := NewPrompt("Test Title", "", "default-value")
	view := model.View()

	// Should still work without description
	if !strings.Contains(view, "Test Title") {
		t.Error("View should contain title")
	}
}

func TestPromptModel_Value(t *testing.T) {
	model := NewPrompt("Test", "", "default-value")

	// Without setting value, should return default
	if model.Value() != "default-value" {
		t.Errorf("Expected default value, got %s", model.Value())
	}

	// After setting value
	model.value = "custom-value"
	if model.Value() != "custom-value" {
		t.Errorf("Expected 'custom-value', got %s", model.Value())
	}

	// Empty value should return default
	model.value = ""
	if model.Value() != "default-value" {
		t.Errorf("Empty value should return default, got %s", model.Value())
	}
}

func TestPromptModel_IsFinished(t *testing.T) {
	model := NewPrompt("Test", "", "default")

	if model.IsFinished() {
		t.Error("Should not be finished initially")
	}

	model.finished = true
	if !model.IsFinished() {
		t.Error("Should be finished after setting flag")
	}
}

func TestSimplePrompt(t *testing.T) {
	// Save original stdin
	oldStdin := os.Stdin

	// Create a pipe for stdin
	r, w, _ := os.Pipe()
	os.Stdin = r

	// Write input to pipe
	w.WriteString("user-input\n")
	w.Close()

	// Capture stdout
	oldStdout := os.Stdout
	rOut, wOut, _ := os.Pipe()
	os.Stdout = wOut

	result := SimplePrompt("Enter value", "default")

	wOut.Close()
	os.Stdout = oldStdout
	os.Stdin = oldStdin

	// Read captured output
	var buf bytes.Buffer
	buf.ReadFrom(rOut)

	if result != "user-input" {
		t.Errorf("Expected 'user-input', got %s", result)
	}
}

func TestSimplePrompt_Empty(t *testing.T) {
	// Save original stdin
	oldStdin := os.Stdin

	// Create a pipe for stdin
	r, w, _ := os.Pipe()
	os.Stdin = r

	// Write empty input (just newline)
	w.WriteString("\n")
	w.Close()

	// Capture stdout
	oldStdout := os.Stdout
	_, wOut, _ := os.Pipe()
	os.Stdout = wOut

	result := SimplePrompt("Enter value", "default-value")

	wOut.Close()
	os.Stdout = oldStdout
	os.Stdin = oldStdin

	if result != "default-value" {
		t.Errorf("Expected 'default-value', got %s", result)
	}
}

