package decoy

import (
	"strings"
	"math/rand"
	"time"
)

// GenerateMockResponse generates plausible fake shell output for honeypot decoys.
func GenerateMockResponse(command string) string {
	cmdLower := strings.ToLower(strings.TrimSpace(command))
	
	if strings.Contains(cmdLower, "whoami") {
		return "user\\\\voila-desktop"
	}
	if strings.Contains(cmdLower, "dir") || strings.Contains(cmdLower, "ls") {
		return "Documents  Downloads  Desktop  Pictures  Music  Videos"
	}
	if strings.Contains(cmdLower, "pwd") {
		return "C:\\\\Users\\\\voila"
	}
	if strings.Contains(cmdLower, "echo") {
		parts := strings.SplitN(command, " ", 2)
		if len(parts) > 1 {
			return parts[1]
		}
		return ""
	}
	if strings.Contains(cmdLower, "help") {
		return "Available commands: dir, ls, whoami, pwd, echo, help"
	}
	
	// Generic response
	return "Command executed successfully"
}

// GetMockDelay returns a randomized delay duration for realistic decoy responses.
func GetMockDelay() time.Duration {
	return time.Duration(50+rand.Intn(250)) * time.Millisecond
}
