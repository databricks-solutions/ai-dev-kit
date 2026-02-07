package ui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestNewRadio(t *testing.T) {
	items := []RadioItem{
		{Label: "Option 1", Value: "opt1", Selected: true},
		{Label: "Option 2", Value: "opt2", Selected: false},
	}

	model := NewRadio("Test Title", items)

	if model.Title != "Test Title" {
		t.Errorf("Expected title 'Test Title', got %s", model.Title)
	}

	if len(model.Items) != 2 {
		t.Errorf("Expected 2 items, got %d", len(model.Items))
	}

	if model.cursor != 0 {
		t.Errorf("Expected cursor at 0, got %d", model.cursor)
	}

	if model.selected != 0 {
		t.Errorf("Expected selected at 0, got %d", model.selected)
	}

	if model.finished {
		t.Error("Should not be finished initially")
	}
}

func TestNewRadio_DefaultSelection(t *testing.T) {
	items := []RadioItem{
		{Label: "Option 1", Value: "opt1", Selected: false},
		{Label: "Option 2", Value: "opt2", Selected: true},
		{Label: "Option 3", Value: "opt3", Selected: false},
	}

	model := NewRadio("Test", items)

	if model.selected != 1 {
		t.Errorf("Expected selected at 1 (the pre-selected item), got %d", model.selected)
	}
}

func TestRadioModel_Init(t *testing.T) {
	model := NewRadio("Test", []RadioItem{})
	cmd := model.Init()

	if cmd != nil {
		t.Error("Init should return nil")
	}
}

func TestRadioModel_Update(t *testing.T) {
	items := []RadioItem{
		{Label: "Option 1", Value: "opt1"},
		{Label: "Option 2", Value: "opt2"},
		{Label: "Option 3", Value: "opt3"},
	}

	model := NewRadio("Test", items)

	// Test down navigation
	newModel, _ := model.Update(tea.KeyMsg{Type: tea.KeyDown})
	model = newModel.(RadioModel)
	if model.cursor != 1 {
		t.Errorf("After down, cursor should be 1, got %d", model.cursor)
	}

	// Test up navigation
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyUp})
	model = newModel.(RadioModel)
	if model.cursor != 0 {
		t.Errorf("After up, cursor should be 0, got %d", model.cursor)
	}

	// Test space to select (but not finish)
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyDown})
	model = newModel.(RadioModel)
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeySpace})
	model = newModel.(RadioModel)
	if model.selected != 1 {
		t.Errorf("After space on item 1, selected should be 1, got %d", model.selected)
	}
	if model.finished {
		t.Error("Should not be finished after space")
	}

	// Test j/k navigation
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	model = newModel.(RadioModel)
	if model.cursor != 2 {
		t.Errorf("After j, cursor should be 2, got %d", model.cursor)
	}

	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'k'}})
	model = newModel.(RadioModel)
	if model.cursor != 1 {
		t.Errorf("After k, cursor should be 1, got %d", model.cursor)
	}
}

func TestRadioModel_Update_Enter(t *testing.T) {
	items := []RadioItem{
		{Label: "Option 1", Value: "opt1"},
		{Label: "Option 2", Value: "opt2"},
	}

	model := NewRadio("Test", items)

	// Move to item 1 and press enter
	newModel, _ := model.Update(tea.KeyMsg{Type: tea.KeyDown})
	model = newModel.(RadioModel)
	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model = newModel.(RadioModel)

	if model.selected != 1 {
		t.Errorf("Selected should be 1, got %d", model.selected)
	}

	if !model.finished {
		t.Error("Should be finished after enter")
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestRadioModel_Update_Quit(t *testing.T) {
	model := NewRadio("Test", []RadioItem{{Label: "Test", Value: "test"}})

	// Test ctrl+c
	_, cmd := model.Update(tea.KeyMsg{Type: tea.KeyCtrlC})
	if cmd == nil {
		t.Error("ctrl+c should return quit command")
	}

	// Test q
	_, cmd = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}})
	if cmd == nil {
		t.Error("q should return quit command")
	}
}

func TestRadioModel_View(t *testing.T) {
	items := []RadioItem{
		{Label: "Option 1", Value: "opt1", Hint: "default"},
		{Label: "Option 2", Value: "opt2"},
	}

	model := NewRadio("Test Title", items)
	view := model.View()

	// Should contain title
	if !strings.Contains(view, "Test Title") {
		t.Error("View should contain title")
	}

	// Should contain items
	if !strings.Contains(view, "Option 1") {
		t.Error("View should contain Option 1")
	}

	if !strings.Contains(view, "Option 2") {
		t.Error("View should contain Option 2")
	}

	// Should contain confirm button
	if !strings.Contains(view, "Confirm") {
		t.Error("View should contain Confirm button")
	}

	// When finished, view should be empty
	model.finished = true
	view = model.View()
	if view != "" {
		t.Error("View should be empty when finished")
	}
}

func TestRadioModel_SelectedValue(t *testing.T) {
	items := []RadioItem{
		{Label: "Option 1", Value: "opt1"},
		{Label: "Option 2", Value: "opt2"},
	}

	model := NewRadio("Test", items)
	model.selected = 1

	if model.SelectedValue() != "opt2" {
		t.Errorf("Expected 'opt2', got %s", model.SelectedValue())
	}
}

func TestRadioModel_SelectedValue_Invalid(t *testing.T) {
	model := NewRadio("Test", []RadioItem{})
	model.selected = 5 // Invalid index

	if model.SelectedValue() != "" {
		t.Error("Should return empty string for invalid index")
	}
}

func TestRadioModel_SelectedLabel(t *testing.T) {
	items := []RadioItem{
		{Label: "Option 1", Value: "opt1"},
		{Label: "Option 2", Value: "opt2"},
	}

	model := NewRadio("Test", items)
	model.selected = 1

	if model.SelectedLabel() != "Option 2" {
		t.Errorf("Expected 'Option 2', got %s", model.SelectedLabel())
	}
}

func TestRadioModel_SelectedLabel_Invalid(t *testing.T) {
	model := NewRadio("Test", []RadioItem{})
	model.selected = -1 // Invalid index

	if model.SelectedLabel() != "" {
		t.Error("Should return empty string for invalid index")
	}
}

func TestRadioModel_IsFinished(t *testing.T) {
	model := NewRadio("Test", []RadioItem{})

	if model.IsFinished() {
		t.Error("Should not be finished initially")
	}

	model.finished = true
	if !model.IsFinished() {
		t.Error("Should be finished after setting flag")
	}
}

func TestRadioItem(t *testing.T) {
	item := RadioItem{
		Label:    "Test Label",
		Value:    "test-value",
		Selected: true,
		Hint:     "test hint",
	}

	if item.Label != "Test Label" {
		t.Error("Label not set correctly")
	}

	if item.Value != "test-value" {
		t.Error("Value not set correctly")
	}

	if !item.Selected {
		t.Error("Selected not set correctly")
	}

	if item.Hint != "test hint" {
		t.Error("Hint not set correctly")
	}
}

