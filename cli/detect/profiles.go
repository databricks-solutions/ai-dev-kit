package detect

import (
	"bufio"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// Profile represents a Databricks configuration profile
type Profile struct {
	Name            string
	Host            string
	HasToken        bool   // Legacy PAT token
	HasOAuth        bool   // OAuth via databricks-cli
	HasServicePrinc bool   // Service principal (client_id + client_secret)
	AuthType        string // The auth_type value if set
}

// IsAuthenticated returns true if the profile has any valid authentication configured
func (p Profile) IsAuthenticated() bool {
	return p.HasToken || p.HasOAuth || p.HasServicePrinc
}

// DetectProfiles reads ~/.databrickscfg and returns available profiles
func DetectProfiles() ([]Profile, error) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}

	cfgPath := filepath.Join(homeDir, ".databrickscfg")
	return parseProfilesFromFile(cfgPath)
}

// parseProfilesFromFile parses the databrickscfg file
func parseProfilesFromFile(path string) ([]Profile, error) {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil // No config file is not an error
		}
		return nil, err
	}
	defer file.Close()

	var profiles []Profile
	var currentProfile *Profile

	// Regex to match section headers [PROFILE_NAME]
	// Allows alphanumeric, underscore, hyphen, and dot characters
	sectionRegex := regexp.MustCompile(`^\[([a-zA-Z0-9._-]+)\]$`)

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Check for section header
		if matches := sectionRegex.FindStringSubmatch(line); matches != nil {
			// Save previous profile
			if currentProfile != nil {
				profiles = append(profiles, *currentProfile)
			}
			currentProfile = &Profile{Name: matches[1]}
			continue
		}

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, ";") {
			continue
		}

		// Parse key-value pairs
		if currentProfile != nil {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) == 2 {
				key := strings.TrimSpace(parts[0])
				value := strings.TrimSpace(parts[1])

				switch key {
				case "host":
					currentProfile.Host = value
				case "token":
					currentProfile.HasToken = value != ""
				case "auth_type":
					currentProfile.AuthType = value
					// databricks-cli auth_type means OAuth authentication is configured
					if value == "databricks-cli" {
						currentProfile.HasOAuth = true
					}
				case "client_id":
					// Service principal auth (needs client_secret too, but having client_id is a good indicator)
					if value != "" {
						currentProfile.HasServicePrinc = true
					}
				}
			}
		}
	}

	// Don't forget the last profile
	if currentProfile != nil {
		profiles = append(profiles, *currentProfile)
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return profiles, nil
}

// HasProfile checks if a specific profile exists
func HasProfile(profiles []Profile, name string) bool {
	for _, p := range profiles {
		if p.Name == name {
			return true
		}
	}
	return false
}

// GetProfile returns a profile by name
func GetProfile(profiles []Profile, name string) *Profile {
	for i := range profiles {
		if profiles[i].Name == name {
			return &profiles[i]
		}
	}
	return nil
}

// ProfileHasToken checks if a profile has a token configured (legacy, use ProfileIsAuthenticated)
func ProfileHasToken(profileName string) bool {
	profiles, err := DetectProfiles()
	if err != nil {
		return false
	}

	profile := GetProfile(profiles, profileName)
	return profile != nil && profile.HasToken
}

// ProfileIsAuthenticated checks if a profile has any valid authentication configured
func ProfileIsAuthenticated(profileName string) bool {
	profiles, err := DetectProfiles()
	if err != nil {
		return false
	}

	profile := GetProfile(profiles, profileName)
	return profile != nil && profile.IsAuthenticated()
}

// GetDefaultProfile returns the first profile or "DEFAULT" if none exist
func GetDefaultProfile(profiles []Profile) string {
	// Check if DEFAULT exists
	for _, p := range profiles {
		if p.Name == "DEFAULT" {
			return "DEFAULT"
		}
	}

	// Return first profile if any exist
	if len(profiles) > 0 {
		return profiles[0].Name
	}

	return "DEFAULT"
}

// DatabricksConfigPath returns the path to the databrickscfg file
func DatabricksConfigPath() string {
	homeDir, _ := os.UserHomeDir()
	return filepath.Join(homeDir, ".databrickscfg")
}

// IsTokenSet checks if DATABRICKS_TOKEN environment variable is set
func IsTokenSet() bool {
	return os.Getenv("DATABRICKS_TOKEN") != ""
}

// IsHostSet checks if DATABRICKS_HOST environment variable is set
func IsHostSet() bool {
	return os.Getenv("DATABRICKS_HOST") != ""
}

