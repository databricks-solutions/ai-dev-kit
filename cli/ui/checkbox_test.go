package ui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestNewCheckbox(t *testing.T) {
	items := []CheckboxItem{
		{Label: "Option 1", Value: "opt1", Checked: true},
		{Label: "Option 2", Value: "opt2", Checked: false},
	}

	model := NewCheckbox("Test Title", items)

	if model.Title != "Test Title" {
		t.Errorf("Expected title 'Test Title', got %s", model.Title)
	}

	if len(model.Items) != 2 {
		t.Errorf("Expected 2 items, got %d", len(model.Items))
	}

	if model.cursor != 0 {
		t.Errorf("Expected cursor at 0, got %d", model.cursor)
	}

	if model.finished {
		t.Error("Should not be finished initially")
	}
}

func TestCheckboxModel_Init(t *testing.T) {
	model := NewCheckbox("Test", []CheckboxItem{})
	cmd := model.Init()

	if cmd != nil {
		t.Error("Init should return nil")
	}
}

func TestCheckboxModel_Update(t *testing.T) {
	items := []CheckboxItem{
		{Label: "Option 1", Value: "opt1", Checked: false},
		{Label: "Option 2", Value: "opt2", Checked: false},
		{Label: "Option 3", Value: "opt3", Checked: false, Disabled: true},
	}

	model := NewCheckbox("Test", items)

	// Test down navigation
	newModel, _ := model.Update(tea.KeyMsg{Type: tea.KeyDown})
	model = newModel.(CheckboxModel)
	if model.cursor != 1 {
		t.Errorf("After down, cursor should be 1, got %d", model.cursor)
	}

	// Test up navigation
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyUp})
	model = newModel.(CheckboxModel)
	if model.cursor != 0 {
		t.Errorf("After up, cursor should be 0, got %d", model.cursor)
	}

	// Test space to toggle
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeySpace})
	model = newModel.(CheckboxModel)
	if !model.Items[0].Checked {
		t.Error("Item should be checked after space")
	}

	// Toggle again
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeySpace})
	model = newModel.(CheckboxModel)
	if model.Items[0].Checked {
		t.Error("Item should be unchecked after second space")
	}

	// Test j/k navigation
	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	model = newModel.(CheckboxModel)
	if model.cursor != 1 {
		t.Errorf("After j, cursor should be 1, got %d", model.cursor)
	}

	newModel, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'k'}})
	model = newModel.(CheckboxModel)
	if model.cursor != 0 {
		t.Errorf("After k, cursor should be 0, got %d", model.cursor)
	}
}

func TestCheckboxModel_Update_Disabled(t *testing.T) {
	items := []CheckboxItem{
		{Label: "Disabled", Value: "disabled", Checked: false, Disabled: true},
	}

	model := NewCheckbox("Test", items)

	// Space on disabled item should not toggle
	newModel, _ := model.Update(tea.KeyMsg{Type: tea.KeySpace})
	model = newModel.(CheckboxModel)
	if model.Items[0].Checked {
		t.Error("Disabled item should not be toggled")
	}
}

func TestCheckboxModel_Update_Confirm(t *testing.T) {
	items := []CheckboxItem{
		{Label: "Option 1", Value: "opt1", Checked: true},
	}

	model := NewCheckbox("Test", items)

	// Move to confirm button (index = len(items))
	model.cursor = len(items)

	// Press enter on confirm
	newModel, cmd := model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model = newModel.(CheckboxModel)

	if !model.finished {
		t.Error("Should be finished after enter on confirm")
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestCheckboxModel_View(t *testing.T) {
	items := []CheckboxItem{
		{Label: "Option 1", Value: "opt1", Checked: true, Hint: "selected"},
		{Label: "Option 2", Value: "opt2", Checked: false},
	}

	model := NewCheckbox("Test Title", items)
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

func TestCheckboxModel_Selected(t *testing.T) {
	items := []CheckboxItem{
		{Label: "Option 1", Value: "opt1", Checked: true},
		{Label: "Option 2", Value: "opt2", Checked: false},
		{Label: "Option 3", Value: "opt3", Checked: true},
	}

	model := NewCheckbox("Test", items)
	selected := model.Selected()

	if len(selected) != 2 {
		t.Errorf("Expected 2 selected, got %d", len(selected))
	}

	// Check values
	expectedValues := map[string]bool{"opt1": true, "opt3": true}
	for _, v := range selected {
		if !expectedValues[v] {
			t.Errorf("Unexpected selected value: %s", v)
		}
	}
}

func TestCheckboxModel_SelectedString(t *testing.T) {
	items := []CheckboxItem{
		{Label: "Option 1", Value: "opt1", Checked: true},
		{Label: "Option 2", Value: "opt2", Checked: true},
	}

	model := NewCheckbox("Test", items)
	str := model.SelectedString()

	if str != "opt1 opt2" {
		t.Errorf("Expected 'opt1 opt2', got %s", str)
	}
}

func TestCheckboxModel_IsFinished(t *testing.T) {
	model := NewCheckbox("Test", []CheckboxItem{})

	if model.IsFinished() {
		t.Error("Should not be finished initially")
	}

	model.finished = true
	if !model.IsFinished() {
		t.Error("Should be finished after setting flag")
	}
}

func TestCheckboxItem(t *testing.T) {
	item := CheckboxItem{
		Label:    "Test Label",
		Value:    "test-value",
		Checked:  true,
		Hint:     "test hint",
		Disabled: false,
	}

	if item.Label != "Test Label" {
		t.Error("Label not set correctly")
	}

	if item.Value != "test-value" {
		t.Error("Value not set correctly")
	}

	if !item.Checked {
		t.Error("Checked not set correctly")
	}

	if item.Hint != "test hint" {
		t.Error("Hint not set correctly")
	}

	if item.Disabled {
		t.Error("Disabled not set correctly")
	}
}

