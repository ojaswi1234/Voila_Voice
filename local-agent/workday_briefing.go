package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
	"unsafe"

	voilav1 "voice-cli-system/proto/v1"
	"golang.org/x/sys/windows"
)

var (
	procGlobalMemoryStatusEx = kernel32.NewProc("GlobalMemoryStatusEx")
	procGetDiskFreeSpaceExW  = kernel32.NewProc("GetDiskFreeSpaceExW")
	procGetTickCount64       = kernel32.NewProc("GetTickCount64")
)

type memoryStatusEx struct {
	Length               uint32
	MemoryLoad           uint32
	TotalPhys            uint64
	AvailPhys            uint64
	TotalPageFile        uint64
	AvailPageFile        uint64
	TotalVirtual         uint64
	AvailVirtual         uint64
	AvailExtendedVirtual uint64
}

// WorkdayBriefing represents a synthesized morning/workday context update
type WorkdayBriefing struct {
	ID               string    `json:"id"`
	Timestamp        time.Time `json:"timestamp"`
	Date             string    `json:"date"`
	Greeting         string    `json:"greeting"`
	ProjectName      string    `json:"project_name"`
	GitBranch        string    `json:"git_branch"`
	UncommittedCount int       `json:"uncommitted_count"`
	TotalRamGB       float64   `json:"total_ram_gb"`
	FreeRamGB        float64   `json:"free_ram_gb"`
	FreeDiskGB       float64   `json:"free_disk_gb"`
	Uptime           string    `json:"uptime"`
	ActiveTasksCount int       `json:"active_tasks_count"`
	SummaryText      string    `json:"summary_text"`
}

type BriefingManager struct {
	mu           sync.Mutex
	lastBriefing *WorkdayBriefing
	lastGenerated time.Time
}

var globalBriefingManager = &BriefingManager{}

// getSystemVitals reads RAM, primary disk space, and uptime via Win32 APIs
func getSystemVitals() (totalRamGB, freeRamGB, freeDiskGB float64, uptime string) {
	// 1. RAM via GlobalMemoryStatusEx
	var mem memoryStatusEx
	mem.Length = uint32(unsafe.Sizeof(mem))
	r1, _, _ := procGlobalMemoryStatusEx.Call(uintptr(unsafe.Pointer(&mem)))
	if r1 != 0 {
		totalRamGB = float64(mem.TotalPhys) / (1024 * 1024 * 1024)
		freeRamGB = float64(mem.AvailPhys) / (1024 * 1024 * 1024)
	}

	// 2. Primary drive free space on C:\
	cPath, err := windows.UTF16PtrFromString("C:\\")
	if err == nil {
		var freeBytesAvail, totalBytes, totalFreeBytes uint64
		r2, _, _ := procGetDiskFreeSpaceExW.Call(
			uintptr(unsafe.Pointer(cPath)),
			uintptr(unsafe.Pointer(&freeBytesAvail)),
			uintptr(unsafe.Pointer(&totalBytes)),
			uintptr(unsafe.Pointer(&totalFreeBytes)),
		)
		if r2 != 0 {
			freeDiskGB = float64(freeBytesAvail) / (1024 * 1024 * 1024)
		}
	}

	// 3. Uptime via GetTickCount64
	r3, _, _ := procGetTickCount64.Call()
	if r3 != 0 {
		dur := time.Duration(r3) * time.Millisecond
		h := int(dur.Hours())
		m := int(dur.Minutes()) % 60
		if h > 24 {
			days := h / 24
			uptime = fmt.Sprintf("%dd %dh", days, h%24)
		} else {
			uptime = fmt.Sprintf("%dh %dm", h, m)
		}
	} else {
		uptime = "unknown"
	}

	return totalRamGB, freeRamGB, freeDiskGB, uptime
}

// getProjectGitStats runs git queries safely in the project directory
func getProjectGitStats() (projectName, branch string, uncommittedCount int) {
	home, _ := os.UserHomeDir()
	desktopPath := filepath.Join(home, "Desktop")
	projectPath := filepath.Join(desktopPath, "Voila_Voice")

	if _, err := os.Stat(projectPath); err != nil {
		projectPath = desktopPath
		projectName = "Desktop"
	} else {
		projectName = "Voila_Voice"
	}

	// 1. Get branch
	cmdBranch := exec.Command("git", "branch", "--show-current")
	cmdBranch.Dir = projectPath
	if out, err := cmdBranch.Output(); err == nil {
		branch = strings.TrimSpace(string(out))
	}
	if branch == "" {
		branch = "main"
	}

	// 2. Get uncommitted files count
	cmdStatus := exec.Command("git", "status", "--porcelain")
	cmdStatus.Dir = projectPath
	if out, err := cmdStatus.Output(); err == nil {
		lines := strings.Split(strings.TrimSpace(string(out)), "\n")
		count := 0
		for _, l := range lines {
			if strings.TrimSpace(l) != "" {
				count++
			}
		}
		uncommittedCount = count
	}

	return projectName, branch, uncommittedCount
}

// synthesizeBriefingSummary calls Ollama Cloud / Groq to produce a 2-3 sentence executive summary
func synthesizeBriefingSummary(projectName, branch string, uncommitted int, freeRam, freeDisk float64, uptime string, activeTasks int) string {
	connData, err := loadConnectionData()
	if err != nil {
		return fmt.Sprintf("Workspace '%s' is on branch '%s' with %d uncommitted items. System has %.1f GB RAM and %.0f GB disk available.", projectName, branch, uncommitted, freeRam, freeDisk)
	}

	prompt := fmt.Sprintf(`You are Voila, an autonomous proactive developer AI assistant.
Current Developer State:
- Project: %s (Branch: %s)
- Uncommitted modified files: %d
- Available System RAM: %.1f GB
- Available Disk Space: %.0f GB
- Host Uptime: %s
- Active background tasks: %d

Compose a crisp, energetic, highly professional morning/workday executive briefing in EXACTLY two sentences. Sentence 1 covers workspace and branch readiness. Sentence 2 covers system vitals and readiness for today's work. Do not output markdown titles or bullet points.`, projectName, branch, uncommitted, freeRam, freeDisk, uptime, activeTasks)

	ctx, cancel := context.WithTimeout(context.Background(), 16*time.Second)
	defer cancel()

	var summary string
	if connData.ActiveMode == "GROQ" && connData.GroqAPIKey != "" {
		m := connData.GroqModel
		if m == "" {
			m = "openai/gpt-oss-120b"
		}
		summary, _ = runFastCompletionGroq(ctx, prompt, connData.GroqAPIKey, m)
	} else if connData.OllamaAPIKey != "" || connData.OllamaBaseURL != "" {
		m := connData.OllamaModel
		if m == "" {
			m = "llama3.2"
		}
		summary, _ = runFastCompletionOllama(ctx, prompt, connData.OllamaBaseURL, m, connData.OllamaAPIKey)
	}

	summary = strings.TrimSpace(summary)
	if summary == "" {
		summary = fmt.Sprintf("Workspace '%s' is active on '%s' with %d uncommitted changes. System has %.1f GB RAM and %.0f GB disk free.", projectName, branch, uncommitted, freeRam, freeDisk)
	}

	return summary
}

// GenerateAndDispatchWorkdayBriefing creates and broadcasts the workday briefing
func GenerateAndDispatchWorkdayBriefing(force bool) (*WorkdayBriefing, error) {
	globalBriefingManager.mu.Lock()
	if !force && globalBriefingManager.lastBriefing != nil && time.Since(globalBriefingManager.lastGenerated) < 45*time.Minute {
		briefing := globalBriefingManager.lastBriefing
		globalBriefingManager.mu.Unlock()
		return briefing, nil
	}
	globalBriefingManager.mu.Unlock()

	now := time.Now()
	hour := now.Hour()
	var greeting string
	if hour < 12 {
		greeting = "Good morning!"
	} else if hour < 17 {
		greeting = "Good afternoon!"
	} else {
		greeting = "Good evening!"
	}

	totalRam, freeRam, freeDisk, uptime := getSystemVitals()
	projName, branch, uncommitted := getProjectGitStats()
	activeTasks := getActiveBGTaskCount()

	summary := synthesizeBriefingSummary(projName, branch, uncommitted, freeRam, freeDisk, uptime, activeTasks)

	briefing := &WorkdayBriefing{
		ID:               fmt.Sprintf("brief-%d", now.Unix()),
		Timestamp:        now,
		Date:             now.Format("Monday, Jan 2"),
		Greeting:         greeting,
		ProjectName:      projName,
		GitBranch:        branch,
		UncommittedCount: uncommitted,
		TotalRamGB:       totalRam,
		FreeRamGB:        freeRam,
		FreeDiskGB:       freeDisk,
		Uptime:           uptime,
		ActiveTasksCount: activeTasks,
		SummaryText:      summary,
	}

	globalBriefingManager.mu.Lock()
	globalBriefingManager.lastBriefing = briefing
	globalBriefingManager.lastGenerated = now
	globalBriefingManager.mu.Unlock()

	// Dispatch telemetry via gRPC to root server
	if globalGRPCTunnelClient != nil && globalGRPCTunnelClient.isConnected.Load() {
		payloadBytes, err := json.Marshal(briefing)
		if err == nil {
			SendTelemetry(&voilav1.AgentTelemetry{
				DeviceId:    getDeviceID(),
				Status:      "IDLE",
				TimestampMs: now.UnixMilli(),
				Payload: &voilav1.AgentTelemetry_FinalResult{
					FinalResult: &voilav1.ExecutionResult{
						CommandId: briefing.ID,
						Summary:   "workday_briefing",
						Output:    string(payloadBytes),
						Status:    "ok",
					},
				},
			})
			log.Printf("[Workday Briefing] Broadcasted morning briefing: %s", summary)
		}
	}

	return briefing, nil
}

// StartWorkdayBriefingScheduler kicks off an initial check and periodic hourly refresh
func StartWorkdayBriefingScheduler() {
	go func() {
		// Wait 8 seconds after boot for gRPC and Ollama connections to stabilize
		time.Sleep(8 * time.Second)
		GenerateAndDispatchWorkdayBriefing(false)

		ticker := time.NewTicker(60 * time.Minute)
		defer ticker.Stop()

		for range ticker.C {
			GenerateAndDispatchWorkdayBriefing(false)
		}
	}()
}
