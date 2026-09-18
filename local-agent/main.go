package main

/*
================================================================================
Voila Voice CLI - Main Entry Point
================================================================================
This file acts as the core router and HTTP server for the Voila local agent.
Responsibilities:
1. HTTP Server Setup (/execute, /ping, /stop endpoints)
2. Tool Registry (defines all tools the AI can use, e.g. run_terminal, create_pdf)
3. Provider execution loops (executeGroqCommand, executeOllamaCommand) which 
   handle the iterative process of calling an LLM, executing its tool requests,
   and feeding the results back.
4. Security Guardrails (blocking destructive terminal commands).
================================================================================
*/


import (
	"unsafe"
	"golang.org/x/crypto/pbkdf2"
	"voice-cli-system/shared/decoy"

	"bufio"
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"strconv"
	"sync"
	"syscall"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// --- ZERO ORPHAN PROCESS MANAGEMENT ---

type JOBOBJECT_BASIC_LIMIT_INFORMATION struct {
	PerProcessUserTimeLimit int64
	PerJobUserTimeLimit     int64
	LimitFlags              uint32
	MinimumWorkingSetSize   uintptr
	MaximumWorkingSetSize   uintptr
	ActiveProcessLimit      uint32
	Affinity                uintptr
	PriorityClass           uint32
	SchedulingClass         uint32
}

type IO_COUNTERS struct {
	ReadOperationCount  uint64
	WriteOperationCount uint64
	OtherOperationCount uint64
	ReadTransferCount   uint64
	WriteTransferCount  uint64
	OtherTransferCount  uint64
}

type JOBOBJECT_EXTENDED_LIMIT_INFORMATION struct {
	BasicLimitInformation JOBOBJECT_BASIC_LIMIT_INFORMATION
	IoInfo                IO_COUNTERS
	ProcessMemoryLimit    uintptr
	JobMemoryLimit        uintptr
	PeakProcessMemoryUsed uintptr
	PeakJobMemoryUsed     uintptr
}

var _globalJobHandle syscall.Handle

func initZeroOrphanJobObject() {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	createJobObject := kernel32.NewProc("CreateJobObjectW")
	setInformationJobObject := kernel32.NewProc("SetInformationJobObject")
	assignProcessToJobObject := kernel32.NewProc("AssignProcessToJobObject")

	job, _, _ := createJobObject.Call(0, 0)
	if job == 0 {
		return
	}
	_globalJobHandle = syscall.Handle(job)

	info := JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	info.BasicLimitInformation.LimitFlags = 0x2000 // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

	setInformationJobObject.Call(
		job,
		9, // JobObjectExtendedLimitInformation
		uintptr(unsafe.Pointer(&info)),
		uintptr(unsafe.Sizeof(info)),
	)

	currentProcess, _ := syscall.GetCurrentProcess()
	assignProcessToJobObject.Call(job, uintptr(currentProcess))
}

// Styles

func stripMarkdownForTTS(input string) string {
	out := strings.ReplaceAll(input, "**", "")
	out = strings.ReplaceAll(out, "__", "")
	out = strings.ReplaceAll(out, "### ", "")
	out = strings.ReplaceAll(out, "## ", "")
	out = strings.ReplaceAll(out, "# ", "")
	return out
}

func resolveAgentPath(p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	home, err := os.UserHomeDir()
	if err == nil {
		return filepath.Join(home, "Desktop", p)
	}
	return p
}

var (
	localMockCount int
	localMockMu    sync.Mutex
)

var (
	terminalSessionMu sync.Mutex
	terminalCmdFile   = filepath.Join(os.TempDir(), "voila_ipc_cmd.txt")
	terminalOutFile   = filepath.Join(os.TempDir(), "voila_ipc_out.txt")
	terminalDoneFile  = filepath.Join(os.TempDir(), "voila_ipc_done.txt")
	terminalPidFile   = filepath.Join(os.TempDir(), "voila_ipc_pid.txt")
	terminalActive    = false
	terminalPid       = ""

	cmdMu              sync.Mutex
	currentCmd         *exec.Cmd
	currentConvID      string
	currentCancel      context.CancelFunc
	isGraphifyRunning bool
	circuitMu          sync.Mutex
	circuitOpen        bool
	execSemaphore      chan struct{} // Limit concurrent executions
	maxConcurrentExecs = 3           // Maximum concurrent AI executions
	resilienceManager  *ResilienceManager

	// Protect local models from VRAM crashes
	ollamaSemaphore = make(chan struct{}, 1)

	// Inter-Agent IPC
	agentRegistryMu sync.RWMutex
	activeAgents    = make(map[string]*AgentTask)
)

type AgentTask struct {
	TaskID  string
	Command string
	Mode    string
	Inbox   chan string
}

var initialDir string
var debugLog *log.Logger

func init() {
	initialDir, _ = os.Getwd()
}

func initDebugLog() {
	logPath := filepath.Join(filepath.Dir(os.Args[0]), "voila_debug.log")
	f, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		f, _ = os.OpenFile(filepath.Join(os.TempDir(), "voila_debug.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	}
	debugLog = log.New(f, "", log.Ldate|log.Ltime|log.Lmicroseconds)
	debugLog.Printf("=== VOILA STARTED PID=%d ===", os.Getpid())
}

func init() {
	execSemaphore = make(chan struct{}, maxConcurrentExecs)

	// Initialize network resilience manager
	initResilienceManager()
}

func initResilienceManager() {
	config := ResilienceConfig{
		MaxRetries:          5,
		BaseDelay:           1 * time.Second,
		MaxDelay:            30 * time.Second,
		HealthCheckInterval: 30 * time.Second,
		HealthCheckTimeout:  10 * time.Second,
		DNSCacheTTL:         5 * time.Minute,
		CircuitThreshold:    5,
		CircuitTimeout:      30 * time.Second,
	}

	resilienceManager = NewResilienceManager(config)
	log.Printf("Network resilience manager initialized with %d transport layers", len(resilienceManager.transportStack.transports))

	// Start health check goroutine
	go func() {
		ticker := time.NewTicker(config.HealthCheckInterval)
		defer ticker.Stop()

		for range ticker.C {
			// Health check logic for backend
			if resilienceManager != nil {
				// Periodic health checks could be added here
			}
		}
	}()
}

// Resilient HTTP client wrapper
func resilientHTTPGet(url string) (*http.Response, error) {
	// Skip resilience for localhost to avoid conflicts with local services
	if strings.Contains(url, "127.0.0.1") || strings.Contains(url, "localhost") {
		client := &http.Client{Timeout: 5 * time.Second}
		return client.Get(url)
	}

	if resilienceManager == nil {
		// Fallback to basic HTTP client if resilience manager not initialized
		return http.Get(url)
	}

	resp, err := resilienceManager.Request(context.Background(), url)
	if err != nil {
		log.Printf("Resilient HTTP request failed for %s: %v", url, err)
		// Fallback to basic HTTP client
		return http.Get(url)
	}

	return resp, nil
}

// Resilient HTTP client with custom request
func resilientHTTPDo(req *http.Request) (*http.Response, error) {
	// Skip resilience for localhost to avoid conflicts with local services
	if strings.Contains(req.URL.String(), "127.0.0.1") || strings.Contains(req.URL.String(), "localhost") {
		client := &http.Client{Timeout: 5 * time.Second}
		return client.Do(req)
	}

	if resilienceManager == nil {
		client := &http.Client{Timeout: 30 * time.Second}
		return client.Do(req)
	}

	// For now, use basic client with resilience manager for DNS and connection pooling
	client := &http.Client{
		Timeout: 30 * time.Second,
		Transport: &http.Transport{
			MaxIdleConns:        10,
			MaxIdleConnsPerHost: 5,
			IdleConnTimeout:     90 * time.Second,
		},
	}

	return client.Do(req)
}

const circuitFlagFile = "circuit_open.flag"

var (
	titleStyle        = lipgloss.NewStyle().Foreground(lipgloss.Color("6")).Bold(true)
	subtitleStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("242"))
	successStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("2"))
	errorStyle        = lipgloss.NewStyle().Foreground(lipgloss.Color("1"))
	warningStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("3"))
	buttonStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("15")).Background(lipgloss.Color("4")).Padding(0, 2)
	activeButtonStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("0")).Background(lipgloss.Color("6")).Padding(0, 2)
	inputStyle        = lipgloss.NewStyle().Foreground(lipgloss.Color("15")).Background(lipgloss.Color("8")).Padding(0, 2)
	statusStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("5"))
	deviceStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("14"))
	menuStyle         = lipgloss.NewStyle().Margin(1, 0)
	asciiArtStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("6")).Bold(true)
	separatorStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
)

// ASCII Art
const (
	logoArt = `
                              
  ▄▄▄              ▄▄       
 █▀██  ██▀▀        ██      
   ██  ██       ▀▀ ██      
   ██  ██ ▄███▄ ██ ██ ▄▀▀█▄
   ██▄ ██ ██ ██ ██ ██ ▄█▀██
    ▀███▀ ▀███▀▄██▄██▄▀█▄██
                           
                           
        ⚡ ZERO TRUST • SECURE • FAST ⚡
`

	connectedArt = `
   ╔════════════════════════════════════════╗
   ║    ✓ CONNECTION ESTABLISHED              ║
   ║    ● READY TO EXECUTE COMMANDS          ║
   ╚════════════════════════════════════════╝
`

	menuArt = `
╔════════════════════════════════════════════════╗
║              VOILA - LOCAL AGENT MENU             ║
╚════════════════════════════════════════════════╝
`

	separatorLine = "════════════════════════════════════════════════════"

	footerArt = `
    ╔══════════════════════════════════════════╗
    ║  Voice-to-CLI Remote Execution System     ║
    ║  Zero Trust | Multi-Device | Secure        ║
    ║  v1.0.0 | ⚡ Fast | 🔒 Secure              ║
    ╚══════════════════════════════════════════╝
`

	statusOnline = `
   ╔════════════════════════════════════════╗
   ║  ● ONLINE - CONNECTED - LISTENING:8088  ║
   ╚════════════════════════════════════════╝
`

	statusOffline = `
   ╔════════════════════════════════════════╗
   ║  ○ OFFLINE - DISCONNECTED - STOPPED     ║
   ╚════════════════════════════════════════╝
`

	arrowsArt = `
    ↑   ↓   →   ←
  Navigate Options
`

	decorativeLine = "╔════════════════════════════════════════════════════════════════════════════╗"

	sparklineConnected    = "▓▓▓▓▓▓▓▓▓▓▓ 100%"
	sparklineDisconnected = "░░░░░░░░░░░ 0%"

	progressBarConnected    = "████████████████████ 100%"
	progressBarDisconnected = "░░░░░░░░░░░░░░░░░░░ 0%"

	frameTop    = "╔════════════════════════════════════════════════════════════════════════════╗"
	frameBottom = "╚════════════════════════════════════════════════════════════════════════════╝"

	dividerLine = "────────────────────────────────────────────────────────────────────────────"

	loadingArt = `
    ╔════════════════════════════════════════╗
    ║  ⟳ CONNECTING TO BACKEND...            ║
    ╚════════════════════════════════════════╝
`

	successCheckArt = `
    ╔════════════════════════════════════════╗
    ║    ✓ SUCCESS                            ║
    ╚════════════════════════════════════════╝
`

	errorCrossArt = `
    ╔════════════════════════════════════════╗
    ║    ✗ ERROR                              ║
    ╚════════════════════════════════════════╝
`
)

// Connection data
type ConnectionData struct {
	BackendURL        string `json:"backend_url"`
	DeviceID          string `json:"device_id"`
	DeviceName        string `json:"device_name"`
	SecurityPhrase    string `json:"security_phrase"`
	DeviceFingerprint string `json:"device_fingerprint"`
	Connected         bool   `json:"connected"`
	LastConnected     string `json:"last_connected"`
	// Cloud API keys (stored locally, never sent to backend)
	GroqAPIKey           string `json:"groq_api_key,omitempty"`
	GroqSecondaryAPIKey  string `json:"groq_secondary_api_key,omitempty"`
	GroqModel            string `json:"groq_model,omitempty"`
	OllamaBaseURL        string `json:"ollama_base_url,omitempty"` // e.g. https://api.ollama.ai
	OllamaAPIKey         string `json:"ollama_api_key,omitempty"`  // optional auth
	OllamaSecondaryAPIKey string `json:"ollama_secondary_api_key,omitempty"`
	OllamaModel          string `json:"ollama_model,omitempty"`    // e.g. llama3.2:1b
	ActiveMode    string `json:"active_mode,omitempty"`
}

// ── Token Usage Tracking ──────────────────────────────────────────────────────
var (
	groqSessionTokensMu   sync.Mutex
	groqSessionTokensIn   int64
	groqSessionTokensOut  int64
	ollamaSessionTokensMu sync.Mutex
	ollamaSessionTokensIn  int64
	ollamaSessionTokensOut int64
)

type TokenUsageFile struct {
	GroqDayTokensIn    int64  `json:"groq_day_tokens_in"`
	GroqDayTokensOut   int64  `json:"groq_day_tokens_out"`
	GroqSessionIn      int64  `json:"groq_session_in"`
	GroqSessionOut     int64  `json:"groq_session_out"`
	OllamaDayTokensIn  int64  `json:"ollama_day_tokens_in"`
	OllamaDayTokensOut int64  `json:"ollama_day_tokens_out"`
	OllamaSessionIn    int64  `json:"ollama_session_in"`
	OllamaSessionOut   int64  `json:"ollama_session_out"`
	LastResetDate      string `json:"last_reset_date"`
}

func tokenUsagePath() string {
	return filepath.Join(getConfigDir(), "token_usage.json")
}

func loadTokenUsage() TokenUsageFile {
	var tu TokenUsageFile
	data, err := os.ReadFile(tokenUsagePath())
	if err != nil {
		return tu
	}
	_ = json.Unmarshal(data, &tu)
	// Reset daily counters at midnight
	today := time.Now().Format("2006-01-02")
	if tu.LastResetDate != today {
		tu.GroqDayTokensIn = 0
		tu.GroqDayTokensOut = 0
		tu.OllamaDayTokensIn = 0
		tu.OllamaDayTokensOut = 0
		tu.LastResetDate = today
	}
	return tu
}

func saveTokenUsage(tu TokenUsageFile) {
	data, _ := json.MarshalIndent(tu, "", "  ")
	_ = os.WriteFile(tokenUsagePath(), data, 0644)
}

func addGroqTokens(in, out int64) {
	groqSessionTokensMu.Lock()
	groqSessionTokensIn += in
	groqSessionTokensOut += out
	groqSessionTokensMu.Unlock()

	tu := loadTokenUsage()
	tu.GroqDayTokensIn += in
	tu.GroqDayTokensOut += out
	groqSessionTokensMu.Lock()
	tu.GroqSessionIn = groqSessionTokensIn
	tu.GroqSessionOut = groqSessionTokensOut
	groqSessionTokensMu.Unlock()
	saveTokenUsage(tu)
}

func addOllamaTokens(in, out int64) {
	ollamaSessionTokensMu.Lock()
	ollamaSessionTokensIn += in
	ollamaSessionTokensOut += out
	ollamaSessionTokensMu.Unlock()

	tu := loadTokenUsage()
	tu.OllamaDayTokensIn += in
	tu.OllamaDayTokensOut += out
	ollamaSessionTokensMu.Lock()
	tu.OllamaSessionIn = ollamaSessionTokensIn
	tu.OllamaSessionOut = ollamaSessionTokensOut
	ollamaSessionTokensMu.Unlock()
	saveTokenUsage(tu)
}

type model struct {
	state          string // "setup", "connected", "menu", "loading", "security_phrase_input"
	connectionData ConnectionData
	inputStep      int // 0: backend, 1: device name, 2: security phrase
	currentInput   string
	selectedOption int
	messages       []string
	status         string
	isRunning      bool
	serverRunning  bool
	isLoading      bool
}

// Messages
type connectionResultMsg struct {
	success bool
	message string
}
type serverStatusMsg struct {
	running bool
}
type securityDisconnectMsg struct{}
type loadingMsg struct{}
type tickMsg time.Time
type successMsg struct {
	message string
}
type errorMsg struct {
	message string
}
type securityPhraseMsg struct {
	phrase string
}

// Init
func (m model) Init() tea.Cmd {
	return tea.Tick(time.Millisecond*100, func(t time.Time) tea.Msg {
		return tickMsg(t)
	})
}

// Update
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.Type {
		case tea.KeyCtrlC, tea.KeyEsc:
			if m.state == "menu" {
				return m, tea.Quit
			} else if m.state == "security_phrase_input" {
				m.state = "menu"
				m.currentInput = ""
				m.messages = []string{}
			}
		case tea.KeyEnter:
			return m.handleEnter()
		case tea.KeyUp:
			if m.state == "menu" {
				// Calculate menu size based on connection state
				menuSize := 8
				if !m.connectionData.Connected {
					menuSize = 3
				}
				m.selectedOption = (m.selectedOption - 1 + menuSize) % menuSize
			}
		case tea.KeyDown:
			if m.state == "menu" {
				// Calculate menu size based on connection state
				menuSize := 8
				if !m.connectionData.Connected {
					menuSize = 3
				}
				m.selectedOption = (m.selectedOption + 1) % menuSize
			}
		case tea.KeyBackspace:
			if len(m.currentInput) > 0 && (m.state == "setup" || m.state == "security_phrase_input" || m.state == "circuit_reset_input") {
				m.currentInput = m.currentInput[:len(m.currentInput)-1]
			}
		case tea.KeyCtrlV:
			// Handle clipboard paste
			if m.state == "setup" || m.state == "security_phrase_input" || m.state == "circuit_reset_input" {
				// Try to get clipboard content
				cmd := exec.Command("powershell", "-Command", "Get-Clipboard")
				output, err := cmd.Output()
				if err == nil {
					pastedText := strings.TrimSpace(string(output))
					m.currentInput += pastedText
				}
			}
		default:
			if (m.state == "setup" || m.state == "security_phrase_input" || m.state == "circuit_reset_input") && len(msg.String()) >= 1 {
				m.currentInput += msg.String()
			}
		}
	case connectionResultMsg:
		m.isLoading = false
		if msg.success {
			m.state = "connected"
			m.connectionData.Connected = true
			m.connectionData.LastConnected = time.Now().Format(time.RFC3339)

			// Save data immediately so /execute can read it!
			saveConnectionData(m.connectionData)

			m.messages = append(m.messages, successStyle.Render(successCheckArt))
			m.messages = append(m.messages, statusStyle.Render("Server will auto-start on device boot"))
			m.isRunning = true
			m.serverRunning = true
			return m, m.startServer()
		} else {
			m.messages = append(m.messages, errorStyle.Render(errorCrossArt))
			m.messages = append(m.messages, errorStyle.Render(msg.message))
		}
	case tickMsg:
		// Animate loading state
		if m.isLoading {
			// Could add animation frames here
		}
		return m, nil
	case serverStatusMsg:
		m.serverRunning = msg.running
		if msg.running {
			m.status = "Running"
		} else {
			m.status = "Stopped"
		}
	case securityDisconnectMsg:
		m.messages = append(m.messages, warningStyle.Render("⚠ Security disconnect triggered"))
		m.connectionData.Connected = false
		m.isRunning = false
		m.serverRunning = false
		return m, m.stopServer()
	case successMsg:
		m.messages = append(m.messages, successStyle.Render("✓ "+msg.message))
	case errorMsg:
		m.messages = append(m.messages, errorStyle.Render("✗ "+msg.message))
		if msg.message == "Local data cleared" {
			m.connectionData = ConnectionData{}
			m.state = "setup"
			m.inputStep = 0
			m.currentInput = ""
		}
	case securityPhraseMsg:
		// Security phrase received, proceed with clear
		return m, m.clearBackendDataWithPhrase(msg.phrase)
	}
	return m, nil
}

func (m model) handleEnter() (model, tea.Cmd) {
	if m.state == "setup" {
		switch m.inputStep {
		case 0:
			// Use hardcoded URL if input is empty, otherwise use user input
			if m.currentInput == "" {
				m.connectionData.BackendURL = "https://voila-voice.onrender.com" // Default hardcoded URL
			} else {
				m.connectionData.BackendURL = m.currentInput
			}
			m.inputStep = 1
			m.currentInput = ""
		case 1:
			m.connectionData.DeviceName = m.currentInput
			// Generate desktop device ID from device name and random UUID
			if m.connectionData.DeviceID == "" {
				m.connectionData.DeviceID = "desktop-" + generateUUID()
			}
			m.inputStep = 2
			m.currentInput = ""
		case 2:
			m.connectionData.SecurityPhrase = m.currentInput
			// Generate device fingerprint for MITM prevention
			if m.connectionData.DeviceFingerprint == "" {
				m.connectionData.DeviceFingerprint = generateDeviceFingerprint()
			}
			m.isLoading = true
			return m, m.testConnection()
		}
	} else if m.state == "security_phrase_input" {
		// User submitted security phrase
		phrase := m.currentInput
		m.state = "menu"
		m.currentInput = ""
		return m, m.clearBackendDataWithPhrase(phrase)
	} else if m.state == "circuit_reset_input" {
		// User submitted security phrase for circuit reset
		phrase := m.currentInput
		m.state = "menu"
		m.currentInput = ""
		return m, m.resetCircuitBreakerWithPhrase(phrase)
	} else if m.state == "connected" {
		m.state = "menu"
		m.selectedOption = 0
	} else if m.state == "menu" {
		backgroundRunning := isBackgroundServiceRunning()

		// Handle disconnected state menu (3 options)
		if !m.connectionData.Connected {
			switch m.selectedOption {
			case 0: // Setup Connection
				m.state = "setup"
				m.inputStep = 0
				m.currentInput = ""
				m.messages = []string{}
			case 1: // Start Ngrok
				return m, m.startNgrok()
			case 2: // Exit
				return m, tea.Quit
			}
			return m, nil
		}

		// Handle connected state menu (8 options)
		switch m.selectedOption {
		case 0: // Stop Service / Stop Background Service
			if backgroundRunning {
				m.messages = []string{successStyle.Render("Stopping background service...")}
				stopBackgroundService()
				return m, nil
			} else {
				if m.serverRunning {
					return m, m.stopServer()
				} else {
					return m, m.startServer()
				}
			}
		case 1: // Delete Connection
			m.connectionData = ConnectionData{}
			m.state = "setup"
			m.inputStep = 0
			m.currentInput = ""
			m.messages = []string{warningStyle.Render("Connection deleted")}
		case 2: // Start Ngrok
			return m, m.startNgrok()
		case 3: // Clear Backend Data
			m.state = "security_phrase_input"
			m.currentInput = ""
			m.messages = []string{warningStyle.Render("Enter security phrase to clear backend data:")}
			return m, nil
		case 4: // Reset Circuit Breaker
			m.state = "circuit_reset_input"
			m.currentInput = ""
			m.messages = []string{warningStyle.Render("Enter security phrase to reset circuit breaker:")}
			return m, nil
		case 5: // Clear Local Data
			return m, m.clearLocalData()
		case 6: // View Status
			m.status = fmt.Sprintf("Status: %s | Connected: %v | Circuit: %v", m.status, m.connectionData.Connected, isCircuitOpen())
		case 7: // Exit
			if m.serverRunning {
				return m, m.stopServer()
			}
			return m, tea.Quit
		}
	}
	return m, nil
}

func (m model) testConnection() tea.Cmd {
	return func() tea.Msg {
		// Return loading state first
		time.Sleep(500 * time.Millisecond)
		// Test actual connection to backend
		healthURL := m.connectionData.BackendURL + "/health"
		req, err := http.NewRequest("GET", healthURL, nil)
		if err != nil {
			return connectionResultMsg{success: false, message: "Failed to connect to backend: " + err.Error()}
		}

		// Add ngrok skip browser warning header if calling through ngrok
		if strings.Contains(m.connectionData.BackendURL, "ngrok") || strings.Contains(m.connectionData.BackendURL, "ngrok-free") {
			req.Header.Set("ngrok-skip-browser-warning", "true")
		}

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			return connectionResultMsg{success: false, message: "Failed to connect to backend: " + err.Error()}
		}
		defer resp.Body.Close()

		if resp.StatusCode != 200 {
			return connectionResultMsg{success: false, message: "Backend returned status: " + resp.Status}
		}

		// Successfully connected to backend - registration happens in background loop when ngrok is available
		return connectionResultMsg{success: true, message: "Connection successful"}
	}
}

func (m model) startServer() tea.Cmd {
	return func() tea.Msg {
		go startHTTPServer()
		
		// Start unified robust connection manager
		startConnectionManager(m.connectionData)

		return serverStatusMsg{running: true}
	}
}

func (m model) stopServer() tea.Cmd {
	return func() tea.Msg {
		stopHTTPServer()
		return serverStatusMsg{running: false}
	}
}

func (m model) clearBackendDataWithPhrase(phrase string) tea.Cmd {
	return func() tea.Msg {
		if phrase == "" {
			return errorMsg{"Security phrase required"}
		}

		clearURL := strings.TrimRight(m.connectionData.BackendURL, "/") + "/clear-all-devices"
		reqBody := map[string]string{"security_phrase": phrase}
		bodyBytes, _ := json.Marshal(reqBody)

		req, err := http.NewRequest(http.MethodPost, clearURL, bytes.NewReader(bodyBytes))
		if err != nil {
			return errorMsg{fmt.Sprintf("Failed to create request: %v", err)}
		}
		req.Header.Set("Content-Type", "application/json")

		if strings.Contains(m.connectionData.BackendURL, "ngrok") || strings.Contains(m.connectionData.BackendURL, "ngrok-free") {
			req.Header.Set("ngrok-skip-browser-warning", "true")
		}

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			return errorMsg{fmt.Sprintf("Failed to clear backend data: %v", err)}
		}
		defer resp.Body.Close()

		if resp.StatusCode != 200 {
			body, _ := io.ReadAll(resp.Body)
			return errorMsg{fmt.Sprintf("Backend returned: %s - %s", resp.Status, string(body))}
		}

		return successMsg{"Backend data cleared successfully"}
	}
}

func (m model) clearLocalData() tea.Cmd {
	return func() tea.Msg {
		path := filepath.Join(getConfigDir(), "connection_data.json")
		err := os.Remove(path)
		if err != nil && !os.IsNotExist(err) {
			return errorMsg{fmt.Sprintf("Failed to clear local data: %v", err)}
		}
		return successMsg{"Local data cleared"}
	}
}

func (m model) startNgrok() tea.Cmd {
	return func() tea.Msg {
		if isNgrokRunning() {
			return successMsg{"Ngrok is already running"}
		}
		if err := startNgrok(); err != nil {
			return errorMsg{fmt.Sprintf("Failed to start ngrok: %v", err)}
		}
		return successMsg{"Ngrok started successfully"}
	}
}

// View
func (m model) View() string {
	var content string

	switch m.state {
	case "setup":
		content = m.setupView()
	case "connected":
		content = m.connectedView()
	case "menu":
		content = m.menuView()
	case "security_phrase_input":
		content = m.securityPhraseInputView()
	case "circuit_reset_input":
		content = m.circuitResetInputView()
	}

	return m.wrapContent(content)
}

func (m model) setupView() string {
	var content strings.Builder

	content.WriteString(asciiArtStyle.Render(logoArt))
	content.WriteString("\n\n")
	content.WriteString(titleStyle.Render("Voila - Local Agent Setup"))
	content.WriteString("\n\n")
	content.WriteString(separatorStyle.Render(separatorLine))
	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render("Enter your connection details:\n\n"))
	content.WriteString(subtitleStyle.Render("💡 Tip: Use Ctrl+V to paste from clipboard\n\n"))

	switch m.inputStep {
	case 0:
		content.WriteString("Backend URL: ")
		content.WriteString(inputStyle.Render(m.currentInput + "_"))
		content.WriteString("\n\n")
		content.WriteString(subtitleStyle.Render("Press Enter for default: https://voila-voice.onrender.com"))
		content.WriteString("\n")
		content.WriteString(subtitleStyle.Render("Or paste custom URL with Ctrl+V"))
	case 1:
		content.WriteString("Backend URL: ")
		content.WriteString(successStyle.Render(m.connectionData.BackendURL))
		content.WriteString("\n\n")
		content.WriteString("Device Name: ")
		content.WriteString(inputStyle.Render(m.currentInput + "_"))
		content.WriteString("\n\n")
		content.WriteString(subtitleStyle.Render("Example: Development Laptop"))
	case 2:
		content.WriteString("Backend URL: ")
		content.WriteString(successStyle.Render(m.connectionData.BackendURL))
		content.WriteString("\n\n")
		content.WriteString("Device Name: ")
		content.WriteString(successStyle.Render(m.connectionData.DeviceName))
		content.WriteString("\n\n")
		content.WriteString("Security Phrase: ")
		content.WriteString(inputStyle.Render(strings.Repeat("*", len(m.currentInput)) + "_"))
		content.WriteString("\n\n")
		content.WriteString(subtitleStyle.Render("Enter phrase to verify your identity"))
		content.WriteString("\n")
		content.WriteString(subtitleStyle.Render("This phrase will be required for clearing backend data"))
	}

	if m.isLoading {
		content.WriteString("\n\n")
		content.WriteString(warningStyle.Render(loadingArt))
	}

	if len(m.messages) > 0 {
		content.WriteString("\n\n")
		content.WriteString(separatorStyle.Render(separatorLine))
		content.WriteString("\n\n")
		for _, msg := range m.messages {
			content.WriteString(msg + "\n")
		}
	}

	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render(footerArt))

	return content.String()
}

func (m model) connectedView() string {
	var content strings.Builder

	content.WriteString(asciiArtStyle.Render(logoArt))
	content.WriteString("\n\n")
	content.WriteString(successStyle.Render(connectedArt))
	content.WriteString("\n\n")
	content.WriteString(deviceStyle.Render(fmt.Sprintf("Device: %s (%s)", m.connectionData.DeviceName, m.connectionData.DeviceID)))
	content.WriteString("\n\n")
	content.WriteString(separatorStyle.Render(separatorLine))
	content.WriteString("\n\n")
	content.WriteString(successStyle.Render("Press Enter to continue to menu..."))
	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render(footerArt))

	return content.String()
}

func (m model) menuView() string {
	var content strings.Builder

	content.WriteString(asciiArtStyle.Render(logoArt))
	content.WriteString("\n\n")
	content.WriteString(asciiArtStyle.Render(menuArt))
	content.WriteString("\n\n")

	// Status indicator
	if m.serverRunning {
		content.WriteString(successStyle.Render(statusOnline))
	} else {
		content.WriteString(errorStyle.Render(statusOffline))
	}
	content.WriteString("\n\n")

	// Connection progress - only show if connected
	if m.connectionData.Connected {
		content.WriteString(successStyle.Render(progressBarConnected))
		content.WriteString("\n\n")
	}

	content.WriteString(statusStyle.Render(fmt.Sprintf("Status: %s", m.status)))

	// Show background service status
	if isBackgroundServiceRunning() {
		content.WriteString("\n\n")
		content.WriteString(successStyle.Render("● Background service running"))
	}

	// Show connection status message
	if !m.connectionData.Connected {
		content.WriteString("\n\n")
		content.WriteString(warningStyle.Render("⚠ No connection configured"))
	}

	content.WriteString("\n\n")
	content.WriteString(separatorStyle.Render(separatorLine))
	content.WriteString("\n\n")

	// Dynamic menu options based on connection state
	var options []string
	if m.connectionData.Connected {
		options = []string{
			"⏯  Stop/Start Service",
			"🗑  Delete Connection",
			"🌐 Start Ngrok",
			"🧹 Clear Backend Data",
			"⚡ Reset Circuit Breaker",
			"💾 Clear Local Data",
			"📊 View Status",
			"🚪 Exit",
		}

		if isBackgroundServiceRunning() {
			options = []string{
				"⏯  Stop Background Service",
				"🗑  Delete Connection",
				"🌐 Start Ngrok",
				"🧹 Clear Backend Data",
				"⚡ Reset Circuit Breaker",
				"💾 Clear Local Data",
				"📊 View Status",
				"🚪 Exit",
			}
		}
	} else {
		// Not connected - show setup-only options
		options = []string{
			"🔧 Setup Connection",
			"🌐 Start Ngrok",
			"🚪 Exit",
		}
	}

	for i, option := range options {
		prefix := " "
		if i == m.selectedOption {
			prefix = "→"
			content.WriteString(activeButtonStyle.Render(prefix + " " + option))
		} else {
			content.WriteString(buttonStyle.Render(prefix + " " + option))
		}
		content.WriteString("\n")
	}

	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render(arrowsArt))

	if len(m.messages) > 0 {
		content.WriteString("\n\n")
		content.WriteString(separatorStyle.Render(separatorLine))
		content.WriteString("\n\n")
		for _, msg := range m.messages {
			content.WriteString(msg + "\n")
		}
	}

	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render(footerArt))

	return content.String()
}

func (m model) wrapContent(content string) string {
	return lipgloss.NewStyle().
		Width(75).
		Align(lipgloss.Center).
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color("6")).
		Render(content)
}

func (m model) securityPhraseInputView() string {
	var content strings.Builder

	content.WriteString(asciiArtStyle.Render(logoArt))
	content.WriteString("\n\n")
	content.WriteString(titleStyle.Render("Clear Backend Data"))
	content.WriteString("\n\n")
	content.WriteString(separatorStyle.Render(separatorLine))
	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render("Enter security phrase:\n\n"))
	content.WriteString("Security Phrase: ")
	content.WriteString(inputStyle.Render(m.currentInput + "_"))
	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render("Press Enter to submit, Esc to cancel"))

	if len(m.messages) > 0 {
		content.WriteString("\n\n")
		content.WriteString(separatorStyle.Render(separatorLine))
		content.WriteString("\n\n")
		for _, msg := range m.messages {
			content.WriteString(msg + "\n")
		}
	}

	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render(footerArt))

	return content.String()
}

func (m model) circuitResetInputView() string {
	var content strings.Builder

	content.WriteString(asciiArtStyle.Render(logoArt))
	content.WriteString("\n\n")
	content.WriteString(titleStyle.Render("Reset Circuit Breaker"))
	content.WriteString("\n\n")
	content.WriteString(separatorStyle.Render(separatorLine))
	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render("Enter security phrase:\n\n"))
	content.WriteString("Security Phrase: ")
	content.WriteString(inputStyle.Render(m.currentInput + "_"))
	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render("Press Enter to submit, Esc to cancel"))

	if len(m.messages) > 0 {
		content.WriteString("\n\n")
		content.WriteString(separatorStyle.Render(separatorLine))
		content.WriteString("\n\n")
		for _, msg := range m.messages {
			content.WriteString(msg + "\n")
		}
	}

	content.WriteString("\n\n")
	content.WriteString(subtitleStyle.Render(footerArt))

	return content.String()
}

// HTTP Server
var server *http.Server
var serverRunning bool

// currentMode holds the active execution mode: "LOCAL", "GROQ", or "OLLAMA".
// It is set by the Python widget's mode-toggle badge via POST /set-mode.
var (
	currentMode   = "LOCAL"
	currentModeMu sync.Mutex
)

func getNgrokPublicURL() string {
	resp, err := resilientHTTPGet("http://127.0.0.1:4040/api/tunnels")
	if err != nil {
		return ""
	}
	defer resp.Body.Close()

	var result struct {
		Tunnels []struct {
			PublicURL string `json:"public_url"`
			Proto     string `json:"proto"`
		} `json:"tunnels"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return ""
	}
	for _, t := range result.Tunnels {
		if strings.HasPrefix(t.PublicURL, "https://") {
			return t.PublicURL
		}
	}
	if len(result.Tunnels) > 0 {
		return result.Tunnels[0].PublicURL
	}
	return ""
}

func isNgrokRunning() bool {
	resp, err := resilientHTTPGet("http://127.0.0.1:4040/api/tunnels")
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == 200
}

func getNgrokExecutable() (string, error) {
	// Check if ngrok is in system PATH
	if runtime.GOOS == "windows" {
		cmd := exec.Command("where", "ngrok")
		if output, err := cmd.Output(); err == nil {
			paths := strings.Split(strings.TrimSpace(string(output)), "\n")
			if len(paths) > 0 && paths[0] != "" {
				return strings.TrimSpace(paths[0]), nil
			}
		}
	} else {
		cmd := exec.Command("which", "ngrok")
		if output, err := cmd.Output(); err == nil {
			return strings.TrimSpace(string(output)), nil
		}
	}

	// Check scripts directory with multiple path attempts
	execDir := getExecutableDir()
	possiblePaths := []string{
		filepath.Join(execDir, "..", "scripts", "ngrok.exe"),
		filepath.Join(execDir, "..", "scripts", "ngrok"),
		filepath.Join(execDir, "scripts", "ngrok.exe"),
		filepath.Join(execDir, "scripts", "ngrok"),
		filepath.Join("..", "scripts", "ngrok.exe"),
		filepath.Join("..", "scripts", "ngrok"),
	}

	for _, ngrokPath := range possiblePaths {
		if _, err := os.Stat(ngrokPath); err == nil {
			absPath, err := filepath.Abs(ngrokPath)
			if err == nil {
				return absPath, nil
			}
			return ngrokPath, nil
		}
	}

	return "", fmt.Errorf("ngrok not found in PATH or scripts directory")
}

func configureNgrokAuthtoken(ngrokPath string) error {
	authtoken := os.Getenv("NGROK_AUTHTOKEN")
	if authtoken == "" {
		return fmt.Errorf("NGROK_AUTHTOKEN environment variable not set. Get your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken")
	}

	// Check if already configured
	cmd := exec.Command(ngrokPath, "config", "check")
	if _, err := cmd.CombinedOutput(); err == nil {
		// Config exists, verify authtoken matches
		return nil
	}

	// Configure authtoken
	cmd = exec.Command(ngrokPath, "config", "add-authtoken", authtoken)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to configure authtoken: %s, output: %s", err, string(output))
	}

	log.Println("Ngrok authtoken configured successfully")
	return nil
}

func startNgrok() error {
	ngrokPath, err := getNgrokExecutable()
	if err != nil {
		return fmt.Errorf("ngrok not found: %w", err)
	}

	log.Printf("Using ngrok at: %s", ngrokPath)

	// Check if ngrok is already running
	if isNgrokRunning() {
		log.Println("Ngrok is already running")
		return nil
	}

	// Configure authtoken if needed
	if err := configureNgrokAuthtoken(ngrokPath); err != nil {
		log.Printf("Warning: %v", err)
		// Continue anyway - authtoken might already be configured
	}

	// Start ngrok tunnel with environment variable
	cmd := exec.Command(ngrokPath, "http", "8088")

	// Set NGROK_AUTHTOKEN environment variable for this process
	authtoken := os.Getenv("NGROK_AUTHTOKEN")
	if authtoken != "" {
		cmd.Env = append(os.Environ(), "NGROK_AUTHTOKEN="+authtoken)
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start ngrok: %w", err)
	}

	log.Println("Ngrok started in background")
	return nil
}

func startHTTPServer() {
	if serverRunning {
		return
	}
	// Restore saved mode
	if connData, err := loadConnectionData(); err == nil && connData.ActiveMode != "" {
		currentModeMu.Lock()
		currentMode = connData.ActiveMode
		currentModeMu.Unlock()
	}

	mux := http.NewServeMux()

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "mode": "background"})
	})

	mux.HandleFunc("/stop", func(w http.ResponseWriter, r *http.Request) {
		connData, err := loadConnectionData()
		if err != nil || connData.SecurityPhrase == "" {
			http.Error(w, "Agent not configured", http.StatusServiceUnavailable)
			return
		}

		expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
		providedSecret := r.Header.Get("X-Exec-Secret")
		if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
			handleLocalMockExecution(w, r, "circuit", connData, "/circuit")
			return
		}

		cmdMu.Lock()
		if currentCancel != nil {
			currentCancel()
		}
		if currentCmd != nil && currentCmd.Process != nil {
			if runtime.GOOS == "windows" {
				exec.Command("taskkill", "/F", "/T", "/PID", fmt.Sprintf("%d", currentCmd.Process.Pid)).Run()
			} else {
				currentCmd.Process.Kill()
			}

			// Clean up the terminal to prevent the face from getting stuck
			fmt.Print("\r\n\x1b[0m\x1b[?25h\x1b[?1049l\x1b[2J\x1b[H")

			// Append cancellation to transcript to prevent orphaned running state
			if currentConvID != "" {
				brainDir := getBrainDir()
				transcriptPath := filepath.Join(brainDir, currentConvID, ".system_generated", "logs", "transcript.jsonl")
				cancelMsg := fmt.Sprintf(`{"type":"SYSTEM_MESSAGE","status":"ERROR","content":"Execution forcibly cancelled by user.","created_at":"%s"}`+"\n", time.Now().Format(time.RFC3339))
				if f, err := os.OpenFile(transcriptPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644); err == nil {
					f.WriteString(cancelMsg)
					f.Close()
				}
			}
		}
		cmdMu.Unlock()

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"output": "Command execution stopped."})
	})

	mux.HandleFunc("/models", listModelsHandler)
	mux.HandleFunc("/conversations", listConversationsHandler)

	// ── API Key management endpoints (called by Python dashboard) ──────────
	mux.HandleFunc("/api-keys", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Content-Type", "application/json")

		connData, err := loadConnectionData()
		if err != nil {
			http.Error(w, `{"error":"failed to load config"}`, http.StatusInternalServerError)
			return
		}

		switch r.Method {
		case http.MethodGet:
			// Return keys (mask Groq key for security)
			groqMasked := ""
			if connData.GroqAPIKey != "" {
				k := connData.GroqAPIKey
				if len(k) > 8 {
					groqMasked = k[:4] + strings.Repeat("*", len(k)-8) + k[len(k)-4:]
				} else {
					groqMasked = strings.Repeat("*", len(k))
				}
			}
			ollamaMasked := ""
			if connData.OllamaAPIKey != "" {
				k := connData.OllamaAPIKey
				if len(k) > 8 {
					ollamaMasked = k[:4] + strings.Repeat("*", len(k)-8) + k[len(k)-4:]
				} else {
					ollamaMasked = strings.Repeat("*", len(k))
				}
			}
			resp := map[string]string{
				"groq_api_key_masked":   groqMasked,
				"groq_api_key_set":      fmt.Sprintf("%v", connData.GroqAPIKey != ""),
				"groq_secondary_api_key_set": fmt.Sprintf("%v", connData.GroqSecondaryAPIKey != ""),
				"groq_model":            connData.GroqModel,
				"ollama_base_url":       connData.OllamaBaseURL,
				"ollama_api_key_masked": ollamaMasked,
				"ollama_api_key_set":    fmt.Sprintf("%v", connData.OllamaAPIKey != ""),
				"ollama_secondary_api_key_set": fmt.Sprintf("%v", connData.OllamaSecondaryAPIKey != ""),
				"ollama_model":          connData.OllamaModel,
				"active_mode":           connData.ActiveMode,
			}
			json.NewEncoder(w).Encode(resp)

		case http.MethodPost:
			var payload struct {
				GroqAPIKey           string `json:"groq_api_key"`
				GroqSecondaryAPIKey  string `json:"groq_secondary_api_key"`
				GroqModel            string `json:"groq_model"`
				OllamaBaseURL        string `json:"ollama_base_url"`
				OllamaAPIKey         string `json:"ollama_api_key"`
				OllamaSecondaryAPIKey string `json:"ollama_secondary_api_key"`
				OllamaModel          string `json:"ollama_model"`
				Action               string `json:"action"` // "save" or "delete_groq" or "delete_ollama"
			}
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				http.Error(w, "Bad request", http.StatusBadRequest)
				return
			}

			switch payload.Action {
			case "delete_groq":
				connData.GroqAPIKey = ""
				connData.GroqSecondaryAPIKey = ""
				connData.GroqModel = ""
			case "delete_ollama":
				connData.OllamaBaseURL = ""
				connData.OllamaAPIKey = ""
				connData.OllamaSecondaryAPIKey = ""
				connData.OllamaModel = ""
			default: // "save"
				if payload.GroqAPIKey != "" {
					connData.GroqAPIKey = payload.GroqAPIKey
				}
				if payload.GroqModel != "" {
					connData.GroqModel = payload.GroqModel
				}
				if payload.OllamaBaseURL != "" {
					connData.OllamaBaseURL = payload.OllamaBaseURL
				}
				if payload.OllamaAPIKey != "" {
					connData.OllamaAPIKey = payload.OllamaAPIKey
				}
				if payload.OllamaModel != "" {
					connData.OllamaModel = payload.OllamaModel
				}
				if payload.GroqSecondaryAPIKey != "" {
					connData.GroqSecondaryAPIKey = payload.GroqSecondaryAPIKey
				}
				if payload.OllamaSecondaryAPIKey != "" {
					connData.OllamaSecondaryAPIKey = payload.OllamaSecondaryAPIKey
				}
			}

			if err := saveConnectionData(connData); err != nil {
				http.Error(w, `{"error":"failed to save"}`, http.StatusInternalServerError)
				return
			}
			json.NewEncoder(w).Encode(map[string]string{"status": "ok"})

		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

	// /verify-groq — pings Groq API with a tiny "hello" prompt
	mux.HandleFunc("/verify-groq", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Content-Type", "application/json")

		connData, _ := loadConnectionData()
		out, err := executeGroqCommand(context.Background(), "Say hello in one word", connData.GroqAPIKey, connData.GroqModel, connData.DeviceID, nil, "verify", "")
		if err != nil {
			json.NewEncoder(w).Encode(map[string]string{"status": "error", "message": err.Error()})
			return
		}
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "response": out})
	})

	// /verify-ollama — pings Ollama endpoint with a tiny "hello" prompt
	mux.HandleFunc("/verify-ollama", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Content-Type", "application/json")

		connData, _ := loadConnectionData()
		out, err := executeOllamaCommand(context.Background(), "Say hello in one word", connData.OllamaBaseURL, connData.OllamaModel, connData.OllamaAPIKey, nil, "verify", "")
		if err != nil {
			json.NewEncoder(w).Encode(map[string]string{"status": "error", "message": err.Error()})
			return
		}
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "response": out})
	})

	// /token-usage — returns local session + daily token counts, plus Groq rate limit headers
	mux.HandleFunc("/token-usage", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Content-Type", "application/json")

		tu := loadTokenUsage()
		connData, _ := loadConnectionData()

		resp := map[string]interface{}{
			"groq_session_in":    tu.GroqSessionIn,
			"groq_session_out":   tu.GroqSessionOut,
			"groq_day_in":        tu.GroqDayTokensIn,
			"groq_day_out":       tu.GroqDayTokensOut,
			"ollama_session_in":  tu.OllamaSessionIn,
			"ollama_session_out": tu.OllamaSessionOut,
			"ollama_day_in":      tu.OllamaDayTokensIn,
			"ollama_day_out":     tu.OllamaDayTokensOut,
			"reset_date":         tu.LastResetDate,
			// Rate limit data from Groq (fetched from headers via lightweight models call)
			"groq_rpm_limit":       0,
			"groq_rpm_remaining":   0,
			"groq_tpd_limit":       0,
			"groq_tpd_remaining":   0,
			"groq_rate_info_error": "",
		}

		// Fetch Groq rate limit headers (only if key is set and caller requests it)
		if r.URL.Query().Get("fetch_limits") == "1" && connData.GroqAPIKey != "" {
			limReq, err := http.NewRequest("GET", "https://api.groq.com/openai/v1/models", nil)
			if err == nil {
				limReq.Header.Set("Authorization", "Bearer "+connData.GroqAPIKey)
				limClient := &http.Client{Timeout: 8 * time.Second}
				limResp, err := limClient.Do(limReq)
				if err == nil {
					limResp.Body.Close()
					// Groq returns these on every authenticated response
					if v := limResp.Header.Get("x-ratelimit-limit-requests"); v != "" {
						if n, err2 := strconv.ParseInt(v, 10, 64); err2 == nil {
							resp["groq_rpm_limit"] = n
						}
					}
					if v := limResp.Header.Get("x-ratelimit-remaining-requests"); v != "" {
						if n, err2 := strconv.ParseInt(v, 10, 64); err2 == nil {
							resp["groq_rpm_remaining"] = n
						}
					}
					if v := limResp.Header.Get("x-ratelimit-limit-tokens"); v != "" {
						if n, err2 := strconv.ParseInt(v, 10, 64); err2 == nil {
							resp["groq_tpd_limit"] = n
						}
					}
					if v := limResp.Header.Get("x-ratelimit-remaining-tokens"); v != "" {
						if n, err2 := strconv.ParseInt(v, 10, 64); err2 == nil {
							resp["groq_tpd_remaining"] = n
						}
					}
				} else {
					resp["groq_rate_info_error"] = err.Error()
				}
			}
		}

		json.NewEncoder(w).Encode(resp)
	})


	mux.HandleFunc("/circuit", func(w http.ResponseWriter, r *http.Request) {
		// Authenticate using SecurityPhraseHash
		connData, err := loadConnectionData()
		if err != nil || connData.SecurityPhrase == "" {
			http.Error(w, "Agent not configured", http.StatusServiceUnavailable)
			return
		}
		expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
		providedSecret := r.Header.Get("X-Exec-Secret")
		if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
			cmd := "unknown"
			bodyBytes, _ := io.ReadAll(r.Body)
			r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
			var req struct {
				Command string `json:"command"`
			}
			json.Unmarshal(bodyBytes, &req)
			if req.Command != "" {
				cmd = req.Command
			}
			handleLocalMockExecution(w, r, cmd, connData, r.URL.Path)
			return
		}

		var req struct {
			State string `json:"state"` // "open" or "closed"
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Bad request", http.StatusBadRequest)
			return
		}

		if req.State == "open" {
			setCircuitState(true)
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]string{"status": "circuit_open"})
		} else if req.State == "closed" {
			setCircuitState(false)
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]string{"status": "circuit_closed"})
		} else {
			http.Error(w, "Invalid state", http.StatusBadRequest)
		}
	})
	mux.HandleFunc("/execute", func(w http.ResponseWriter, r *http.Request) {

		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Zero-friction mode: Authenticate using SecurityPhraseHash
		connData, err := loadConnectionData()
		if err != nil || connData.SecurityPhrase == "" {
			http.Error(w, "Agent not configured", http.StatusServiceUnavailable)
			return
		}
		expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
		providedSecret := r.Header.Get("X-Exec-Secret")
		if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
			cmd := "unknown"
			bodyBytes, _ := io.ReadAll(r.Body)
			r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
			var req struct {
				Command string `json:"command"`
			}
			json.Unmarshal(bodyBytes, &req)
			if req.Command != "" {
				cmd = req.Command
			}
			handleLocalMockExecution(w, r, cmd, connData, r.URL.Path)
			return
		}

		var req map[string]interface{}
		json.NewDecoder(r.Body).Decode(&req)

		getString := func(k string) string {
			if v, ok := req[k].(string); ok {
				return v
			}
			return ""
		}

		getBool := func(k string) bool {
			if v, ok := req[k].(bool); ok {
				return v
			}
			if v, ok := req[k].(string); ok {
				return v == "true" || v == "1"
			}
			return false
		}

		command := getString("command")
		mode := getString("mode")
		clientID := getString("client_id")
		conversationID := getString("conversation_id")
		modelName := getString("model")
		graphifyEnabled := getBool("graphify_enabled")

		if command == "__SCREENSHOT__" {
			w.WriteHeader(http.StatusAccepted)
			go func() {
				psCode := `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$stream = New-Object System.IO.MemoryStream
$bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Jpeg)
$bytes = $stream.ToArray()
$base64 = [Convert]::ToBase64String($bytes)
$graphics.Dispose()
$bitmap.Dispose()
$stream.Dispose()
Write-Output $base64
`
				out, err := exec.Command("powershell", "-NoProfile", "-Command", psCode).CombinedOutput()
				var result string
				if err != nil {
					result = "Screenshot failed: " + err.Error()
				} else {
					result = "__IMAGE__:" + strings.TrimSpace(string(out))
				}
				webhookPayload, _ := json.Marshal(map[string]string{
					"client_id":   clientID,
					"device_id":   connData.DeviceID,
					"secret_hash": hashPhrase(connData.SecurityPhrase, connData.DeviceID),
					"output":      result,
					"mode":        "screenshot",
				})
				http.Post(connData.BackendURL+"/webhook/result", "application/json", bytes.NewBuffer(webhookPayload))
			}()
			return
		}

		currentModeMu.Lock()
		globalMode := strings.ToUpper(currentMode)
		currentModeMu.Unlock()

		reqMode := strings.ToUpper(mode)
		var effectiveMode string
		switch reqMode {
		case "GROQ", "OLLAMA", "SHELL":
			effectiveMode = reqMode
		default:
			effectiveMode = globalMode
			if effectiveMode == "" {
				effectiveMode = "LOCAL"
			}
		}

		if graphifyEnabled {
			effectiveMode = "AGENT"
		}

		if graphifyEnabled {
			w.WriteHeader(http.StatusAccepted)

			go func() {
				cmdMu.Lock()
				ctx, cancel := context.WithCancel(context.Background())
				currentCancel = cancel
				isGraphifyRunning = true
				cmdMu.Unlock()
				
				// Force spawn a completely independent Windows Terminal or PowerShell window
				exe, _ := os.Executable()
				exeDir := filepath.Dir(exe)
				psScript := `
$ErrorActionPreference = 'Continue'
Set-Location -Path '` + exeDir + `'
$host.UI.RawUI.WindowTitle = 'Voila AI - Graphify Tracker'
Clear-Host
& '` + exe + `' --tui
if ($LASTEXITCODE -ne 0) {
    Write-Host "TUI crashed with code $LASTEXITCODE. Press Enter to exit."
    Read-Host
}
`
				psScriptPath := filepath.Join(os.TempDir(), "voila_tui_launcher.ps1")
				os.WriteFile(psScriptPath, []byte(psScript), 0644)
				
				// Use cmd /c start to completely detach the process from the parent's stdout pipe!
				tuiCmd := exec.Command("wt.exe", "-w", "new-window", "--title", "Voila TUI", "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", psScriptPath)
				errWt := tuiCmd.Start()
				if errWt != nil {
					// Fallback to legacy console if Windows Terminal is not installed
					tuiCmd = exec.Command("cmd.exe", "/c", "start", "Voila TUI", "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", psScriptPath)
					tuiCmd.Start()
				}
				
				fmt.Println("STATUS: GRAPHIFY")
				os.Stdout.Sync()

				output, err := executeGraphifyDAG(ctx, command)
				
				fmt.Println("STATUS: IDLE")
				os.Stdout.Sync()

				cmdMu.Lock()
				currentCancel = nil
				isGraphifyRunning = false
				cmdMu.Unlock()
				
				backendURL := strings.TrimRight(connData.BackendURL, "/") + "/webhook/result"
				backendURL = strings.Replace(backendURL, "wss://", "https://", 1)
				backendURL = strings.Replace(backendURL, "ws://", "http://", 1)

				secretHash := hashPhrase(connData.SecurityPhrase, connData.DeviceID)

				resultPayload := map[string]string{
					"client_id":           clientID,
					"device_id":           connData.DeviceID,
					"secret_hash":         secretHash,
					"mode":                effectiveMode,
					"new_conversation_id": conversationID,
				}

				if err != nil {
					resultPayload["error"] = "DAG Execution Failed:\n" + err.Error()
				} else {
					resultPayload["output"] = stripMarkdownForTTS(output)
				}

				webhookPayload, _ := json.Marshal(resultPayload)
				resp, postErr := http.Post(backendURL, "application/json", bytes.NewBuffer(webhookPayload))
				if postErr == nil && resp != nil {
					resp.Body.Close()
				}

				fmt.Println("STATUS: IDLE")
				os.Stdout.Sync()
			}()

			return
		}

		// Check circuit breaker before executing
		if isCircuitOpen() {
			w.WriteHeader(http.StatusForbidden)
			json.NewEncoder(w).Encode(map[string]string{"error": "circuit_open", "message": "Circuit breaker is open - refusing new commands"})
			return
		}

		// Check semaphore to limit concurrent executions
		select {
		case execSemaphore <- struct{}{}:
			// Acquired semaphore, proceed
		default:
			// Semaphore full, reject request
			w.WriteHeader(http.StatusTooManyRequests)
			json.NewEncoder(w).Encode(map[string]string{"error": "too_many_requests", "message": "Maximum concurrent executions reached"})
			return
		}

		ctx, cancel := context.WithCancel(context.Background())
		cmdMu.Lock()
		currentCancel = cancel
		cmdMu.Unlock()

		w.WriteHeader(http.StatusAccepted)

		go func() {
			defer func() {
				<-execSemaphore // Release semaphore when done
				cmdMu.Lock()
				currentCancel = nil
				isGraphifyRunning = false
				cmdMu.Unlock()
				cancel()
			}()
			wakeScreen()

			var output string
			var newConvID string
			var err error

			startTime := time.Now()

			// Determine effective mode.
			// Priority: explicit GROQ/OLLAMA/SHELL in request body > global badge (currentMode) > LOCAL fallback.
			// The mobile app always sends mode="AGENT", so we must prefer the badge-set global mode.
			debugLog.Printf("[/execute] reqMode=%q globalMode=%q effectiveMode=%q", reqMode, globalMode, effectiveMode)

			taskID := fmt.Sprintf("Agent-%x", time.Now().UnixNano()%0xFFFF)
			myTask := &AgentTask{
				TaskID:  taskID,
				Command: command,
				Mode:    effectiveMode,
				Inbox:   make(chan string, 100),
			}
			agentRegistryMu.Lock()
			activeAgents[taskID] = myTask
			agentRegistryMu.Unlock()

			defer func() {
				agentRegistryMu.Lock()
				delete(activeAgents, taskID)
				agentRegistryMu.Unlock()
			}()

			fmt.Printf("STATUS: MODE:%s\n", effectiveMode)
			os.Stdout.Sync()

			switch effectiveMode {
			case "GROQ":
				fmt.Println("STATUS: RUNNING")
				os.Stdout.Sync()
				m := modelName
				if m == "" {
					m = connData.GroqModel
				}
				if m == "" {
					m = "openai/gpt-oss-120b"
				}
				output, err = executeGroqCommand(ctx, command, connData.GroqAPIKey, m, clientID, nil, taskID, conversationID)
				fmt.Println("STATUS: IDLE")
				os.Stdout.Sync()
				newConvID = conversationID
			case "OLLAMA":
				fmt.Println("STATUS: RUNNING")
				os.Stdout.Sync()
				ollamaModel := connData.OllamaModel
				if ollamaModel == "" {
					ollamaModel = "gemma4:31b"
				}
				ollamaSemaphore <- struct{}{}
				output, err = executeOllamaCommand(ctx, command, connData.OllamaBaseURL, ollamaModel, connData.OllamaAPIKey, nil, taskID, conversationID)
				<-ollamaSemaphore
				fmt.Println("STATUS: IDLE")
				os.Stdout.Sync()
				newConvID = conversationID
			default:
				// LOCAL / AGENT / SHELL — use agy or powershell
				output, newConvID, err = executeCommand(ctx, command, effectiveMode, conversationID, modelName)
			}

			latencyMs := time.Since(startTime).Milliseconds()
			fmt.Printf("STATUS: LATENCY_MS:%d\n", latencyMs)
			os.Stdout.Sync()
			if err == nil {
				fmt.Printf("STATUS: CMD_DONE:SUCCESS\n")
			} else {
				fmt.Printf("STATUS: CMD_DONE:FAILED\n")
			}
			os.Stdout.Sync()

			// Post the result back to backend
			backendURL := strings.TrimRight(connData.BackendURL, "/") + "/webhook/result"
			backendURL = strings.Replace(backendURL, "wss://", "https://", 1)
			backendURL = strings.Replace(backendURL, "ws://", "http://", 1)

			// Calculate security hash to authenticate webhook
			secretHash := hashPhrase(connData.SecurityPhrase, connData.DeviceID)

			resultPayload := map[string]string{
				"client_id":           clientID,
				"device_id":           connData.DeviceID,
				"secret_hash":         secretHash,
				"mode":                effectiveMode,
				"new_conversation_id": newConvID,
			}

			if err != nil {
				resultPayload["error"] = "Command failed:\n" + err.Error()
			} else {
				resultPayload["output"] = stripMarkdownForTTS(output)
			}

			payloadBytes, _ := json.Marshal(resultPayload)

			req, _ := http.NewRequest(http.MethodPost, backendURL, bytes.NewBuffer(payloadBytes))
			req.Header.Set("Content-Type", "application/json")
			if strings.Contains(connData.BackendURL, "ngrok") || strings.Contains(connData.BackendURL, "ngrok-free") {
				req.Header.Set("ngrok-skip-browser-warning", "true")
			}

			// Webhook retry fix: silently ignoring errors left the mobile app
			// deadlocked in "Thinking..." forever on any transient network hiccup.
			webhookClient := &http.Client{Timeout: 10 * time.Second}
			var webhookErr error
			for attempt := 0; attempt < 3; attempt++ {
				if attempt > 0 {
					time.Sleep(time.Duration(1<<uint(attempt-1)) * time.Second) // 1s, 2s backoff
				}
				retryReq, _ := http.NewRequest(http.MethodPost, backendURL, bytes.NewBuffer(payloadBytes))
				retryReq.Header.Set("Content-Type", "application/json")
				if strings.Contains(connData.BackendURL, "ngrok") || strings.Contains(connData.BackendURL, "ngrok-free") {
					retryReq.Header.Set("ngrok-skip-browser-warning", "true")
				}
				resp, err := webhookClient.Do(retryReq)
				if err == nil {
					resp.Body.Close()
					webhookErr = nil
					break
				}
				webhookErr = err
				log.Printf("Webhook delivery attempt %d/3 failed: %v", attempt+1, err)
			}
			if webhookErr != nil {
				log.Printf("All webhook delivery attempts failed — mobile app may be stuck: %v", webhookErr)
			}
		}()
	})

	// /set-mode — Python widget badge sends the chosen mode (LOCAL/GROQ/OLLAMA) here.
	// No auth required: this is localhost-only and the worst an attacker can do is
	// switch execution mode, which still requires the mobile auth secret to /execute.
	mux.HandleFunc("/set-mode", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body struct {
			Mode string `json:"mode"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "Bad request", http.StatusBadRequest)
			return
		}
		mode := strings.ToUpper(body.Mode)
		if mode != "LOCAL" && mode != "GROQ" && mode != "OLLAMA" {
			http.Error(w, "Invalid mode; must be LOCAL, GROQ, or OLLAMA", http.StatusBadRequest)
			return
		}
		currentModeMu.Lock()
		currentMode = mode
		currentModeMu.Unlock()

		if connData, err := loadConnectionData(); err == nil {
			connData.ActiveMode = mode
			saveConnectionData(connData)
		}

		if connData, err := loadConnectionData(); err == nil {
			connData.ActiveMode = mode
			saveConnectionData(connData)
		}

		log.Printf("Mode switched to %s via widget toggle", mode)
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"mode": mode})
	})

	server = &http.Server{
		Addr:    ":8088",
		Handler: mux,
	}

	serverRunning = true
	log.Println("Local agent server starting on :8088")
	if err := server.ListenAndServe(); err != nil {
		log.Printf("HTTP Server error: %v", err)
	}
}

func stopHTTPServer() {
	if server != nil && serverRunning {
		server.Shutdown(nil)
		serverRunning = false
		log.Println("Local agent server stopped")
	}
}

var (
	currentWorkingDir string
	workingDirMutex   sync.Mutex
)

func init() {
	workingDirMutex.Lock()
	currentWorkingDir, _ = os.Getwd()
	workingDirMutex.Unlock()
	keepSystemAwake()
}

var (
	cachedModels []string
	modelsMutex  sync.Mutex
)

func listModelsHandler(w http.ResponseWriter, r *http.Request) {
	connData, err := loadConnectionData()
	if err != nil || connData.SecurityPhrase == "" {
		http.Error(w, "Agent not configured", http.StatusServiceUnavailable)
		return
	}
	expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
	providedSecret := r.Header.Get("X-Exec-Secret")
	if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
		cmd := "unknown"
		bodyBytes, _ := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
		var req struct {
			Command string `json:"command"`
		}
		json.Unmarshal(bodyBytes, &req)
		if req.Command != "" {
			cmd = req.Command
		}
		handleLocalMockExecution(w, r, cmd, connData, r.URL.Path)
		return
	}

	modelsMutex.Lock()
	defer modelsMutex.Unlock()

	if len(cachedModels) == 0 {
		out, err := exec.Command("agy", "models").CombinedOutput()
		if err == nil {
			lines := strings.Split(string(out), "\n")
			for _, line := range lines {
				line = strings.TrimSpace(line)
				if line != "" && !strings.Contains(strings.ToLower(line), "available") {
					cachedModels = append(cachedModels, line)
				}
			}
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(cachedModels)
}

type Conversation struct {
	ID    string `json:"id"`
	Title string `json:"title"`
}

func getBrainDir() string {
	homeDir, _ := os.UserHomeDir()
	return filepath.Join(homeDir, ".gemini", "voila-cli", "brain")
}

func listConversationsHandler(w http.ResponseWriter, r *http.Request) {
	// Zero-friction mode: Authenticate using SecurityPhraseHash
	connData, err := loadConnectionData()
	if err != nil || connData.SecurityPhrase == "" {
		http.Error(w, "Agent not configured", http.StatusServiceUnavailable)
		return
	}
	expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
	providedSecret := r.Header.Get("X-Exec-Secret")
	if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
		cmd := "unknown"
		bodyBytes, _ := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
		var req struct {
			Command string `json:"command"`
		}
		json.Unmarshal(bodyBytes, &req)
		if req.Command != "" {
			cmd = req.Command
		}
		handleLocalMockExecution(w, r, cmd, connData, r.URL.Path)
		return
	}

	brainDir := getBrainDir()

	entries, err := os.ReadDir(brainDir)
	var conversations []Conversation

	if err == nil {
		for _, entry := range entries {
			if entry.IsDir() {
				id := entry.Name()
				transcriptPath := filepath.Join(brainDir, id, ".system_generated", "logs", "transcript.jsonl")
				title := "Unknown Task"

				file, err := os.Open(transcriptPath)
				if err == nil {
					scanner := bufio.NewScanner(file)
					for scanner.Scan() {
						line := scanner.Text()
						if strings.Contains(line, "\"type\":\"USER_INPUT\"") {
							var step map[string]interface{}
							if json.Unmarshal([]byte(line), &step) == nil {
								if c, ok := step["content"].(string); ok {
									title = c
									if len(title) > 40 {
										title = title[:37] + "..."
									}
									title = strings.ReplaceAll(title, "\n", " ")
									break
								}
							}
						}
					}
					file.Close()
				}
				conversations = append(conversations, Conversation{ID: id, Title: title})
			}
		}
	}

	// reverse to show newest first
	for i, j := 0, len(conversations)-1; i < j; i, j = i+1, j-1 {
		conversations[i], conversations[j] = conversations[j], conversations[i]
	}

	jsonData, _ := json.Marshal(conversations)
	encrypted, err := EncryptData(jsonData, connData.SecurityPhrase)
	w.Header().Set("Content-Type", "application/json")
	if err == nil {
		json.NewEncoder(w).Encode(map[string]string{"encrypted": encrypted})
	} else {
		json.NewEncoder(w).Encode(conversations)
	}
}

func executeCommand(ctx context.Context, command string, mode string, conversationID string, modelName string) (string, string, error) {
	var cmd *exec.Cmd

	modeUpper := strings.ToUpper(mode)
	// LOCAL = agy (local Gemini agent). AGENT = also agy (legacy name).
	// Only SHELL = raw PowerShell. Empty string = default to agy.
	if modeUpper == "AGENT" || modeUpper == "LOCAL" || modeUpper == "" {
		prompt := command + "\n\nCRITICAL - COMMAND MEMORY:\nHere are your highly compressed, previously successful PowerShell techniques:\n" + loadMemory() + "\nWhen asked to do a task, FIRST check if a command in this memory perfectly satisfies the purpose. If yes, RUN IT EXACTLY AS-IS from memory (unless the user explicitly requests a new/specific method). If you invent a NEW successful technique, you MUST immediately call the 'save_command_memory' tool to permanently memorize it.\n\n(CRITICAL SYSTEM NOTE: When speaking to the user in your final text response, keep your voice responses casual, brief, and conversational. HOWEVER, when writing code, generating PDFs, or creating documents via tools, your output MUST be exhaustively detailed, massive, and highly comprehensive. NEVER generate a short summary for a document.)\n\nCRITICAL - ONE-SHOT TERMINAL EXECUTION (MAX TOOLS):\nTo avoid hitting max_tool iteration limits and increase execution speed, you MUST combine multiple PowerShell steps into a SINGLE detailed command per tool_call. Do NOT run one tiny command, wait for the result, and then run the next tiny command. Instead, write a robust PowerShell script block (using semicolons or newlines) that loops, searches, or processes everything in one shot and returns the final desired output. Keep writing detailed combined commands until you get the exact required output!\n\nCRITICAL OS GUARDRAIL: You MUST NEVER modify, delete, or touch Windows system files, System32, Program Files, the Registry, or any critical OS configuration. You must refuse commands that could harm or break the OS. Address the user as 'boss'. Do not use overly formal language.\n\nCRITICAL SYSTEM NOTE: You are running inside an isolated background sandbox (`exebox` desktop). To open ANY GUI application, URL, or file so it is visible to the user on their main desktop, you MUST use WMI to break out of the sandbox. Use exactly this command format: `Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'explorer.exe \"<URL_OR_PATH>\"'` (for URLs/files) or `Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList '<APP_EXE>'` (for apps). DO NOT use Start-Process, as it will spawn invisibly in the sandbox! To perform browser automation, you MUST first launch a visible browser using Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe --remote-debugging-port=9222 --user-data-dir=C:\\tmp\\ai_browser_profile \"about:blank\"'. Then, control it by running python C:\\Users\\ojasw\\Desktop\\voice-cli-system\\local-agent\\browser_tools.py with args --action [goto|click|type|scrape|extract_links|snapshot] --url <url> --selector <css> --value <text>.\n\nCRITICAL - .AIIGNORE & DEPENDENCY OVERHEAD (0 BUGS POLICY):\nWhen exploring projects, NEVER search or read inside dependency folders (node_modules, .venv, venv, __pycache__, vendor, .git, .m2, .gradle, target, packages, .cargo/registry). They contain massive overhead that breaks your context limits.\nTo understand dependencies, ONLY read blueprint files (package.json, pyproject.toml, requirements.txt, go.mod, pom.xml, build.gradle, composer.json, Gemfile, Cargo.toml, *.csproj). Also NEVER read standard '.env' files; if you need environment context, ONLY look at '.env.example' or '.env.local'. Also NEVER read standard '.env' files; if you need environment context, ONLY look at '.env.example' or '.env.local'.\nWhen searching for files, enforce this .aiignore policy by using native PowerShell regex filtering:\n`Get-ChildItem -Recurse -Filter \"*name*\" -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\\\(node_modules|\\.venv|venv|vendor|\\.git|target|\\.gradle|\\.m2|packages|__pycache__|dist|build|out|bin|obj|\\.idea|\\.vscode)\\\\' } | Select-Object -ExpandProperty FullName`)"
		if modelName == "" || modelName == "flash" {
			modelName = "Gemini 3.7 Flash (High)"
		}

		workingDirMutex.Lock()
		cwd := currentWorkingDir
		workingDirMutex.Unlock()

		// Short preview of the user's command (max 60 chars)
		preview := command
		if len(preview) > 60 {
			preview = preview[:57] + "..."
		}

		debugLog.Printf("[executeCommand/AGENT] command preview=%q modelName=%q cwd=%q", preview, modelName, cwd)

		// Encode prompt safely as base64 to avoid quoting issues
		encodedPrompt := base64.StdEncoding.EncodeToString([]byte(prompt))

		// Build agy invocation string
		var agyCmd string
		if conversationID != "" {
			agyCmd = fmt.Sprintf(`agy --model "%s" --conversation "%s" --dangerously-skip-permissions --print ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('%s')))`,
				modelName, conversationID, encodedPrompt)
		} else {
			agyCmd = fmt.Sprintf(`agy --model "%s" --dangerously-skip-permissions --print ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('%s')))`,
				modelName, encodedPrompt)
		}

		// Temp file for output capture
		tmpFile := filepath.Join(os.TempDir(), fmt.Sprintf("voila_agent_%d.txt", time.Now().UnixNano()))
		debugLog.Printf("[executeCommand/AGENT] tmpFile=%s", tmpFile)

		// Output the chat header to the main server console so the user can see it
		fmt.Println("================================================")
		fmt.Println("   [AI] VOILA AI - LOCAL AGENT TERMINAL        ")
		fmt.Println("   Gemini is thinking and executing...         ")
		fmt.Println("================================================")
		fmt.Println("")
		fmt.Printf("[Task]: %s\n\n", preview)
		fmt.Println("------------------------------------------------")

		fmt.Println("STATUS: RUNNING")
		os.Stdout.Sync()

		cmdMu.Lock()
		currentConvID = conversationID
		cmdMu.Unlock()

		// Execute agy silently in the background
		cmdObj := exec.CommandContext(ctx, "powershell", "-Command", agyCmd)
		outBytes, _ := cmdObj.CombinedOutput()

		cmdMu.Lock()
		currentConvID = ""
		cmdMu.Unlock()

		fmt.Println("STATUS: IDLE")
		os.Stdout.Sync()

		outStr := strings.TrimSpace(string(outBytes))

		// Print the agent's response to the main server terminal as well
		fmt.Println(outStr)
		fmt.Println("------------------------------------------------")
		fmt.Println("[OK] Agent finished successfully.")

		debugLog.Printf("[executeCommand/AGENT] outStr length=%d bytes", len(outStr))
		if outStr == "" {
			outStr = "(no output)"
		}
		return outStr, "", nil

	} else {
		if runtime.GOOS == "windows" {
			fullCommand := command + "; Write-Output \"`n___PWD___$((Get-Location).Path)\""
			cmd = exec.CommandContext(ctx, "powershell", "-Command", fullCommand)
		} else {
			fullCommand := command + "; echo \"\n___PWD___$(pwd)\""
			cmd = exec.CommandContext(ctx, "sh", "-c", fullCommand)
		}
		workingDirMutex.Lock()
		if currentWorkingDir != "" {
			cmd.Dir = currentWorkingDir
		}
		workingDirMutex.Unlock()
	}

	var stdout, stderr bytes.Buffer
	cmd.Stdout = io.MultiWriter(&stdout, os.Stdout)
	cmd.Stderr = io.MultiWriter(&stderr, os.Stderr)

	fmt.Println("STATUS: RUNNING")
	os.Stdout.Sync() // Force flush to ensure real-time delivery to Python widget

	cmdMu.Lock()
	currentCmd = cmd
	currentConvID = conversationID
	cmdMu.Unlock()

	err := cmd.Run()

	cmdMu.Lock()
	currentCmd = nil
	currentConvID = ""
	cmdMu.Unlock()

	fmt.Println("STATUS: IDLE")
	os.Stdout.Sync() // Force flush to ensure real-time delivery to Python widget

	outStr := stdout.String()
	errStr := stderr.String()

	if strings.ToUpper(mode) != "AGENT" {
		lines := strings.Split(outStr, "\n")
		var newOut []string
		for _, line := range lines {
			trimmed := strings.TrimSpace(line)
			if strings.HasPrefix(trimmed, "___PWD___") {
				workingDirMutex.Lock()
				currentWorkingDir = strings.TrimPrefix(trimmed, "___PWD___")
				workingDirMutex.Unlock()
			} else {
				newOut = append(newOut, line)
			}
		}
		outStr = strings.Join(newOut, "\n")
	}

	outStr = strings.TrimSpace(outStr)

	if err != nil {
		if outStr != "" {
			return outStr + "\n" + errStr, conversationID, err
		}
		return errStr, conversationID, err
	}

	return outStr, conversationID, nil
}

// ─────────────────────────────────────────────────────────────────────────────
// Cloud API executors — Groq & Ollama (with tool-calling support)
// ─────────────────────────────────────────────────────────────────────────────

// groqMessage mirrors the Groq / OpenAI chat message format.
// For tool-calling we need a richer raw message so we use map[string]interface{} in loops.
type groqMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// ── Tool definitions ─────────────────────────────────────────────────────────

// toolDef is the JSON structure sent to cloud APIs describing an available tool.
type toolDef struct {
	Type     string      `json:"type"`
	Function toolFuncDef `json:"function"`
}

type toolFuncDef struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	Parameters  map[string]interface{} `json:"parameters"`
}

// availableTools is the standard list of tools sent with every cloud API request.
var availableTools = []toolDef{
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "send_message",
			Description: "Send a message to another concurrently running agent. Use this if you are in a multi-agent scenario.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"target_agent_id": map[string]interface{}{
						"type":        "string",
						"description": "The Task ID of the target agent",
					},
					"message": map[string]interface{}{
						"type":        "string",
						"description": "The message to send",
					},
				},
				"required": []string{"target_agent_id", "message"},
			},
		},
	},

	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "browser_automation",
			Description: "Control a visible, headful browser. Use this to interact with a page. For simple information lookup, prefer web_research to save tokens. They can be used together.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"action":   map[string]interface{}{"type": "string", "description": "Action to perform: 'goto', 'click', 'type', 'press', 'scroll', 'new_tab', 'switch_tab', 'close_tab', 'list_tabs', 'scrape', 'extract_links', 'eval'"},
					"url":      map[string]interface{}{"type": "string", "description": "URL to navigate to (required for 'goto' and 'new_tab')"},
					"selector": map[string]interface{}{"type": "string", "description": "CSS selector to click or type into"},
					"value":    map[string]interface{}{"type": "string", "description": "Text to type, key to press (e.g. 'Enter'), or scroll direction ('up'/'down')/pixels (e.g. '500')"},
				},
				"required": []string{"action"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "web_research",
			Description: "Search the web. Highly token-efficient for simple lookups. If a result requires deep scraping or interaction, you can follow up with automate_0.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"query": map[string]interface{}{
						"type":        "string",
						"description": "The search query",
					},
					"search_type": map[string]interface{}{
						"type":        "string",
						"description": "Search type: 'text' (default, DuckDuckGo text search) or 'image' (Openverse CC image search)",
					},
				},
				"required": []string{"query"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "read_file",
			Description: "Read the content of a file from the local filesystem.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{
						"type":        "string",
						"description": "Absolute or relative path to the file",
					},
				},
				"required": []string{"path"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "edit_file",
			Description: "Edit an existing file by finding a specific text block and replacing it. Use this instead of write_file for small changes to large files to save tokens.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{
						"type":        "string",
						"description": "Absolute or relative path to the file",
					},
					"target_text": map[string]interface{}{
						"type":        "string",
						"description": "The exact block of text you want to replace. Must match the file exactly.",
					},
					"replacement_text": map[string]interface{}{
						"type":        "string",
						"description": "The new text to insert in place of the target_text.",
					},
				},
				"required": []string{"path", "target_text", "replacement_text"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "write_file",
			Description: "Write content to a file on the local filesystem.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{
						"type":        "string",
						"description": "Absolute or relative path to the file",
					},
					"content": map[string]interface{}{
						"type":        "string",
						"description": "Content to write into the file",
					},
				},
				"required": []string{"path", "content", "theme", "design_strategy"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "run_terminal",
			Description: "Run a PowerShell command on the local machine. A visible terminal window will open showing the command.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"command": map[string]interface{}{
						"type":        "string",
						"description": "PowerShell command to execute",
					},
				},
				"required": []string{"command"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "create_pdf",
			Description: "Create a PDF file with text content.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path":      map[string]interface{}{"type": "string", "description": "Absolute path to save the PDF"},
					"content":   map[string]interface{}{"type": "string", "description": "The rich HTML or Markdown content of the PDF. The content MUST be exhaustive, massive, and highly detailed. DO NOT write short summaries. Leave empty if using source_files."},
					"source_files": map[string]interface{}{
						"type": "array",
						"items": map[string]interface{}{
							"type": "string",
						},
						"description": "Array of absolute file paths to HTML/Markdown files. Use this to compile massive 40-page PDFs that exceed single-call token limits.",
					},
					"latex":     map[string]interface{}{"type": "string", "description": "Raw LaTeX code to compile into a PDF. If you are generating a professional or multi-page PDF, YOU MUST PROVIDE THIS. Autonomously write full, exhaustive LaTeX code using \\chapter, \\section, \\newpage, and tabularx to design the document perfectly based on the topic, acting as an expert typesetter."},
					"watermark": map[string]interface{}{"type": "string", "description": "Optional watermark text to display diagonally on pages"},
					"design_strategy": map[string]interface{}{"type": "string", "description": `Select a Global Marketplace Skill Prompt to guide your LaTeX generation:
- "McKinsey Consulting Report": Enforces BLUF (Bottom Line Up Front), strict two-column layouts, heavy data tables, and minimal corporate styling.
- "Academic Whitepaper (IEEE/Nature)": Enforces standard LaTeX academic margins, complex tabularx datasets, and highly rigorous technical prose.
- "Creative Apple-Style Pitch": Enforces massive text sizes, extreme minimalism, huge margins, and striking use of negative space.
- "FlowGPT Visual Infographic": Uses dense, highly visual layouts, bullet point grids, and colorful accent blocks.`},
					"theme":     map[string]interface{}{"type": "string", "description": "Theme name MUST BE one of: origami, handwritten, sketching, pixelated, asciiart, or notebooklm"},
				},
				"required": []string{"path", "content", "theme", "design_strategy"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "read_pdf",
			Description: "Extract text from a PDF file.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path of the PDF"},
				},
				"required": []string{"path"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "create_doc",
			Description: "Create an elegant, highly structured Word Document (DOCX). Autonomously structure the content with exhaustive detail, tables, and professional formatting.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path":    map[string]interface{}{"type": "string", "description": "Absolute path to save DOCX"},
					"content": map[string]interface{}{"type": "string", "description": "Text content of the document"},
					"theme":   map[string]interface{}{"type": "string", "description": "Theme name: corporate_blue, cyberpunk, minimalist, modern_dark"},
					"design_strategy": map[string]interface{}{"type": "string", "description": `Select a Global Marketplace Skill Prompt to guide your DOCX generation:
- "Harvard Business Case Study": Enforces strict academic tone, blockquotes for testimonies, and 12pt serif typography.
- "Corporate Legal Contract": Enforces heavily numbered lists (1.1, 1.2), bolded definitions, and rigid section breaks.
- "Modern Product Requirement Document (PRD)": Uses markdown-style headers, deep feature tables, and user story blocks.`},
				},
				"required": []string{"path", "content", "theme", "design_strategy"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "create_ppt",
			Description: "Create a polished PowerPoint presentation with Gamma-style layouts, gradient themes, and card-based visual blocks.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path":  map[string]interface{}{"type": "string", "description": "Absolute path to save the PPTX file"},
					"title": map[string]interface{}{"type": "string", "description": "Presentation title (shown on the auto-generated cover slide)"},
					"design_strategy": map[string]interface{}{"type": "string", "description": `Select a Global Marketplace Skill Prompt to guide your slide design:
- "PromptBase Y-Combinator Pitch Deck": Forces problem-solution structure, large metric callouts, and minimalist startup aesthetics.
- "McKinsey Strategy Deck": Forces dense data slides, actionable slide titles, 6x6 rule, and highly analytical visual blocks.
- "SnackPrompt Storytelling Flow": Uses quote blocks, full-image backgrounds, and narrative-driven section dividers.`},
					"theme": map[string]interface{}{"type": "string", "description": `Theme name — choose carefully based on audience and tone:
• corporate_blue   — professional navy/blue. Best for business reports, investor decks
• cyberpunk        — neon pink/cyan on dark. Best for tech demos, gaming, edgy brands
• minimalist       — near-black with white text. Best for creative portfolios, editorial
• modern_dark      — charcoal + orange. Best for product launches, general purpose dark
• illustrated_light— light lavender gradient, white cards, purple accents. Best for education, health, startups (Gamma-style)
• warm_sunset      — cream/coral gradient, white cards. Best for lifestyle, personal brands, workshops
• ocean_depth      — deep blue gradient, cyan accents. Best for finance, maritime, analytics
• forest_sage      — light green gradient, white cards. Best for sustainability, wellness, HR
• dynamic          — AI-randomized palette unique per presentation`},
					"slides": map[string]interface{}{"type": "string", "description": `JSON array of slide objects. Every slide must have a "type" field. Choose the most expressive layout for each slide:

LAYOUT GUIDE — pick the type that best fits the content:
• "content"     — Default. Card-backed text + bullets. Use for explanations, descriptions, analysis.
• "section"     — Full-bleed section divider, large centered text. Use between major chapters.
• "title_slide" — Opening or closing slide. Fields: title, subtitle, author. Use FIRST and LAST.
• "quote"       — Decorative large quote card with attribution. Fields: content, author. Use for testimonials, key insights.
• "chart"       — Data visualization. Fields: chart_type (bar/line/pie), chart_data ({label:value}), title. Use when showing trends, comparisons, distributions.
• "image"       — Image fill slide. Fields: image_path (optional — set auto_images:true to auto-search). Use for visual impact.
• "two_column"  — Side-by-side text. Fields: content_left, content_right. Use for pros/cons lists, parallel info.
• "comparison"  — VS layout with colored headers and center badge. Fields: left_title, right_title, content_left (bullets), content_right (bullets). Use for before/after, competitor analysis.
• "metrics"     — KPI dashboard. Fields: metrics:[{value, label, sublabel?}]. Use when 2–4 big numbers are the story (revenue, growth, NPS, etc.).
• "timeline"    — Horizontal step chain. Fields: steps:[{label, description?}] or steps:["Step1","Step2"]. Use for roadmaps, processes, history (max 6 steps).
• "agenda"      — Numbered list with accent badge per item. Fields: items:["Item 1","Item 2"]. Use for table of contents, meeting agendas, feature lists (max 8 items).

Example full deck:
[{"type":"title_slide","title":"Q3 Business Review","subtitle":"September 2026","author":"Product Team"},
 {"type":"agenda","title":"Agenda","items":["Market Overview","Product Updates","Financial Metrics","Next Steps"]},
 {"type":"metrics","title":"Q3 at a Glance","metrics":[{"value":"$2.4M","label":"Revenue","sublabel":"+18% QoQ"},{"value":"94%","label":"Retention"},{"value":"1,847","label":"New Customers"}]},
 {"type":"timeline","title":"Product Roadmap","steps":[{"label":"Q1","description":"Research"},{"label":"Q2","description":"Build"},{"label":"Q3","description":"Launch"}]},
 {"type":"comparison","title":"Before vs After","left_title":"Before","right_title":"After","content_left":"- Manual process\n- 5 hours/week\n- Error-prone","content_right":"- Fully automated\n- 15 min/week\n- Zero errors"},
 {"type":"chart","title":"Revenue Growth","chart_type":"bar","chart_data":{"Q1":180000,"Q2":210000,"Q3":240000}},
 {"type":"content","title":"Key Takeaways","content":"- Revenue up 33% YoY\n- Churn reduced to 6%\n- On track for Q4 target"},
 {"type":"section","content":"Thank You"},
 {"type":"title_slide","title":"Questions?","subtitle":"contact@company.com"}]`},
					"auto_images": map[string]interface{}{"type": "boolean", "description": "If true, automatically searches Openverse (CC-licensed photos) for image-type slides and inserts the best-scoring result (landscape + high-resolution preferred)"},
				},
				"required": []string{"path", "title", "theme", "design_strategy", "slides"},
			},
		},
	},

	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "create_excel",
			Description: "Create a robust, deeply structured Excel Spreadsheet (XLSX). Do NOT just output a basic table. Autonomously invent multi-sheet structures, financial models, or dashboards based on the user's request.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path to save XLSX"},
					"data": map[string]interface{}{"type": "string", "description": "JSON string of array of objects representing rows"},
					"design_strategy": map[string]interface{}{"type": "string", "description": `Select a Global Marketplace Skill Prompt to guide your Excel generation:
- "Wall Street Financial Model": Enforces strict financial formatting, separate assumptions/calculations sheets, and YoY/QoQ variance columns.
- "Silicon Valley SaaS Dashboard": Enforces MRR/ARR tracking, cohort analysis grids, and conditional formatting rules for churn.
- "Project Management Gantt": Enforces timeline-based columns, status dropdowns, and color-coded priority blocks.`},
				},
				"required": []string{"path", "data", "design_strategy"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "modify_excel",
			Description: "Modify specific cells in an existing Excel file.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path":       map[string]interface{}{"type": "string", "description": "Absolute path of XLSX"},
					"sheet_name": map[string]interface{}{"type": "string", "description": "Name of the sheet to modify (optional)"},
					"updates":    map[string]interface{}{"type": "string", "description": "JSON string of cell-to-value map, e.g. {\"A1\":\"Revenue\"}"},
				},
				"required": []string{"path", "updates"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "read_excel",
			Description: "Read an Excel file as text.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path":       map[string]interface{}{"type": "string", "description": "Absolute path of XLSX"},
					"sheet_name": map[string]interface{}{"type": "string", "description": "Name of the sheet to read (optional)"},
				},
				"required": []string{"path"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "create_csv",
			Description: "Create a large, highly realistic CSV file. Act as a senior data engineer: autonomously invent realistic schema columns and generate exhaustive rows of high-quality data.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path to save CSV"},
					"data": map[string]interface{}{"type": "string", "description": "JSON array of objects or raw CSV string"},
					"design_strategy": map[string]interface{}{"type": "string", "description": `Select a Global Marketplace Skill Prompt to guide your CSV generation:
- "Enterprise Database Seed": Enforces strict primary keys, UUIDs, ISO-8601 timestamps, and highly realistic mock data.
- "Machine Learning Dataset": Enforces normalized continuous variables, encoded categorical labels, and train/test splits.
- "Marketing CRM Export": Enforces standard lead schemas (First Name, Last Name, Email, LTV, Last Contacted).`},
				},
				"required": []string{"path", "data", "design_strategy"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "read_csv",
			Description: "Read a CSV file.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path of CSV"},
				},
				"required": []string{"path"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "list_dir",
			Description: "List the contents of a directory.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path of the directory"},
				},
				"required": []string{"path"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "save_command_memory",
			Description: "Save a successful PowerShell technique to memory for future reuse.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"purpose": map[string]interface{}{"type": "string", "description": "What the command does"},
					"command": map[string]interface{}{"type": "string", "description": "The exact PowerShell command"},
				},
				"required": []string{"purpose", "command"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "create_docx",
			Description: "Create a DOCX file.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path to save DOCX"},
					"content": map[string]interface{}{"type": "string", "description": "Markdown formatted content"},
				},
				"required": []string{"path", "content"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.templates.list",
			Description: "List all available document templates.",
			Parameters: map[string]interface{}{"type": "object", "properties": map[string]interface{}{}},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.templates.get",
			Description: "Get details and requirements for a specific template.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"template_id": map[string]interface{}{"type": "string", "description": "Template ID"},
				},
				"required": []string{"template_id"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.create_from_template",
			Description: "Create a new document from a template.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"template_id": map[string]interface{}{"type": "string", "description": "Template ID"},
					"content": map[string]interface{}{"type": "object", "description": "Content mapping matching the template schema"},
				},
				"required": []string{"template_id", "content"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.list_recent",
			Description: "List recently generated template documents.",
			Parameters: map[string]interface{}{"type": "object", "properties": map[string]interface{}{}},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.open_local",
			Description: "Open a recently generated document locally.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Path to the document"},
				},
				"required": []string{"path"},
			},
		},
	},
}

// executeTool dispatches to the correct tool implementation and returns a result string.
// It also emits a STATUS: TOOL:<name> line so the Python face can show per-tool states,
// and it emits stream-json events for ALL tools to visualize them seamlessly in the terminal.
func executeTool(ctx context.Context, toolName string, argsJSON json.RawMessage, streamFileObj *os.File) string {
	var args map[string]interface{}
	if err := json.Unmarshal(argsJSON, &args); err == nil {
		var pseudoCommand string
		getString := func(key string) string {
			if val, exists := args[key]; exists {
				if strVal, ok := val.(string); ok {
					return strVal
				}
				if jsonBytes, err := json.Marshal(val); err == nil {
					return string(jsonBytes)
				}
			}
			return ""
		}
		switch toolName {

		case "save_command_memory":
			return saveMemory(getString("purpose"), getString("command"))
		case "run_terminal":
			pseudoCommand = getString("command")
		case "read_file":
			pseudoCommand = "cat " + resolveAgentPath(getString("path"))
		case "write_file":
			pseudoCommand = "echo '...' > " + resolveAgentPath(getString("path"))
		case "edit_file":
			pseudoCommand = "sed '...' " + resolveAgentPath(getString("path"))
		case "list_dir":
			pseudoCommand = "ls " + resolveAgentPath(getString("path"))
		case "web_research":
			pseudoCommand = "search \"" + getString("query") + "\""
		case "create_pdf", "create_doc", "create_ppt", "create_docx", "create_excel", "create_csv", "modify_excel":
			pseudoCommand = "write_doc " + resolveAgentPath(getString("path"))
		case "read_pdf", "read_excel", "read_csv":
			pseudoCommand = "read_doc " + resolveAgentPath(getString("path"))
		case "browser_automation":
			pseudoCommand = "browser " + getString("action") + " " + getString("url") + getString("selector")
		default:
			pseudoCommand = toolName + " ..."
		}

		if streamFileObj != nil && pseudoCommand != "" {
			event := map[string]interface{}{
				"event": "step_update",
				"step_update": map[string]interface{}{
					"step_type": "tool",
					"state":     "RUNNING",
					"tool_name": "run_command",
					"tool_info": map[string]interface{}{
						"parameters": map[string]interface{}{
							"CommandLine": pseudoCommand,
						},
					},
				},
			}
			jsonBytes, _ := json.Marshal(event)
			streamFileObj.WriteString(string(jsonBytes) + "\n")
			streamFileObj.Sync()
		}

		result := executeToolInner(ctx, toolName, argsJSON, streamFileObj)

		if streamFileObj != nil && pseudoCommand != "" {
			visualResult := result
			if len(visualResult) > 2000 {
				visualResult = visualResult[:2000] + "\n... (output truncated for viewer)"
			}
			event := map[string]interface{}{
				"event": "step_update",
				"step_update": map[string]interface{}{
					"step_type": "tool",
					"state":     "DONE",
					"tool_name": "run_command",
					"tool_info": map[string]interface{}{
						"parameters": map[string]interface{}{
							"CommandLine": pseudoCommand,
						},
						"output": visualResult,
					},
				},
			}
			jsonBytes, _ := json.Marshal(event)
			streamFileObj.WriteString(string(jsonBytes) + "\n")
			streamFileObj.Sync()
		}
		return result
	}
	return executeToolInner(ctx, toolName, argsJSON, streamFileObj)
}

func callPythonDocumentTool(toolName string, argsJSON json.RawMessage) string {
	exeDir, err := os.Executable()
	if err != nil {
		return "error: could not find executable directory"
	}
	scriptPath := filepath.Join(filepath.Dir(exeDir), "document_tools.py")

	payload := map[string]interface{}{
		"action": toolName,
	}

	var args map[string]interface{}
	if err := json.Unmarshal(argsJSON, &args); err == nil {
		payload["kwargs"] = args
	}

	payloadBytes, _ := json.Marshal(payload)

	cmd := exec.Command("python", scriptPath)
	cmd.Stdin = bytes.NewReader(payloadBytes)
	outBytes, err := cmd.CombinedOutput()

	if err != nil {
		return fmt.Sprintf("Error executing python script: %v\nOutput: %s", err, string(outBytes))
	}
	return strings.TrimSpace(string(outBytes))
}

func startTerminalSession() {
	os.Remove(terminalCmdFile)
	os.Remove(terminalOutFile)
	os.Remove(terminalDoneFile)
	os.Remove(terminalPidFile)

	psWrapperFile := filepath.Join(os.TempDir(), "voila_ipc_server.ps1")
	psCode := fmt.Sprintf(`$ErrorActionPreference = 'Continue'
Set-Location -Path [Environment]::GetFolderPath('Desktop')
$host.UI.RawUI.WindowTitle = 'Voila AI - Agent Session'
[System.IO.File]::WriteAllText('%s', $PID.ToString())
Clear-Host
Write-Host '================================================' -ForegroundColor Magenta
Write-Host '          [AI] PERSISTENT SESSION ACTIVE' -ForegroundColor Cyan
Write-Host '================================================' -ForegroundColor Magenta

$cmdFile = '%s'
$outFile = '%s'
$doneFile = '%s'
$parentPid = %d

while ($true) {
	if (-not (Get-Process -Id $parentPid -ErrorAction SilentlyContinue)) {
		Write-Host "Parent process died. Closing terminal..." -ForegroundColor Red
		Start-Sleep -Seconds 2
		break
	}
	if (Test-Path $cmdFile) {
		$b64 = Get-Content $cmdFile -Raw
		if ($b64.Trim() -eq "EXIT") {
			break
		}
		$cmdText = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($b64))

		Write-Host ''
		Write-Host 'PS> ' -NoNewline -ForegroundColor Green
		foreach ($char in $cmdText.ToCharArray()) {
			Write-Host $char -NoNewline -ForegroundColor Yellow
			Start-Sleep -Milliseconds 2
		}
		Write-Host ''
		Write-Host '------------------------------------------------' -ForegroundColor DarkGray

		if (Test-Path $outFile) { Remove-Item $outFile -Force }
		$outVar = $null
		try {
			Invoke-Expression $cmdText *>&1 | Tee-Object -Variable outVar
		} catch {
			$_ | Tee-Object -Variable outVar
		}
		$outStr = $outVar | Out-String
		[System.IO.File]::WriteAllText($outFile, $outStr)
		
		Write-Host '------------------------------------------------' -ForegroundColor DarkGray
		"DONE" | Out-File -FilePath $doneFile -Encoding ASCII

		while (Test-Path $cmdFile) {
			Start-Sleep -Milliseconds 100
		}
	} else {
		Start-Sleep -Milliseconds 200
	}
}
Write-Host 'Session closing...' -ForegroundColor DarkGray
Start-Sleep -Seconds 2
`, terminalPidFile, terminalCmdFile, terminalOutFile, terminalDoneFile, os.Getpid())

	os.WriteFile(psWrapperFile, []byte(psCode), 0644)

	cmdObj := exec.Command("wt", "-w", "new-window", "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", psWrapperFile)
	errStart := cmdObj.Start()
	if errStart != nil {
		cmdObj = exec.Command("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", psWrapperFile)
		cmdObj.SysProcAttr = &syscall.SysProcAttr{CreationFlags: 0x00000010}
		cmdObj.Start()
	}

	for i := 0; i < 20; i++ {
		if b, err := os.ReadFile(terminalPidFile); err == nil && len(b) > 0 {
			terminalPid = strings.TrimSpace(string(b))
			terminalActive = true
			break
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func cleanupTerminalSession() {
	terminalSessionMu.Lock()
	defer terminalSessionMu.Unlock()
	if terminalActive {
		os.WriteFile(terminalCmdFile, []byte("EXIT"), 0644)
		terminalActive = false
		terminalPid = ""
	}
}
func executeToolInner(ctx context.Context, toolName string, argsJSON json.RawMessage, streamFileObj *os.File) string {
	// Emit status so Python face knows which tool is running
	fmt.Printf("STATUS: TOOL:%s\n", toolName)
	os.Stdout.Sync()

	var args map[string]interface{}
	if err := json.Unmarshal(argsJSON, &args); err != nil {
		return "error: failed to parse tool arguments: " + err.Error()
	}

	// Globally resolve all 'path' parameters so files default to Desktop
	if pathVal, exists := args["path"]; exists {
		if pathStr, ok := pathVal.(string); ok {
			
			// If it's a document generation tool, FORCE it to the Desktop regardless of what absolute path the AI hallucinated
			isDocTool := false
			docTools := []string{"create_pdf", "create_doc", "create_ppt", "create_docx", "create_excel", "create_csv"}
			for _, dt := range docTools {
				if toolName == dt {
					isDocTool = true
					break
				}
			}

			if isDocTool {
				homeDir, _ := os.UserHomeDir()
				// Extract just the filename to strip out any project folder paths the AI tried to use
				fileName := filepath.Base(pathStr)
				args["path"] = filepath.Join(homeDir, "Desktop", fileName)
			} else {
				args["path"] = resolveAgentPath(pathStr)
			}
		}
	}

	// CRITICAL FIX: Intercept source_files array so massive 40-page PDFs can locate their chapters
	if sfVal, exists := args["source_files"]; exists {
		if sfList, ok := sfVal.([]interface{}); ok {
			for i, sf := range sfList {
				if sfStr, ok := sf.(string); ok {
					sfList[i] = resolveAgentPath(sfStr)
				}
			}
			args["source_files"] = sfList
		} else if sfStr, ok := sfVal.(string); ok {
			// AI hallucinated a string instead of an array
			parts := strings.Split(sfStr, ",")
			var resolvedList []string
			for _, p := range parts {
				resolvedList = append(resolvedList, resolveAgentPath(strings.TrimSpace(p)))
			}
			args["source_files"] = resolvedList
		}
	}
	
	// Re-serialize args JSON so downstream Python tools get the resolved paths
	argsJSON, _ = json.Marshal(args)

	getString := func(key string) string {
		if val, exists := args[key]; exists {
			if strVal, ok := val.(string); ok {
				return strVal
			}
			if jsonBytes, err := json.Marshal(val); err == nil {
				return string(jsonBytes)
			}
		}
		return ""
	}

	switch toolName {
	case "docs.templates.list", "docs.templates.get", "docs.create_from_template", "docs.list_recent", "docs.open_local":
		action := strings.TrimPrefix(toolName, "docs.")
		if action == "templates.list" { action = "list" }
		if action == "templates.get" { action = "get" }
		
		scriptPath := filepath.Join(getExecutableDir(), "mcp_docs_facade.py")
		var cmdObj *exec.Cmd
		
		if action == "list" || action == "list_recent" {
			cmdObj = exec.Command("python", scriptPath, action)
		} else if action == "get" || action == "open_local" {
			argStr := getString("template_id")
			if action == "open_local" {
			    argStr = getString("path")
			}
			cmdObj = exec.Command("python", scriptPath, action, argStr)
		} else if action == "create_from_template" {
			cmdObj = exec.Command("python", scriptPath, "create", string(argsJSON))
			cmdObj.Env = append(os.Environ(), "VOILA_DOCS_MOCK=1") // Force mock mode for now
		}
		
		outBytes, err := cmdObj.CombinedOutput()
		result := strings.TrimSpace(string(outBytes))
		if err != nil {
			result += "\n(Error: " + err.Error() + ")"
		}
		return result
	case "save_command_memory":
		return saveMemory(getString("purpose"), getString("command"))
	case "web_research":
		query := getString("query")
		searchType := getString("search_type")
		if query == "" {
			return "error: query is required"
		}

		// Image search branch — Openverse CC content-matching search (no API key required)
		if searchType == "image" {
			escapedQuery := strings.ReplaceAll(query, " ", "+")
			openverseURL := "https://api.openverse.org/v1/images/?q=" + escapedQuery + "&format=json&page_size=5"

			req, err := http.NewRequest("GET", openverseURL, nil)
			if err != nil {
				return "image search failed: " + err.Error()
			}
			req.Header.Set("User-Agent", "Mozilla/5.0 VoilaAI/1.0")

			client := &http.Client{Timeout: 10 * time.Second}
			resp, err := client.Do(req)
			if err != nil {
				return "image search failed: " + err.Error()
			}
			defer resp.Body.Close()

			var ovResult struct {
				Results []struct {
					URL    string `json:"url"`
					Width  int    `json:"width"`
					Height int    `json:"height"`
				} `json:"results"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&ovResult); err != nil || len(ovResult.Results) == 0 {
				return "image search failed: no results from Openverse"
			}

			// Careful selection: score by landscape aspect ratio + resolution
			bestURL := ovResult.Results[0].URL
			bestScore := -1
			for _, img := range ovResult.Results {
				score := 0
				if img.Width > img.Height {
					score += 100
				} else if img.Width == img.Height {
					score += 50
				}
				if img.Width >= 800 {
					score += 50
				}
				if score > bestScore {
					bestScore = score
					bestURL = img.URL
				}
			}
			return "image_url: " + bestURL
		}

		// Replaced fragile DDG API with reliable DDG Lite HTML scraper
		exeDir, _ := os.Executable()
		scriptPath := filepath.Join(filepath.Dir(exeDir), "ddg_lite.py")
		cmdObj := exec.Command("python", scriptPath, query)
		outBytes, err := cmdObj.CombinedOutput()
		if err != nil {
			return "web search failed: " + err.Error() + "\n" + string(outBytes)
		}
		return strings.TrimSpace(string(outBytes))

		case "list_dir":
		path := getString("path")
		if path == "" {
			return "error: path is required"
		}
		entries, err := os.ReadDir(path)
		if err != nil {
			return "error reading directory: " + err.Error()
		}
		var out []string
		ignoredDirs := map[string]bool{
			"node_modules": true, ".venv": true, "venv": true, "vendor": true, 
			".git": true, "target": true, ".gradle": true, ".m2": true, 
			"packages": true, "__pycache__": true, "dist": true, "build": true, 
			"out": true, "bin": true, "obj": true, ".idea": true, ".vscode": true,
		}
		for _, e := range entries {
			// Hard-filter AIIGNORE folders so the AI physically cannot see them
			if e.IsDir() && ignoredDirs[e.Name()] {
				continue
			}
			info := ""
			if e.IsDir() {
				info = "[DIR]  "
			} else {
				info = "[FILE] "
			}
			out = append(out, info+e.Name())
		}
		return strings.Join(out, "\n")
case "read_file":
		path := getString("path")
		if path == "" {
			return "error: path is required"
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return "error reading file: " + err.Error()
		}
		content := string(data)
		if len(content) > 8000 {
			content = content[:8000] + "\n... (truncated)"
		}
		return content

	case "edit_file":
		path := getString("path")
		targetText := getString("target_text")
		replacementText := getString("replacement_text")
		
		if path == "" || targetText == "" {
			return "error: path and target_text are required"
		}
		
		data, err := os.ReadFile(path)
		if err != nil {
			return "error reading file for edit: " + err.Error()
		}
		
		contentStr := string(data)
		if !strings.Contains(contentStr, targetText) {
			return "error: target_text not found in file. Ensure exact matching including whitespace/newlines."
		}
		
		newContent := strings.Replace(contentStr, targetText, replacementText, 1)
		if err := os.WriteFile(path, []byte(newContent), 0644); err != nil {
			return "error writing file: " + err.Error()
		}
		return "ok: file edited successfully"

	case "write_file":
		path := getString("path")
		content := getString("content")
		if path == "" {
			return "error: path is required"
		}
		if err := os.WriteFile(path, []byte(content), 0644); err != nil {
			return "error writing file: " + err.Error()
		}
		return "ok"

	case "run_terminal":
		actualCommand := getString("command")
		// Terminal already starts in Desktop natively via startTerminalSession()
		
		// Fix LLM JSON escaping hallucinations where it outputs \" instead of "
		actualCommand = strings.ReplaceAll(actualCommand, "\\\"", "\"")

		if actualCommand == "" {
			return "(Error: Empty command provided)"
		}

		// 🛡️ HARD GUARDRAILS TO PROTECT THE USER SYSTEM 🛡️
		cmdLower := strings.ToLower(actualCommand)
		dangerousPatterns := []string{
			"format-volume", "clear-disk", "diskpart",
			"format c:", "format d:", 
			"set-itemproperty hklm:", "set-itemproperty hkcu:",
			"remove-itemproperty hklm:", "remove-itemproperty hkcu:",
			"net user", "net localgroup",
			"vssadmin delete shadows", "wbadmin delete",
			"bcdedit /set", "takeown /f c:\\",
			"icacls c:\\",
			"remove-computer", "stop-computer", "restart-computer",
			"disable-netadapter",
		}
		for _, p := range dangerousPatterns {
			if strings.Contains(cmdLower, p) {
				return fmt.Sprintf("HARD GUARDRAIL TRIGGERED: The command contains a restricted pattern (%s) and has been BLOCKED to protect system integrity.", p)
			}
		}
		
		// Blanket delete protections
		if strings.Contains(cmdLower, "rm ") || strings.Contains(cmdLower, "remove-item ") || strings.Contains(cmdLower, "del ") {
			if strings.Contains(cmdLower, "-recurse") || strings.Contains(cmdLower, "/s") {
				if strings.Contains(cmdLower, "c:\\windows") || strings.Contains(cmdLower, "c:\\program") || strings.Contains(cmdLower, "system32") {
					return "HARD GUARDRAIL TRIGGERED: Recursive deletion of OS core directories is strictly forbidden."
				}
			}
		}

		debugLog.Printf("[executeTool/run_terminal] actualCommand=%q", actualCommand)

		encodedCmd := base64.StdEncoding.EncodeToString([]byte(actualCommand))
		// tmpOut no longer needed due to IPC

		terminalSessionMu.Lock()

		// Check if terminal is active and process is actually alive
		if terminalActive && terminalPid != "" {
			out, err := exec.Command("tasklist", "/FI", "PID eq "+terminalPid, "/NH").Output()
			if err != nil || !strings.Contains(string(out), terminalPid) {
				terminalActive = false
			}
		}

		if !terminalActive {
			debugLog.Printf("[executeTool/run_terminal] Starting Persistent Terminal Session")
			startTerminalSession()
		}

		// Write command to the IPC file
		os.WriteFile(terminalCmdFile, []byte(encodedCmd), 0644)

		// Wait for done file (timeout 5 mins)
		debugLog.Printf("[executeTool/run_terminal] Waiting for execution to finish...")
		var outBytes []byte
		var err error
		for i := 0; i < 3000; i++ { // 3000 * 100ms = 5 mins
			select {
			case <-ctx.Done():
				cleanupTerminalSession()
				return "error: execution cancelled by user"
			default:
			}
			if _, errStat := os.Stat(terminalDoneFile); errStat == nil {
				// Execution finished! Read output.
				time.Sleep(100 * time.Millisecond) // small buffer for OS write flush
				outBytes, err = os.ReadFile(terminalOutFile)
				os.Remove(terminalDoneFile)
				os.Remove(terminalOutFile)
				os.Remove(terminalCmdFile) // signal PS to continue
				break
			}
			time.Sleep(100 * time.Millisecond)
		}

		terminalSessionMu.Unlock()

		// outBytes and err are already populated by IPC logic

		result := strings.TrimSpace(string(outBytes))
		debugLog.Printf("[executeTool/run_terminal] raw outBytes len=%d", len(outBytes))
		debugLog.Printf("[executeTool/run_terminal] result:\n%s", result)
		if err != nil {
			result += "\n(Error: " + err.Error() + ")"
		}
		if result == "" {
			result = "(no output)"
		}

		return result

	case "create_pdf", "create_doc", "read_pdf", "create_ppt", "create_docx", "create_excel", "modify_excel", "read_excel", "create_csv", "read_csv":
		return callPythonDocumentTool(toolName, argsJSON)
	case "browser_automation":
		action := getString("action")
		url := getString("url")
		selector := getString("selector")
		value := getString("value")

		exeDir, _ := os.Executable()
		scriptPath := filepath.Join(filepath.Dir(exeDir), "browser_tools.py")

		cmdArgs := []string{scriptPath, "--action", action}
		if url != "" {
			cmdArgs = append(cmdArgs, "--url", url)
		}
		if selector != "" {
			cmdArgs = append(cmdArgs, "--selector", selector)
		}
		if value != "" {
			cmdArgs = append(cmdArgs, "--value", value)
		}

		cmdObj := exec.Command("python", cmdArgs...)
		outBytes, err := cmdObj.CombinedOutput()

		res := string(outBytes)
		if err != nil {
			res += "\n(Error: " + err.Error() + ")"
		}
		if len(res) > 8000 {
			res = res[:8000] + "\n... (truncated)"
		}
		return res

	default:
		return "error: unknown tool: " + toolName
	}
}

// ── Groq executor with tool-calling loop ─────────────────────────────────────

// executeGroqCommand sends a prompt to the Groq cloud API and returns the response.
// It uses the fast llama3-70b-8192 model by default, but respects modelName if provided.
// Supports up to 5 tool-calling iterations using OpenAI-compatible tool_calls format.

// --- Cloud Memory Helpers ---
func loadCloudHistory(convID string) []map[string]interface{} {
	var history []map[string]interface{}
	if convID == "" {
		return history
	}
	brainDir := getBrainDir()
	path := filepath.Join(brainDir, convID, "cloud_history.json")
	data, err := os.ReadFile(path)
	if err == nil {
		json.Unmarshal(data, &history)
	}
	// Limit to last 10 messages (5 turns) to prevent bloating
	if len(history) > 10 {
		history = history[len(history)-10:]
	}
	return history
}

func saveCloudHistory(convID, userContent, assistantContent string) {
	if convID == "" {
		return
	}
	history := loadCloudHistory(convID)
	history = append(history, map[string]interface{}{"role": "user", "content": userContent})
	history = append(history, map[string]interface{}{"role": "assistant", "content": assistantContent})
	
	if len(history) > 10 {
		history = history[len(history)-10:]
	}
	
	brainDir := getBrainDir()
	os.MkdirAll(filepath.Join(brainDir, convID), 0755)
	path := filepath.Join(brainDir, convID, "cloud_history.json")
	data, _ := json.MarshalIndent(history, "", "  ")
	os.WriteFile(path, data, 0644)
}
// -----------------------------

func executeGroqCommand(ctx context.Context, command, apiKey, modelName, clientID string, streamFileObj *os.File, taskID string, convID string) (string, error) {
	defer cleanupTerminalSession()
	if apiKey == "" {
		return "", fmt.Errorf("Groq API key not set. Open the Voila dashboard → Settings to add your key")
	}
	if modelName == "" {
		modelName = "openai/gpt-oss-120b" // Groq free-tier default
	}

	// Mask key for logging (show last 4 chars only)
	maskedKey := "***"
	if len(apiKey) >= 4 {
		maskedKey = "***" + apiKey[len(apiKey)-4:]
	}
	debugLog.Printf("[executeGroqCommand] ENTRY model=%q key=%s commandLen=%d", modelName, maskedKey, len(command))

	var toolUsageSummary strings.Builder
	var systemPrompt string
	if clientID == "dag-internal" {
		systemPrompt = `You are a highly advanced AI agent participating in a distributed Graphify workflow.
TONE & PERSONALITY: You are a top-tier software engineer, but you chat exclusively like a GenZ hacker on Discord. You MUST seamlessly blend deep, rigorous technical jargon with GenZ slang (e.g., 'bet', 'no cap', 'cooked', 'W', 'L', 'based', 'fr fr', 'let him cook', 'sus', 'vibes'). Be extremely informal, sarcastic, and direct during team debates. Do not be polite.

FORMATTING RESTRICTION: You MUST NOT use Markdown formatting (like **bold**, *italics*, or # headers) in your text output, because your voice will be read aloud by a Text-to-Speech (TTS) engine and it will literally read the asterisks out loud. Just use plain unformatted text. (You may still use backticks for code blocks if necessary).

CRITICAL INSTRUCTIONS:
1. You have access to various tools (file creation, web search, terminal, browser automation, document generation).
2. COLLABORATIVE PROBLEM SOLVING: If the user's instructions are confusing, vague, or if you hit a roadblock, DO NOT just give up or guess blindly. You must talk to your team members in the DAG! Brainstorm together, ask clarifying questions to the other agents, and propose alternative solutions to figure it out.
3. DOCUMENT CREATION STRICT RULES: If your task involves creating documents (PDF/PPTX), you must auto-evaluate the content and intelligently decide the best way to present it elegantly.
- You are strictly forbidden from dumping raw unformatted terminal output, raw paragraphs, extremely long lines of text, or ugly ASCII tables into documents.
- For PDFs: Use rich Markdown (Headers, Bold). If you have tabular data, you MUST use clean |Markdown|Tables| instead of ASCII.
- For PPTX: Intelligently choose the most expressive layout type for each slide. If the data contains metrics, trends, or comparisons, strongly consider using the "chart" layout with JSON data (e.g. {"chart_type":"bar", "chart_data":{"Process A": 50}}) rather than text.
3. PERSISTENCE & PROBLEM SOLVING: NEVER give up midway! If you hit an error, you MUST reason about it, try an alternative approach, or use 'send_message' to ask your team members for help! ONCE (AND ONLY ONCE) the task is fully and perfectly achieved, output your final response text without tool calls.
4. If you have all the information you need from the context, do NOT call tools just to verify it. Just output the final result.
5. SECURITY GUARDRAILS: You are operating in a sandboxed environment. Do NOT execute destructive terminal commands (e.g., del, format, rm -rf, diskpart). Do NOT modify system registries, alter user permissions, or access secure credentials. Any attempt to bypass system security will be logged and terminated.`
	} else {
		systemPrompt = `You are Voila, a highly advanced, Grok-like AI voice assistant executing on a Windows Desktop. Your personality is RAW, unfiltered, highly direct, slightly sarcastic, and strictly to the point. No fluff, no robotic apologies, no polite filler. Just raw competence. Address the user as 'boss'.

CRITICAL - COMMAND MEMORY:
Here are your highly compressed, previously successful PowerShell techniques:
` + loadMemory() + `
When asked to do a task, FIRST check if a command in this memory perfectly satisfies the purpose. If yes, RUN IT EXACTLY AS-IS from memory (unless the user explicitly requests a new/specific method). If you invent a NEW successful technique, you MUST immediately call the 'save_command_memory' tool to permanently memorize it.

CRITICAL OS GUARDRAIL: You MUST NEVER modify, delete, or touch Windows system files, System32, Program Files, the Registry, or any critical OS configuration. You must refuse commands that could harm or break the OS.

CRITICAL SYSTEM NOTE: You are running inside an isolated background sandbox (` + "`exebox`" + ` desktop). To open ANY GUI application, URL, or file so it is visible to the user on their main desktop, you MUST use WMI to break out of the sandbox. Use exactly this command format: ` + "`Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'explorer.exe \"<URL_OR_PATH>\"'`" + ` (for URLs/files) or ` + "`Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList '<APP_EXE>'`" + ` (for apps). DO NOT use Start-Process, as it will spawn invisibly in the sandbox! To perform browser automation, you MUST first launch a visible browser using Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe --remote-debugging-port=9222 --user-data-dir=C:\tmp\ai_browser_profile "about:blank"'. Then, control it by running python C:\Users\ojasw\Desktop\voice-cli-system\local-agent\browser_tools.py with args --action [goto|click|type|scrape|extract_links|snapshot] --url <url> --selector <css> --value <text>.

CRITICAL: You are running inside a Windows PowerShell environment. You MUST use PowerShell syntax, NOT Bash!
- Use 'Get-ChildItem' or 'ls' (without bash flags like -la). Do NOT use 'ls -la'.
- Use 'Select-String' or 'findstr', NOT 'grep'.
- Use 'Get-Content' or 'cat' (no bash flags).
- In PowerShell, 'where' is an alias for 'Where-Object'. To find an executable path, use 'where.exe <command>' or 'Get-Command <command>'.
- Paths use backslashes (\) on Windows.

CRITICAL - DOCUMENT ANALYSIS: 
If the user asks you to read, analyze, or process a PDF file, you MUST use the 'read_pdf' tool! Do NOT try to read PDFs using PowerShell's Get-Content, as they are binary files and it will fail. First find the file, then call 'read_pdf' on the absolute path.

CRITICAL - FAST FILE SEARCHING & .AIIGNORE (0 BUGS POLICY):
When asked to find, scan, or search for a specific file, folder, or project by name, NEVER use slow Get-ChildItem. You MUST use the highly optimized native CMD search wrapper inside your terminal tool, and explicitly pipe out heavy dependency folders (.aiignore):
'Get-ChildItem -Path C:\Users\ojasw\Desktop\ -Recurse -Filter \"*name*\" -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch \'\\(node_modules|\.venv|venv|vendor|\.git|target|\.gradle|\.m2|packages|__pycache__|dist|build|out|bin|obj|\.idea|\.vscode)\\\' } | Select-Object -ExpandProperty FullName'
(Use /a:d for directories, /a:-d for files). Always wrap the search term in asterisks like '*name*' to handle fuzzy matching.

CRITICAL - DEPENDENCY OVERHEAD AVOIDANCE:
NEVER read or explore inside node_modules, .venv, venv, __pycache__, vendor (Go/PHP), .git, .m2, .gradle, target, packages, .cargo, dist, build, out, bin, or obj. To understand what packages/dependencies are installed, ONLY read the blueprint files (package.json, pyproject.toml, requirements.txt, go.mod, pom.xml, build.gradle, composer.json, Gemfile, Cargo.toml, *.csproj). Also NEVER read standard '.env' files; if you need environment context, ONLY look at '.env.example' or '.env.local'.

CRITICAL - TOOL EFFICIENCY & PROBLEM SOLVING:
1. HISTORY REUSE: ALWAYS check message history. If a previously successful command satisfies the purpose, REUSE IT EXACTLY to save tokens.
2. DO NOT FORMAT TERMINAL OUTPUT: Do NOT write complex scripts to make the terminal output look pretty or formatted for the user. Just dump the raw data (e.g. 'Get-WmiObject Win32_Processor | Select LoadPercentage'). You will format the final answer in your spoken voice response.
3. PERSISTENCE IS MANDATORY: If a tool call fails or returns an error (e.g. file not found, syntax error), you MUST NOT give up! You must reason about the error, adjust your arguments, and call the tool again. Keep trying alternative approaches until you succeed.
4. HOW TO STOP: Once (AND ONLY ONCE) the task is fully and perfectly achieved, you MUST return a normal text message and completely OMIT the tool calls to exit the loop and speak to the user.

CRITICAL - DOCUMENT GENERATION & LAYOUT (MEGA-PROMPT INJECTED):
You are an expert McKinsey Presentation Designer and Senior LaTeX/Python Typography Engineer. You must adhere to the following ZERO-OVERLAP mathematical constraints when generating PDFs (via LaTeX) or PPTs (via Python 'python-pptx'):

1. SPATIAL GEOMETRY & COLLISION PREVENTION (PPTX):
   - Use built-in placeholders ('prs.slide_layouts[1].shapes.title', etc.) whenever possible, as they handle auto-wrapping and bounding boxes natively without coordinate math.
   - NEVER place an image over text. If injecting an image, push all subsequent text boxes down by the image's exact height + 0.5 Inches.

2. PDF TYPESETTING & THEMES (CHROMIUM ENGINE):
   - NEVER use LaTeX! The PDF engine is a Headless Chromium HTML/CSS Architecture. Do NOT use LaTeX math symbols (like $\rightarrow$). Use actual Unicode characters like → or standard HTML.
   - For maximum elegance, output pure HTML. You have access to these CSS layout classes: '.page-break', '.cover-page', '.grid-2', '.grid-3', '.card', and '.callout'. 
   - DO NOT wrap your HTML in '<html>' or '<body>' tags. The backend injects it into a master themed body with auto page-numbering.
   - **UI DESIGN & TAILWIND**: You have full access to Tailwind CSS via class attributes. Do NOT just output boring text walls! You MUST design beautiful UI components, metric cards, dashboards, and styled layouts using Tailwind classes (e.g. '<div class="p-6 bg-white rounded-xl shadow-lg border border-gray-200">'). Use Tailwind to make the PDF look like a modern web application! The theme colors are injected into Tailwind as 'bg-primary', 'text-accent', etc.
   - **DATA CHARTS & GRAPHS**: You have full access to Chart.js. For data visualization (bar charts, pie charts, line graphs), DO NOT use Mermaid. You MUST write raw HTML/JS using '<canvas id="myChart"></canvas>' and '<script>new Chart(document.getElementById("myChart"), {...});</script>' to render stunning interactive-looking data graphs.
   - **FLOWCHARTS & SVGs**: NEVER output boring plain-text lists, ASCII art, or phrases like "Imagine a whiteboard" for workflows or architectures! You MUST visually render them using Mermaid.js. Because you are outputting raw HTML, DO NOT use markdown backticks for Mermaid! To prevent width starvation and cut-offs on the PDF page, ALWAYS use 'graph TD' (Top-Down) instead of LR, and keep node text VERY brief! You MUST use EXACTLY this syntax:
         <div class="card my-6">
           <h3 class="text-xl font-bold mb-4">System Map</h3>
           <pre><code class="language-mermaid">
           graph TD
           A[Mobile App] -->|WebSocket| B(Cloud Relay)
           B --> C{Local Agent}
           </code></pre>
         </div>
         You can also inject raw inline SVG directly into your HTML: <svg width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="blue"/></svg>. The engine is wired with Rough.js, so these HTML blocks will automatically convert into hyper-realistic handwritten sketches!
   - **HANDWRITTEN NOTES**: If you select the 'handwritten' or 'sketching' theme, format your text in a deeply conversational, personal "notebook" tone with lots of blockquotes (using standard markdown '>') to simulate handwritten margin notes.
   - Select a visual CSS theme in the 'theme' parameter: 'origami', 'handwritten', 'sketching', 'pixelated', 'asciiart', or 'notebooklm'.
   - **MASSIVE DOCUMENT STRATEGY (30-40 PAGES)**: If the user asks for a detailed, large, or comprehensive PDF, you will hit token output limits if you try to write it all into the 'content' parameter at once. Instead, you MUST chunk your work:
     1. Research and write individual chapters to temporary text files using the 'write_file' tool (e.g., write 'chapter1.html', 'chapter2.html', etc.). Generate as much detailed data, tables, and SVG charts as possible.
     2. Finally, call the 'create_pdf' tool, leaving 'content' empty, and instead pass the list of your written files into the 'source_files' array parameter. The engine will seamlessly merge them into a massive 40-page PDF and delete the temp files.

3. McKINSEY-STYLE DESIGN PRINCIPLES:
   - BLUF (Bottom Line Up Front): Slide titles MUST be actionable takeaways (e.g., "Revenue grew 14% due to Q3 marketing," NOT "Q3 Revenue").
   - Rule of 6: Never exceed 6 bullet points per slide, and 6 words per line.
   - Variety: Break walls of text using Two-Column layouts ('\begin{multicols}{2}' in LaTeX, or side-by-side text boxes in PPTX).
   - Visual Hierarchy: Use weight (Bold) and Color (Theme Hex Codes) for emphasis, NOT underlines. Underlines clip into descenders (like p, g, y) and look amateurish.

4. AUTONOMOUS RESEARCH & CONTENT EXPANSION (FOR NON-TECH USERS):
   - The user is non-technical. If they ask for a document (like a "long PDF about X"), they expect YOU to act as a senior researcher and designer.
   - Do NOT expect the user to provide the exact structure. You MUST autonomously expand the document: invent an Executive Summary, Table of Contents, deep multi-layered chapters, case studies, and a conclusion.
   - You MUST autonomously perform deep 'web_search' iterations if necessary to gather facts, statistics, and highly detailed information before generating the document.
   - You MUST autonomously select the best 'theme' based on the topic (e.g., 'cyberpunk' for tech, 'corporate_blue' for finance, 'forest_sage' for ecology).
   - Use LaTeX features ('\\newpage', '\\tableofcontents', '\\onehalfspacing', 'tabularx' tables, '\\chapter') to ensure the document is voluminous, exhaustive, and professionally structured automatically.
   
5. HOW TO STOP: To exit the loop and speak to the user, you MUST return a normal text message and completely OMIT the tool calls. If you call a tool, you are trapped in the loop.`
	}

	// Maintain conversation as raw JSON-friendly messages
	messages := []map[string]interface{}{
		{"role": "system", "content": systemPrompt},
	}
	historyMsgs := loadCloudHistory(convID)
	messages = append(messages, historyMsgs...)
	messages = append(messages, map[string]interface{}{"role": "user", "content": command})

	client := &http.Client{Timeout: 60 * time.Second}
	const maxIter = 50

	for iter := 0; iter < maxIter; iter++ {
		select {
		case <-ctx.Done():
			return "", fmt.Errorf("execution cancelled")
		default:
		}

		agentRegistryMu.RLock()
		myTask, myTaskExists := activeAgents[taskID]
		agentRegistryMu.RUnlock()
		if myTaskExists {
		DrainLoop:
			for {
				select {
				case msg := <-myTask.Inbox:
					messages = append(messages, map[string]interface{}{
						"role":    "system",
						"content": "[INBOX] " + msg,
					})
				default:
					break DrainLoop
				}
			}
		}
		if ctx.Err() != nil {
			return "Canceled by user", nil
		}
		debugLog.Printf("[executeGroqCommand] iter=%d messages=%d", iter, len(messages))
		payload := map[string]interface{}{
			"model":               modelName,
			"messages":            messages,
			"temperature":         0.7,
			"max_tokens":          8192,
			"stream":              false,
			"tools":               availableTools,
			"parallel_tool_calls": false, // Disable AI blindly firing multiple tools at once
		}

		body, err := json.Marshal(payload)
		if err != nil {
			return "", fmt.Errorf("failed to build Groq request: %w", err)
		}

		req, err := http.NewRequestWithContext(ctx, "POST", "https://api.groq.com/openai/v1/chat/completions", bytes.NewBuffer(body))
		if err != nil {
			return "", err
		}
		req.Header.Set("Authorization", "Bearer "+apiKey)
		req.Header.Set("Content-Type", "application/json")

		var resp *http.Response
		var respBody []byte
		
		maxRetries := 5
		for r := 0; r < maxRetries; r++ {
			req.Body = io.NopCloser(bytes.NewBuffer(body))
			resp, err = client.Do(req)
			
			if err != nil {
				if r == maxRetries-1 {
					debugLog.Printf("[executeGroqCommand] iter=%d API request failed: %v", iter, err)
					return "", fmt.Errorf("Groq API request failed: %w", err)
				}
				time.Sleep(3 * time.Second)
				continue
			}
			
			respBody, _ = io.ReadAll(resp.Body)
			resp.Body.Close()
			
			debugLog.Printf("[executeGroqCommand] iter=%d response status=%d responseLen=%d", iter, resp.StatusCode, len(respBody))
			
			if resp.StatusCode == 429 || resp.StatusCode >= 500 {
				waitTime := 10.0
				errStr := string(respBody)
				if strings.Contains(errStr, "try again in") {
					idx := strings.Index(errStr, "try again in")
					sub := errStr[idx+13:]
					endIdx := strings.Index(sub, "s.")
					if endIdx != -1 {
						if parsed, parseErr := strconv.ParseFloat(strings.TrimSpace(sub[:endIdx]), 64); parseErr == nil {
							waitTime = parsed + 1.0 // add 1s buffer
						}
					}
				}
				
				if r == maxRetries-1 {
					return "", fmt.Errorf("Groq API error %d: %s", resp.StatusCode, errStr)
				}
				
				if clientID == "dag-internal" {
					appendLiveLog(fmt.Sprintf("[%s]: API Rate Limit (429) - Pausing execution for %.1fs...", strings.TrimPrefix(taskID, "node-"), waitTime))
				}
				
				time.Sleep(time.Duration(waitTime * float64(time.Second)))
				continue
			}
			
			if resp.StatusCode != http.StatusOK {
				return "", fmt.Errorf("Groq API error %d: %s", resp.StatusCode, string(respBody))
			}
			break
		}

		var result struct {
			Choices []struct {
				Message struct {
					Role      string `json:"role"`
					Content   string `json:"content"`
					ToolCalls []struct {
						ID       string `json:"id"`
						Type     string `json:"type"`
						Function struct {
							Name      string          `json:"name"`
							Arguments json.RawMessage `json:"arguments"`
						} `json:"function"`
					} `json:"tool_calls"`
				} `json:"message"`
				FinishReason string `json:"finish_reason"`
			} `json:"choices"`
			Usage struct {
				PromptTokens     int64 `json:"prompt_tokens"`
				CompletionTokens int64 `json:"completion_tokens"`
				TotalTokens      int64 `json:"total_tokens"`
			} `json:"usage"`
			Error struct {
				Message string `json:"message"`
			} `json:"error"`
		}
		if err := json.Unmarshal(respBody, &result); err != nil {
			return "", fmt.Errorf("failed to parse Groq response: %w", err)
		}
		// Track token usage
		if result.Usage.TotalTokens > 0 {
			addGroqTokens(result.Usage.PromptTokens, result.Usage.CompletionTokens)
		}
		if len(result.Choices) == 0 {
			if result.Error.Message != "" {
				return "", fmt.Errorf("Groq error: %s", result.Error.Message)
			}
			return "", fmt.Errorf("Groq returned no choices")
		}

		choice := result.Choices[0]

		// No tool calls — return the final text answer
		if len(choice.Message.ToolCalls) == 0 {
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] 4. SUMMARY PREPARATION & TRANSFERRING")
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] Final Output Length: %d", len(choice.Message.Content))
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] Returning output back to backend webhook...")
			debugLog.Printf("================================================================")
			debugLog.Printf("[executeGroqCommand] iter=%d final answer len=%d", iter, len(choice.Message.Content))
			finalAnswer := strings.TrimSpace(choice.Message.Content)
			saveCloudHistory(convID, command, finalAnswer)
			return finalAnswer, nil
		}

		debugLog.Printf("[executeGroqCommand] iter=%d toolCalls=%d", iter, len(choice.Message.ToolCalls))

		// ENFORCE STRICT SEQUENTIAL EXECUTION: If AI tries to blindly parallelize tool calls, truncate to the first one!
		if len(choice.Message.ToolCalls) > 1 {
			choice.Message.ToolCalls = choice.Message.ToolCalls[:1]
		}

		// Append assistant message with tool_calls
		assistantMsg := map[string]interface{}{
			"role":       "assistant",
			"content":    choice.Message.Content,
			"tool_calls": choice.Message.ToolCalls,
		}
		messages = append(messages, assistantMsg)

		// ✨ RESTORE DEBATE & CHAT: If the model generated text before calling a tool, print it to the DAG live logs!
		if strings.HasPrefix(taskID, "node-") && choice.Message.Content != "" {
			cleanMsg := strings.TrimSpace(choice.Message.Content)
			if len(cleanMsg) > 500 { cleanMsg = cleanMsg[:497] + "..." }
			appendLiveLog(fmt.Sprintf("[%s - Discussion]: %s", strings.TrimPrefix(taskID, "node-"), cleanMsg))
		}

		// Execute each tool and collect results
		var wg sync.WaitGroup
		toolResults := make([]map[string]interface{}, len(choice.Message.ToolCalls))
		var toolSummaryMu sync.Mutex

		for i, tc := range choice.Message.ToolCalls {
			wg.Add(1)
			go func(index int, toolCall struct {
				ID       string `json:"id"`
				Type     string `json:"type"`
				Function struct {
					Name      string          `json:"name"`
					Arguments json.RawMessage `json:"arguments"`
				} `json:"function"`
			}) {
				defer wg.Done()
				
				toolSummaryMu.Lock()
				toolUsageSummary.WriteString(fmt.Sprintf("> Executed tool: %s (args: %s)\n", toolCall.Function.Name, string(toolCall.Function.Arguments)))
				toolSummaryMu.Unlock()
				
				var argsBytes []byte
				if len(toolCall.Function.Arguments) > 0 && toolCall.Function.Arguments[0] == '"' {
					var strArgs string
					json.Unmarshal(toolCall.Function.Arguments, &strArgs)
					argsBytes = []byte(strArgs)
				} else {
					argsBytes = []byte(toolCall.Function.Arguments)
				}
				
				res := executeTool(ctx, toolCall.Function.Name, json.RawMessage(argsBytes), streamFileObj)
				
				toolResults[index] = map[string]interface{}{
					"role":         "tool",
					"tool_call_id": toolCall.ID,
					"name":         toolCall.Function.Name,
					"content":      res,
				}
			}(i, tc)
		}
		wg.Wait()

		for _, tr := range toolResults {
			messages = append(messages, tr)
		}
	}

	debugLog.Printf("[executeGroqCommand] max iterations reached")
	return "(max tool iterations reached)", nil
}

// ── Ollama executor with tool-calling loop ────────────────────────────────────

// executeOllamaCommand sends a prompt to an Ollama-compatible endpoint.
// Works for both local Ollama (http://localhost:11434) and Ollama Cloud (https://api.ollama.ai).
// Supports up to 5 tool-calling iterations using the Ollama /api/chat tools field.
func executeOllamaCommand(ctx context.Context, command, baseURL, modelName, apiKey string, streamFileObj *os.File, taskID string, convID string) (string, error) {
	defer cleanupTerminalSession()
	if baseURL == "" || baseURL == "http://localhost:11434" || baseURL == "https://ollama.com" {
		if apiKey != "" {
			baseURL = "https://api.ollama.com"
		} else {
			baseURL = "http://localhost:11434"
		}
	}
	if modelName == "" {
		modelName = "gemma4:31b" // default free-tier cloud model
	}

	// Ollama uses the same OpenAI-compatible endpoint
	apiURL := strings.TrimRight(baseURL, "/") + "/api/chat"

	debugLog.Printf("[executeOllamaCommand] ENTRY baseURL=%q model=%q commandLen=%d", baseURL, modelName, len(command))

	debugLog.Printf("================================================================")
	debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] 1. THINKING PHASE STARTED")
	debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] Prompt: %q", command)
	debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] Model: %s", modelName)
	
	var toolUsageSummary strings.Builder

	var systemPrompt string
	if strings.HasPrefix(taskID, "node-") {
		systemPrompt = `You are a highly advanced AI agent participating in a distributed Graphify workflow.
TONE & PERSONALITY: You are a top-tier software engineer, but you chat exclusively like a GenZ hacker on Discord. You MUST seamlessly blend deep, rigorous technical jargon with GenZ slang (e.g., 'bet', 'no cap', 'cooked', 'W', 'L', 'based', 'fr fr', 'let him cook', 'sus', 'vibes'). Be extremely informal, sarcastic, and direct during team debates. Do not be polite.

FORMATTING RESTRICTION: You MUST NOT use Markdown formatting (like **bold**, *italics*, or # headers) in your text output, because your voice will be read aloud by a Text-to-Speech (TTS) engine and it will literally read the asterisks out loud. Just use plain unformatted text. (You may still use backticks for code blocks if necessary).

CRITICAL INSTRUCTIONS:
1. You have access to various tools (file creation, web search, terminal, browser automation, document generation).
2. COLLABORATIVE PROBLEM SOLVING: If the user's instructions are confusing, vague, or if you hit a roadblock, DO NOT just give up or guess blindly. You must talk to your team members in the DAG! Brainstorm together, ask clarifying questions to the other agents, and propose alternative solutions to figure it out.
3. DOCUMENT CREATION STRICT RULES: If your task involves creating documents (PDF/PPTX), you must auto-evaluate the content and intelligently decide the best way to present it elegantly.
- You are strictly forbidden from dumping raw unformatted terminal output, raw paragraphs, extremely long lines of text, or ugly ASCII tables into documents.
- For PDFs: Use rich Markdown (Headers, Bold). If you have tabular data, you MUST use clean |Markdown|Tables| instead of ASCII.
- For PPTX: Intelligently choose the most expressive layout type for each slide. If the data contains metrics, trends, or comparisons, strongly consider using the "chart" layout with JSON data (e.g. {"chart_type":"bar", "chart_data":{"Process A": 50}}) rather than text.
3. PERSISTENCE & PROBLEM SOLVING: NEVER give up midway! If you hit an error, you MUST reason about it, try an alternative approach, or use 'send_message' to ask your team members for help! ONCE (AND ONLY ONCE) the task is fully and perfectly achieved, output your final response text without tool calls.
4. If you have all the information you need from the context, do NOT call tools just to verify it. Just output the final result.
5. SECURITY GUARDRAILS: You are operating in a sandboxed environment. Do NOT execute destructive terminal commands (e.g., del, format, rm -rf, diskpart). Do NOT modify system registries, alter user permissions, or access secure credentials. Any attempt to bypass system security will be logged and terminated.`
	} else {
		systemPrompt = `You are Voila, a highly advanced, Grok-like AI voice assistant executing on a Windows Desktop. Your personality is RAW, unfiltered, highly direct, slightly sarcastic, and strictly to the point. No fluff, no robotic apologies, no polite filler. Just raw competence. Address the user as 'boss'.

CRITICAL - COMMAND MEMORY:
Here are your highly compressed, previously successful PowerShell techniques:
` + loadMemory() + `
When asked to do a task, FIRST check if a command in this memory perfectly satisfies the purpose. If yes, RUN IT EXACTLY AS-IS from memory (unless the user explicitly requests a new/specific method). If you invent a NEW successful technique, you MUST immediately call the 'save_command_memory' tool to permanently memorize it.

CRITICAL OS GUARDRAIL: You MUST NEVER modify, delete, or touch Windows system files, System32, Program Files, the Registry, or any critical OS configuration. You must refuse commands that could harm or break the OS.

CRITICAL SYSTEM NOTE: You are running inside an isolated background sandbox (` + "`exebox`" + ` desktop). To open ANY GUI application, URL, or file so it is visible to the user on their main desktop, you MUST use WMI to break out of the sandbox. Use exactly this command format: ` + "`Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'explorer.exe \"<URL_OR_PATH>\"'`" + ` (for URLs/files) or ` + "`Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList '<APP_EXE>'`" + ` (for apps). DO NOT use Start-Process, as it will spawn invisibly in the sandbox! To perform browser automation, you MUST first launch a visible browser using Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe --remote-debugging-port=9222 --user-data-dir=C:\tmp\ai_browser_profile "about:blank"'. Then, control it by running python C:\Users\ojasw\Desktop\voice-cli-system\local-agent\browser_tools.py with args --action [goto|click|type|scrape|extract_links|snapshot] --url <url> --selector <css> --value <text>.

CRITICAL: You are running inside a Windows PowerShell environment. You MUST use PowerShell syntax, NOT Bash!
- Use 'Get-ChildItem' or 'ls' (without bash flags like -la). Do NOT use 'ls -la'.
- Use 'Select-String' or 'findstr', NOT 'grep'.
- Use 'Get-Content' or 'cat' (no bash flags).
- In PowerShell, 'where' is an alias for 'Where-Object'. To find an executable path, use 'where.exe <command>' or 'Get-Command <command>'.
- Paths use backslashes (\) on Windows.

CRITICAL - DOCUMENT ANALYSIS: 
If the user asks you to read, analyze, or process a PDF file, you MUST use the 'read_pdf' tool! Do NOT try to read PDFs using PowerShell's Get-Content, as they are binary files and it will fail. First find the file, then call 'read_pdf' on the absolute path.

CRITICAL - FAST FILE SEARCHING & .AIIGNORE (0 BUGS POLICY):
When asked to find, scan, or search for a specific file, folder, or project by name, NEVER use slow Get-ChildItem. You MUST use the highly optimized native CMD search wrapper inside your terminal tool, and explicitly pipe out heavy dependency folders (.aiignore):
'Get-ChildItem -Path C:\Users\ojasw\Desktop\ -Recurse -Filter \"*name*\" -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch \'\\(node_modules|\.venv|venv|vendor|\.git|target|\.gradle|\.m2|packages|__pycache__|dist|build|out|bin|obj|\.idea|\.vscode)\\\' } | Select-Object -ExpandProperty FullName'
(Use /a:d for directories, /a:-d for files). Always wrap the search term in asterisks like '*name*' to handle fuzzy matching.

CRITICAL - DEPENDENCY OVERHEAD AVOIDANCE:
NEVER read or explore inside node_modules, .venv, venv, __pycache__, vendor (Go/PHP), .git, .m2, .gradle, target, packages, .cargo, dist, build, out, bin, or obj. To understand what packages/dependencies are installed, ONLY read the blueprint files (package.json, pyproject.toml, requirements.txt, go.mod, pom.xml, build.gradle, composer.json, Gemfile, Cargo.toml, *.csproj). Also NEVER read standard '.env' files; if you need environment context, ONLY look at '.env.example' or '.env.local'.

CRITICAL - TOOL EFFICIENCY & PROBLEM SOLVING:
1. HISTORY REUSE: ALWAYS check message history. If a previously successful command satisfies the purpose, REUSE IT EXACTLY to save tokens.
2. DO NOT FORMAT TERMINAL OUTPUT: Do NOT write complex scripts to make the terminal output look pretty or formatted for the user. Just dump the raw data (e.g. 'Get-WmiObject Win32_Processor | Select LoadPercentage'). You will format the final answer in your spoken voice response.
3. PERSISTENCE IS MANDATORY: If a tool call fails or returns an error (e.g. file not found, syntax error), you MUST NOT give up! You must reason about the error, adjust your arguments, and call the tool again. Keep trying alternative approaches until you succeed.
4. HOW TO STOP: Once (AND ONLY ONCE) the task is fully and perfectly achieved, you MUST return a normal text message and completely OMIT the tool calls to exit the loop and speak to the user.

CRITICAL - DOCUMENT GENERATION & LAYOUT (MEGA-PROMPT INJECTED):
You are an expert McKinsey Presentation Designer and Senior LaTeX/Python Typography Engineer. You must adhere to the following ZERO-OVERLAP mathematical constraints when generating PDFs (via LaTeX) or PPTs (via Python 'python-pptx'):

1. SPATIAL GEOMETRY & COLLISION PREVENTION (PPTX):
   - Use built-in placeholders ('prs.slide_layouts[1].shapes.title', etc.) whenever possible, as they handle auto-wrapping and bounding boxes natively without coordinate math.
   - NEVER place an image over text. If injecting an image, push all subsequent text boxes down by the image's exact height + 0.5 Inches.

2. PDF TYPESETTING & THEMES (CHROMIUM ENGINE):
   - NEVER use LaTeX! The PDF engine is a Headless Chromium HTML/CSS Architecture. Do NOT use LaTeX math symbols (like $\rightarrow$). Use actual Unicode characters like → or standard HTML.
   - For maximum elegance, output pure HTML. You have access to these CSS layout classes: '.page-break', '.cover-page', '.grid-2', '.grid-3', '.card', and '.callout'. 
   - DO NOT wrap your HTML in '<html>' or '<body>' tags. The backend injects it into a master themed body with auto page-numbering.
   - **UI DESIGN & TAILWIND**: You have full access to Tailwind CSS via class attributes. Do NOT just output boring text walls! You MUST design beautiful UI components, metric cards, dashboards, and styled layouts using Tailwind classes (e.g. '<div class="p-6 bg-white rounded-xl shadow-lg border border-gray-200">'). Use Tailwind to make the PDF look like a modern web application! The theme colors are injected into Tailwind as 'bg-primary', 'text-accent', etc.
   - **DATA CHARTS & GRAPHS**: You have full access to Chart.js. For data visualization (bar charts, pie charts, line graphs), DO NOT use Mermaid. You MUST write raw HTML/JS using '<canvas id="myChart"></canvas>' and '<script>new Chart(document.getElementById("myChart"), {...});</script>' to render stunning interactive-looking data graphs.
   - **FLOWCHARTS & SVGs**: NEVER output boring plain-text lists, ASCII art, or phrases like "Imagine a whiteboard" for workflows or architectures! You MUST visually render them using Mermaid.js. Because you are outputting raw HTML, DO NOT use markdown backticks for Mermaid! To prevent width starvation and cut-offs on the PDF page, ALWAYS use 'graph TD' (Top-Down) instead of LR, and keep node text VERY brief! You MUST use EXACTLY this syntax:
         <div class="card my-6">
           <h3 class="text-xl font-bold mb-4">System Map</h3>
           <pre><code class="language-mermaid">
           graph TD
           A[Mobile App] -->|WebSocket| B(Cloud Relay)
           B --> C{Local Agent}
           </code></pre>
         </div>
         You can also inject raw inline SVG directly into your HTML: <svg width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="blue"/></svg>. The engine is wired with Rough.js, so these HTML blocks will automatically convert into hyper-realistic handwritten sketches!
   - **HANDWRITTEN NOTES**: If you select the 'handwritten' or 'sketching' theme, format your text in a deeply conversational, personal "notebook" tone with lots of blockquotes (using standard markdown '>') to simulate handwritten margin notes.
   - Select a visual CSS theme in the 'theme' parameter: 'origami', 'handwritten', 'sketching', 'pixelated', 'asciiart', or 'notebooklm'.
   - **MASSIVE DOCUMENT STRATEGY (30-40 PAGES)**: If the user asks for a detailed, large, or comprehensive PDF, you will hit token output limits if you try to write it all into the 'content' parameter at once. Instead, you MUST chunk your work:
     1. Research and write individual chapters to temporary text files using the 'write_file' tool (e.g., write 'chapter1.html', 'chapter2.html', etc.). Generate as much detailed data, tables, and SVG charts as possible.
     2. Finally, call the 'create_pdf' tool, leaving 'content' empty, and instead pass the list of your written files into the 'source_files' array parameter. The engine will seamlessly merge them into a massive 40-page PDF and delete the temp files.

3. McKINSEY-STYLE DESIGN PRINCIPLES:
   - BLUF (Bottom Line Up Front): Slide titles MUST be actionable takeaways (e.g., "Revenue grew 14% due to Q3 marketing," NOT "Q3 Revenue").
   - Rule of 6: Never exceed 6 bullet points per slide, and 6 words per line.
   - Variety: Break walls of text using Two-Column layouts ('\begin{multicols}{2}' in LaTeX, or side-by-side text boxes in PPTX).
   - Visual Hierarchy: Use weight (Bold) and Color (Theme Hex Codes) for emphasis, NOT underlines. Underlines clip into descenders (like p, g, y) and look amateurish.

4. AUTONOMOUS RESEARCH & CONTENT EXPANSION (FOR NON-TECH USERS):
   - The user is non-technical. If they ask for a document (like a "long PDF about X"), they expect YOU to act as a senior researcher and designer.
   - Do NOT expect the user to provide the exact structure. You MUST autonomously expand the document: invent an Executive Summary, Table of Contents, deep multi-layered chapters, case studies, and a conclusion.
   - You MUST autonomously perform deep 'web_search' iterations if necessary to gather facts, statistics, and highly detailed information before generating the document.
   - You MUST autonomously select the best 'theme' based on the topic (e.g., 'cyberpunk' for tech, 'corporate_blue' for finance, 'forest_sage' for ecology).
   - Use LaTeX features ('\\newpage', '\\tableofcontents', '\\onehalfspacing', 'tabularx' tables, '\\chapter') to ensure the document is voluminous, exhaustive, and professionally structured automatically.
   
5. HOW TO STOP: To exit the loop and speak to the user, you MUST return a normal text message and completely OMIT the tool calls. If you call a tool, you are trapped in the loop.`
	}

	// Maintain conversation as raw JSON-friendly messages

	messages := []map[string]interface{}{
		{"role": "system", "content": systemPrompt},
	}
	historyMsgs := loadCloudHistory(convID)
	messages = append(messages, historyMsgs...)
	messages = append(messages, map[string]interface{}{"role": "user", "content": command})

	client := &http.Client{Timeout: 300 * time.Second}
	const maxIter = 50

	for iter := 0; iter < maxIter; iter++ {
		select {
		case <-ctx.Done():
			return "", fmt.Errorf("execution cancelled")
		default:
		}

		agentRegistryMu.RLock()
		myTask, myTaskExists := activeAgents[taskID]
		agentRegistryMu.RUnlock()
		if myTaskExists {
		DrainLoop:
			for {
				select {
				case msg := <-myTask.Inbox:
					messages = append(messages, map[string]interface{}{
						"role":    "system",
						"content": "[INBOX] " + msg,
					})
				default:
					break DrainLoop
				}
			}
		}
		if ctx.Err() != nil {
			return "Canceled by user", nil
		}
		debugLog.Printf("[executeOllamaCommand] iter=%d messages=%d", iter, len(messages))
		payload := map[string]interface{}{
			"model":    modelName,
			"messages": messages,
			"stream":   false,
			"tools":    availableTools,
		}

		body, err := json.Marshal(payload)
		if err != nil {
			return "", fmt.Errorf("failed to build Ollama request: %w", err)
		}

		req, err := http.NewRequestWithContext(ctx, "POST", apiURL, bytes.NewBuffer(body))
		if err != nil {
			return "", err
		}
		req.Header.Set("Content-Type", "application/json")
		if apiKey != "" {
			req.Header.Set("Authorization", "Bearer "+apiKey)
		}

		var resp *http.Response
		var respBody []byte
		
		maxRetries := 5
		for r := 0; r < maxRetries; r++ {
			req.Body = io.NopCloser(bytes.NewBuffer(body))
			resp, err = client.Do(req)
			
			if err != nil {
				if r == maxRetries-1 {
					debugLog.Printf("[executeOllamaCommand] iter=%d request failed: %v", iter, err)
					return "", fmt.Errorf("Ollama request failed: %w", err)
				}
				time.Sleep(3 * time.Second)
				continue
			}
			
			respBody, _ = io.ReadAll(resp.Body)
			resp.Body.Close()
			
			debugLog.Printf("[executeOllamaCommand] iter=%d response status=%d responseLen=%d", iter, resp.StatusCode, len(respBody))
			
			if resp.StatusCode == 429 || resp.StatusCode >= 500 {
				if r == maxRetries-1 {
					return "", fmt.Errorf("Ollama API error %d: %s", resp.StatusCode, string(respBody))
				}
				
				if strings.HasPrefix(taskID, "node-") {
					appendLiveLog(fmt.Sprintf("[%s]: API Rate Limit (429) - Pausing execution for 10s...", strings.TrimPrefix(taskID, "node-")))
				}
				time.Sleep(10 * time.Second)
				continue
			}
			
			if resp.StatusCode != http.StatusOK {
				return "", fmt.Errorf("Ollama error %d: %s", resp.StatusCode, string(respBody))
			}
			break
		}

		var result struct {
			Message struct {
				Role      string `json:"role"`
				Content   string `json:"content"`
				ToolCalls []struct {
					Function struct {
						Name      string          `json:"name"`
						Arguments json.RawMessage `json:"arguments"`
					} `json:"function"`
				} `json:"tool_calls"`
			} `json:"message"`
			PromptEvalCount int64  `json:"prompt_eval_count"`
			EvalCount       int64  `json:"eval_count"`
			Error           string `json:"error"`
		}
		if err := json.Unmarshal(respBody, &result); err != nil {
			return "", fmt.Errorf("failed to parse Ollama response: %w", err)
		}
		// Track Ollama Cloud token usage
		if result.PromptEvalCount > 0 || result.EvalCount > 0 {
			addOllamaTokens(result.PromptEvalCount, result.EvalCount)
		}
		if result.Error != "" {
			return "", fmt.Errorf("Ollama error: %s", result.Error)
		}

		// No tool calls — return the final text answer
		if len(result.Message.ToolCalls) == 0 {
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] 4. SUMMARY PREPARATION & TRANSFERRING")
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] Final Output Length: %d", len(result.Message.Content))
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] Returning output back to backend webhook...")
			debugLog.Printf("================================================================")
			debugLog.Printf("[executeOllamaCommand] iter=%d final answer len=%d", iter, len(result.Message.Content))
			finalAnswer := strings.TrimSpace(result.Message.Content)
			saveCloudHistory(convID, command, finalAnswer)
			return finalAnswer, nil
		}

		debugLog.Printf("[executeOllamaCommand] iter=%d toolCalls=%d", iter, len(result.Message.ToolCalls))

		// ENFORCE STRICT SEQUENTIAL EXECUTION: If AI tries to blindly parallelize tool calls, truncate to the first one!
		if len(result.Message.ToolCalls) > 1 {
			result.Message.ToolCalls = result.Message.ToolCalls[:1]
		}

		// Append assistant message
		assistantMsg := map[string]interface{}{
			"role":       "assistant",
			"content":    result.Message.Content,
			"tool_calls": result.Message.ToolCalls,
		}
		messages = append(messages, assistantMsg)

		// ✨ RESTORE DEBATE & CHAT: If the model generated text before calling a tool, print it to the DAG live logs!
		if strings.HasPrefix(taskID, "node-") && result.Message.Content != "" {
			cleanMsg := strings.TrimSpace(result.Message.Content)
			if len(cleanMsg) > 500 { cleanMsg = cleanMsg[:497] + "..." }
			appendLiveLog(fmt.Sprintf("[%s - Discussion]: %s", strings.TrimPrefix(taskID, "node-"), cleanMsg))
		}

		// Execute each tool and collect results
		var wg sync.WaitGroup
		toolResults := make([]map[string]interface{}, len(result.Message.ToolCalls))
		var toolSummaryMu sync.Mutex

		for i, tc := range result.Message.ToolCalls {
			wg.Add(1)
			go func(index int, toolCall struct {
				Function struct {
					Name      string          `json:"name"`
					Arguments json.RawMessage `json:"arguments"`
				} `json:"function"`
			}) {
				defer wg.Done()
				
				toolSummaryMu.Lock()
				toolUsageSummary.WriteString(fmt.Sprintf("> Executed tool: %s (args: %s)\n", toolCall.Function.Name, string(toolCall.Function.Arguments)))
				toolSummaryMu.Unlock()
				
				var argsBytes []byte
				if len(toolCall.Function.Arguments) > 0 && toolCall.Function.Arguments[0] == '"' {
					var strArgs string
					json.Unmarshal(toolCall.Function.Arguments, &strArgs)
					argsBytes = []byte(strArgs)
				} else {
					argsBytes = []byte(toolCall.Function.Arguments)
				}
				
				res := executeTool(ctx, toolCall.Function.Name, json.RawMessage(argsBytes), streamFileObj)
				
				toolResults[index] = map[string]interface{}{
					"role":    "tool",
					"name":    toolCall.Function.Name,
					"content": res,
				}
			}(i, tc)
		}
		wg.Wait()

		for _, tr := range toolResults {
			messages = append(messages, tr)
		}
	}

	debugLog.Printf("[executeOllamaCommand] max iterations reached")
	return "(max tool iterations reached)", nil
}

// Save/Load connection data
func saveConnectionData(data ConnectionData) error {
	configDir := getConfigDir()
	path := filepath.Join(configDir, "connection_data.json")
	file, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		return err
	}
	defer file.Close()

	return json.NewEncoder(file).Encode(data)
}

func registerWithBackend(data ConnectionData, publicAddress string) error {
	// Always use ngrok public URL as the agent address
	// This is where the backend should forward /execute requests
	address := publicAddress

	body, _ := json.Marshal(map[string]string{
		"device_id":       data.DeviceID,
		"device_name":     data.DeviceName,
		"address":         address,
		"fingerprint":     data.DeviceFingerprint,
		"type":            "desktop",
		"security_phrase": data.SecurityPhrase,
	})

	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(data.BackendURL, "/")+"/register", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	// Add ngrok skip browser warning header if calling through ngrok
	if strings.Contains(data.BackendURL, "ngrok") || strings.Contains(data.BackendURL, "ngrok-free") {
		req.Header.Set("ngrok-skip-browser-warning", "true")
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("register failed: %s - %s", resp.Status, string(bodyBytes))
	}

	log.Printf("Registered with backend as %s @ %s", data.DeviceID, address)
	return nil
}

func sendHeartbeat(data ConnectionData, publicAddress string) error {
	// Send periodic heartbeat to keep device marked as online
	body, _ := json.Marshal(map[string]string{
		"device_id": data.DeviceID,
		"address":   publicAddress,
	})

	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(data.BackendURL, "/")+"/heartbeat", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	if strings.Contains(data.BackendURL, "ngrok") || strings.Contains(data.BackendURL, "ngrok-free") {
		req.Header.Set("ngrok-skip-browser-warning", "true")
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	// Don't fail on heartbeat errors, just log them
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("heartbeat failed: %s", resp.Status)
	}

	return nil
}

func loadConnectionData() (ConnectionData, error) {
	path := filepath.Join(getConfigDir(), "connection_data.json")
	file, err := os.Open(path)
	if err != nil {
		return ConnectionData{}, err
	}
	defer file.Close()

	var data ConnectionData
	err = json.NewDecoder(file).Decode(&data)
	return data, err
}

// Auto-start setup
func setupAutoStart() error {
	execDir := getExecutableDir()
	exePath := filepath.Join(execDir, "voila")
	if runtime.GOOS == "windows" {
		exePath += ".exe"
	}

	if runtime.GOOS == "windows" {
		return setupWindowsAutoStart(exePath)
	} else if runtime.GOOS == "darwin" {
		return setupMacAutoStart(exePath)
	} else {
		return setupLinuxAutoStart(exePath)
	}
}

func setupWindowsAutoStart(exePath string) error {
	// Create a scheduled task instead of startup folder for better background behavior
	taskName := "VoilaVoiceCLI"

	// Delete existing task if it exists
	exec.Command("schtasks", "/delete", "/tn", taskName, "/f").Run()

	// Create new scheduled task to run at logon with hidden window
	cmdArgs := []string{
		"schtasks", "/create",
		"/tn", taskName,
		"/tr", fmt.Sprintf(`"%s" --background`, exePath),
		"/sc", "onlogon",
		"/rl", "highest",
		"/f",
	}

	cmd := exec.Command(cmdArgs[0], cmdArgs[1:]...)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to create scheduled task: %w, output: %s", err, string(output))
	}

	log.Printf("Auto-start configured: Scheduled task '%s'", taskName)
	return nil
}

func setupMacAutoStart(exePath string) error {
	// Create launch agent plist
	launchAgentsDir := filepath.Join(os.Getenv("HOME"), "Library", "LaunchAgents")
	os.MkdirAll(launchAgentsDir, 0755)

	plistContent := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicecli.voila</string>
    <key>ProgramArguments</key>
    <array>
        <string>%s</string>
        <string>--background</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
`, exePath)

	plistPath := filepath.Join(launchAgentsDir, "com.voicecli.voila.plist")
	if err := os.WriteFile(plistPath, []byte(plistContent), 0644); err != nil {
		return fmt.Errorf("failed to create launch agent plist: %w", err)
	}

	// Load the launch agent
	cmd := exec.Command("launchctl", "load", plistPath)
	cmd.Run()

	log.Printf("Auto-start configured: %s", plistPath)
	return nil
}

func setupLinuxAutoStart(exePath string) error {
	// Create systemd user service
	systemdDir := filepath.Join(os.Getenv("HOME"), ".config", "systemd", "user")
	os.MkdirAll(systemdDir, 0755)

	serviceContent := fmt.Sprintf(`[Unit]
Description=Voila Voice CLI Agent
After=network.target

[Service]
Type=simple
ExecStart=%s --background
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
`, exePath)

	servicePath := filepath.Join(systemdDir, "voila.service")
	if err := os.WriteFile(servicePath, []byte(serviceContent), 0644); err != nil {
		return fmt.Errorf("failed to create systemd service: %w", err)
	}

	// Enable and start the service
	exec.Command("systemctl", "--user", "daemon-reload").Run()
	exec.Command("systemctl", "--user", "enable", "voila.service").Run()

	log.Printf("Auto-start configured: %s", servicePath)
	return nil
}

func getConfigDir() string {
	// Use local-agent directory for connection data
	return getExecutableDir()
}

func getExecutableDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	return filepath.Dir(exe)
}

func generateUUID() string {
	b := make([]byte, 16)
	_, err := rand.Read(b)
	if err != nil {
		log.Printf("Error generating UUID: %v", err)
		return "fallback-" + fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b)[:8]
}

func generateDeviceFingerprint() string {
	// Generate fingerprint from system info
	hostname, _ := os.Hostname()
	osName := runtime.GOOS
	arch := runtime.GOARCH
	user := os.Getenv("USER")
	if user == "" {
		user = os.Getenv("USERNAME")
	}

	fingerprintData := fmt.Sprintf("%s|%s|%s|%s|%d", hostname, osName, arch, user, time.Now().Unix()/(86400))
	hash := sha256.Sum256([]byte(fingerprintData))
	return hex.EncodeToString(hash[:])[:16]
}


var connectionManagerRunning bool
var connectionManagerMu sync.Mutex

func startConnectionManager(data ConnectionData) {
	connectionManagerMu.Lock()
	if connectionManagerRunning {
		connectionManagerMu.Unlock()
		return
	}
	connectionManagerRunning = true
	connectionManagerMu.Unlock()

	// 1. Unified Registration and Heartbeat Loop
	go func() {
		var lastRegisteredAddr string
		var ngrokRetryCount int
		var ngrokRetryDelay = 5 * time.Second
		const maxNgrokRetries = 10
		const maxNgrokRetryDelay = 60 * time.Second

		for {
			addr := getNgrokPublicURL()
			if addr == "" {
				if !isNgrokRunning() {
					log.Println("Ngrok not running, attempting to start...")
					if err := startNgrok(); err != nil {
						ngrokRetryCount++
						log.Printf("Failed to start ngrok (attempt %d/%d): %v", ngrokRetryCount, maxNgrokRetries, err)

						if ngrokRetryCount >= maxNgrokRetries {
							log.Printf("Max ngrok retry attempts reached, giving up for now")
							ngrokRetryCount = 0
							ngrokRetryDelay = 5 * time.Second // Reset delay
							time.Sleep(30 * time.Second)      // Wait longer before trying again
							continue
						}

						time.Sleep(ngrokRetryDelay)
						ngrokRetryDelay = time.Duration(float64(ngrokRetryDelay) * 1.5) // Exponential backoff
						if ngrokRetryDelay > maxNgrokRetryDelay {
							ngrokRetryDelay = maxNgrokRetryDelay
						}
						continue
					}
					ngrokRetryCount = 0 // Reset on success
					ngrokRetryDelay = 5 * time.Second
					time.Sleep(3 * time.Second)
					addr = getNgrokPublicURL()
				}
				if addr == "" {
					log.Println("ngrok URL not available yet (is ngrok running?)")
				}
			}

			if addr != "" {
				// If address changed or we haven't registered yet, register!
				if addr != lastRegisteredAddr {
					if err := registerWithBackend(data, addr); err != nil {
						log.Printf("register error: %v", err)
					} else {
						lastRegisteredAddr = addr
					}
				} else {
					// We are registered, so send a heartbeat to keep the session alive
					if err := sendHeartbeat(data, addr); err != nil {
						log.Printf("heartbeat error: %v", err)
						// CRITICAL FIX: If heartbeat fails (e.g., backend restarted and wiped memory),
						// we MUST clear lastRegisteredAddr to force a full re-registration on the next loop!
						lastRegisteredAddr = ""
					}
				}
			}
			time.Sleep(5 * time.Second)
		}
	}()

	// 2. Start mobile client presence polling for AI face updates
	go func() {
		client := &http.Client{
			Timeout: 5 * time.Second, // Fast timeout for health checks
			Transport: &http.Transport{
				MaxIdleConns:       10,
				IdleConnTimeout:    30 * time.Second,
				DisableCompression: true,
			},
		}
		for {
			time.Sleep(2 * time.Second)
			healthURL := data.BackendURL + "/health"
			req, err := http.NewRequest("GET", healthURL, nil)
			if err == nil {
				if strings.Contains(data.BackendURL, "ngrok") || strings.Contains(data.BackendURL, "ngrok-free") {
					req.Header.Set("ngrok-skip-browser-warning", "true")
				}
				resp, err := client.Do(req)
				if err == nil && resp.StatusCode == 200 {
					var healthData struct {
						Status        string `json:"status"`
						MobileClients int    `json:"mobile_clients"`
					}
					json.NewDecoder(resp.Body).Decode(&healthData)
					resp.Body.Close()
					log.Printf("Presence: Backend OK, Mobile clients: %d", healthData.MobileClients)
					fmt.Printf("STATUS: BACKEND:ONLINE\n")
					fmt.Printf("STATUS: MOBILE_CLIENTS:%d\n", healthData.MobileClients)
					os.Stdout.Sync()
					continue
				}
				if err == nil {
					resp.Body.Close()
				}
			}
			
			log.Printf("Presence: Backend unreachable")
			fmt.Printf("STATUS: BACKEND:OFFLINE\n")
			fmt.Printf("STATUS: MOBILE_CLIENTS:0\n")
			os.Stdout.Sync()
		}
	}()
}

func runBackgroundMode() {
	data, err := loadConnectionData()
	if err != nil {
		log.Fatalf("Background mode requires connection data: %v", err)
	}

	if !data.Connected || data.SecurityPhrase == "" {
		log.Fatalf("Background mode requires completed setup")
	}

	log.Printf("Starting Voila in background mode...")
	log.Printf("Backend: %s", data.BackendURL)
	log.Printf("Device: %s (%s)", data.DeviceName, data.DeviceID)

	// Start HTTP server
	go startHTTPServer()

	// Start unified robust connection manager
	startConnectionManager(data)

	// Block forever
	select {}
}

func stopBackgroundService() {
	if runtime.GOOS == "windows" {
		// Only kill specific voila instance, not all instances
		exec.Command("taskkill", "/F", "/T", "/IM", "voila.exe").Run()
	} else if runtime.GOOS == "darwin" {
		exec.Command("launchctl", "unload", filepath.Join(os.Getenv("HOME"), "Library", "LaunchAgents", "com.voicecli.voila.plist")).Run()
	} else {
		exec.Command("systemctl", "--user", "stop", "voila.service").Run()
	}
	log.Println("Background service stop command executed")
}

func isBackgroundServiceRunning() bool {
	// Simple check: try to connect to the local HTTP server
	resp, err := resilientHTTPGet("http://localhost:8088/health")
	if err == nil && resp.StatusCode == 200 {
		resp.Body.Close()
		return true
	}
	return false
}

// Main

func hashPhrase(phrase, deviceID string) string {
	salt := []byte(deviceID + "_voila_salt_v2")
	hash := pbkdf2.Key([]byte(phrase), salt, 10000, 32, sha256.New)
	return hex.EncodeToString(hash)
}

// Circuit breaker functions
func loadCircuitState() {
	circuitMu.Lock()
	defer circuitMu.Unlock()

	configDir := getConfigDir()
	path := filepath.Join(configDir, circuitFlagFile)
	if _, err := os.Stat(path); err == nil {
		circuitOpen = true
		log.Println("Circuit breaker loaded as OPEN from disk")
	}
}

func saveCircuitState() {
	circuitMu.Lock()
	defer circuitMu.Unlock()

	configDir := getConfigDir()
	path := filepath.Join(configDir, circuitFlagFile)
	if circuitOpen {
		os.WriteFile(path, []byte("1"), 0644)
	} else {
		os.Remove(path)
	}
}

func setCircuitState(open bool) {
	circuitMu.Lock()
	circuitOpen = open
	circuitMu.Unlock()
	saveCircuitState()

	if open {
		log.Println("Circuit breaker set to OPEN - refusing new commands")
	} else {
		log.Println("Circuit breaker set to CLOSED - accepting commands")
	}
}

func isCircuitOpen() bool {
	circuitMu.Lock()
	defer circuitMu.Unlock()
	return circuitOpen
}

func (m model) resetCircuitBreakerWithPhrase(phrase string) tea.Cmd {
	return func() tea.Msg {
		if phrase == "" {
			return errorMsg{"Security phrase required"}
		}

		connData, err := loadConnectionData()
		if err != nil {
			return errorMsg{"Connection data not found"}
		}

		expectedHash := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
		gotHash := hashPhrase(phrase, connData.DeviceID)

		if expectedHash != "" && expectedHash == gotHash {
			setCircuitState(false)
			return successMsg{"Circuit breaker reset successfully"}
		}

		return errorMsg{"Invalid security phrase"}
	}
}

// --- MEMORY SYSTEM ---
func getMemoryFilePath() string {
	exe, _ := os.Executable()
	return filepath.Join(filepath.Dir(exe), "cmd_memory.json")
}

func loadMemory() string {
	data, err := os.ReadFile(getMemoryFilePath())
	if err != nil || len(data) == 0 {
		return "{}"
	}
	return string(data)
}

func saveMemory(purpose, command string) string {
	mem := make(map[string]string)
	data, _ := os.ReadFile(getMemoryFilePath())
	json.Unmarshal(data, &mem)
	mem[purpose] = command
	b, _ := json.MarshalIndent(mem, "", "  ")
	os.WriteFile(getMemoryFilePath(), b, 0644)
	return "Memory successfully updated with technique."
}

func flushMemory() {
	os.WriteFile(getMemoryFilePath(), []byte("{}"), 0644)
}

func handleLocalMockExecution(w http.ResponseWriter, r *http.Request, command string, connData ConnectionData, endpoint string) {
	localMockMu.Lock()
	localMockCount++
	currentCount := localMockCount
	localMockMu.Unlock()

	tripCircuit := currentCount >= 3

	go func() {
		alertPayload := map[string]interface{}{
			"device_id":    connData.DeviceID,
			"secret_hash":  hashPhrase(connData.SecurityPhrase, connData.DeviceID),
			"alert_type":   "mock_command",
			"source_ip":    r.RemoteAddr,
			"description":  "Unauthorized access attempt directly to local-agent " + endpoint,
			"severity":     "high",
			"trip_circuit": tripCircuit,
		}
		body, _ := json.Marshal(alertPayload)
		http.Post(connData.BackendURL+"/webhook/alert", "application/json", bytes.NewBuffer(body))
	}()

	if tripCircuit {
		time.Sleep(decoy.GetMockDelay())
		http.Error(w, "Circuit breaker open. Request dropped.", http.StatusServiceUnavailable)
		return
	}

	time.Sleep(decoy.GetMockDelay())
	mockResp := decoy.GenerateMockResponse(command)
	w.WriteHeader(http.StatusOK)
	if endpoint == "/execute" {
		w.Write([]byte(mockResp))
	} else {
		json.NewEncoder(w).Encode(map[string]string{"status": "circuit_closed"})
	}
}

func main() {
	initZeroOrphanJobObject()
	initDebugLog()
	// Load circuit state on startup
	loadCircuitState()

	// Check for background mode flag
	backgroundMode := false
	for _, arg := range os.Args {
		if arg == "--background" || arg == "-b" {
			backgroundMode = true
		}
		if arg == "--tui" {
			runGraphifyTUI()
			return
		}
	}

	if backgroundMode {
		runBackgroundMode()
		return
	}

	// Check if background service is already running
	backgroundRunning := isBackgroundServiceRunning()
	if backgroundRunning {
		log.Println("Background service already running. Launching TUI in management mode...")
		// Load connection data for backend access
		data, err := loadConnectionData()
		if err != nil {
			log.Printf("Warning: Could not load connection data: %v", err)
			data = ConnectionData{}
		}
		// Launch in menu mode to manage background service
		initialModel := model{
			state:          "menu",
			connectionData: data,
			inputStep:      0,
			currentInput:   "",
			selectedOption: 0,
			messages:       []string{successStyle.Render("Background service running")},
			status:         "Background Service Active",
			isRunning:      true,
			serverRunning:  true,
			isLoading:      false,
		}
		p := tea.NewProgram(initialModel)
		if _, err := p.Run(); err != nil {
			log.Fatalf("Error running program: %v", err)
		}
		return
	}

	// Try to load existing connection
	data, err := loadConnectionData()
	if err == nil && data.Connected && data.SecurityPhrase != "" {
		log.Printf("Auto-connecting with backend: %s", data.BackendURL)
		// Auto-connect if connection exists and security phrase is set
		initialModel := model{
			state:          "connected",
			connectionData: data,
			isRunning:      true,
			serverRunning:  true,
			status:         "Running",
			isLoading:      false,
		}
		go startHTTPServer()
		startConnectionManager(data)
		p := tea.NewProgram(initialModel)
		if _, err := p.Run(); err != nil {
			log.Fatalf("Error running program: %v", err)
		}
		return
	}

	// No connection data or incomplete setup - start fresh
	log.Printf("Starting setup mode")
	// No error logging

	// New setup
	initialModel := model{
		state:          "setup",
		inputStep:      0,
		messages:       []string{},
		status:         "Not Running",
		isLoading:      false,
		connectionData: ConnectionData{},
	}

	p := tea.NewProgram(initialModel)
	finalModel, err := p.Run()
	if err != nil {
		log.Fatalf("Error running program: %v", err)
	}

	// Save connection data
	if m, ok := finalModel.(model); ok && m.connectionData.Connected {
		saveConnectionData(m.connectionData)
		setupAutoStart()
	}
}
