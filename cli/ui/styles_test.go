package ui

import (
	"strings"
	"testing"
)

func TestRenderSuccess(t *testing.T) {
	result := RenderSuccess("test message")

	if !strings.Contains(result, IconCheck) {
		t.Error("RenderSuccess should contain check icon")
	}

	if !strings.Contains(result, "test message") {
		t.Error("RenderSuccess should contain the message")
	}
}

func TestRenderError(t *testing.T) {
	result := RenderError("error message")

	if !strings.Contains(result, IconCross) {
		t.Error("RenderError should contain cross icon")
	}

	if !strings.Contains(result, "error message") {
		t.Error("RenderError should contain the message")
	}
}

func TestRenderWarning(t *testing.T) {
	result := RenderWarning("warning message")

	if !strings.Contains(result, IconWarning) {
		t.Error("RenderWarning should contain warning icon")
	}

	if !strings.Contains(result, "warning message") {
		t.Error("RenderWarning should contain the message")
	}
}

func TestRenderInfo(t *testing.T) {
	result := RenderInfo("info message")

	if !strings.Contains(result, "info message") {
		t.Error("RenderInfo should contain the message")
	}
}

func TestRenderStep(t *testing.T) {
	result := RenderStep("step title")

	if !strings.Contains(result, "step title") {
		t.Error("RenderStep should contain the title")
	}
}

func TestRenderHint(t *testing.T) {
	result := RenderHint("hint text")

	if !strings.Contains(result, "hint text") {
		t.Error("RenderHint should contain the text")
	}
}

func TestRenderCheckbox(t *testing.T) {
	tests := []struct {
		name     string
		checked  bool
		label    string
		hint     string
		focused  bool
		contains []string
	}{
		{
			name:     "checked focused",
			checked:  true,
			label:    "Option A",
			hint:     "selected",
			focused:  true,
			contains: []string{IconCheck, "Option A", IconArrow},
		},
		{
			name:     "unchecked not focused",
			checked:  false,
			label:    "Option B",
			hint:     "",
			focused:  false,
			contains: []string{"[ ]", "Option B"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := RenderCheckbox(tt.checked, tt.label, tt.hint, tt.focused)
			for _, s := range tt.contains {
				if !strings.Contains(result, s) {
					t.Errorf("RenderCheckbox should contain %q, got: %s", s, result)
				}
			}
		})
	}
}

func TestRenderRadio(t *testing.T) {
	tests := []struct {
		name     string
		selected bool
		label    string
		hint     string
		focused  bool
		contains []string
	}{
		{
			name:     "selected focused",
			selected: true,
			label:    "Option A",
			hint:     "default",
			focused:  true,
			contains: []string{IconDot, "Option A", IconArrow},
		},
		{
			name:     "not selected not focused",
			selected: false,
			label:    "Option B",
			hint:     "",
			focused:  false,
			contains: []string{IconCircle, "Option B"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := RenderRadio(tt.selected, tt.label, tt.hint, tt.focused)
			for _, s := range tt.contains {
				if !strings.Contains(result, s) {
					t.Errorf("RenderRadio should contain %q, got: %s", s, result)
				}
			}
		})
	}
}

func TestRenderConfirmButton(t *testing.T) {
	// Focused
	result := RenderConfirmButton(true)
	if !strings.Contains(result, "Confirm") {
		t.Error("RenderConfirmButton should contain 'Confirm'")
	}
	if !strings.Contains(result, IconArrow) {
		t.Error("Focused confirm button should show arrow")
	}

	// Not focused
	result = RenderConfirmButton(false)
	if !strings.Contains(result, "Confirm") {
		t.Error("RenderConfirmButton should contain 'Confirm'")
	}
}

func TestPadLabel(t *testing.T) {
	tests := []struct {
		label    string
		width    int
		expected int
	}{
		{"short", 10, 10},
		{"exactly10!", 10, 10},
		{"longer than width", 10, 17}, // Returns original length if longer
	}

	for _, tt := range tests {
		t.Run(tt.label, func(t *testing.T) {
			result := PadLabel(tt.label, tt.width)
			// Note: lipgloss might add escape sequences, so we check minimum length
			if len(result) < len(tt.label) {
				t.Errorf("PadLabel result too short: %d < %d", len(result), len(tt.label))
			}
		})
	}
}

func TestDatabricksLogo(t *testing.T) {
	// Logo should be non-empty
	if DatabricksLogo == "" {
		t.Error("DatabricksLogo should not be empty")
	}

	// Logo should contain DATABRICKS text (ASCII art)
	// The logo uses block characters to spell out DATABRICKS
	if !strings.Contains(DatabricksLogo, "█") {
		t.Error("DatabricksLogo should contain block characters")
	}
}

func TestIcons(t *testing.T) {
	// Verify icon constants are defined
	icons := map[string]string{
		"IconCheck":   IconCheck,
		"IconCross":   IconCross,
		"IconWarning": IconWarning,
		"IconArrow":   IconArrow,
		"IconDot":     IconDot,
		"IconCircle":  IconCircle,
		"IconSquare":  IconSquare,
		"IconEmpty":   IconEmpty,
	}

	for name, icon := range icons {
		if icon == "" {
			t.Errorf("%s should not be empty", name)
		}
	}
}

func TestStyles(t *testing.T) {
	// Test that styles can be used without panic
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("Style rendering panicked: %v", r)
		}
	}()

	// Test various styles
	_ = TitleStyle.Render("Title")
	_ = SubtitleStyle.Render("Subtitle")
	_ = TextStyle.Render("Text")
	_ = DimStyle.Render("Dim")
	_ = MutedStyle.Render("Muted")
	_ = SuccessStyle.Render("Success")
	_ = WarningStyle.Render("Warning")
	_ = ErrorStyle.Render("Error")
	_ = InfoStyle.Render("Info")
	_ = SelectedStyle.Render("Selected")
	_ = CursorStyle.Render("Cursor")
	_ = ActiveStyle.Render("Active")
	_ = InactiveStyle.Render("Inactive")
	_ = ButtonStyle.Render("Button")
	_ = ButtonInactiveStyle.Render("ButtonInactive")
	_ = BoxStyle.Render("Box")
	_ = SummaryBoxStyle.Render("SummaryBox")
	_ = HeaderBoxStyle.Render("Header")
	_ = LogoStyle.Render("Logo")
	_ = SubtitleLogoStyle.Render("SubtitleLogo")
}

