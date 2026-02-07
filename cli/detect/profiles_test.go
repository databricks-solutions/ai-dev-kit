package detect

import (
	"os"
	"path/filepath"
	"testing"
)

func TestParseProfilesFromFile(t *testing.T) {
	// Create a temporary test file
	tmpDir := t.TempDir()
	cfgPath := filepath.Join(tmpDir, ".databrickscfg")

	testConfig := `; Test configuration file
[DEFAULT]
host      = https://test.cloud.databricks.com
auth_type = databricks-cli

[profile-with-token]
host  = https://token.cloud.databricks.com
token = dapi123456789

[service-principal]
host          = https://sp.cloud.databricks.com
client_id     = abc-123
client_secret = secret-xyz

[profile.with.dots]
host = https://dots.cloud.databricks.com
token = dapi987654321

# Commented profile should be ignored
# [commented]
# host = https://ignored.com
`

	if err := os.WriteFile(cfgPath, []byte(testConfig), 0644); err != nil {
		t.Fatalf("Failed to create test config: %v", err)
	}

	profiles, err := parseProfilesFromFile(cfgPath)
	if err != nil {
		t.Fatalf("parseProfilesFromFile failed: %v", err)
	}

	// Should have 4 profiles
	if len(profiles) != 4 {
		t.Errorf("Expected 4 profiles, got %d", len(profiles))
	}

	// Test DEFAULT profile
	defaultProfile := GetProfile(profiles, "DEFAULT")
	if defaultProfile == nil {
		t.Fatal("DEFAULT profile not found")
	}
	if !defaultProfile.HasOAuth {
		t.Error("DEFAULT profile should have OAuth")
	}
	if defaultProfile.Host != "https://test.cloud.databricks.com" {
		t.Errorf("Unexpected host: %s", defaultProfile.Host)
	}

	// Test token profile
	tokenProfile := GetProfile(profiles, "profile-with-token")
	if tokenProfile == nil {
		t.Fatal("profile-with-token not found")
	}
	if !tokenProfile.HasToken {
		t.Error("profile-with-token should have HasToken=true")
	}
	if !tokenProfile.IsAuthenticated() {
		t.Error("profile-with-token should be authenticated")
	}

	// Test service principal profile
	spProfile := GetProfile(profiles, "service-principal")
	if spProfile == nil {
		t.Fatal("service-principal not found")
	}
	if !spProfile.HasServicePrinc {
		t.Error("service-principal should have HasServicePrinc=true")
	}
	if !spProfile.IsAuthenticated() {
		t.Error("service-principal should be authenticated")
	}

	// Test profile with dots in name
	dotsProfile := GetProfile(profiles, "profile.with.dots")
	if dotsProfile == nil {
		t.Fatal("profile.with.dots not found - dots in profile names should be supported")
	}
}

func TestParseProfilesFromFile_NotExists(t *testing.T) {
	profiles, err := parseProfilesFromFile("/nonexistent/path/.databrickscfg")
	if err != nil {
		t.Errorf("Should not return error for nonexistent file: %v", err)
	}
	if profiles != nil {
		t.Errorf("Should return nil profiles for nonexistent file")
	}
}

func TestIsAuthenticated(t *testing.T) {
	tests := []struct {
		name     string
		profile  Profile
		expected bool
	}{
		{
			name:     "No auth",
			profile:  Profile{Name: "test"},
			expected: false,
		},
		{
			name:     "Has token",
			profile:  Profile{Name: "test", HasToken: true},
			expected: true,
		},
		{
			name:     "Has OAuth",
			profile:  Profile{Name: "test", HasOAuth: true},
			expected: true,
		},
		{
			name:     "Has Service Principal",
			profile:  Profile{Name: "test", HasServicePrinc: true},
			expected: true,
		},
		{
			name:     "Multiple auth methods",
			profile:  Profile{Name: "test", HasToken: true, HasOAuth: true},
			expected: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.profile.IsAuthenticated(); got != tt.expected {
				t.Errorf("IsAuthenticated() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func TestHasProfile(t *testing.T) {
	profiles := []Profile{
		{Name: "DEFAULT"},
		{Name: "test-profile"},
		{Name: "another.profile"},
	}

	if !HasProfile(profiles, "DEFAULT") {
		t.Error("Should find DEFAULT profile")
	}

	if !HasProfile(profiles, "test-profile") {
		t.Error("Should find test-profile")
	}

	if HasProfile(profiles, "nonexistent") {
		t.Error("Should not find nonexistent profile")
	}
}

func TestGetDefaultProfile(t *testing.T) {
	// With DEFAULT profile
	profiles := []Profile{
		{Name: "first"},
		{Name: "DEFAULT"},
		{Name: "third"},
	}
	if got := GetDefaultProfile(profiles); got != "DEFAULT" {
		t.Errorf("GetDefaultProfile() = %v, want DEFAULT", got)
	}

	// Without DEFAULT profile
	profilesNoDefault := []Profile{
		{Name: "first"},
		{Name: "second"},
	}
	if got := GetDefaultProfile(profilesNoDefault); got != "first" {
		t.Errorf("GetDefaultProfile() = %v, want first", got)
	}

	// Empty profiles
	if got := GetDefaultProfile(nil); got != "DEFAULT" {
		t.Errorf("GetDefaultProfile(nil) = %v, want DEFAULT", got)
	}
}

func TestIsTokenSet(t *testing.T) {
	// Save original value
	original := os.Getenv("DATABRICKS_TOKEN")
	defer os.Setenv("DATABRICKS_TOKEN", original)

	// Test with token set
	os.Setenv("DATABRICKS_TOKEN", "test-token")
	if !IsTokenSet() {
		t.Error("IsTokenSet() should return true when token is set")
	}

	// Test without token
	os.Unsetenv("DATABRICKS_TOKEN")
	if IsTokenSet() {
		t.Error("IsTokenSet() should return false when token is not set")
	}
}

func TestIsHostSet(t *testing.T) {
	// Save original value
	original := os.Getenv("DATABRICKS_HOST")
	defer os.Setenv("DATABRICKS_HOST", original)

	// Test with host set
	os.Setenv("DATABRICKS_HOST", "https://test.databricks.com")
	if !IsHostSet() {
		t.Error("IsHostSet() should return true when host is set")
	}

	// Test without host
	os.Unsetenv("DATABRICKS_HOST")
	if IsHostSet() {
		t.Error("IsHostSet() should return false when host is not set")
	}
}

