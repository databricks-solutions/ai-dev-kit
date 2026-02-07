package ui

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// SummaryItem represents a key-value pair in the summary
type SummaryItem struct {
	Key   string
	Value string
}

// SummaryModel displays an installation summary with confirmation
type SummaryModel struct {
	Title     string
	Items     []SummaryItem
	cursor    int
	confirmed bool
	cancelled bool
}

// NewSummary creates a new summary model
func NewSummary(title string, items []SummaryItem) SummaryModel {
	return SummaryModel{
		Title:  title,
		Items:  items,
		cursor: 0, // 0 = Yes, 1 = No
	}
}

// Init implements tea.Model
func (m SummaryModel) Init() tea.Cmd {
	return nil
}

// Update implements tea.Model
func (m SummaryModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q":
			m.cancelled = true
			return m, tea.Quit

		case "left", "h":
			if m.cursor > 0 {
				m.cursor--
			}

		case "right", "l":
			if m.cursor < 1 {
				m.cursor++
			}

		case "y", "Y":
			m.confirmed = true
			return m, tea.Quit

		case "n", "N":
			m.cancelled = true
			return m, tea.Quit

		case "enter":
			if m.cursor == 0 {
				m.confirmed = true
			} else {
				m.cancelled = true
			}
			return m, tea.Quit
		}
	}

	return m, nil
}

// View implements tea.Model
func (m SummaryModel) View() string {
	if m.confirmed || m.cancelled {
		return ""
	}

	var b strings.Builder

	b.WriteString("\n")
	b.WriteString("  " + SubtitleStyle.Render(m.Title) + "\n")
	b.WriteString("  " + strings.Repeat("─", 40) + "\n")

	// Key-value pairs
	for _, item := range m.Items {
		b.WriteString(fmt.Sprintf("  %-14s %s\n",
			item.Key+":",
			ActiveStyle.Render(item.Value)))
	}

	b.WriteString("\n")

	// Confirmation buttons
	var yesBtn, noBtn string
	if m.cursor == 0 {
		yesBtn = ButtonStyle.Render("[ Yes ]")
		noBtn = ButtonInactiveStyle.Render("[ No ]")
	} else {
		yesBtn = ButtonInactiveStyle.Render("[ Yes ]")
		noBtn = ButtonStyle.Render("[ No ]")
	}

	b.WriteString("  Proceed with installation? " + yesBtn + " " + noBtn + "\n")
	b.WriteString("  " + DimStyle.Render("←/→ select · y/n · enter confirm") + "\n")

	return b.String()
}

// IsConfirmed returns true if user confirmed
func (m SummaryModel) IsConfirmed() bool {
	return m.confirmed
}

// IsCancelled returns true if user cancelled
func (m SummaryModel) IsCancelled() bool {
	return m.cancelled
}

// RunSummary runs the summary confirmation interactively
func RunSummary(title string, items []SummaryItem) (bool, error) {
	model := NewSummary(title, items)
	p := tea.NewProgram(model)

	finalModel, err := p.Run()
	if err != nil {
		return false, fmt.Errorf("summary error: %w", err)
	}

	result := finalModel.(SummaryModel)
	return result.IsConfirmed(), nil
}

// PrintSummary prints a non-interactive summary (for silent mode or after confirmation)
func PrintSummary(title string, items []SummaryItem) {
	fmt.Println()
	fmt.Println("  " + SubtitleStyle.Render(title))
	fmt.Println("  " + strings.Repeat("─", 40))

	for _, item := range items {
		fmt.Printf("  %-14s %s\n",
			item.Key+":",
			ActiveStyle.Render(item.Value))
	}
	fmt.Println()
}

// PrintCompletionMessage prints the installation complete message with next steps
func PrintCompletionMessage(profile string, tools []string, installDir string) {
	fmt.Println()
	fmt.Println(SuccessStyle.Render("  Installation complete!"))
	fmt.Println("  " + strings.Repeat("─", 40))
	fmt.Println()

	step := 1
	fmt.Printf("  %d. Configure profile %s or set environment variables DATABRICKS_HOST and DATABRICKS_TOKEN\n", step, profile)
	fmt.Printf("     Authenticate: %s\n", InfoStyle.Render(fmt.Sprintf("databricks auth login --profile %s", profile)))
	step++

	// Tool-specific instructions
	for _, tool := range tools {
		switch tool {
		case "cursor":
			fmt.Printf("  %d. Enable MCP in Cursor: %s\n", step, TextStyle.Render("Cursor → Settings → Cursor Settings → Tools & MCP → Toggle 'databricks'"))
			step++
		case "copilot":
			fmt.Printf("  %d. In Copilot Chat, click %s (tool icon, bottom-right) and enable %s\n", step, TextStyle.Render("Configure Tools"), TextStyle.Render("databricks"))
			step++
			fmt.Printf("  %d. Use Copilot in %s to access Databricks skills and MCP tools\n", step, TextStyle.Render("Agent mode"))
			step++
		}
	}

	fmt.Printf("  %d. Open your project in your tool of choice\n", step)
	step++
	fmt.Printf("  %d. Try: %s\n", step, InfoStyle.Render("\"List my SQL warehouses\""))
	fmt.Println()
}

