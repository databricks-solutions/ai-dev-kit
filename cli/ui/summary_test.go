package ui

import (
	"bytes"
	"os"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestNewSummary(t *testing.T) {
	items := []SummaryItem{
		{Key: "Key1", Value: "Value1"},
		{Key: "Key2", Value: "Value2"},
	}

	model := NewSummary("Test Summary", items)

	if model.Title != "Test Summary" {
		t.Errorf("Expected title 'Test Summary', got %s", model.Title)
	}

	if len(model.Items) != 2 {
		t.Errorf("Expected 2 items, got %d", len(model.Items))
	}

	if model.cursor != 0 {
		t.Errorf("Expected cursor at 0, got %d", model.cursor)
	}

	if model.confirmed {
		t.Error("Should not be confirmed initially")
	}

	if model.cancelled {
		t.Error("Should not be cancelled initially")
	}
}

func TestSummaryModel_Init(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})
	cmd := model.Init()

	if cmd != nil {
		t.Error("Init should return nil")
	}
}

func TestSummaryModel_Update_Navigation(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})

	// Test left/right navigation
	newModel, _ := model.Update(tea.KeyMsg{Type: tea.KeyRight})
	model = newModel.(SummaryModel)
	if model.cursor != 1 {
		t.Errorf("After right, cursor should be 1, got %d", model.cursor)
	}

	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyLeft})
	model = newModel.(SummaryModel)
	if model.cursor != 0 {
		t.Errorf("After left, cursor should be 0, got %d", model.cursor)
	}

	// Test h/l navigation
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'l'}})
	model = newModel.(SummaryModel)
	if model.cursor != 1 {
		t.Errorf("After l, cursor should be 1, got %d", model.cursor)
	}

	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'h'}})
	model = newModel.(SummaryModel)
	if model.cursor != 0 {
		t.Errorf("After h, cursor should be 0, got %d", model.cursor)
	}
}

func TestSummaryModel_Update_Confirm(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})
	model.cursor = 0 // Yes button

	// Press enter
	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model = newModel.(SummaryModel)

	if !model.confirmed {
		t.Error("Should be confirmed after enter on Yes")
	}

	if model.cancelled {
		t.Error("Should not be cancelled")
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestSummaryModel_Update_Cancel(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})
	model.cursor = 1 // No button

	// Press enter
	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model = newModel.(SummaryModel)

	if model.confirmed {
		t.Error("Should not be confirmed")
	}

	if !model.cancelled {
		t.Error("Should be cancelled after enter on No")
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestSummaryModel_Update_YKey(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})

	// Press y
	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'y'}})
	model = newModel.(SummaryModel)

	if !model.confirmed {
		t.Error("Should be confirmed after y")
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}

	// Test Y
	model = NewSummary("Test", []SummaryItem{})
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'Y'}})
	model = newModel.(SummaryModel)

	if !model.confirmed {
		t.Error("Should be confirmed after Y")
	}
}

func TestSummaryModel_Update_NKey(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})

	// Press n
	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}})
	model = newModel.(SummaryModel)

	if !model.cancelled {
		t.Error("Should be cancelled after n")
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}

	// Test N
	model = NewSummary("Test", []SummaryItem{})
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'N'}})
	model = newModel.(SummaryModel)

	if !model.cancelled {
		t.Error("Should be cancelled after N")
	}
}

func TestSummaryModel_Update_CtrlC(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})

	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyCtrlC})
	model = newModel.(SummaryModel)

	if !model.cancelled {
		t.Error("Should be cancelled after ctrl+c")
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestSummaryModel_View(t *testing.T) {
	items := []SummaryItem{
		{Key: "Tools", Value: "claude, cursor"},
		{Key: "Profile", Value: "DEFAULT"},
	}

	model := NewSummary("Test Summary", items)
	view := model.View()

	// Should contain title
	if !strings.Contains(view, "Test Summary") {
		t.Error("View should contain title")
	}

	// Should contain items
	if !strings.Contains(view, "Tools") {
		t.Error("View should contain Tools key")
	}

	if !strings.Contains(view, "claude, cursor") {
		t.Error("View should contain Tools value")
	}

	// Should contain buttons
	if !strings.Contains(view, "Yes") {
		t.Error("View should contain Yes button")
	}

	if !strings.Contains(view, "No") {
		t.Error("View should contain No button")
	}

	// When confirmed or cancelled, view should be empty
	model.confirmed = true
	view = model.View()
	if view != "" {
		t.Error("View should be empty when confirmed")
	}

	model.confirmed = false
	model.cancelled = true
	view = model.View()
	if view != "" {
		t.Error("View should be empty when cancelled")
	}
}

func TestSummaryModel_IsConfirmed(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})

	if model.IsConfirmed() {
		t.Error("Should not be confirmed initially")
	}

	model.confirmed = true
	if !model.IsConfirmed() {
		t.Error("Should be confirmed after setting flag")
	}
}

func TestSummaryModel_IsCancelled(t *testing.T) {
	model := NewSummary("Test", []SummaryItem{})

	if model.IsCancelled() {
		t.Error("Should not be cancelled initially")
	}

	model.cancelled = true
	if !model.IsCancelled() {
		t.Error("Should be cancelled after setting flag")
	}
}

func TestSummaryItem(t *testing.T) {
	item := SummaryItem{
		Key:   "Test Key",
		Value: "Test Value",
	}

	if item.Key != "Test Key" {
		t.Error("Key not set correctly")
	}

	if item.Value != "Test Value" {
		t.Error("Value not set correctly")
	}
}

func TestPrintSummary(t *testing.T) {
	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	items := []SummaryItem{
		{Key: "Key1", Value: "Value1"},
		{Key: "Key2", Value: "Value2"},
	}

	PrintSummary("Test Title", items)

	w.Close()
	os.Stdout = old

	var buf bytes.Buffer
	buf.ReadFrom(r)
	output := buf.String()

	if !strings.Contains(output, "Test Title") {
		t.Error("Output should contain title")
	}

	if !strings.Contains(output, "Key1") {
		t.Error("Output should contain Key1")
	}

	if !strings.Contains(output, "Value1") {
		t.Error("Output should contain Value1")
	}
}

func TestPrintCompletionMessage(t *testing.T) {
	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	PrintCompletionMessage("DEFAULT", []string{"claude", "cursor"}, "/test/path")

	w.Close()
	os.Stdout = old

	var buf bytes.Buffer
	buf.ReadFrom(r)
	output := buf.String()

	if !strings.Contains(output, "complete") {
		t.Error("Output should contain 'complete'")
	}

	if !strings.Contains(output, "DEFAULT") {
		t.Error("Output should contain profile name")
	}
}

