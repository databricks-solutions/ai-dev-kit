package detect

import (
	"testing"
)

func TestGetToolByValue(t *testing.T) {
	tools := []Tool{
		{Name: "Claude Code", Value: "claude", Detected: true},
		{Name: "Cursor", Value: "cursor", Detected: false},
		{Name: "GitHub Copilot", Value: "copilot", Detected: true},
	}

	// Find existing tool
	tool := GetToolByValue(tools, "cursor")
	if tool == nil {
		t.Fatal("Should find cursor tool")
	}
	if tool.Name != "Cursor" {
		t.Errorf("Expected Cursor, got %s", tool.Name)
	}

	// Not find nonexistent tool
	tool = GetToolByValue(tools, "nonexistent")
	if tool != nil {
		t.Error("Should not find nonexistent tool")
	}
}

func TestFilterSelected(t *testing.T) {
	tools := []Tool{
		{Name: "Claude Code", Value: "claude", Detected: true},
		{Name: "Cursor", Value: "cursor", Detected: false},
		{Name: "GitHub Copilot", Value: "copilot", Detected: true},
		{Name: "OpenAI Codex", Value: "codex", Detected: false},
	}

	selected := FilterSelected(tools)

	if len(selected) != 2 {
		t.Errorf("Expected 2 selected tools, got %d", len(selected))
	}

	// Check that only detected tools are included
	expectedSelected := map[string]bool{"claude": true, "copilot": true}
	for _, s := range selected {
		if !expectedSelected[s] {
			t.Errorf("Unexpected selected tool: %s", s)
		}
	}
}

func TestFilterSelected_Empty(t *testing.T) {
	tools := []Tool{
		{Name: "Claude Code", Value: "claude", Detected: false},
		{Name: "Cursor", Value: "cursor", Detected: false},
	}

	selected := FilterSelected(tools)

	if len(selected) != 0 {
		t.Errorf("Expected 0 selected tools, got %d", len(selected))
	}
}

func TestDetectTools(t *testing.T) {
	tools := DetectTools()

	// Should always return 4 tools
	if len(tools) != 4 {
		t.Errorf("Expected 4 tools, got %d", len(tools))
	}

	// Verify expected tool values
	expectedValues := map[string]bool{
		"claude":  false,
		"cursor":  false,
		"copilot": false,
		"codex":   false,
	}

	for _, tool := range tools {
		if _, ok := expectedValues[tool.Value]; !ok {
			t.Errorf("Unexpected tool value: %s", tool.Value)
		}
		expectedValues[tool.Value] = true
	}

	// Check all expected values were found
	for value, found := range expectedValues {
		if !found {
			t.Errorf("Missing tool value: %s", value)
		}
	}

	// At least one tool should be detected (fallback to claude if nothing found)
	anyDetected := false
	for _, tool := range tools {
		if tool.Detected {
			anyDetected = true
			break
		}
	}
	if !anyDetected {
		t.Error("At least one tool should be detected (default fallback)")
	}
}

