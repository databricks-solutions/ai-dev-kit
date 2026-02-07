package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
)

// PromptModel is a bubbletea model for text input with a default value
type PromptModel struct {
	Title       string
	Description string
	Default     string
	textInput   textinput.Model
	finished    bool
	value       string
}

// NewPrompt creates a new text input prompt
func NewPrompt(title, description, defaultValue string) PromptModel {
	ti := textinput.New()
	ti.Placeholder = defaultValue
	ti.Focus()
	ti.CharLimit = 256
	ti.Width = 50

	return PromptModel{
		Title:       title,
		Description: description,
		Default:     defaultValue,
		textInput:   ti,
		finished:    false,
	}
}

// Init implements tea.Model
func (m PromptModel) Init() tea.Cmd {
	return textinput.Blink
}

// Update implements tea.Model
func (m PromptModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			return m, tea.Quit

		case "enter":
			m.finished = true
			m.value = m.textInput.Value()
			if m.value == "" {
				m.value = m.Default
			}
			return m, tea.Quit
		}
	}

	m.textInput, cmd = m.textInput.Update(msg)
	return m, cmd
}

// View implements tea.Model
func (m PromptModel) View() string {
	if m.finished {
		return ""
	}

	var b strings.Builder

	// Title
	b.WriteString("\n")
	b.WriteString("  " + SubtitleStyle.Render(m.Title) + "\n")

	// Description
	if m.Description != "" {
		b.WriteString("  " + DimStyle.Render(m.Description) + "\n")
	}

	b.WriteString("\n")

	// Input field
	b.WriteString("  " + m.textInput.View() + "\n")

	// Default hint
	b.WriteString("  " + DimStyle.Render(fmt.Sprintf("Press Enter for default: %s", m.Default)) + "\n")

	return b.String()
}

// Value returns the input value (or default if empty)
func (m PromptModel) Value() string {
	if m.value == "" {
		return m.Default
	}
	return m.value
}

// IsFinished returns whether input is complete
func (m PromptModel) IsFinished() bool {
	return m.finished
}

// RunPrompt runs the text input interactively and returns the value
func RunPrompt(title, description, defaultValue string) (string, error) {
	model := NewPrompt(title, description, defaultValue)
	p := tea.NewProgram(model)

	finalModel, err := p.Run()
	if err != nil {
		return "", fmt.Errorf("prompt error: %w", err)
	}

	result := finalModel.(PromptModel)
	return result.Value(), nil
}

// SimplePrompt displays a simple prompt and returns the input (non-TUI fallback)
func SimplePrompt(prompt, defaultValue string) string {
	fmt.Printf("  %s [%s]: ", prompt, defaultValue)
	var input string
	fmt.Scanln(&input)
	if input == "" {
		return defaultValue
	}
	return input
}

