package installer

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// CheckVersion compares local and remote versions
// Returns true if update is needed, false if up to date
func CheckVersion(cfg *Config) (needsUpdate bool, localVer string, remoteVer string, err error) {
	// Determine version file path based on scope
	verFile := cfg.VersionFile()
	if cfg.Scope == "project" {
		verFile = cfg.ProjectVersionFile()
	}

	// Check if version file exists
	if !pathExists(verFile) {
		return true, "", "", nil // First install
	}

	// Force reinstall bypasses version check
	if cfg.Force {
		return true, "", "", nil
	}

	// Read local version
	data, err := os.ReadFile(verFile)
	if err != nil {
		return true, "", "", nil
	}
	localVer = strings.TrimSpace(string(data))

	// Fetch remote version
	remoteVer, err = fetchRemoteVersion()
	if err != nil {
		// Can't check remote, allow install
		return true, localVer, "", nil
	}

	// Compare versions
	if localVer == remoteVer {
		return false, localVer, remoteVer, nil
	}

	return true, localVer, remoteVer, nil
}

// fetchRemoteVersion fetches the version from the remote repository
func fetchRemoteVersion() (string, error) {
	url := RawURL + "/VERSION"

	resp, err := http.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	version := strings.TrimSpace(string(data))

	// Validate version doesn't contain error text
	if strings.Contains(version, "404") ||
		strings.Contains(version, "Not Found") ||
		strings.Contains(version, "error") {
		return "", fmt.Errorf("invalid version response")
	}

	return version, nil
}

// SaveVersion saves the current version to disk
func SaveVersion(cfg *Config) error {
	version, err := fetchRemoteVersion()
	if err != nil {
		version = "dev"
	}

	// Save to install directory
	if err := os.MkdirAll(cfg.InstallDir, 0755); err != nil {
		return err
	}

	if err := os.WriteFile(cfg.VersionFile(), []byte(version+"\n"), 0644); err != nil {
		return err
	}

	// Also save to project directory if in project scope
	if cfg.Scope == "project" {
		projectDir := filepath.Dir(cfg.ProjectVersionFile())
		if err := os.MkdirAll(projectDir, 0755); err != nil {
			return err
		}
		if err := os.WriteFile(cfg.ProjectVersionFile(), []byte(version+"\n"), 0644); err != nil {
			return err
		}
	}

	return nil
}

// GetCurrentVersion returns the currently installed version
func GetCurrentVersion(cfg *Config) string {
	verFile := cfg.VersionFile()
	if cfg.Scope == "project" {
		verFile = cfg.ProjectVersionFile()
	}

	data, err := os.ReadFile(verFile)
	if err != nil {
		return "unknown"
	}

	return strings.TrimSpace(string(data))
}

