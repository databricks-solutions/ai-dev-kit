package cmd

import (
	"strings"
	"testing"
)

func TestLaunchCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "launch", "--help")
	if err != nil {
		t.Fatalf("Launch help failed: %v", err)
	}

	expectedStrings := []string{
		"Launch standalone AI Dev Kit projects",
		"starter",
		"builder",
	}

	for _, s := range expectedStrings {
		if !strings.Contains(output, s) {
			t.Errorf("Launch help should contain %q", s)
		}
	}
}

func TestLaunchStarterCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "launch", "starter", "--help")
	if err != nil {
		t.Fatalf("Launch starter help failed: %v", err)
	}

	expectedStrings := []string{
		"AI Dev Project",
		"--copy-to",
		"--profile",
	}

	for _, s := range expectedStrings {
		if !strings.Contains(output, s) {
			t.Errorf("Launch starter help should contain %q", s)
		}
	}
}

func TestLaunchStarterFlags(t *testing.T) {
	cmd := launchStarterCmd

	// Check --copy-to flag
	copyToFlag := cmd.Flags().Lookup("copy-to")
	if copyToFlag == nil {
		t.Error("--copy-to flag should exist")
	}

	// Check --profile flag
	profileFlag := cmd.Flags().Lookup("profile")
	if profileFlag == nil {
		t.Error("--profile flag should exist")
	}
	if profileFlag.Shorthand != "p" {
		t.Error("--profile should have shorthand -p")
	}
}

func TestLaunchBuilderCommand_Help(t *testing.T) {
	output, err := executeCommand(rootCmd, "launch", "builder", "--help")
	if err != nil {
		t.Fatalf("Launch builder help failed: %v", err)
	}

	expectedStrings := []string{
		"Visual Builder App",
		"--copy-to",
		"--deploy",
		"--skip-build",
	}

	for _, s := range expectedStrings {
		if !strings.Contains(output, s) {
			t.Errorf("Launch builder help should contain %q", s)
		}
	}
}

func TestLaunchBuilderFlags(t *testing.T) {
	cmd := launchBuilderCmd

	// Check --copy-to flag
	copyToFlag := cmd.Flags().Lookup("copy-to")
	if copyToFlag == nil {
		t.Error("--copy-to flag should exist")
	}

	// Check --deploy flag
	deployFlag := cmd.Flags().Lookup("deploy")
	if deployFlag == nil {
		t.Error("--deploy flag should exist")
	}

	// Check --skip-build flag
	skipBuildFlag := cmd.Flags().Lookup("skip-build")
	if skipBuildFlag == nil {
		t.Error("--skip-build flag should exist")
	}
}

