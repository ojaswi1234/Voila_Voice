package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"
)

type SurveillanceState struct {
	Armed           bool   `json:"armed"`
	Locked          bool   `json:"locked"`
	LastAlertTs     string `json:"last_alert_ts"`
	LastAlertReason string `json:"last_alert_reason"`
	GestureTrained  bool   `json:"gesture_trained"`
}

var (
	survState   SurveillanceState
	survStateMu sync.Mutex
	monitorCmd  *exec.Cmd
)

func getSurveillanceStatePath() string {
	return filepath.Join(getLocalAgentDir(), "surveillance_state.json")
}

func loadSurveillanceState() {
	survStateMu.Lock()
	defer survStateMu.Unlock()
	
	path := getSurveillanceStatePath()
	b, err := os.ReadFile(path)
	if err == nil {
		json.Unmarshal(b, &survState)
	}
	
	// Reset armed/locked on startup so we don't accidentally lock ourselves out if monitor isn't running
	survState.Armed = false
	survState.Locked = false
	saveSurveillanceStateLocked()
}

func saveSurveillanceStateLocked() {
	path := getSurveillanceStatePath()
	b, _ := json.MarshalIndent(survState, "", "  ")
	os.WriteFile(path, b, 0644)
}


var gestureDaemonCmd *exec.Cmd

func startGestureDaemon() {
	scriptPath := filepath.Join(getLocalAgentDir(), "surveillance", "gesture_omega.py")
	gestureDaemonCmd = exec.Command("python", scriptPath, "daemon")
	gestureDaemonCmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	err := gestureDaemonCmd.Start()
	if err == nil {
		go func(cmd *exec.Cmd) {
			cmd.Wait()
		}(gestureDaemonCmd)
	}
}

func startSurveillanceMonitor() {
	survStateMu.Lock()
	defer survStateMu.Unlock()
	if monitorCmd != nil && monitorCmd.Process != nil {
		return // already running
	}
	
	scriptPath := filepath.Join(getLocalAgentDir(), "surveillance", "monitor.py")
	monitorCmd = exec.Command("python", scriptPath)
	monitorCmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	err := monitorCmd.Start()
	if err == nil {
		go func(cmd *exec.Cmd) {
			cmd.Wait()
		}(monitorCmd)
	}
}

func stopSurveillanceMonitor() {
	survStateMu.Lock()
	defer survStateMu.Unlock()
	if monitorCmd != nil && monitorCmd.Process != nil {
		monitorCmd.Process.Kill()
		monitorCmd = nil
	}
}

func setupSurveillanceRoutes(mux *http.ServeMux) {
	startGestureDaemon()
	mux.HandleFunc("/surveillance/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		survStateMu.Lock()
		defer survStateMu.Unlock()
		json.NewEncoder(w).Encode(survState)
	})

	mux.HandleFunc("/surveillance/arm", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		log.Printf("[Surveillance] ARM requested")
		survStateMu.Lock()
		survState.Armed = true
		saveSurveillanceStateLocked()
		survStateMu.Unlock()
		startSurveillanceMonitor()
		w.Write([]byte(`{"status":"armed"}`))
	})

	mux.HandleFunc("/surveillance/disarm", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		log.Printf("[Surveillance] DISARM requested")
		survStateMu.Lock()
		survState.Armed = false
		survState.Locked = false
		saveSurveillanceStateLocked()
		survStateMu.Unlock()
		stopSurveillanceMonitor()
		w.Write([]byte(`{"status":"disarmed"}`))
	})

	mux.HandleFunc("/surveillance/lock", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		log.Printf("[Surveillance] LOCK requested")
		survStateMu.Lock()
		survState.Locked = true
		// Lock implicitly arms
		survState.Armed = true
		saveSurveillanceStateLocked()
		survStateMu.Unlock()
		startSurveillanceMonitor()
		w.Write([]byte(`{"status":"locked"}`))
	})

	mux.HandleFunc("/surveillance/unlock", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		log.Printf("[Surveillance] UNLOCK requested")
		survStateMu.Lock()
		survState.Locked = false
		survState.Armed = false
		saveSurveillanceStateLocked()
		survStateMu.Unlock()
		stopSurveillanceMonitor()
		w.Write([]byte(`{"status":"unlocked"}`))
	})

	mux.HandleFunc("/surveillance/alert", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		if r.Method == "POST" {
			var payload map[string]string
			if err := json.NewDecoder(r.Body).Decode(&payload); err == nil {
				reason := payload["reason"]
				log.Printf("[Surveillance] INTRUDER ALERT: %s", reason)
				survStateMu.Lock()
				survState.LastAlertTs = time.Now().Format(time.RFC3339)
				survState.LastAlertReason = reason
				saveSurveillanceStateLocked()
				survStateMu.Unlock()
				
				// Push intruder alert to mobile! (In prototype, mobile polls /surveillance/status)
			}
		}
		w.Write([]byte(`{"status":"ok"}`))
	})
	
	mux.HandleFunc("/surveillance/gesture/train", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		scriptPath := filepath.Join(getLocalAgentDir(), "surveillance", "gesture_omega.py")
		cmd := exec.Command("python", scriptPath, "train")
		out, _ := cmd.CombinedOutput()
		
		survStateMu.Lock()
		survState.GestureTrained = true
		saveSurveillanceStateLocked()
		survStateMu.Unlock()
		
		w.Write([]byte(fmt.Sprintf(`{"status":"trained", "output": "%s"}`, string(out))))
	})
	
	mux.HandleFunc("/surveillance/gesture/capture", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		intent := r.URL.Query().Get("intent") // "lock" or "unlock"
		
		scriptPath := filepath.Join(getLocalAgentDir(), "surveillance", "gesture_omega.py")
		cmd := exec.Command("python", scriptPath, "capture")
		outBytes, _ := cmd.CombinedOutput()
		out := string(outBytes)
		
		result := "no_match"
		if intent == "lock" && bytesContains(outBytes, []byte("MATCH_OMEGA")) {
			result = "matched_lock"
			survStateMu.Lock()
			survState.Locked = true
			survState.Armed = true
			saveSurveillanceStateLocked()
			survStateMu.Unlock()
			startSurveillanceMonitor()
		} else if intent == "unlock" && bytesContains(outBytes, []byte("MATCH_WATER_OMEGA")) {
			result = "matched_unlock"
			survStateMu.Lock()
			survState.Locked = false
			survState.Armed = false
			saveSurveillanceStateLocked()
			survStateMu.Unlock()
			stopSurveillanceMonitor()
		}
		
		w.Write([]byte(fmt.Sprintf(`{"result":"%s", "raw": "%s"}`, result, out)))
	})
}

func bytesContains(b []byte, sub []byte) bool {
	// Simple helper to avoid importing bytes if not needed
	s := string(b)
	subStr := string(sub)
	return len(s) >= len(subStr) && (s == subStr || s[:len(subStr)] == subStr || s[len(s)-len(subStr):] == subStr || func() bool {
		for i := 0; i <= len(s)-len(subStr); i++ {
			if s[i:i+len(subStr)] == subStr {
				return true
			}
		}
		return false
	}())
}

func isSurveillanceLocked() bool {
	survStateMu.Lock()
	defer survStateMu.Unlock()
	return survState.Locked
}
