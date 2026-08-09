package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"
)

const PASSPHRASE = "secret passphrase"

type Task struct {
	ID        int
	Command   string
	Status    string // "pending", "running", "completed", "failed"
	Result    string
	CreatedAt time.Time
}

type Agent struct {
	authenticated bool
	tasks          []Task
	taskFile       string
	mu             sync.RWMutex
}

type CommandRequest struct {
	Command string `json:"command"`
}

type CommandResponse struct {
	Output string `json:"output"`
	Error  string `json:"error,omitempty"`
}

func NewAgent() *Agent {
	taskFile := "tasks.json"
	
	// Load existing tasks
	tasks := loadTasks(taskFile)
	
	return &Agent{
		authenticated: false,
		tasks:          tasks,
		taskFile:       taskFile,
	}
}

func loadTasks(filename string) []Task {
	data, err := os.ReadFile(filename)
	if err != nil {
		return []Task{}
	}
	
	var tasks []Task
	err = json.Unmarshal(data, &tasks)
	if err != nil {
		return []Task{}
	}
	
	return tasks
}

func saveTasks(filename string, tasks []Task) error {
	data, err := json.MarshalIndent(tasks, "", "  ")
	if err != nil {
		return err
	}
	
	return os.WriteFile(filename, data, 0644)
}

func (a *Agent) addTask(command string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	
	task := Task{
		ID:        len(a.tasks) + 1,
		Command:   command,
		Status:    "pending",
		CreatedAt: time.Now(),
	}
	
	a.tasks = append(a.tasks, task)
	return saveTasks(a.taskFile, a.tasks)
}

func (a *Agent) processPendingTasks() error {
	a.mu.Lock()
	defer a.mu.Unlock()
	
	for i := range a.tasks {
		if a.tasks[i].Status == "pending" {
			// Mark as running
			a.tasks[i].Status = "running"
			saveTasks(a.taskFile, a.tasks)
			
			// Execute command
			result := a.executeCommand(a.tasks[i].Command)
			
			// Update with result
			if strings.Contains(result, "ERROR") {
				a.tasks[i].Status = "failed"
			} else {
				a.tasks[i].Status = "completed"
			}
			a.tasks[i].Result = result
			
			saveTasks(a.taskFile, a.tasks)
			log.Printf("Task %d completed: %s", a.tasks[i].ID, a.tasks[i].Status)
		}
	}
	
	return nil
}

func (a *Agent) getTaskHistory() []Task {
	a.mu.RLock()
	defer a.mu.RUnlock()
	
	// Return last 50 tasks
	if len(a.tasks) <= 50 {
		return a.tasks
	}
	
	return a.tasks[len(a.tasks)-50:]
}

func (a *Agent) verifyPassphrase(input string) bool {
	return strings.TrimSpace(input) == PASSPHRASE
}

func (a *Agent) executeCommand(cmd string) string {
	a.mu.RLock()
	auth := a.authenticated
	a.mu.RUnlock()

	if !auth {
		return "ERROR: Not authenticated"
	}

	// Execute via PowerShell for Windows compatibility
	execCmd := exec.Command("powershell", "-Command", cmd)
	output, err := execCmd.CombinedOutput()
	if err != nil {
		return fmt.Sprintf("ERROR: %v\nOutput: %s", err, string(output))
	}

	return string(output)
}

func (a *Agent) handleExecute(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req CommandRequest
	err := json.NewDecoder(r.Body).Decode(&req)
	if err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		return
	}

	// Execute directly for now (synchronous)
	output := a.executeCommand(req.Command)
	response := CommandResponse{Output: output}
	
	json.NewEncoder(w).Encode(response)
}

func (a *Agent) handleHistory(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	tasks := a.getTaskHistory()
	json.NewEncoder(w).Encode(tasks)
}

func (a *Agent) handleQueue(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req CommandRequest
	err := json.NewDecoder(r.Body).Decode(&req)
	if err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		return
	}

	// Add to offline queue
	err = a.addTask(req.Command)
	if err != nil {
		http.Error(w, "Failed to queue task", http.StatusInternalServerError)
		return
	}

	response := CommandResponse{Output: "Command added to offline queue"}
	json.NewEncoder(w).Encode(response)
}

func (a *Agent) handleProcess(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Process pending tasks
	go a.processPendingTasks()

	response := CommandResponse{Output: "Processing pending tasks"}
	json.NewEncoder(w).Encode(response)
}

func (a *Agent) handleAuth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		Passphrase string `json:"passphrase"`
	}
	
	err := json.NewDecoder(r.Body).Decode(&req)
	if err != nil {
		log.Printf("JSON decode error: %v", err)
		http.Error(w, "Invalid request: "+err.Error(), http.StatusBadRequest)
		return
	}

	log.Printf("Auth attempt with passphrase: %s", req.Passphrase)

	if a.verifyPassphrase(req.Passphrase) {
		a.mu.Lock()
		a.authenticated = true
		a.mu.Unlock()
		
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]bool{"authenticated": true})
		log.Println("Authentication successful")
	} else {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		json.NewEncoder(w).Encode(map[string]bool{"authenticated": false})
		log.Println("Authentication failed")
	}
}

func main() {
	agent := NewAgent()

	// Process any pending tasks from previous session (offline recovery)
	log.Println("Processing pending tasks from offline queue...")
	go agent.processPendingTasks()

	// Start HTTP server for backend communication
	http.HandleFunc("/execute", agent.handleExecute)
	http.HandleFunc("/auth", agent.handleAuth)
	http.HandleFunc("/history", agent.handleHistory)
	http.HandleFunc("/queue", agent.handleQueue)
	http.HandleFunc("/process", agent.handleProcess)

	log.Println("Antigravity Local Agent Started")
	log.Println("HTTP server starting on :8088")
	log.Fatal(http.ListenAndServe(":8088", nil))
}
