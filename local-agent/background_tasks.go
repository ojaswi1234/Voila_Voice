package main

import (
	"bytes"
	"fmt"
	"os/exec"
	"strings"
	"sync"
	"time"
)

type BGTask struct {
	ID        string
	Command   string
	Status    string // "running", "completed", "failed"
	Stdout    *bytes.Buffer
	Stderr    *bytes.Buffer
	StartTime time.Time
	EndTime   time.Time
	Cmd       *exec.Cmd
}

var (
	bgTasks   = make(map[string]*BGTask)
	bgTasksMu sync.RWMutex
	bgTaskIdx = 1
)

func generateSnapshot(stdout, stderr []byte) string {
	outStr := strings.TrimSpace(string(stdout))
	errStr := strings.TrimSpace(string(stderr))
	
	var sb strings.Builder
	
	truncateLog := func(log string, name string) {
		if log == "" {
			return
		}
		lines := strings.Split(log, "\n")
		sb.WriteString(fmt.Sprintf("--- %s ---\n", name))
		if len(lines) <= 60 {
			sb.WriteString(log + "\n")
		} else {
			sb.WriteString(strings.Join(lines[:30], "\n") + "\n")
			sb.WriteString(fmt.Sprintf("\n... [ %d lines truncated ] ...\n\n", len(lines)-60))
			sb.WriteString(strings.Join(lines[len(lines)-30:], "\n") + "\n")
		}
	}

	truncateLog(outStr, "STDOUT")
	truncateLog(errStr, "STDERR")

	if sb.Len() == 0 {
		return "(no output)"
	}
	return sb.String()
}

func spawnBGTask(command string) string {
	bgTasksMu.Lock()
	id := fmt.Sprintf("TASK-%d", bgTaskIdx)
	bgTaskIdx++
	
	task := &BGTask{
		ID:        id,
		Command:   command,
		Status:    "running",
		Stdout:    &bytes.Buffer{},
		Stderr:    &bytes.Buffer{},
		StartTime: time.Now(),
	}
	bgTasks[id] = task
	bgTasksMu.Unlock()

	// Spawn in a goroutine
	go func() {
		// Use powershell to run the command, same as terminal
		cmd := exec.Command("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command)
		
		// If running from local-agent, we want to run in the Desktop or Voila_Voice dir?
		// Native run_terminal runs in Desktop. Let's do the same.
		// Wait, native run_terminal uses Set-Location -Path [Environment]::GetFolderPath('Desktop')
		// We can just prepend it.
		fullCmd := fmt.Sprintf("Set-Location -Path [Environment]::GetFolderPath('Desktop'); %s", command)
		cmd = exec.Command("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", fullCmd)

		cmd.Stdout = task.Stdout
		cmd.Stderr = task.Stderr
		task.Cmd = cmd
		
		err := cmd.Run()

		bgTasksMu.Lock()
		defer bgTasksMu.Unlock()
		task.EndTime = time.Now()
		if err != nil {
			task.Status = "failed"
			fmt.Fprintf(task.Stderr, "\n[Execution Error: %v]", err)
		} else {
			task.Status = "completed"
		}
	}()

	return id
}

func getBGTaskStatus(id string) (string, error) {
	bgTasksMu.RLock()
	defer bgTasksMu.RUnlock()

	task, exists := bgTasks[id]
	if !exists {
		return "", fmt.Errorf("task %s not found", id)
	}

	duration := time.Since(task.StartTime).Round(time.Second)
	if task.Status != "running" {
		duration = task.EndTime.Sub(task.StartTime).Round(time.Second)
	}

	snapshot := generateSnapshot(task.Stdout.Bytes(), task.Stderr.Bytes())

	res := fmt.Sprintf("Task ID: %s\nCommand: %s\nStatus: %s\nDuration: %s\n\n%s", 
		task.ID, task.Command, strings.ToUpper(task.Status), duration, snapshot)
	return res, nil
}

func waitForBGTask(id string) string {
	for {
		bgTasksMu.RLock()
		task, exists := bgTasks[id]
		if !exists {
			bgTasksMu.RUnlock()
			return fmt.Sprintf("error: task %s not found", id)
		}
		status := task.Status
		bgTasksMu.RUnlock()

		if status != "running" {
			res, _ := getBGTaskStatus(id)
			return res
		}
		time.Sleep(500 * time.Millisecond)
	}
}
