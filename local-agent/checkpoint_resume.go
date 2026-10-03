package main

/*
	checkpoint_resume.go

	Implements conversation checkpoint/resume for when:
	1. API rate limits (429) exhaust all retries
	2. maxIter (50) is approaching and task is not done
	3. BG TASK mode: pauses LLM, waits for bg work, resumes with snapshot

	When a checkpoint is saved:
	  - The full messages[] array is serialized to disk under brain/<convID>/checkpoint.json
	  - The original command (user goal) is saved so we can re-bootstrap
	  - A "reason" string explains why we paused (rate_limit / bg_task / max_iter)

	When resuming:
	  - Checkpoint is loaded from disk
	  - A system injection message is prepended explaining the pause
	  - LLM continues from where it left off
*/

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Checkpoint represents a saved conversation mid-execution
type Checkpoint struct {
	ConvID      string                   `json:"conv_id"`
	TaskID      string                   `json:"task_id"`
	Command     string                   `json:"command"`     // original user goal
	Messages    []map[string]interface{} `json:"messages"`    // full conversation history
	SavedAt     time.Time                `json:"saved_at"`
	Reason      string                   `json:"reason"`      // "rate_limit" | "bg_task" | "max_iter"
	BGTaskIDs   []string                 `json:"bg_task_ids"` // any spawned BG tasks to check on resume
	Model       string                   `json:"model"`
	ApiKey      string                   `json:"api_key"`     // encrypted? for now store as-is in local file
	ResumeAfter time.Time                `json:"resume_after"` // when it's safe to resume
}

// comradeNotification is a message injected into the LLM loop when a COMORADE task completes
type comradeNotification struct {
	TaskID   string
	Label    string
	Snapshot string
}

// comradeNotifyCh is a buffered channel — background task goroutines push here when done
// The LLM loop drains this between iterations
var comradeNotifyCh = make(chan comradeNotification, 32)

// checkpointPath returns the path for a conversation's checkpoint file
func checkpointPath(convID, taskID string) string {
	key := convID
	if key == "" {
		key = taskID
	}
	if key == "" {
		key = "default"
	}
	dir := filepath.Join(getBrainDir(), key)
	os.MkdirAll(dir, 0755)
	return filepath.Join(dir, "checkpoint.json")
}

// saveCheckpoint writes the current conversation state to disk
func saveCheckpoint(cp *Checkpoint) error {
	path := checkpointPath(cp.ConvID, cp.TaskID)
	data, err := json.MarshalIndent(cp, "", "  ")
	if err != nil {
		return fmt.Errorf("checkpoint marshal: %w", err)
	}
	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("checkpoint write: %w", err)
	}
	logBGInfo("Checkpoint", "Saved %s reason=%s msgs=%d bgTasks=%v", path, cp.Reason, len(cp.Messages), cp.BGTaskIDs)
	return nil
}

// loadCheckpoint loads a saved checkpoint for a conversation
func loadCheckpoint(convID, taskID string) (*Checkpoint, error) {
	path := checkpointPath(convID, taskID)
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err // file not found = no checkpoint
	}
	var cp Checkpoint
	if err := json.Unmarshal(data, &cp); err != nil {
		return nil, fmt.Errorf("checkpoint unmarshal: %w", err)
	}
	logBGInfo("Checkpoint", "Loaded %s reason=%s msgs=%d", path, cp.Reason, len(cp.Messages))
	return &cp, nil
}

// clearCheckpoint removes the checkpoint file after successful resume
func clearCheckpoint(convID, taskID string) {
	path := checkpointPath(convID, taskID)
	os.Remove(path)
	logBGInfo("Checkpoint", "Cleared %s", path)
}

// buildResumeInjection builds the system-side injection message that orients the LLM on resume
func buildResumeInjection(cp *Checkpoint) string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("[SYSTEM: RESUME FROM CHECKPOINT — Reason: %s, Paused at: %s]\n\n",
		cp.Reason, cp.SavedAt.Format("15:04:05")))

	switch cp.Reason {
	case "rate_limit":
		sb.WriteString("The API rate limit was hit during your previous execution. The system has paused, waited, and is now resuming. Continue exactly where you left off. Your previous tool results are in the conversation history above.\n")
	case "bg_task":
		sb.WriteString("Background tasks have completed. Their snapshots are in the conversation history above. Analyze the results and decide: (1) continue next steps, (2) retry failed tasks, or (3) return a summary if goal is achieved.\n")
	case "max_iter":
		sb.WriteString("The tool-call iteration limit was reached in a previous session. This is a FRESH continuation. Review what was accomplished in the conversation above and pick up from where it stopped. Do NOT restart from scratch.\n")
	}

	if len(cp.BGTaskIDs) > 0 {
		sb.WriteString(fmt.Sprintf("\nBackground tasks that were running: %v\n", cp.BGTaskIDs))
		sb.WriteString("Their results have been fetched and injected into the conversation history.\n")
	}

	sb.WriteString("\nYour original goal was: " + cp.Command)
	return sb.String()
}

// fetchAndInjectBGResults looks up all checkpoint BGTaskIDs and appends their snapshots
// to the messages array so the LLM can analyze them on resume
func fetchAndInjectBGResults(messages []map[string]interface{}, bgTaskIDs []string) []map[string]interface{} {
	for _, id := range bgTaskIDs {
		snapshot, err := getBGTaskStatus(id)
		if err != nil {
			snapshot = fmt.Sprintf("[Task %s: status unavailable — %v]", id, err)
		}
		messages = append(messages, map[string]interface{}{
			"role":    "tool",
			"name":    "check_bg_task",
			"content": snapshot,
		})
		logBGInfo("Checkpoint", "Injected BG task %s snapshot (%d bytes)", id, len(snapshot))
	}
	return messages
}

// drainComradeNotifications drains any completed COMORADE task notifications and returns
// them as injection messages to be appended to the current conversation
func drainComradeNotifications() []map[string]interface{} {
	var injections []map[string]interface{}
	for {
		select {
		case notif := <-comradeNotifyCh:
			msg := fmt.Sprintf("[BG TASK COMORADE COMPLETED]\nTask ID: %s\nLabel: %s\n\n%s",
				notif.TaskID, notif.Label, notif.Snapshot)
			injections = append(injections, map[string]interface{}{
				"role":    "tool",
				"name":    "check_bg_task",
				"content": msg,
			})
			logBGInfo("Comrade", "Drained notification for task %s", notif.TaskID)
		default:
			return injections
		}
	}
}

// isDuplicateBGTask returns true if a task with the same command is already running
func isDuplicateBGTask(command string) (bool, string) {
	bgTasksMu.RLock()
	defer bgTasksMu.RUnlock()
	normalized := strings.TrimSpace(strings.ToLower(command))
	for id, task := range bgTasks {
		if task.Status == "running" && strings.TrimSpace(strings.ToLower(task.Command)) == normalized {
			return true, id
		}
	}
	return false, ""
}
