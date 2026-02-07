package ui

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// CheckboxItem represents a single checkbox option
type CheckboxItem struct {
	Label    string
	Value    string
	Checked  bool
	Hint     string
	Disabled bool
}

// CheckboxModel is a bubbletea model for multi-select checkboxes
type CheckboxModel struct {
	Title    string
	Items    []CheckboxItem
	cursor   int
	finished bool
}

// NewCheckbox creates a new checkbox selection model
func NewCheckbox(title string, items []CheckboxItem) CheckboxModel {
	return CheckboxModel{
		Title:    title,
		Items:    items,
		cursor:   0,
		finished: false,
	}
}

// Init implements tea.Model
func (m CheckboxModel) Init() tea.Cmd {
	return nil
}

// Update implements tea.Model
func (m CheckboxModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q":
			return m, tea.Quit

		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}

		case "down", "j":
			// Allow going to confirm button (cursor == len(items))
			if m.cursor < len(m.Items) {
				m.cursor++
			}

		case " ":
			// Toggle checkbox if on an item
			if m.cursor < len(m.Items) && !m.Items[m.cursor].Disabled {
				m.Items[m.cursor].Checked = !m.Items[m.cursor].Checked
			}

		case "enter":
			if m.cursor < len(m.Items) && !m.Items[m.cursor].Disabled {
				// Toggle and stay
				m.Items[m.cursor].Checked = !m.Items[m.cursor].Checked
			} else if m.cursor == len(m.Items) {
				// On confirm button - finish
				m.finished = true
				return m, tea.Quit
			}
		}
	}

	return m, nil
}

// View implements tea.Model
func (m CheckboxModel) View() string {
	if m.finished {
		return ""
	}

	var b strings.Builder

	// Title
	b.WriteString("\n")
	b.WriteString("  " + SubtitleStyle.Render(m.Title) + "\n")

	// Help text
	b.WriteString("  " + DimStyle.Render("↑/↓ navigate · space/enter toggle · enter on Confirm to finish") + "\n\n")

	// Items
	for i, item := range m.Items {
		focused := i == m.cursor
		line := RenderCheckbox(item.Checked, PadLabel(item.Label, 16), item.Hint, focused)
		b.WriteString("  " + line + "\n")
	}

	// Blank line before confirm
	b.WriteString("\n")

	// Confirm button
	b.WriteString("  " + RenderConfirmButton(m.cursor == len(m.Items)) + "\n")

	return b.String()
}

// Selected returns the values of all checked items
func (m CheckboxModel) Selected() []string {
	var selected []string
	for _, item := range m.Items {
		if item.Checked {
			selected = append(selected, item.Value)
		}
	}
	return selected
}

// SelectedString returns selected values as space-separated string
func (m CheckboxModel) SelectedString() string {
	return strings.Join(m.Selected(), " ")
}

// IsFinished returns whether the selection is complete
func (m CheckboxModel) IsFinished() bool {
	return m.finished
}

// RunCheckbox runs the checkbox interactively and returns selected values
func RunCheckbox(title string, items []CheckboxItem) ([]string, error) {
	model := NewCheckbox(title, items)
	p := tea.NewProgram(model)

	finalModel, err := p.Run()
	if err != nil {
		return nil, fmt.Errorf("checkbox error: %w", err)
	}

	result := finalModel.(CheckboxModel)
	return result.Selected(), nil
}

