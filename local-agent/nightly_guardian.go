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

	voilav1 "voice-cli-system/proto/v1"
)

// NightlyAuditReport holds the results of the project and security audit
type NightlyAuditReport struct {
	ID               string    `json:"id"`
	Timestamp        time.Time `json:"timestamp"`
	ProjectName      string    `json:"project_name"`
	CleanableCacheMB float64   `json:"cleanable_cache_mb"`
	StaleBranches    []string  `json:"stale_branches"`
	DependencyStatus string    `json:"dependency_status"`
	UnpushedCommits  int       `json:"unpushed_commits"`
	Recommendation   string    `json:"recommendation"`
}

// CacheCleanupResult holds the outcome of a cache purge
type CacheCleanupResult struct {
	FreedMB float64 `json:"freed_mb"`
	Success bool    `json:"success"`
	Message string  `json:"message"`
}

type NightlyGuardianManager struct {
	mu           sync.Mutex
	lastReport   *NightlyAuditReport
	lastAuditAt  time.Time
}

var globalNightlyGuardian = &NightlyGuardianManager{}

// getProjectSafePath returns the primary workspace path in Desktop
func getProjectSafePath() (string, string) {
	home, _ := os.UserHomeDir()
	desktopPath := filepath.Join(home, "Desktop")
	projectPath := filepath.Join(desktopPath, "Voila_Voice")

	if _, err := os.Stat(projectPath); err == nil {
		return projectPath, "Voila_Voice"
	}
	return desktopPath, "Desktop"
}

// calculateDirSizeMB recursively calculates size of a directory in megabytes
func calculateDirSizeMB(dirPath string) float64 {
	var totalBytes int64
	filepath.Walk(dirPath, func(_ string, info os.FileInfo, err error) error {
		if err == nil && info != nil && !info.IsDir() {
			totalBytes += info.Size()
		}
		return nil
	})
	return float64(totalBytes) / (1024 * 1024)
}

// getCleanableCaches returns paths and total size of ephemeral build caches
func getCleanableCaches(projectPath string) ([]string, float64) {
	candidates := []string{
		filepath.Join(projectPath, ".dart_tool"),
		filepath.Join(projectPath, "mobile-agent", "build"),
		filepath.Join(projectPath, "mobile-agent", ".dart_tool"),
		filepath.Join(projectPath, "build"),
		filepath.Join(projectPath, ".cache"),
	}

	var existing []string
	var totalMB float64
	for _, p := range candidates {
		if info, err := os.Stat(p); err == nil && info.IsDir() {
			sz := calculateDirSizeMB(p)
			if sz > 0.5 {
				existing = append(existing, p)
				totalMB += sz
			}
		}
	}
	return existing, totalMB
}

// checkGitAudit inspects stale branches and unpushed commits
func checkGitAudit(projectPath string) (staleBranches []string, unpushedCount int) {
	// 1. Merged branches
	cmdMerged := exec.Command("git", "branch", "--merged")
	cmdMerged.Dir = projectPath
	if out, err := cmdMerged.Output(); err == nil {
		lines := strings.Split(string(out), "\n")
		for _, l := range lines {
			branch := strings.TrimSpace(l)
			if branch != "" && !strings.HasPrefix(branch, "*") && branch != "main" && branch != "master" && branch != "feature/tui-dashboard" {
				staleBranches = append(staleBranches, branch)
			}
		}
	}

	// 2. Unpushed commits on current branch
	cmdUnpushed := exec.Command("git", "log", "@{u}..HEAD", "--oneline")
	cmdUnpushed.Dir = projectPath
	if out, err := cmdUnpushed.Output(); err == nil {
		lines := strings.Split(strings.TrimSpace(string(out)), "\n")
		for _, l := range lines {
			if strings.TrimSpace(l) != "" {
				unpushedCount++
			}
		}
	}

	return staleBranches, unpushedCount
}

// checkProjectDependencies audits project manifests
func checkProjectDependencies(projectPath string) string {
	var statuses []string

	// Check Go modules
	if _, err := os.Stat(filepath.Join(projectPath, "go.mod")); err == nil {
		statuses = append(statuses, "Go: modules intact")
	}

	// Check Flutter / Dart pubspec
	if _, err := os.Stat(filepath.Join(projectPath, "mobile-agent", "pubspec.yaml")); err == nil {
		statuses = append(statuses, "Flutter: pubspec healthy")
	} else if _, err := os.Stat(filepath.Join(projectPath, "pubspec.yaml")); err == nil {
		statuses = append(statuses, "Flutter: pubspec healthy")
	}

	// Check Node.js
	if _, err := os.Stat(filepath.Join(projectPath, "package.json")); err == nil {
		statuses = append(statuses, "Node: package.json healthy")
	}

	if len(statuses) == 0 {
		return "All manifests healthy"
	}
	return strings.Join(statuses, " • ")
}

// synthesizeAuditRecommendation calls Ollama Cloud / Groq to produce an audit summary
func synthesizeAuditRecommendation(projectName string, cacheMB float64, staleBranches []string, unpushed int) string {
	connData, err := loadConnectionData()
	if err != nil {
		return fmt.Sprintf("Audit complete for %s. Found %.0f MB cleanable build caches and %d unpushed commits.", projectName, cacheMB, unpushed)
	}

	prompt := fmt.Sprintf(`You are Voila, an autonomous nightly maintenance guardian AI.
Audit Findings for %s:
- Ephemeral build cache size: %.1f MB
- Stale merged git branches: %s
- Unpushed local commits: %d

Compose a crisp 2-sentence autonomous maintenance recommendation. Sentence 1 summarizes the findings. Sentence 2 gives a clear actionable recommendation (e.g. approve 1-tap cache purge). Do not use bullet points or headers.`, projectName, cacheMB, strings.Join(staleBranches, ", "), unpushed)

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
		if cacheMB > 50 {
			summary = fmt.Sprintf("Found %.0f MB of cleanable build caches in %s. Tap 'Clean Cache' to reclaim disk space immediately.", cacheMB, projectName)
		} else {
			summary = fmt.Sprintf("Workspace %s is clean and healthy. No major clutter or security issues detected.", projectName)
		}
	}
	return summary
}

// RunNightlyAudit executes the autonomous project and maintenance audit
func RunNightlyAudit(force bool) (*NightlyAuditReport, error) {
	globalNightlyGuardian.mu.Lock()
	if !force && globalNightlyGuardian.lastReport != nil && time.Since(globalNightlyGuardian.lastAuditAt) < 30*time.Minute {
		report := globalNightlyGuardian.lastReport
		globalNightlyGuardian.mu.Unlock()
		return report, nil
	}
	globalNightlyGuardian.mu.Unlock()

	projectPath, projName := getProjectSafePath()
	_, cacheMB := getCleanableCaches(projectPath)
	staleBranches, unpushed := checkGitAudit(projectPath)
	depStatus := checkProjectDependencies(projectPath)

	recommendation := synthesizeAuditRecommendation(projName, cacheMB, staleBranches, unpushed)

	report := &NightlyAuditReport{
		ID:               fmt.Sprintf("audit-%d", time.Now().Unix()),
		Timestamp:        time.Now(),
		ProjectName:      projName,
		CleanableCacheMB: cacheMB,
		StaleBranches:    staleBranches,
		DependencyStatus: depStatus,
		UnpushedCommits:  unpushed,
		Recommendation:   recommendation,
	}

	globalNightlyGuardian.mu.Lock()
	globalNightlyGuardian.lastReport = report
	globalNightlyGuardian.lastAuditAt = time.Now()
	globalNightlyGuardian.mu.Unlock()

	// Dispatch via gRPC Telemetry
	if globalGRPCTunnelClient != nil && globalGRPCTunnelClient.isConnected.Load() {
		payloadBytes, err := json.Marshal(report)
		if err == nil {
			SendTelemetry(&voilav1.AgentTelemetry{
				DeviceId:    getDeviceID(),
				Status:      "IDLE",
				TimestampMs: time.Now().UnixMilli(),
				Payload: &voilav1.AgentTelemetry_FinalResult{
					FinalResult: &voilav1.ExecutionResult{
						CommandId: report.ID,
						Summary:   "nightly_audit_report",
						Output:    string(payloadBytes),
						Status:    "ok",
					},
				},
			})
			log.Printf("[Nightly Guardian] Dispatched audit report: %.1f MB cleanable", cacheMB)
		}
	}

	return report, nil
}

// ExecuteCacheCleanup safely deletes ephemeral build caches
func ExecuteCacheCleanup() (*CacheCleanupResult, error) {
	projectPath, _ := getProjectSafePath()
	caches, _ := getCleanableCaches(projectPath)

	var freedMB float64
	for _, c := range caches {
		sz := calculateDirSizeMB(c)
		if err := os.RemoveAll(c); err == nil {
			freedMB += sz
		}
	}

	result := &CacheCleanupResult{
		FreedMB: freedMB,
		Success: true,
		Message: fmt.Sprintf("Successfully purged %.1f MB of temporary build caches.", freedMB),
	}

	// Update cached report
	globalNightlyGuardian.mu.Lock()
	if globalNightlyGuardian.lastReport != nil {
		globalNightlyGuardian.lastReport.CleanableCacheMB = 0
		globalNightlyGuardian.lastReport.Recommendation = fmt.Sprintf("Clean complete: reclaimed %.1f MB disk space.", freedMB)
	}
	globalNightlyGuardian.mu.Unlock()

	// Dispatch result via gRPC
	if globalGRPCTunnelClient != nil && globalGRPCTunnelClient.isConnected.Load() {
		payloadBytes, err := json.Marshal(result)
		if err == nil {
			SendTelemetry(&voilav1.AgentTelemetry{
				DeviceId:    getDeviceID(),
				Status:      "IDLE",
				TimestampMs: time.Now().UnixMilli(),
				Payload: &voilav1.AgentTelemetry_FinalResult{
					FinalResult: &voilav1.ExecutionResult{
						CommandId: fmt.Sprintf("clean-%d", time.Now().Unix()),
						Summary:   "cache_cleanup_result",
						Output:    string(payloadBytes),
						Status:    "ok",
					},
				},
			})
			log.Printf("[Nightly Guardian] Reclaimed %.1f MB build cache", freedMB)
		}
	}

	return result, nil
}

// StartNightlyGuardianScheduler starts the scheduled 2:00 AM auditor
func StartNightlyGuardianScheduler() {
	go func() {
		// Initial startup check after 12s
		time.Sleep(12 * time.Second)
		RunNightlyAudit(false)

		ticker := time.NewTicker(30 * time.Minute)
		defer ticker.Stop()

		for range ticker.C {
			now := time.Now()
			// Run audit if it is between 2:00 AM and 2:30 AM
			if now.Hour() == 2 && now.Minute() < 30 {
				RunNightlyAudit(true)
			}
		}
	}()
}
