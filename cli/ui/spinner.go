package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// SpinnerModel is a bubbletea model for showing progress
type SpinnerModel struct {
	spinner  spinner.Model
	message  string
	finished bool
	success  bool
	result   string
}

// TaskFunc is a function that performs work and returns success/error message
type TaskFunc func() (string, error)

// TaskCompleteMsg signals task completion
type TaskCompleteMsg struct {
	Success bool
	Message string
}

// NewSpinner creates a new spinner with a message
func NewSpinner(message string) SpinnerModel {
	s := spinner.New()
	s.Spinner = spinner.Dot
	s.Style = lipgloss.NewStyle().Foreground(ColorPrimary)

	return SpinnerModel{
		spinner: s,
		message: message,
	}
}

// Init implements tea.Model
func (m SpinnerModel) Init() tea.Cmd {
	return m.spinner.Tick
}

// Update implements tea.Model
func (m SpinnerModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q":
			return m, tea.Quit
		}

	case TaskCompleteMsg:
		m.finished = true
		m.success = msg.Success
		m.result = msg.Message
		return m, tea.Quit

	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}

	return m, nil
}

// View implements tea.Model
func (m SpinnerModel) View() string {
	if m.finished {
		if m.success {
			return "  " + RenderSuccess(m.result) + "\n"
		}
		return "  " + RenderError(m.result) + "\n"
	}
	return "  " + m.spinner.View() + " " + m.message + "\n"
}

// RunWithSpinner executes a task while showing a spinner
func RunWithSpinner(message string, task TaskFunc) error {
	model := NewSpinner(message)
	p := tea.NewProgram(model)

	// Run task in goroutine
	go func() {
		result, err := task()
		if err != nil {
			p.Send(TaskCompleteMsg{Success: false, Message: err.Error()})
		} else {
			p.Send(TaskCompleteMsg{Success: true, Message: result})
		}
	}()

	_, err := p.Run()
	return err
}

// ProgressItem represents a step in a multi-step process
type ProgressItem struct {
	Message string
	Status  string // "pending", "running", "done", "error"
}

// ProgressModel shows multiple steps with their status
type ProgressModel struct {
	Title   string
	Items   []ProgressItem
	current int
	spinner spinner.Model
}

// NewProgress creates a new progress model
func NewProgress(title string, items []string) ProgressModel {
	s := spinner.New()
	s.Spinner = spinner.Dot
	s.Style = lipgloss.NewStyle().Foreground(ColorPrimary)

	progressItems := make([]ProgressItem, len(items))
	for i, msg := range items {
		status := "pending"
		if i == 0 {
			status = "running"
		}
		progressItems[i] = ProgressItem{Message: msg, Status: status}
	}

	return ProgressModel{
		Title:   title,
		Items:   progressItems,
		current: 0,
		spinner: s,
	}
}

// Init implements tea.Model
func (m ProgressModel) Init() tea.Cmd {
	return m.spinner.Tick
}

// StepCompleteMsg signals a step is done
type StepCompleteMsg struct {
	Index   int
	Success bool
}

// Update implements tea.Model
func (m ProgressModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q":
			return m, tea.Quit
		}

	case StepCompleteMsg:
		if msg.Index < len(m.Items) {
			if msg.Success {
				m.Items[msg.Index].Status = "done"
			} else {
				m.Items[msg.Index].Status = "error"
			}

			// Move to next step
			if msg.Index+1 < len(m.Items) {
				m.current = msg.Index + 1
				m.Items[m.current].Status = "running"
			} else {
				// All done
				return m, tea.Quit
			}
		}

	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}

	return m, nil
}

// View implements tea.Model
func (m ProgressModel) View() string {
	var b strings.Builder

	b.WriteString("\n")
	b.WriteString("  " + SubtitleStyle.Render(m.Title) + "\n\n")

	for _, item := range m.Items {
		var prefix string
		switch item.Status {
		case "pending":
			prefix = MutedStyle.Render("○")
		case "running":
			prefix = m.spinner.View()
		case "done":
			prefix = SuccessStyle.Render(IconCheck)
		case "error":
			prefix = ErrorStyle.Render(IconCross)
		}
		b.WriteString(fmt.Sprintf("  %s %s\n", prefix, item.Message))
	}

	return b.String()
}

