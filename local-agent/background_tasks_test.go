package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func init() {
	initDebugLog()
}

func TestIsLongRunningCommand(t *testing.T) {
	tests := []struct {
		cmd      string
		expected bool
	}{
		{"npm install express", true},
		{"npm i", true},
		{"npm run dev", false},
		{"pip install -r requirements.txt", true},
		{"go build .", true},
		{"echo hello", false},
		{"git clone https://github.com/test", true},
		{"docker build -t test .", true},
		{"cat package.json", false},
	}

	for _, tt := range tests {
		result := isLongRunningCommand(tt.cmd)
		if result != tt.expected {
			t.Errorf("isLongRunningCommand(%q) = %v; want %v", tt.cmd, result, tt.expected)
		}
	}
}

func TestBGTaskLifecycleAndDedup(t *testing.T) {
	// Clean up existing map for isolation
	bgTasksMu.Lock()
	bgTasks = make(map[string]*BGTask)
	bgTaskIdx = 0
	bgTasksMu.Unlock()

	// Drain any existing comrade notifications
	for len(comradeNotifyCh) > 0 {
		<-comradeNotifyCh
	}

	cmd1 := "echo 'hello world'"
	
	// Test spawning
	taskID1, _ := spawnBGTaskSafe(cmd1, "test-label")
	if taskID1 == "" {
		t.Fatalf("spawnBGTaskSafe failed, got empty ID")
	}

	// Test dedup
	taskID2, _ := spawnBGTaskSafe(cmd1, "test-label")
	if taskID2 != taskID1 {
		t.Errorf("Expected dedup to return %s, got %s", taskID1, taskID2)
	}

	// Wait for the task to finish
	time.Sleep(1 * time.Second)

	bgTasksMu.RLock()
	task, exists := bgTasks[taskID1]
	bgTasksMu.RUnlock()

	if !exists {
		t.Fatalf("Task %s not found in map", taskID1)
	}

	if task.Status != "completed" {
		t.Errorf("Expected task status 'completed', got '%s'", task.Status)
	}

	// Check if comradeNotifyCh got the message
	select {
	case notif := <-comradeNotifyCh:
		if notif.TaskID != taskID1 {
			t.Errorf("Expected comrade notification for %s, got %s", taskID1, notif.TaskID)
		}
	default:
		t.Errorf("Expected comrade notification in channel, but channel was empty")
	}
}

func TestBGTaskPersistence(t *testing.T) {
	// Create a dummy task
	taskID := "TASK-999"
	task := &BGTask{
		ID:        taskID,
		Command:   "echo test",
		Status:    "completed",
		Label:     "test persist",
		StartTime: time.Now().Add(-1 * time.Minute),
		EndTime:   time.Now(),
	}

	// Save to disk
	saveBGTaskMeta(task)

	// Verify file exists
	file := filepath.Join(bgTasksDir(), taskID+".meta.json")
	if _, err := os.Stat(file); os.IsNotExist(err) {
		t.Fatalf("Meta file not created at %s", file)
	}

	// Read and verify content
	b, err := os.ReadFile(file)
	if err != nil {
		t.Fatalf("Failed to read meta file: %v", err)
	}
	var loadedTask BGTask
	if err := json.Unmarshal(b, &loadedTask); err != nil {
		t.Fatalf("Failed to unmarshal meta file: %v", err)
	}

	if loadedTask.ID != taskID || loadedTask.Status != "completed" || loadedTask.Command != "echo test" {
		t.Errorf("Loaded task data mismatch: %+v", loadedTask)
	}

	// Cleanup
	os.Remove(file)
}
