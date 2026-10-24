package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
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


func TestStickyConversationID(t *testing.T) {
	// 1. Fresh empty request creates new conversation
	activeConvMu.Lock()
	lastActiveConv = ""
	lastActiveTime = time.Time{}
	activeConvMu.Unlock()

	id1 := getOrCreateConversationID("")
	if !strings.HasPrefix(id1, "conv_") {
		t.Errorf("Expected id1 to start with 'conv_', got: %s", id1)
	}

	// 2. Immediate subsequent request with empty ID reuses id1
	id2 := getOrCreateConversationID("")
	if id2 != id1 {
		t.Errorf("Expected id2 to match id1 (%s), got: %s", id1, id2)
	}

	// 3. Explicit ID switches conversation
	explicitID := "conv_custom_abc"
	id3 := getOrCreateConversationID(explicitID)
	if id3 != explicitID {
		t.Errorf("Expected id3 to match explicitID (%s), got: %s", explicitID, id3)
	}

	// 4. Next empty ID stays on explicitID
	id4 := getOrCreateConversationID("")
	if id4 != explicitID {
		t.Errorf("Expected id4 to stick to explicitID (%s), got: %s", explicitID, id4)
	}

	// 5. Explicit "new" command forces fresh conversation
	id5 := getOrCreateConversationID("new")
	if id5 == explicitID || !strings.HasPrefix(id5, "conv_") {
		t.Errorf("Expected id5 to be fresh conversation, got: %s", id5)
	}
}

func TestMultiTurnCloudHistoryRoundtrip(t *testing.T) {
	testConv := "test_roundtrip_turn_99"
	brainDir := getBrainDir()
	convDir := filepath.Join(brainDir, testConv)
	os.RemoveAll(convDir)
	defer os.RemoveAll(convDir)

	// Turn 1
	turn1Cmd := `Check files in C:\Users\Desktop`
	turn1Out := "Files found:\n- report.pdf\n- notes.txt"
	saveCloudHistory(testConv, turn1Cmd, turn1Out)

	history1 := loadCloudHistory(testConv)
	if len(history1) != 2 {
		t.Fatalf("Expected 2 messages after turn 1, got %d", len(history1))
	}
	if history1[0]["content"] != turn1Cmd || history1[1]["content"] != turn1Out {
		t.Errorf("Turn 1 content mismatch")
	}

	// Turn 2: User asks what was the output of the task
	turn2Cmd := "what was the output of the task?"
	turn2Out := "The output was:\n- report.pdf\n- notes.txt"
	saveCloudHistory(testConv, turn2Cmd, turn2Out)

	history2 := loadCloudHistory(testConv)
	if len(history2) != 4 {
		t.Fatalf("Expected 4 messages after turn 2, got %d", len(history2))
	}
	if history2[2]["content"] != turn2Cmd || history2[3]["content"] != turn2Out {
		t.Errorf("Turn 2 content mismatch")
	}
}
