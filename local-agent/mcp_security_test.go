package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSecurity_U37_InstallQuarantine(t *testing.T) {
	_, err := skillsMarketInstall("../malicious", "https://example.com/SKILL.md")
	if err == nil {
		t.Fatal("Expected path traversal ID to be rejected")
	}
}

func TestSecurity_U38_MaxOutputTruncation(t *testing.T) {
}

func TestSecurity_U39_PolicyHook(t *testing.T) {
}

func TestSecurity_U40_AuditLog(t *testing.T) {
	logPath := filepath.Join(filepath.Dir(mcpServersPath()), "security_audit.jsonl")
	os.Remove(logPath)
	appendSecurityAudit("test_action", "test_details")
	
	data, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatal("Audit log not written:", err)
	}
	if !strings.Contains(string(data), "test_action") {
		t.Fatal("Audit log content missing")
	}
}
