// Package ui provides terminal UI components for the aidevkit CLI
package ui

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"

	"github.com/charmbracelet/lipgloss"
)

// Color palette - Official Databricks brand colors
var (
	// Databricks brand colors
	ColorLava     = lipgloss.Color("#FF3621") // Lava 600 - Primary
	ColorNavy     = lipgloss.Color("#0B2026") // Navy 900
	ColorOatMed   = lipgloss.Color("#EEEDE9") // Oat Medium
	ColorOatLight = lipgloss.Color("#F9F7F4") // Oat Light

	// Primary colors (mapped to brand)
	ColorPrimary   = ColorLava
	ColorSecondary = ColorNavy
	ColorAccent    = lipgloss.Color("#00A972") // Green for success

	// Semantic colors
	ColorSuccess = lipgloss.Color("#00A972") // Green
	ColorWarning = lipgloss.Color("#F2994A") // Orange
	ColorError   = lipgloss.Color("#EB5757") // Red
	ColorInfo    = lipgloss.Color("#56CCF2") // Light blue

	// Neutral colors
	ColorMuted   = lipgloss.Color("#6B7280") // Gray for hints
	ColorSubtle  = ColorNavy                 // Navy for subtle elements
	ColorText    = ColorOatLight             // Oat Light for text
	ColorDimText = lipgloss.Color("#9CA3AF") // Dimmed text
)

// Text styles
var (
	// Title style for headers
	TitleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorText).
			MarginBottom(1)

	// Subtitle for section headers
	SubtitleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorPrimary)

	// Normal text
	TextStyle = lipgloss.NewStyle().
			Foreground(ColorText)

	// Dimmed text for hints and secondary info
	DimStyle = lipgloss.NewStyle().
			Foreground(ColorDimText)

	// Muted style for less important text
	MutedStyle = lipgloss.NewStyle().
			Foreground(ColorMuted)
)

// Status indicator styles
var (
	// Success checkmark
	SuccessStyle = lipgloss.NewStyle().
			Foreground(ColorSuccess)

	// Warning style
	WarningStyle = lipgloss.NewStyle().
			Foreground(ColorWarning)

	// Error style
	ErrorStyle = lipgloss.NewStyle().
			Foreground(ColorError)

	// Info style
	InfoStyle = lipgloss.NewStyle().
			Foreground(ColorInfo)
)

// Interactive element styles
var (
	// Selected/focused item
	SelectedStyle = lipgloss.NewStyle().
			Foreground(ColorPrimary).
			Bold(true)

	// Cursor indicator
	CursorStyle = lipgloss.NewStyle().
			Foreground(ColorInfo).
			Bold(true)

	// Active/enabled checkbox
	ActiveStyle = lipgloss.NewStyle().
			Foreground(ColorSuccess)

	// Inactive checkbox
	InactiveStyle = lipgloss.NewStyle().
			Foreground(ColorMuted)

	// Button style (for Confirm, etc.)
	ButtonStyle = lipgloss.NewStyle().
			Foreground(ColorSuccess).
			Bold(true)

	// Inactive button
	ButtonInactiveStyle = lipgloss.NewStyle().
				Foreground(ColorMuted)
)

// Box and container styles
var (
	// Box with border
	BoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ColorSubtle).
			Padding(1, 2)

	// Summary box
	SummaryBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ColorPrimary).
			Padding(1, 2).
			MarginTop(1).
			MarginBottom(1)

	// Header box
	HeaderBoxStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorText).
			Background(ColorSecondary).
			Padding(0, 2).
			MarginBottom(1)
)

// Status indicators (icons)
const (
	IconCheck   = "✓"
	IconCross   = "✗"
	IconWarning = "!"
	IconArrow   = "❯"
	IconDot     = "●"
	IconCircle  = "○"
	IconSquare  = "■"
	IconEmpty   = "□"
)

// Render helpers
func RenderSuccess(text string) string {
	return SuccessStyle.Render(IconCheck) + " " + text
}

func RenderError(text string) string {
	return ErrorStyle.Render(IconCross) + " " + text
}

func RenderWarning(text string) string {
	return WarningStyle.Render(IconWarning) + " " + text
}

func RenderInfo(text string) string {
	return InfoStyle.Render("•") + " " + text
}

func RenderStep(text string) string {
	return SubtitleStyle.Render(text)
}

func RenderHint(text string) string {
	return DimStyle.Render(text)
}

// Checkbox rendering
func RenderCheckbox(checked bool, label string, hint string, focused bool) string {
	var checkbox string
	if checked {
		checkbox = ActiveStyle.Render("[" + IconCheck + "]")
	} else {
		checkbox = InactiveStyle.Render("[ ]")
	}

	var cursor string
	if focused {
		cursor = CursorStyle.Render(IconArrow) + " "
	} else {
		cursor = "  "
	}

	var hintText string
	if hint != "" {
		if checked {
			hintText = " " + ActiveStyle.Render(hint)
		} else {
			hintText = " " + MutedStyle.Render(hint)
		}
	}

	return cursor + checkbox + " " + label + hintText
}

// Radio button rendering
func RenderRadio(selected bool, label string, hint string, focused bool) string {
	var radio string
	if selected {
		radio = ActiveStyle.Render("(" + IconDot + ")")
	} else {
		radio = InactiveStyle.Render("(" + IconCircle + ")")
	}

	var cursor string
	if focused {
		cursor = CursorStyle.Render(IconArrow) + " "
	} else {
		cursor = "  "
	}

	var hintText string
	if hint != "" {
		if selected {
			hintText = " " + ActiveStyle.Render(hint)
		} else {
			hintText = " " + MutedStyle.Render(hint)
		}
	}

	return cursor + radio + " " + label + hintText
}

// Render confirm button
func RenderConfirmButton(focused bool) string {
	if focused {
		return CursorStyle.Render(IconArrow) + " " + ButtonStyle.Render("[ Confirm ]")
	}
	return "  " + ButtonInactiveStyle.Render("[ Confirm ]")
}

// Padded label for alignment
func PadLabel(label string, width int) string {
	if len(label) >= width {
		return label
	}
	return label + lipgloss.NewStyle().Width(width-len(label)).Render("")
}

// ClearScreen clears the terminal screen and positions cursor with padding
func ClearScreen() {
	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		cmd = exec.Command("cmd", "/c", "cls")
	} else {
		cmd = exec.Command("clear")
	}
	cmd.Stdout = os.Stdout
	cmd.Run()
	// Fallback: ANSI escape codes
	fmt.Print("\033[H\033[2J")
	// Add vertical padding at top
	fmt.Println()
	fmt.Println()
}

// DatabricksLogo is the ASCII art text logo
const DatabricksLogo = `
  ██████╗  █████╗ ████████╗ █████╗ ██████╗ ██████╗ ██╗ ██████╗██╗  ██╗███████╗
  ██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██║██╔════╝██║ ██╔╝██╔════╝
  ██║  ██║███████║   ██║   ███████║██████╔╝██████╔╝██║██║     █████╔╝ ███████╗
  ██║  ██║██╔══██║   ██║   ██╔══██║██╔══██╗██╔══██╗██║██║     ██╔═██╗ ╚════██║
  ██████╔╝██║  ██║   ██║   ██║  ██║██████╔╝██║  ██║██║╚██████╗██║  ██╗███████║
  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝
`

// LogoStyle styles the ASCII logo
var LogoStyle = lipgloss.NewStyle().
	Foreground(ColorPrimary).
	Bold(true)

// SubtitleLogoStyle for the subtitle under the logo
var SubtitleLogoStyle = lipgloss.NewStyle().
	Foreground(ColorDimText)

// PrintLogo prints the Databricks ASCII logo with styling
func PrintLogo() {
	fmt.Println(LogoStyle.Render(DatabricksLogo))
	fmt.Println(SubtitleLogoStyle.Render("                    ─────  AI Dev Kit Installer  ─────"))
	fmt.Println()
}

