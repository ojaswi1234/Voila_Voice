package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"

	voilav1 "voice-cli-system/proto/v1"
	"golang.org/x/sys/windows"
)

var (
	user32                     = syscall.NewLazyDLL("user32.dll")
	procOpenClipboard          = user32.NewProc("OpenClipboard")
	procCloseClipboard         = user32.NewProc("CloseClipboard")
	procGetClipboardData       = user32.NewProc("GetClipboardData")
	procIsClipboardFormatAvail = user32.NewProc("IsClipboardFormatAvailable")
	procGlobalLock             = kernel32.NewProc("GlobalLock")
	procGlobalUnlock           = kernel32.NewProc("GlobalUnlock")
)

const (
	cfUnicodeText = 13
)

// ClipboardSuggestion represents a proactive analysis of copied error/content
type ClipboardSuggestion struct {
	ID             string    `json:"id"`
	Timestamp      time.Time `json:"timestamp"`
	Language       string    `json:"language"`
	Category       string    `json:"category"` // error, stacktrace, github_pr, json_snippet
	ErrorType      string    `json:"error_type"`
	Summary        string    `json:"summary"`
	RecommendedFix string    `json:"recommended_fix"`
	Snippet        string    `json:"snippet"`
}

type ClipboardInterceptor struct {
	mu           sync.Mutex
	lastHash     string
	lastAnalyzed time.Time
	stopChan     chan struct{}
	running      bool
}

var globalClipboardInterceptor = &ClipboardInterceptor{
	stopChan: make(chan struct{}),
}

// readWindowsClipboard reads the current text from the Windows clipboard safely
func readWindowsClipboard() (string, error) {
	// Try up to 3 times in case another process holds the clipboard lock momentarily
	for attempt := 0; attempt < 3; attempt++ {
		r, _, _ := procOpenClipboard.Call(0)
		if r != 0 {
			defer procCloseClipboard.Call()

			avail, _, _ := procIsClipboardFormatAvail.Call(uintptr(cfUnicodeText))
			if avail == 0 {
				return "", nil // No unicode text in clipboard
			}

			hMem, _, _ := procGetClipboardData.Call(uintptr(cfUnicodeText))
			if hMem == 0 {
				return "", nil
			}

			ptr, _, _ := procGlobalLock.Call(hMem)
			if ptr == 0 {
				return "", fmt.Errorf("failed to lock global memory")
			}
			defer procGlobalUnlock.Call(hMem)

			text := windows.UTF16PtrToString((*uint16)(unsafe.Pointer(ptr)))
			return text, nil
		}
		time.Sleep(20 * time.Millisecond)
	}
	return "", fmt.Errorf("could not open clipboard")
}

// redactSensitiveContent removes API keys, tokens, and credentials from text
func redactSensitiveContent(text string) string {
	patterns := []*regexp.Regexp{
		regexp.MustCompile(`(?i)(bearer\s+)[A-Za-z0-9\-_\.]{16,}`),
		regexp.MustCompile(`(?i)(sk-[A-Za-z0-9]{20,})`),
		regexp.MustCompile(`(?i)(ghp_[A-Za-z0-9]{20,})`),
		regexp.MustCompile(`(?i)(github_pat_[A-Za-z0-9]{20,})`),
		regexp.MustCompile(`(?i)(aws_access_key_id|aws_secret_access_key)\s*[:=]\s*[A-Za-z0-9\/+=]{16,}`),
		regexp.MustCompile(`(?i)(password|secret|passwd|token)\s*[:=]\s*["']?[^"'\s]{8,}["']?`),
	}

	res := text
	for _, p := range patterns {
		res = p.ReplaceAllString(res, "[REDACTED_CREDENTIAL]")
	}
	return res
}

// detectErrorCategory returns category, language, and error signature
func detectErrorCategory(text string) (category string, language string, errSig string) {
	lower := strings.ToLower(text)

	// Dart / Flutter errors
	if strings.Contains(text, "Unhandled Exception:") ||
		strings.Contains(lower, "flutter") && (strings.Contains(lower, "error") || strings.Contains(lower, "exception")) ||
		strings.Contains(text, "RenderFlex overflowed") ||
		strings.Contains(text, "The getter '") ||
		strings.Contains(text, "NoSuchMethodError") {
		return "stacktrace", "Dart/Flutter", extractFirstMatchingLine(text, []string{"Exception", "Error", "RenderFlex"})
	}

	// Python errors
	if strings.Contains(text, "Traceback (most recent call last):") ||
		strings.Contains(text, "SyntaxError:") ||
		strings.Contains(text, "AttributeError:") ||
		strings.Contains(text, "TypeError:") ||
		strings.Contains(text, "ModuleNotFoundError:") {
		return "stacktrace", "Python", extractFirstMatchingLine(text, []string{"Error:", "Exception:"})
	}

	// Go errors
	if strings.Contains(text, "panic: runtime error:") ||
		strings.Contains(text, "goroutine ") && strings.Contains(text, "[running]:") ||
		strings.Contains(text, "cannot use") && strings.Contains(text, "in argument to") ||
		strings.Contains(text, "undefined:") {
		return "stacktrace", "Go", extractFirstMatchingLine(text, []string{"panic:", "cannot use", "undefined:"})
	}

	// Node.js / TypeScript errors
	if strings.Contains(text, "ReferenceError:") ||
		strings.Contains(text, "Cannot find module") ||
		strings.Contains(text, "npm ERR!") ||
		strings.Contains(text, "TS") && strings.Contains(text, "error TS") ||
		strings.Contains(text, "Uncaught TypeError:") {
		return "stacktrace", "TypeScript/Node", extractFirstMatchingLine(text, []string{"Error:", "npm ERR!", "TS"})
	}

	// Rust errors
	if strings.Contains(text, "error[E") || strings.Contains(text, "panicked at '") {
		return "stacktrace", "Rust", extractFirstMatchingLine(text, []string{"error[E", "panicked at"})
	}

	// GitHub PR / Issue URLs
	prRegex := regexp.MustCompile(`https?://github\.com/[^/]+/[^/]+/(pull|issues)/\d+`)
	if prRegex.MatchString(text) {
		return "github_link", "GitHub", prRegex.FindString(text)
	}

	return "", "", ""
}

func extractFirstMatchingLine(text string, keywords []string) string {
	lines := strings.Split(text, "\n")
	for _, l := range lines {
		trimmed := strings.TrimSpace(l)
		for _, kw := range keywords {
			if strings.Contains(trimmed, kw) {
				return trimmed
			}
		}
	}
	if len(lines) > 0 {
		return strings.TrimSpace(lines[0])
	}
	return ""
}

// analyzeClipboardWithLLM generates a fast diagnosis using Ollama Cloud / Groq
func analyzeClipboardWithLLM(text, language, errSig string) (string, string) {
	connData, err := loadConnectionData()
	if err != nil {
		return errSig, "Inspect code around the failing stack frame or check dependencies."
	}

	prompt := fmt.Sprintf(`You are an expert compiler and runtime debugger. A developer just copied the following %s error to their clipboard:
"""
%s
"""
Analyze it concisely in exactly two lines:
ROOT_CAUSE: (1 sentence explaining the direct cause)
RECOMMENDED_FIX: (1 sentence specific code or command fix)`, language, text)

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	var completion string
	if connData.ActiveMode == "GROQ" && connData.GroqAPIKey != "" {
		m := connData.GroqModel
		if m == "" {
			m = "openai/gpt-oss-120b"
		}
		completion, _ = runFastCompletionGroq(ctx, prompt, connData.GroqAPIKey, m)
	} else if connData.OllamaAPIKey != "" || connData.OllamaBaseURL != "" {
		m := connData.OllamaModel
		if m == "" {
			m = "llama3.2"
		}
		completion, _ = runFastCompletionOllama(ctx, prompt, connData.OllamaBaseURL, m, connData.OllamaAPIKey)
	}

	var rootCause, recFix string
	lines := strings.Split(completion, "\n")
	for _, l := range lines {
		l = strings.TrimSpace(l)
		if strings.HasPrefix(l, "ROOT_CAUSE:") {
			rootCause = strings.TrimSpace(strings.TrimPrefix(l, "ROOT_CAUSE:"))
		} else if strings.HasPrefix(l, "RECOMMENDED_FIX:") {
			recFix = strings.TrimSpace(strings.TrimPrefix(l, "RECOMMENDED_FIX:"))
		}
	}

	if rootCause == "" {
		rootCause = errSig
	}
	if recFix == "" {
		recFix = "Inspect code around the failing stack frame or check dependencies."
	}

	return rootCause, recFix
}

// StartClipboardInterceptor launches the ambient clipboard monitor in a goroutine
func StartClipboardInterceptor() {
	globalClipboardInterceptor.mu.Lock()
	if globalClipboardInterceptor.running {
		globalClipboardInterceptor.mu.Unlock()
		return
	}
	globalClipboardInterceptor.running = true
	globalClipboardInterceptor.mu.Unlock()

	log.Printf("[Clipboard Watchdog] Ambient Smart Clipboard Interceptor started.")

	go func() {
		ticker := time.NewTicker(1500 * time.Millisecond)
		defer ticker.Stop()

		for {
			select {
			case <-globalClipboardInterceptor.stopChan:
				log.Printf("[Clipboard Watchdog] Interceptor stopped.")
				return
			case <-ticker.C:
				text, err := readWindowsClipboard()
				if err != nil || text == "" {
					continue
				}

				// Trim and bound length
				text = strings.TrimSpace(text)
				if len(text) < 15 || len(text) > 20000 {
					continue
				}

				// Check hash for change
				h := sha256.Sum256([]byte(text))
				hashStr := hex.EncodeToString(h[:])

				globalClipboardInterceptor.mu.Lock()
				if hashStr == globalClipboardInterceptor.lastHash {
					globalClipboardInterceptor.mu.Unlock()
					continue
				}
				// Throttling: at least 6s between analysis to prevent LLM spam
				if time.Since(globalClipboardInterceptor.lastAnalyzed) < 6*time.Second {
					globalClipboardInterceptor.mu.Unlock()
					continue
				}
				globalClipboardInterceptor.lastHash = hashStr
				globalClipboardInterceptor.lastAnalyzed = time.Now()
				globalClipboardInterceptor.mu.Unlock()

				// Detect categories
				category, language, errSig := detectErrorCategory(text)
				if category == "" {
					continue // Not an error or actionable link
				}

				log.Printf("[Clipboard Watchdog] Detected %s (%s): %s", category, language, errSig)

				// Redact any credentials before sending
				cleanSnippet := redactSensitiveContent(text)
				if len(cleanSnippet) > 800 {
					cleanSnippet = cleanSnippet[:800] + "..."
				}

				// Fast background analysis
				go func(snippet, cat, lang, sig string) {
					rootCause, recFix := analyzeClipboardWithLLM(snippet, lang, sig)

					suggestion := ClipboardSuggestion{
						ID:             fmt.Sprintf("clip-%d", time.Now().Unix()),
						Timestamp:      time.Now(),
						Language:       lang,
						Category:       cat,
						ErrorType:      sig,
						Summary:        rootCause,
						RecommendedFix: recFix,
						Snippet:        snippet,
					}

					payloadBytes, err := json.Marshal(suggestion)
					if err != nil {
						return
					}

					// Dispatch via gRPC Telemetry to root server
					if globalGRPCTunnelClient != nil && globalGRPCTunnelClient.isConnected.Load() {
						SendTelemetry(&voilav1.AgentTelemetry{
							DeviceId:    getDeviceID(),
							Status:      "IDLE",
							TimestampMs: time.Now().UnixMilli(),
							Payload: &voilav1.AgentTelemetry_FinalResult{
								FinalResult: &voilav1.ExecutionResult{
									CommandId: suggestion.ID,
									Summary:   "clipboard_suggestion",
									Output:    string(payloadBytes),
									Status:    "ok",
								},
							},
						})
						log.Printf("[Clipboard Watchdog] Dispatched proactive suggestion: %s", rootCause)
					}
				}(cleanSnippet, category, language, errSig)
			}
		}
	}()
}
