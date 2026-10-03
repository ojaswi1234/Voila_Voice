package main

import (
	"testing"
	"time"
)

func init() {
	initDebugLog()
}

func TestCheckpointLifecycle(t *testing.T) {
	convID := "conv-test-123"
	taskID := "task-test-456"
	
	// Ensure cleanup
	clearCheckpoint(convID, taskID)
	
	cp := &Checkpoint{
		ConvID:      convID,
		TaskID:      taskID,
		Command:     "Create a NextJS app",
		Messages:    []map[string]interface{}{{"role": "user", "content": "hello"}},
		SavedAt:     time.Now(),
		ResumeAfter: time.Now().Add(5 * time.Second),
		Reason:      "rate_limit",
		Model:       "gpt-4",
		BGTaskIDs:   []string{"TASK-1"},
	}
	
	err := saveCheckpoint(cp)
	if err != nil {
		t.Fatalf("saveCheckpoint failed: %v", err)
	}
	
	// Verify it can be loaded
	loadedCP, err := loadCheckpoint(convID, taskID)
	if err != nil {
		t.Fatalf("loadCheckpoint failed: %v", err)
	}
	
	if loadedCP.ConvID != convID || loadedCP.Reason != "rate_limit" || len(loadedCP.Messages) != 1 {
		t.Errorf("Loaded checkpoint data mismatch: %+v", loadedCP)
	}
	
	// Verify clear
	clearCheckpoint(convID, taskID)
	_, err = loadCheckpoint(convID, taskID)
	if err == nil {
		t.Errorf("Expected error loading cleared checkpoint, got nil")
	}
}

func TestBuildResumeInjection(t *testing.T) {
	cp := &Checkpoint{
		Reason: "rate_limit",
	}
	msg := buildResumeInjection(cp)
	if msg == "" {
		t.Errorf("Expected non-empty resume injection message")
	}
}
