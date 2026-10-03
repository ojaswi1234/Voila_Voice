package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sync"
	
)

var (
	bgLog   *log.Logger
	bgLogMu sync.Mutex
)

// initBGLogger creates a dedicated 'bglogs' directory and initializes a comprehensive logger
// for the background task and checkpointing mechanisms.
func initBGLogger() {
	bgLogMu.Lock()
	defer bgLogMu.Unlock()

	if bgLog != nil {
		return
	}

	exeDir, err := os.Executable()
	if err != nil {
		exeDir = "."
	}
	baseDir := filepath.Dir(exeDir)

	bgLogsDir := filepath.Join(baseDir, "bglogs")
	if err := os.MkdirAll(bgLogsDir, 0755); err != nil {
		fmt.Printf("Warning: Could not create bglogs directory: %v\n", err)
		bgLogsDir = filepath.Join(os.TempDir(), "voila_bglogs")
		os.MkdirAll(bgLogsDir, 0755)
	}

	logFile := filepath.Join(bgLogsDir, "bg_workflow.log")
	f, err := os.OpenFile(logFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		fmt.Printf("Warning: Could not open bg_workflow.log: %v\n", err)
		return
	}

	bgLog = log.New(f, "", log.Ldate|log.Ltime|log.Lmicroseconds)
	bgLog.Printf("=== BG TASK LOGGER INITIALIZED [PID=%d] ===", os.Getpid())
}

// writeBGLog is a helper to write to the bgLogger safely
func writeBGLog(level, component, format string, args ...interface{}) {
	bgLogMu.Lock()
	defer bgLogMu.Unlock()
	
	if bgLog == nil {
		return
	}

	msg := fmt.Sprintf(format, args...)
	bgLog.Printf("[%s] [%s] %s", level, component, msg)
}

// Convenience loggers
func logBGInfo(component, format string, args ...interface{}) {
	writeBGLog("INFO", component, format, args...)
}

func logBGWarn(component, format string, args ...interface{}) {
	writeBGLog("WARN", component, format, args...)
}

func logBGError(component, format string, args ...interface{}) {
	writeBGLog("ERROR", component, format, args...)
}

func logBGDebug(component, format string, args ...interface{}) {
	// Can be toggled if needed, currently always logs
	writeBGLog("DEBUG", component, format, args...)
}
