package ui

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// RadioItem represents a single radio option
type RadioItem struct {
	Label    string
	Value    string
	Selected bool
	Hint     string
}

// RadioModel is a bubbletea model for single-select radio buttons
type RadioModel struct {
	Title    string
	Items    []RadioItem
	cursor   int
	selected int
	finished bool
}

// NewRadio creates a new radio selection model
func NewRadio(title string, items []RadioItem) RadioModel {
	selected := 0
	for i, item := range items {
		if item.Selected {
			selected = i
			break
		}
	}

	return RadioModel{
		Title:    title,
		Items:    items,
		cursor:   0,
		selected: selected,
		finished: false,
	}
}

// Init implements tea.Model
func (m RadioModel) Init() tea.Cmd {
	return nil
}

// Update implements tea.Model
func (m RadioModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
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
			// Allow going to confirm button
			if m.cursor < len(m.Items) {
				m.cursor++
			}

		case " ":
			// Space selects but keeps browsing
			if m.cursor < len(m.Items) {
				m.selected = m.cursor
			}

		case "enter":
			if m.cursor < len(m.Items) {
				// Select and confirm
				m.selected = m.cursor
			}
			// Always finish on enter (either selecting item or on confirm button)
			m.finished = true
			return m, tea.Quit
		}
	}

	return m, nil
}

// View implements tea.Model
func (m RadioModel) View() string {
	if m.finished {
		return ""
	}

	var b strings.Builder

	// Title
	b.WriteString("\n")
	b.WriteString("  " + SubtitleStyle.Render(m.Title) + "\n")

	// Help text
	b.WriteString("  " + DimStyle.Render("↑/↓ navigate · enter confirm · space preview") + "\n\n")

	// Items
	for i, item := range m.Items {
		focused := i == m.cursor
		selected := i == m.selected
		line := RenderRadio(selected, PadLabel(item.Label, 20), item.Hint, focused)
		b.WriteString("  " + line + "\n")
	}

	// Blank line before confirm
	b.WriteString("\n")

	// Confirm button
	b.WriteString("  " + RenderConfirmButton(m.cursor == len(m.Items)) + "\n")

	return b.String()
}

// SelectedValue returns the value of the selected item
func (m RadioModel) SelectedValue() string {
	if m.selected >= 0 && m.selected < len(m.Items) {
		return m.Items[m.selected].Value
	}
	return ""
}

// SelectedLabel returns the label of the selected item
func (m RadioModel) SelectedLabel() string {
	if m.selected >= 0 && m.selected < len(m.Items) {
		return m.Items[m.selected].Label
	}
	return ""
}

// IsFinished returns whether the selection is complete
func (m RadioModel) IsFinished() bool {
	return m.finished
}

// RunRadio runs the radio selector interactively and returns the selected value
func RunRadio(title string, items []RadioItem) (string, error) {
	model := NewRadio(title, items)
	p := tea.NewProgram(model)

	finalModel, err := p.Run()
	if err != nil {
		return "", fmt.Errorf("radio error: %w", err)
	}

	result := finalModel.(RadioModel)
	return result.SelectedValue(), nil
}

