package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// -------------------------------------------------------------------
// BGTask - persisted to disk so restarts don't lose in-flight work
// -------------------------------------------------------------------

type BGTask struct {
	ID        string    `json:"id"`
	Command   string    `json:"command"`
	Status    string    `json:"status"` // "running", "completed", "failed"
	StartTime time.Time `json:"start_time"`
	EndTime   time.Time `json:"end_time"`
	Label     string    `json:"label"` // human-readable hint e.g. "npm install"

	// Runtime-only (not persisted - rebuilt on startup)
	Stdout *bytes.Buffer `json:"-"`
	Stderr *bytes.Buffer `json:"-"`
	Cmd    *exec.Cmd     `json:"-"`

	// Snapshot written to disk periodically and on completion
	SnapshotFile string `json:"snapshot_file"`
}

var (
	bgTasks   = make(map[string]*BGTask)
	bgTasksMu sync.RWMutex
	bgTaskIdx = 1
)

// bgTasksDir returns a stable directory for BG task persistence
func bgTasksDir() string {
	dir := filepath.Join(os.TempDir(), "voila_bg_tasks")
	os.MkdirAll(dir, 0755)
	return dir
}

// generateSnapshot builds an abbreviated log: first 30 + last 30 lines
func generateSnapshot(stdout, stderr []byte) string {
	outStr := strings.TrimSpace(string(stdout))
	errStr := strings.TrimSpace(string(stderr))

	var sb strings.Builder

	truncateLog := func(log string, name string) {
		if log == "" {
			return
		}
		lines := strings.Split(log, "\n")
		sb.WriteString(fmt.Sprintf("--- %s (%d lines) ---\n", name, len(lines)))
		if len(lines) <= 60 {
			sb.WriteString(log + "\n")
		} else {
			sb.WriteString(strings.Join(lines[:30], "\n") + "\n")
			sb.WriteString(fmt.Sprintf("\n... [ %d lines omitted for brevity ] ...\n\n", len(lines)-60))
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

// persistSnapshot writes the current snapshot to disk so it survives restarts
func persistSnapshot(task *BGTask) {
	if task.SnapshotFile == "" {
		return
	}
	snap := generateSnapshot(task.Stdout.Bytes(), task.Stderr.Bytes())
	os.WriteFile(task.SnapshotFile, []byte(snap), 0644)
}

// saveBGTaskMeta saves task metadata (not snapshot) to disk as JSON
func saveBGTaskMeta(task *BGTask) {
	metaFile := filepath.Join(bgTasksDir(), task.ID+".meta.json")
	data, _ := json.Marshal(task)
	os.WriteFile(metaFile, data, 0644)
}

// loadBGTasksFromDisk loads all previous tasks on startup
func loadBGTasksFromDisk() {
	dir := bgTasksDir()
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	bgTasksMu.Lock()
	defer bgTasksMu.Unlock()
	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".meta.json") {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var task BGTask
		if json.Unmarshal(data, &task) != nil {
			continue
		}
		// Tasks that were "running" on disk are now dead (process died) - mark failed
		if task.Status == "running" {
			task.Status = "failed"
			task.EndTime = time.Now()
		}
		// Restore snapshot from disk
		task.Stdout = &bytes.Buffer{}
		task.Stderr = &bytes.Buffer{}
		if task.SnapshotFile != "" {
			if snap, err := os.ReadFile(task.SnapshotFile); err == nil {
				task.Stdout.Write(snap)
			}
		}
		bgTasks[task.ID] = &task
		logBGInfo("BGTask", "Loaded persisted task %s status=%s", task.ID, task.Status)
	}
}

// isLongRunningCommand heuristically detects commands that should auto-run as BG TASK COMORADE
func isLongRunningCommand(cmd string) bool {
	lower := strings.ToLower(strings.TrimSpace(cmd))
	
	commands := []string{
		"npm install", "npm i", "npm ci", "npm run build",
		"pip install", "pip3 install",
		"yarn install", "yarn add", "yarn build",
		"go build", "go mod download", "go mod tidy",
		"cargo build", "cargo install",
		"docker build", "docker pull", "docker compose",
		"git clone", "git pull",
		"flutter pub get", "flutter build",
		"gradle build", "mvn install", "mvn package",
		"apt install", "apt-get install",
		"choco install",
		"winget install",
	}

	for _, p := range commands {
		if lower == p || strings.HasPrefix(lower, p+" ") {
			return true
		}
	}
	
	if strings.Contains(lower, "wget ") || strings.Contains(lower, "curl -O") || strings.Contains(lower, "curl --output") || strings.HasPrefix(lower, "make ") || strings.HasPrefix(lower, "cmake ") {
		return true
	}
	
	return false
}

// spawnBGTask spawns a command in a goroutine, persists metadata, returns task ID
func spawnBGTask(command string) string {
	return spawnBGTaskWithLabel(command, command)
}

// spawnBGTaskSafe is the public entry point - checks for duplicates first
func spawnBGTaskSafe(command, label string) (string, bool) {
	if isDup, existingID := isDuplicateBGTask(command); isDup {
		logBGWarn("BGTask", "Duplicate detected - command already running as %s", existingID)
		return existingID, true // true = was duplicate
	}
	return spawnBGTaskWithLabel(command, label), false
}

func spawnBGTaskWithLabel(command, label string) string {
	bgTasksMu.Lock()
	id := fmt.Sprintf("TASK-%d", bgTaskIdx)
	bgTaskIdx++

	snapshotFile := filepath.Join(bgTasksDir(), id+".snapshot.txt")
	task := &BGTask{
		ID:           id,
		Command:      command,
		Label:        label,
		Status:       "running",
		Stdout:       &bytes.Buffer{},
		Stderr:       &bytes.Buffer{},
		StartTime:    time.Now(),
		SnapshotFile: snapshotFile,
	}
	bgTasks[id] = task
	bgTasksMu.Unlock()

	// Persist meta immediately so mobile/dashboard can see it
	saveBGTaskMeta(task)
	logBGInfo("BGTask", "Spawned task %s: %s", id, command)

	go func() {
		fullCmd := fmt.Sprintf("Set-Location -Path [Environment]::GetFolderPath('Desktop'); %s", command)
		cmd := exec.Command("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", fullCmd)
		cmd.Stdout = task.Stdout
		cmd.Stderr = task.Stderr
		task.Cmd = cmd

		// Periodic snapshot flush (every 10s)
		done := make(chan struct{})
		go func() {
			ticker := time.NewTicker(10 * time.Second)
			defer ticker.Stop()
			for {
				select {
				case <-ticker.C:
					bgTasksMu.RLock()
					persistSnapshot(task)
					bgTasksMu.RUnlock()
				case <-done:
					return
				}
			}
		}()

		err := cmd.Run()
		close(done)

		bgTasksMu.Lock()
		defer bgTasksMu.Unlock()
		task.EndTime = time.Now()
		if err != nil {
			task.Status = "failed"
			fmt.Fprintf(task.Stderr, "\n[Execution Error: %v]", err)
			logBGError("BGTask", "Task %s FAILED: %v", id, err)
		} else {
			task.Status = "completed"
			logBGInfo("BGTask", "Task %s COMPLETED in %s", id, task.EndTime.Sub(task.StartTime).Round(time.Second))
		}
		persistSnapshot(task)
		saveBGTaskMeta(task)

		// Push completion notification to the running LLM loop (COMORADE mode)
		snapshot := generateSnapshot(task.Stdout.Bytes(), task.Stderr.Bytes())
		select {
		case comradeNotifyCh <- comradeNotification{
			TaskID:   task.ID,
			Label:    task.Label,
			Snapshot: snapshot,
		}:
			logBGInfo("BGTask", "COMORADE notification sent for %s", task.ID)
		default:
			// Channel full - log and move on (LLM can still poll via check_bg_task)
			logBGWarn("BGTask", "COMORADE channel full, notification for %s dropped (use check_bg_task)", task.ID)
		}
	}()

	return id
}

func getBGTaskStatus(id string) (string, error) {
	bgTasksMu.RLock()
	defer bgTasksMu.RUnlock()

	task, exists := bgTasks[id]
	if !exists {
		// Try to load from disk
		metaFile := filepath.Join(bgTasksDir(), id+".meta.json")
		data, err := os.ReadFile(metaFile)
		if err != nil {
			return "", fmt.Errorf("task %s not found (not in memory or on disk)", id)
		}
		var t BGTask
		if json.Unmarshal(data, &t) != nil {
			return "", fmt.Errorf("task %s metadata corrupted", id)
		}
		task = &t
	}

	duration := time.Since(task.StartTime).Round(time.Second)
	if task.Status != "running" {
		duration = task.EndTime.Sub(task.StartTime).Round(time.Second)
	}

	var snapshot string
	if task.Stdout != nil {
		snapshot = generateSnapshot(task.Stdout.Bytes(), task.Stderr.Bytes())
	} else if task.SnapshotFile != "" {
		if data, err := os.ReadFile(task.SnapshotFile); err == nil {
			snapshot = string(data)
		}
	}
	if snapshot == "" {
		snapshot = "(no output yet)"
	}

	return fmt.Sprintf("Task ID: %s\nLabel: %s\nStatus: %s\nDuration: %s\n\n%s",
		task.ID, task.Label, strings.ToUpper(task.Status), duration, snapshot), nil
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

// listBGTasks returns a JSON-serializable list of all tasks
func listBGTasks() []map[string]string {
	bgTasksMu.RLock()
	defer bgTasksMu.RUnlock()

	var list []map[string]string
	for _, task := range bgTasks {
		dur := time.Since(task.StartTime).Round(time.Second).String()
		if task.Status != "running" {
			dur = task.EndTime.Sub(task.StartTime).Round(time.Second).String()
		}
		list = append(list, map[string]string{
			"id":       task.ID,
			"label":    task.Label,
			"command":  task.Command,
			"status":   task.Status,
			"duration": dur,
		})
	}
	return list
}
