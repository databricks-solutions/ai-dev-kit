package ui

import (
	"strings"
	"testing"

	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
)

func TestNewSpinner(t *testing.T) {
	model := NewSpinner("Loading...")

	if model.message != "Loading..." {
		t.Errorf("Expected message 'Loading...', got %s", model.message)
	}

	if model.finished {
		t.Error("Should not be finished initially")
	}
}

func TestSpinnerModel_Init(t *testing.T) {
	model := NewSpinner("Test")
	cmd := model.Init()

	// Init should return a spinner tick command
	if cmd == nil {
		t.Error("Init should return a command for spinner tick")
	}
}

func TestSpinnerModel_Update_TaskComplete(t *testing.T) {
	model := NewSpinner("Loading...")

	// Send success message
	newModel, cmd := model.Update(TaskCompleteMsg{Success: true, Message: "Done!"})
	model = newModel.(SpinnerModel)

	if !model.finished {
		t.Error("Should be finished after task complete")
	}

	if !model.success {
		t.Error("Should be success")
	}

	if model.result != "Done!" {
		t.Errorf("Result should be 'Done!', got %s", model.result)
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestSpinnerModel_Update_TaskFailed(t *testing.T) {
	model := NewSpinner("Loading...")

	// Send failure message
	newModel, cmd := model.Update(TaskCompleteMsg{Success: false, Message: "Error occurred"})
	model = newModel.(SpinnerModel)

	if !model.finished {
		t.Error("Should be finished after task complete")
	}

	if model.success {
		t.Error("Should not be success")
	}

	if model.result != "Error occurred" {
		t.Errorf("Result should be 'Error occurred', got %s", model.result)
	}

	if cmd == nil {
		t.Error("Should return quit command")
	}
}

func TestSpinnerModel_Update_SpinnerTick(t *testing.T) {
	model := NewSpinner("Loading...")

	// Send spinner tick message
	newModel, cmd := model.Update(spinner.TickMsg{})
	model = newModel.(SpinnerModel)

	// Should not be finished
	if model.finished {
		t.Error("Should not be finished on spinner tick")
	}

	// Should return another tick command
	if cmd == nil {
		t.Error("Should return tick command")
	}
}

func TestSpinnerModel_Update_Quit(t *testing.T) {
	model := NewSpinner("Loading...")

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

func TestSpinnerModel_View(t *testing.T) {
	model := NewSpinner("Loading...")
	view := model.View()

	// Should contain the message
	if !strings.Contains(view, "Loading...") {
		t.Error("View should contain the message")
	}

	// After success
	model.finished = true
	model.success = true
	model.result = "Success!"
	view = model.View()

	if !strings.Contains(view, "Success!") {
		t.Error("Success view should contain result")
	}

	if !strings.Contains(view, IconCheck) {
		t.Error("Success view should contain check icon")
	}

	// After failure
	model.success = false
	model.result = "Failed!"
	view = model.View()

	if !strings.Contains(view, "Failed!") {
		t.Error("Failure view should contain result")
	}

	if !strings.Contains(view, IconCross) {
		t.Error("Failure view should contain cross icon")
	}
}

func TestTaskCompleteMsg(t *testing.T) {
	successMsg := TaskCompleteMsg{Success: true, Message: "Done"}
	if !successMsg.Success {
		t.Error("Success should be true")
	}
	if successMsg.Message != "Done" {
		t.Error("Message should be 'Done'")
	}

	failMsg := TaskCompleteMsg{Success: false, Message: "Error"}
	if failMsg.Success {
		t.Error("Success should be false")
	}
	if failMsg.Message != "Error" {
		t.Error("Message should be 'Error'")
	}
}

func TestNewProgress(t *testing.T) {
	items := []string{"Step 1", "Step 2", "Step 3"}
	model := NewProgress("Progress Test", items)

	if model.Title != "Progress Test" {
		t.Errorf("Expected title 'Progress Test', got %s", model.Title)
	}

	if len(model.Items) != 3 {
		t.Errorf("Expected 3 items, got %d", len(model.Items))
	}

	if model.current != 0 {
		t.Errorf("Expected current at 0, got %d", model.current)
	}

	// First item should be running
	if model.Items[0].Status != "running" {
		t.Errorf("First item should be 'running', got %s", model.Items[0].Status)
	}

	// Other items should be pending
	if model.Items[1].Status != "pending" {
		t.Errorf("Second item should be 'pending', got %s", model.Items[1].Status)
	}
}

func TestProgressModel_Init(t *testing.T) {
	model := NewProgress("Test", []string{"Step 1"})
	cmd := model.Init()

	// Init should return a spinner tick command
	if cmd == nil {
		t.Error("Init should return a command")
	}
}

func TestProgressModel_Update_StepComplete(t *testing.T) {
	model := NewProgress("Test", []string{"Step 1", "Step 2", "Step 3"})

	// Complete step 0
	newModel, _ := model.Update(StepCompleteMsg{Index: 0, Success: true})
	model = newModel.(ProgressModel)

	if model.Items[0].Status != "done" {
		t.Errorf("Step 0 should be 'done', got %s", model.Items[0].Status)
	}

	if model.Items[1].Status != "running" {
		t.Errorf("Step 1 should be 'running', got %s", model.Items[1].Status)
	}

	if model.current != 1 {
		t.Errorf("Current should be 1, got %d", model.current)
	}
}

func TestProgressModel_Update_StepFailed(t *testing.T) {
	model := NewProgress("Test", []string{"Step 1", "Step 2"})

	// Fail step 0
	newModel, _ := model.Update(StepCompleteMsg{Index: 0, Success: false})
	model = newModel.(ProgressModel)

	if model.Items[0].Status != "error" {
		t.Errorf("Step 0 should be 'error', got %s", model.Items[0].Status)
	}
}

func TestProgressModel_Update_LastStep(t *testing.T) {
	model := NewProgress("Test", []string{"Step 1"})

	// Complete last step
	newModel, cmd := model.Update(StepCompleteMsg{Index: 0, Success: true})
	model = newModel.(ProgressModel)

	if model.Items[0].Status != "done" {
		t.Errorf("Step 0 should be 'done', got %s", model.Items[0].Status)
	}

	// Should quit after last step
	if cmd == nil {
		t.Error("Should return quit command after last step")
	}
}

func TestProgressModel_View(t *testing.T) {
	model := NewProgress("Progress Test", []string{"Step 1", "Step 2"})
	view := model.View()

	// Should contain title
	if !strings.Contains(view, "Progress Test") {
		t.Error("View should contain title")
	}

	// Should contain steps
	if !strings.Contains(view, "Step 1") {
		t.Error("View should contain Step 1")
	}

	if !strings.Contains(view, "Step 2") {
		t.Error("View should contain Step 2")
	}
}

func TestProgressItem(t *testing.T) {
	item := ProgressItem{
		Message: "Test Step",
		Status:  "running",
	}

	if item.Message != "Test Step" {
		t.Error("Message not set correctly")
	}

	if item.Status != "running" {
		t.Error("Status not set correctly")
	}
}

func TestStepCompleteMsg(t *testing.T) {
	msg := StepCompleteMsg{Index: 2, Success: true}

	if msg.Index != 2 {
		t.Error("Index should be 2")
	}

	if !msg.Success {
		t.Error("Success should be true")
	}
}

