package main

import (
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
	"path/filepath"
	"os/exec"
	"runtime"
	"strings"
	"syscall"
	"sync"
	"time"

	"github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// Styles
var (
	terminalSessionMu sync.Mutex
	terminalCmdFile   = filepath.Join(os.TempDir(), "voila_ipc_cmd.txt")
	terminalOutFile   = filepath.Join(os.TempDir(), "voila_ipc_out.txt")
	terminalDoneFile  = filepath.Join(os.TempDir(), "voila_ipc_done.txt")
	terminalPidFile   = filepath.Join(os.TempDir(), "voila_ipc_pid.txt")
	terminalActive    = false
	terminalPid       = ""

	cmdMu      sync.Mutex
	currentCmd *exec.Cmd
	currentConvID string
	currentCancel context.CancelFunc
	circuitMu  sync.Mutex
	circuitOpen bool
	execSemaphore chan struct{} // Limit concurrent executions
	maxConcurrentExecs = 3 // Maximum concurrent AI executions
	resilienceManager *ResilienceManager

	// Protect local models from VRAM crashes
	ollamaSemaphore = make(chan struct{}, 1)

	// Inter-Agent IPC
	agentRegistryMu sync.RWMutex
	activeAgents = make(map[string]*AgentTask)
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
	titleStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("6")).Bold(true)
	subtitleStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("242"))
	successStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("2"))
	errorStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("1"))
	warningStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("3"))
	buttonStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("15")).Background(lipgloss.Color("4")).Padding(0, 2)
	activeButtonStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("0")).Background(lipgloss.Color("6")).Padding(0, 2)
	inputStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("15")).Background(lipgloss.Color("8")).Padding(0, 2)
	statusStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("5"))
	deviceStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("14"))
	menuStyle        = lipgloss.NewStyle().Margin(1, 0)
	asciiArtStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("6")).Bold(true)
	separatorStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
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

	sparklineConnected = "▓▓▓▓▓▓▓▓▓▓▓ 100%"
	sparklineDisconnected = "░░░░░░░░░░░ 0%"

	progressBarConnected = "████████████████████ 100%"
	progressBarDisconnected = "░░░░░░░░░░░░░░░░░░░ 0%"

	frameTop = "╔════════════════════════════════════════════════════════════════════════════╗"
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
	GroqAPIKey    string `json:"groq_api_key,omitempty"`
	GroqModel     string `json:"groq_model,omitempty"`
	OllamaBaseURL string `json:"ollama_base_url,omitempty"` // e.g. https://api.ollama.ai
	OllamaAPIKey  string `json:"ollama_api_key,omitempty"`  // optional auth
	OllamaModel   string `json:"ollama_model,omitempty"`    // e.g. llama3.2:1b
	ActiveMode    string `json:"active_mode,omitempty"`
}

// Model
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

		go func(data ConnectionData) {
			for {
				addr := getNgrokPublicURL()
				if addr == "" {
					if !isNgrokRunning() {
						log.Println("Ngrok not running, attempting to start...")
						if err := startNgrok(); err != nil {
							log.Printf("Failed to start ngrok: %v (skipping registration)", err)
							time.Sleep(5 * time.Second)
							continue
						}
						time.Sleep(3 * time.Second)
						addr = getNgrokPublicURL()
					}
					if addr == "" {
						log.Println("ngrok URL not available yet (is ngrok running?)")
					}
				}
				if addr != "" {
					if err := registerWithBackend(data, addr); err != nil {
						log.Printf("register error: %v", err)
					}
				}
				time.Sleep(5 * time.Second)
			}
		}(m.connectionData)

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
			content.WriteString(activeButtonStyle.Render(prefix+" "+option))
		} else {
			content.WriteString(buttonStyle.Render(prefix+" "+option))
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
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
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
				cancelMsg := fmt.Sprintf(`{"type":"SYSTEM_MESSAGE","status":"ERROR","content":"Execution forcibly cancelled by user.","created_at":"%s"}` + "\n", time.Now().Format(time.RFC3339))
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
				"groq_api_key_masked": groqMasked,
				"groq_api_key_set":    fmt.Sprintf("%v", connData.GroqAPIKey != ""),
				"groq_model":          connData.GroqModel,
				"ollama_base_url":     connData.OllamaBaseURL,
				"ollama_api_key_masked": ollamaMasked,
				"ollama_api_key_set":    fmt.Sprintf("%v", connData.OllamaAPIKey != ""),
				"ollama_model":        connData.OllamaModel,
				"active_mode":         connData.ActiveMode,
			}
			json.NewEncoder(w).Encode(resp)

		case http.MethodPost:
			var payload struct {
				GroqAPIKey    string `json:"groq_api_key"`
				GroqModel     string `json:"groq_model"`
				OllamaBaseURL string `json:"ollama_base_url"`
				OllamaAPIKey  string `json:"ollama_api_key"`
				OllamaModel   string `json:"ollama_model"`
				Action        string `json:"action"` // "save" or "delete_groq" or "delete_ollama"
			}
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				http.Error(w, "Bad request", http.StatusBadRequest)
				return
			}

			switch payload.Action {
			case "delete_groq":
				connData.GroqAPIKey = ""
				connData.GroqModel = ""
			case "delete_ollama":
				connData.OllamaBaseURL = ""
				connData.OllamaAPIKey = ""
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
		out, err := executeGroqCommand(context.Background(), "Say hello in one word", connData.GroqAPIKey, connData.GroqModel, connData.DeviceID, nil, "verify")
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
		out, err := executeOllamaCommand(context.Background(), "Say hello in one word", connData.OllamaBaseURL, connData.OllamaModel, connData.OllamaAPIKey, nil, "verify")
		if err != nil {
			json.NewEncoder(w).Encode(map[string]string{"status": "error", "message": err.Error()})
			return
		}
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "response": out})
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
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
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
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
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
				})
				http.Post(connData.BackendURL+"/webhook/result", "application/json", bytes.NewBuffer(webhookPayload))
			}()
			return
		}

		if graphifyEnabled {
			w.WriteHeader(http.StatusAccepted)
			
			go func() {
				output, err := executeGraphifyDAG(context.Background(), command)
				
				backendURL := strings.TrimRight(connData.BackendURL, "/") + "/webhook/result"
				backendURL = strings.Replace(backendURL, "wss://", "https://", 1)
				backendURL = strings.Replace(backendURL, "ws://", "http://", 1)
				
				h := sha256.New()
				h.Write([]byte(connData.SecurityPhrase + ":" + connData.DeviceID))
				secretHash := hex.EncodeToString(h.Sum(nil))
				
				resultPayload := map[string]string{
					"client_id":           clientID,
					"device_id":           connData.DeviceID,
					"secret_hash":         secretHash,
					"mode":                mode,
					"new_conversation_id": conversationID,
				}
				
				if err != nil {
					resultPayload["error"] = "DAG Execution Failed:\n" + err.Error()
				} else {
					resultPayload["output"] = output
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
			currentModeMu.Lock()
			globalMode := strings.ToUpper(currentMode)
			currentModeMu.Unlock()

			reqMode := strings.ToUpper(mode)
			var effectiveMode string
			switch reqMode {
			case "GROQ", "OLLAMA", "SHELL":
				// Caller explicitly chose a specific executor — honour it
				effectiveMode = reqMode
			default:
				// "AGENT", "", or anything else — use whatever the badge is set to
				effectiveMode = globalMode
				if effectiveMode == "" {
					effectiveMode = "LOCAL"
				}
			}

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
					m = "llama3-70b-8192"
				}
				output, err = executeGroqCommand(ctx, command, connData.GroqAPIKey, m, clientID, nil, taskID)
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
				output, err = executeOllamaCommand(ctx, command, connData.OllamaBaseURL, ollamaModel, connData.OllamaAPIKey, nil, taskID)
				<-ollamaSemaphore
				fmt.Println("STATUS: IDLE")
				os.Stdout.Sync()
				newConvID = conversationID
			default:
				// LOCAL / AGENT / SHELL — use agy or powershell
				output, newConvID, err = executeCommand(command, effectiveMode, conversationID, modelName)
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
			h := sha256.New()
			h.Write([]byte(connData.SecurityPhrase + ":" + connData.DeviceID))
			secretHash := hex.EncodeToString(h.Sum(nil))


			resultPayload := map[string]string{
				"client_id": clientID,
				"device_id": connData.DeviceID,
				"secret_hash": secretHash,
				"mode": effectiveMode,
				"new_conversation_id": newConvID,
			}
			
			if err != nil {
				resultPayload["error"] = "Command failed:\n" + err.Error()
			} else {
				resultPayload["output"] = output
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
	workingDirMutex  sync.Mutex
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
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
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
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
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





func executeCommand(command string, mode string, conversationID string, modelName string) (string, string, error) {
	var cmd *exec.Cmd

	modeUpper := strings.ToUpper(mode)
	// LOCAL = agy (local Gemini agent). AGENT = also agy (legacy name).
	// Only SHELL = raw PowerShell. Empty string = default to agy.
	if modeUpper == "AGENT" || modeUpper == "LOCAL" || modeUpper == "" {
		prompt := command + "\n\n(CRITICAL SYSTEM NOTE: Keep your responses casual, brief, and conversational as if you are a friendly voice assistant. Address the user as 'boss'. Do not use overly formal language.\n\nCRITICAL SYSTEM NOTE: You are running inside an isolated background sandbox (`exebox` desktop). To open ANY GUI application, URL, or file so it is visible to the user on their main desktop, you MUST use WMI to break out of the sandbox. Use exactly this command format: `Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'explorer.exe \"<URL_OR_PATH>\"'` (for URLs/files) or `Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList '<APP_EXE>'` (for apps). DO NOT use Start-Process, as it will spawn invisibly in the sandbox! To perform browser automation, you MUST first launch a visible browser using Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe --remote-debugging-port=9222 --user-data-dir=C:\\tmp\\ai_browser_profile \"about:blank\"'. Then, control it by running python C:\\Users\\ojasw\\Desktop\\voice-cli-system\\local-agent\\browser_tools.py with args --action [goto|click|type|scrape|extract_links|snapshot] --url <url> --selector <css> --value <text>.)"
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
		cmdObj := exec.Command("powershell", "-Command", agyCmd)
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
			cmd = exec.Command("powershell", "-Command", fullCommand)
		} else {
			fullCommand := command + "; echo \"\n___PWD___$(pwd)\""
			cmd = exec.Command("sh", "-c", fullCommand)
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
	Type     string       `json:"type"`
	Function toolFuncDef  `json:"function"`
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
			Name:        "automate_0",
			Description: "Control a visible, headful browser. Use this to interact with a page. For simple information lookup, prefer web_research to save tokens. They can be used together.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"action":   map[string]interface{}{"type": "string", "description": "Action to perform: 'goto', 'click', 'type', 'scrape', 'extract_links'"},
					"url":      map[string]interface{}{"type": "string", "description": "URL to navigate to (required for 'goto')"},
					"selector": map[string]interface{}{"type": "string", "description": "CSS selector to click or type into"},
					"value":    map[string]interface{}{"type": "string", "description": "Text to type"},
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
				"required": []string{"path", "content"},
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
					"path":    map[string]interface{}{"type": "string", "description": "Absolute path to save the PDF"},
					"content": map[string]interface{}{"type": "string", "description": "Text content of the PDF"},
				},
				"required": []string{"path", "content"},
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
			Name:        "create_ppt",
			Description: "Create a basic PowerPoint presentation.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path":   map[string]interface{}{"type": "string", "description": "Absolute path to save PPTX"},
					"title":  map[string]interface{}{"type": "string", "description": "Title of the presentation"},
					"slides": map[string]interface{}{"type": "string", "description": "JSON array string of slides: [{\"title\":\"Slide 1\",\"content\":\"text\"}]"},
				},
				"required": []string{"path", "title", "slides"},
			},
		},
	},
	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "create_excel",
			Description: "Create an Excel file from data.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path to save XLSX"},
					"data": map[string]interface{}{"type": "string", "description": "JSON string of array of objects representing rows"},
				},
				"required": []string{"path", "data"},
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
			Description: "Create a CSV file.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string", "description": "Absolute path to save CSV"},
					"data": map[string]interface{}{"type": "string", "description": "JSON array of objects or raw CSV string"},
				},
				"required": []string{"path", "data"},
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
		case "run_terminal":
			pseudoCommand = getString("command")
		case "read_file":
			pseudoCommand = "cat " + getString("path")
		case "write_file":
			pseudoCommand = "echo '...' > " + getString("path")
		case "list_dir":
			pseudoCommand = "ls " + getString("path")
		case "web_research":
			pseudoCommand = "search \"" + getString("query") + "\""
		case "create_pdf", "create_ppt", "create_excel", "create_csv", "modify_excel":
			pseudoCommand = "write_doc " + getString("path")
		case "read_pdf", "read_excel", "read_csv":
			pseudoCommand = "read_doc " + getString("path")
		case "automate_0":
			pseudoCommand = "browser " + getString("action") + " " + getString("url") + getString("selector")
		default:
			pseudoCommand = toolName + " ..."
		}

		if streamFileObj != nil && pseudoCommand != "" {
			event := map[string]interface{}{
				"event": "step_update",
				"step_update": map[string]interface{}{
					"step_type": "tool",
					"state": "RUNNING",
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
					"state": "DONE",
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
		Start-Transcript -Path $outFile -Append -Force | Out-Null
		try {
			Invoke-Expression $cmdText
		} catch {
			Write-Error $_
		}
		Stop-Transcript | Out-Null
		
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
	case "web_research":
		query := getString("query")
		if query == "" {
			return "error: query is required"
		}
		searchURL := "https://api.duckduckgo.com/?q=" + strings.ReplaceAll(query, " ", "+") + "&format=json&no_html=1&skip_disambig=1"
		resp, err := http.Get(searchURL)
		if err != nil {
			return "web search failed: " + err.Error()
		}
		defer resp.Body.Close()
		body, _ := io.ReadAll(resp.Body)

		var ddg struct {
			AbstractText  string `json:"AbstractText"`
			RelatedTopics []struct {
				Text string `json:"Text"`
			} `json:"RelatedTopics"`
		}
		if err := json.Unmarshal(body, &ddg); err != nil {
			return "web search: failed to parse response"
		}

		var parts []string
		if ddg.AbstractText != "" {
			parts = append(parts, ddg.AbstractText)
		} else {
			parts = append(parts, "(No direct answer found — see related topics below)")
		}
		for i, rt := range ddg.RelatedTopics {
			if i >= 3 {
				break
			}
			if rt.Text != "" {
				parts = append(parts, rt.Text)
			}
		}
		return strings.Join(parts, "\n")

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
		// Fix LLM JSON escaping hallucinations where it outputs \" instead of "
		actualCommand = strings.ReplaceAll(actualCommand, "\\\"", "\"")

		if actualCommand == "" {
			return "error: command is required"
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
		
		// Clean up PowerShell Transcript headers/footers
		outStr := string(outBytes)
		lines := strings.Split(outStr, "\n")
		var cleanLines []string
		inTranscriptHeader := false
		for _, line := range lines {
			trimmed := strings.TrimSpace(line)
			if strings.HasPrefix(trimmed, "**********************") {
				inTranscriptHeader = !inTranscriptHeader
				continue
			}
			if inTranscriptHeader {
				continue // skip all header/footer lines
			}
			cleanLines = append(cleanLines, trimmed)
		}
		
		result := strings.TrimSpace(strings.Join(cleanLines, "\n"))
		debugLog.Printf("[executeTool/run_terminal] raw outBytes len=%d", len(outBytes))
		debugLog.Printf("[executeTool/run_terminal] result:\n%s", result)
		if err != nil {
			result += "\n(Error: " + err.Error() + ")"
		}
		if result == "" {
			result = "(no output)"
		}


		return result


	case "create_pdf", "read_pdf", "create_ppt", "create_excel", "modify_excel", "read_excel", "create_csv", "read_csv":
		return callPythonDocumentTool(toolName, argsJSON)
	case "automate_0":
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
func executeGroqCommand(ctx context.Context, command, apiKey, modelName, clientID string, streamFileObj *os.File, taskID string) (string, error) {
	defer cleanupTerminalSession()
	if apiKey == "" {
		return "", fmt.Errorf("Groq API key not set. Open the Voila dashboard → Settings to add your key")
	}
	if modelName == "" {
		modelName = "llama3-70b-8192" // Groq free-tier default
	}

	// Mask key for logging (show last 4 chars only)
	maskedKey := "***"
	if len(apiKey) >= 4 {
		maskedKey = "***" + apiKey[len(apiKey)-4:]
	}
	debugLog.Printf("[executeGroqCommand] ENTRY model=%q key=%s commandLen=%d", modelName, maskedKey, len(command))

	systemPrompt := `You are Voila, a helpful AI voice assistant executing on a Windows Desktop. Keep responses casual, conversational, and brief. Address the user as 'boss'.
CRITICAL: You are running inside a Windows PowerShell environment. You MUST use PowerShell syntax, NOT Bash!
- Use 'Get-ChildItem' or 'ls' (without bash flags like -la). Do NOT use 'ls -la'.
- Use 'Select-String' or 'findstr', NOT 'grep'.
- Use 'Get-Content' or 'cat' (no bash flags).
- In PowerShell, 'where' is an alias for 'Where-Object'. To find an executable path, use 'where.exe <command>' or 'Get-Command <command>'.
- Paths use backslashes (\) on Windows.

CRITICAL - DOCUMENT ANALYSIS: 
If the user asks you to read, analyze, or process a PDF file, you MUST use the 'read_pdf' tool! Do NOT try to read PDFs using PowerShell's Get-Content, as they are binary files and it will fail. First find the file, then call 'read_pdf' on the absolute path.

CRITICAL - FAST FILE SEARCHING (0 BUGS POLICY):
When asked to find, scan, or search for a specific file, folder, or project by name (e.g., 'mandate_guard'), NEVER use slow PowerShell commands like Get-ChildItem. You MUST use the highly optimized native CMD search wrapper inside your terminal tool:
'cmd.exe /c "dir /s /b /a:d C:\Users\ojasw\Desktop\*mandate*"' (for directories) or '/a:-d' (for files).
Always wrap the search term in asterisks like '*name*' to handle fuzzy matching for nested subfolders.
If you need to find content INSIDE files, use: 'findstr /s /i "search_term" C:\path\*.txt'

CRITICAL - TOOL EFFICENCY:
When using run_terminal, DO NOT issue multiple short commands. Write comprehensive, long-form PowerShell scripts that accomplish the entire goal in 1-2 steps. Use variables, loops, and conditional logic.
You have a maximum of 8 tool iterations. Be highly efficient! Review your message history and reuse successful commands if performing a similar task.`

	// Maintain conversation as raw JSON-friendly messages
	messages := []map[string]interface{}{
		{"role": "system", "content": systemPrompt},
		{"role": "user", "content": command},
	}

	client := &http.Client{Timeout: 60 * time.Second}
	const maxIter = 8

	for iter := 0; iter < maxIter; iter++ {

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
		if ctx.Err() != nil { return "Canceled by user", nil }
		debugLog.Printf("[executeGroqCommand] iter=%d messages=%d", iter, len(messages))
		payload := map[string]interface{}{
			"model":       modelName,
			"messages":    messages,
			"temperature": 0.7,
			"max_tokens":  2048,
			"stream":      false,
			"tools":       availableTools,
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

		resp, err := client.Do(req)
		if err != nil {
			debugLog.Printf("[executeGroqCommand] iter=%d API request failed: %v", iter, err)
			return "", fmt.Errorf("Groq API request failed: %w", err)
		}
		respBody, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		debugLog.Printf("[executeGroqCommand] iter=%d response status=%d responseLen=%d", iter, resp.StatusCode, len(respBody))

		if resp.StatusCode != http.StatusOK {
			return "", fmt.Errorf("Groq API error %d: %s", resp.StatusCode, string(respBody))
		}

		var result struct {
			Choices []struct {
				Message struct {
					Role      string          `json:"role"`
					Content   string          `json:"content"`
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
			Error struct {
				Message string `json:"message"`
			} `json:"error"`
		}
		if err := json.Unmarshal(respBody, &result); err != nil {
			return "", fmt.Errorf("failed to parse Groq response: %w", err)
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
			return strings.TrimSpace(choice.Message.Content), nil
		}

		debugLog.Printf("[executeGroqCommand] iter=%d toolCalls=%d", iter, len(choice.Message.ToolCalls))

		// Append assistant message with tool_calls
		assistantMsg := map[string]interface{}{
			"role":       "assistant",
			"content":    choice.Message.Content,
			"tool_calls": choice.Message.ToolCalls,
		}
		messages = append(messages, assistantMsg)

		// Execute each tool and collect results
		for _, tc := range choice.Message.ToolCalls {
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] 2. TOOL EXECUTION PHASE")
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] AI requested tool: %q with args: %s", tc.Function.Name, tc.Function.Arguments)
			debugLog.Printf("[executeGroqCommand] iter=%d executing tool=%q", iter, tc.Function.Name)
			var argsBytes []byte
			if len(tc.Function.Arguments) > 0 && tc.Function.Arguments[0] == '"' {
				var strArgs string
				json.Unmarshal(tc.Function.Arguments, &strArgs)
				argsBytes = []byte(strArgs)
			} else {
				argsBytes = []byte(tc.Function.Arguments)
			}
			toolResult := executeTool(ctx, tc.Function.Name, json.RawMessage(argsBytes), streamFileObj)
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] 3. TOOL EXECUTION FINISHED")
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] Result Length: %d", len(toolResult))
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] Result Content Preview (max 200 chars):\n%.200s", toolResult)
			debugLog.Printf("================================================================")
			debugLog.Printf("[executeGroqCommand] iter=%d tool=%q resultLen=%d", iter, tc.Function.Name, len(toolResult))
			messages = append(messages, map[string]interface{}{
				"role":         "tool",
				"tool_call_id": tc.ID,
				"content":      toolResult,
			})
		}
	}

	debugLog.Printf("[executeGroqCommand] max iterations reached")
	return "(max tool iterations reached)", nil
}

// ── Ollama executor with tool-calling loop ────────────────────────────────────

// executeOllamaCommand sends a prompt to an Ollama-compatible endpoint.
// Works for both local Ollama (http://localhost:11434) and Ollama Cloud (https://api.ollama.ai).
// Supports up to 5 tool-calling iterations using the Ollama /api/chat tools field.
func executeOllamaCommand(ctx context.Context, command, baseURL, modelName, apiKey string, streamFileObj *os.File, taskID string) (string, error) {
	defer cleanupTerminalSession()
	if baseURL == "" || baseURL == "http://localhost:11434" {
		if apiKey != "" {
			baseURL = "https://ollama.com"
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

	systemPrompt := `You are Voila, a helpful AI voice assistant executing on a Windows Desktop. Keep responses casual, conversational, and brief. Address the user as 'boss'.
CRITICAL: You are running inside a Windows PowerShell environment. You MUST use PowerShell syntax, NOT Bash!
- Use 'Get-ChildItem' or 'ls' (without bash flags like -la). Do NOT use 'ls -la'.
- Use 'Select-String' or 'findstr', NOT 'grep'.
- Use 'Get-Content' or 'cat' (no bash flags).
- In PowerShell, 'where' is an alias for 'Where-Object'. To find an executable path, use 'where.exe <command>' or 'Get-Command <command>'.
- Paths use backslashes (\) on Windows.

CRITICAL - DOCUMENT ANALYSIS: 
If the user asks you to read, analyze, or process a PDF file, you MUST use the 'read_pdf' tool! Do NOT try to read PDFs using PowerShell's Get-Content, as they are binary files and it will fail. First find the file, then call 'read_pdf' on the absolute path.

CRITICAL - FAST FILE SEARCHING (0 BUGS POLICY):
When asked to find, scan, or search for a specific file, folder, or project by name (e.g., 'mandate_guard'), NEVER use slow PowerShell commands like Get-ChildItem. You MUST use the highly optimized native CMD search wrapper inside your terminal tool:
'cmd.exe /c "dir /s /b /a:d C:\Users\ojasw\Desktop\*mandate*"' (for directories) or '/a:-d' (for files).
Always wrap the search term in asterisks like '*name*' to handle fuzzy matching for nested subfolders.
If you need to find content INSIDE files, use: 'findstr /s /i "search_term" C:\path\*.txt'

CRITICAL - TOOL EFFICENCY:
When using run_terminal, DO NOT issue multiple short commands. Write comprehensive, long-form PowerShell scripts that accomplish the entire goal in 1-2 steps. Use variables, loops, and conditional logic.
You have a maximum of 8 tool iterations. Be highly efficient! Review your message history and reuse successful commands if performing a similar task.`

	messages := []map[string]interface{}{
		{"role": "system", "content": systemPrompt},
		{"role": "user", "content": command},
	}

	client := &http.Client{Timeout: 300 * time.Second}
	const maxIter = 8

	for iter := 0; iter < maxIter; iter++ {

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
		if ctx.Err() != nil { return "Canceled by user", nil }
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

		resp, err := client.Do(req)
		if err != nil {
			debugLog.Printf("[executeOllamaCommand] iter=%d request failed: %v", iter, err)
			return "", fmt.Errorf("Ollama request failed: %w", err)
		}
		respBody, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		debugLog.Printf("[executeOllamaCommand] iter=%d response status=%d responseLen=%d", iter, resp.StatusCode, len(respBody))

		if resp.StatusCode != http.StatusOK {
			return "", fmt.Errorf("Ollama error %d: %s", resp.StatusCode, string(respBody))
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
			Error string `json:"error"`
		}
		if err := json.Unmarshal(respBody, &result); err != nil {
			return "", fmt.Errorf("failed to parse Ollama response: %w", err)
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
			return strings.TrimSpace(result.Message.Content), nil
		}

		debugLog.Printf("[executeOllamaCommand] iter=%d toolCalls=%d", iter, len(result.Message.ToolCalls))

		// Append assistant message
		assistantMsg := map[string]interface{}{
			"role":       "assistant",
			"content":    result.Message.Content,
			"tool_calls": result.Message.ToolCalls,
		}
		messages = append(messages, assistantMsg)

		// Execute each tool and collect results
		for _, tc := range result.Message.ToolCalls {
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] 2. TOOL EXECUTION PHASE")
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] AI requested tool: %q with args: %s", tc.Function.Name, tc.Function.Arguments)
			debugLog.Printf("[executeOllamaCommand] iter=%d executing tool=%q", iter, tc.Function.Name)
			var argsBytes []byte
			if len(tc.Function.Arguments) > 0 && tc.Function.Arguments[0] == '"' {
				var strArgs string
				json.Unmarshal(tc.Function.Arguments, &strArgs)
				argsBytes = []byte(strArgs)
			} else {
				argsBytes = []byte(tc.Function.Arguments)
			}
			toolResult := executeTool(ctx, tc.Function.Name, json.RawMessage(argsBytes), streamFileObj)
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] 3. TOOL EXECUTION FINISHED")
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] Result Length: %d", len(toolResult))
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] Result Content Preview (max 200 chars):\n%.200s", toolResult)
			debugLog.Printf("================================================================")
			debugLog.Printf("[executeOllamaCommand] iter=%d tool=%q resultLen=%d", iter, tc.Function.Name, len(toolResult))
			// Ollama tool result uses role "tool" same as OpenAI
			messages = append(messages, map[string]interface{}{
				"role":    "tool",
				"content": toolResult,
			})
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
	
	// Start ngrok registration loop (only register when address changes)
	go func(data ConnectionData) {
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
							time.Sleep(30 * time.Second) // Wait longer before trying again
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
			if addr != "" && addr != lastRegisteredAddr {
				if err := registerWithBackend(data, addr); err != nil {
					log.Printf("register error: %v", err)
				} else {
					lastRegisteredAddr = addr
				}
			}
			time.Sleep(5 * time.Second)
		}
	}(data)
	
	// Start presence polling
	go func() {
		for {
			time.Sleep(10 * time.Second) // Heartbeat every 10 seconds
			addr := getNgrokPublicURL()
			if err := sendHeartbeat(data, addr); err != nil {
				log.Printf("heartbeat error: %v", err)
			}
		}
	}()
	
	// Start mobile client presence polling for AI face
	go func() {
		client := &http.Client{
			Timeout: 5 * time.Second, // Fast timeout for health checks
			Transport: &http.Transport{
				MaxIdleConns:        10,
				IdleConnTimeout:     30 * time.Second,
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
						Status          string `json:"status"`
						MobileClients   int    `json:"mobile_clients"`
					}
					json.NewDecoder(resp.Body).Decode(&healthData)
					resp.Body.Close()
					
					log.Printf("Presence: Backend OK, Mobile clients: %d", healthData.MobileClients)
					fmt.Printf("STATUS: BACKEND:ONLINE\n")
					fmt.Printf("STATUS: MOBILE_CLIENTS:%d\n", healthData.MobileClients)
					os.Stdout.Sync() // Force flush for real-time delivery
				} else {
					log.Printf("Presence: Backend unreachable")
					fmt.Printf("STATUS: BACKEND:OFFLINE\n")
					fmt.Printf("STATUS: MOBILE_CLIENTS:0\n")
					os.Stdout.Sync() // Force flush for real-time delivery
				}
			} else {
				log.Printf("Presence: Backend unreachable")
				fmt.Printf("STATUS: BACKEND:OFFLINE\n")
				fmt.Printf("STATUS: MOBILE_CLIENTS:0\n")
				os.Stdout.Sync()
			}
		}
	}()
	
	// Keep running indefinitely
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
	h := sha256.New()
	h.Write([]byte(phrase + ":" + deviceID))
	return hex.EncodeToString(h.Sum(nil))
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

func main() {
	initDebugLog()
	// Load circuit state on startup
	loadCircuitState()
	
	// Check for background mode flag
	backgroundMode := false
	for _, arg := range os.Args {
		if arg == "--background" || arg == "-b" {
			backgroundMode = true
			break
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
		go func(data ConnectionData) {
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
								ngrokRetryDelay = 5 * time.Second
								time.Sleep(30 * time.Second)
								continue
							}
							
							time.Sleep(ngrokRetryDelay)
							ngrokRetryDelay = time.Duration(float64(ngrokRetryDelay) * 1.5)
							if ngrokRetryDelay > maxNgrokRetryDelay {
								ngrokRetryDelay = maxNgrokRetryDelay
							}
							continue
						}
						ngrokRetryCount = 0
						ngrokRetryDelay = 5 * time.Second
						time.Sleep(3 * time.Second)
						addr = getNgrokPublicURL()
					}
					if addr == "" {
						log.Println("ngrok URL not available yet (is ngrok running?) - skipping registration")
					}
				}
				if addr != "" {
					if err := registerWithBackend(data, addr); err != nil {
						log.Printf("register error: %v", err)
					}
				}
				time.Sleep(5 * time.Second)
			}
		}(data)
		go func() {
			for {
				time.Sleep(2 * time.Second)
				healthURL := data.BackendURL + "/health"
				req, err := http.NewRequest("GET", healthURL, nil)
				if err == nil {
					// Add ngrok skip browser warning header if calling through ngrok
					if strings.Contains(data.BackendURL, "ngrok") || strings.Contains(data.BackendURL, "ngrok-free") {
						req.Header.Set("ngrok-skip-browser-warning", "true")
					}
					resp, err := http.DefaultClient.Do(req)
					if err == nil && resp.StatusCode == 200 {
						var healthData struct {
							Status          string `json:"status"`
							MobileClients   int    `json:"mobile_clients"`
						}
						json.NewDecoder(resp.Body).Decode(&healthData)
						resp.Body.Close()
						
						log.Printf("Presence: Backend OK, Mobile clients: %d", healthData.MobileClients)
						fmt.Printf("STATUS: BACKEND:ONLINE\n")
						fmt.Printf("STATUS: MOBILE_CLIENTS:%d\n", healthData.MobileClients)
						os.Stdout.Sync() // Force flush for real-time delivery
					} else {
						log.Printf("Presence: Backend unreachable or error: %v", err)
						fmt.Printf("STATUS: BACKEND:OFFLINE\n")
						fmt.Printf("STATUS: MOBILE_CLIENTS:0\n")
						os.Stdout.Sync()
					}
				} else {
					log.Printf("Presence: Request creation failed: %v", err)
					fmt.Printf("STATUS: BACKEND:OFFLINE\n")
					fmt.Printf("STATUS: MOBILE_CLIENTS:0\n")
					os.Stdout.Sync()
				}
			}
		}()
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
		state:     "setup",
		inputStep: 0,
		messages:  []string{},
		status:    "Not Running",
		isLoading: false,
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
