package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestProceduralCommandMemoryRetrieval(t *testing.T) {
	// Setup test brain directory
	tmpDir, err := os.MkdirTemp("", "voila_mem_test_*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Save test techniques
	saveMemory("Find listening port", "Get-NetTCPConnection -LocalPort 8080")
	saveMemory("Kill process by name", "Stop-Process -Name 'notepad' -Force")
	saveMemory("List directory sorted by size", "Get-ChildItem | Sort-Object Length -Descending")

	// Test relevant technique retrieval
	res := getRelevantCommandMemory("how to kill process listening on port 8080", 2)
	if res == "" {
		t.Errorf("Expected relevant memory techniques, got empty string")
	}
	if !strings.Contains(res, "8080") && !strings.Contains(res, "Stop-Process") {
		t.Errorf("Expected result to contain port or process command, got: %s", res)
	}
}

func TestAppendMemoryFact(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "voila_fact_test_*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Test appending a global memory fact
	testFact := "User prefers dark mode and pnpm package manager"
	res := appendMemoryFact(testFact, "global", "preference")
	if !strings.HasPrefix(res, "ok:") && !strings.Contains(res, "Fact already recorded") {
		t.Errorf("Expected ok response, got: %s", res)
	}

	// Verify deduplication
	resDup := appendMemoryFact(testFact, "global", "preference")
	if !strings.Contains(resDup, "already recorded") {
		t.Errorf("Expected deduplication message, got: %s", resDup)
	}
}

func TestAsyncUpdateSessionSummary(t *testing.T) {
	tmpConv := "test_conv_summary_99"
	brainDir := getBrainDir()
	convDir := filepath.Join(brainDir, tmpConv)
	os.MkdirAll(convDir, 0755)
	defer os.RemoveAll(convDir)

	// Create 10 dummy turns (5 user/assistant pairs)
	history := []map[string]interface{}{
		{"role": "user", "content": "Initialize project with git and go mod"},
		{"role": "assistant", "content": "Initialized git repository and created go.mod file"},
		{"role": "user", "content": "Create main.go with http server"},
		{"role": "assistant", "content": "Created main.go listening on port 8080"},
		{"role": "user", "content": "Add unit tests for health check"},
		{"role": "assistant", "content": "Added health_test.go with TestHealthCheck"},
		{"role": "user", "content": "Run tests and verify pass"},
		{"role": "assistant", "content": "Tests executed successfully. All passed."},
		{"role": "user", "content": "Current turn: add database connection"},
		{"role": "assistant", "content": "Connecting to postgres..."},
	}

	asyncUpdateSessionSummary(tmpConv, history)

	summaryFile := filepath.Join(convDir, "session_summary.md")
	data, err := os.ReadFile(summaryFile)
	if err != nil {
		t.Fatalf("Expected session_summary.md to be created: %v", err)
	}

	summaryText := string(data)
	if !strings.Contains(summaryText, "Historical Session Milestones") {
		t.Errorf("Expected summary to contain milestones header, got: %s", summaryText)
	}
	if !strings.Contains(summaryText, "Initialize project") {
		t.Errorf("Expected summary to contain milestone 1, got: %s", summaryText)
	}
}
