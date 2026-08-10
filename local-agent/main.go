package main

import (
	"bytes"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// Styles
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
    __  __          _      __  __ _____    _ 
   / / / /___  ____| | /| / / / /__  __| |
  / /_/ / __ \/ __ \ |/ |/ / / / _ \/ __| |
 / __  / /_/ / / / / /|  / / /  __/ /_| | 
/_/ /_/\____/_/ /_/_/ |_/_/_/_/\___\__,_| 
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
║         ANTIGRAVITY - LOCAL AGENT MENU         ║
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
	BackendURL     string `json:"backend_url"`
	DeviceID       string `json:"device_id"`
	DeviceName     string `json:"device_name"`
	Passphrase     string `json:"passphrase"`
	SecurityPhrase string `json:"security_phrase"`
	DeviceFingerprint string `json:"device_fingerprint"`
	Connected      bool   `json:"connected"`
	LastConnected   string `json:"last_connected"`
}

// Model
type model struct {
	state          string // "setup", "connected", "menu", "loading"
	connectionData ConnectionData
	inputStep      int // 0: backend, 1: device name, 2: passphrase, 3: security phrase
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
			}
		case tea.KeyEnter:
			return m.handleEnter()
		case tea.KeyUp:
			if m.state == "menu" {
				m.selectedOption = (m.selectedOption - 1 + 4) % 4
			}
		case tea.KeyDown:
			if m.state == "menu" {
				m.selectedOption = (m.selectedOption + 1) % 4
			}
		case tea.KeyBackspace:
			if len(m.currentInput) > 0 {
				m.currentInput = m.currentInput[:len(m.currentInput)-1]
			}
		case tea.KeyCtrlV:
			// Handle clipboard paste
			if m.state == "setup" {
				// Try to get clipboard content
				cmd := exec.Command("powershell", "-Command", "Get-Clipboard")
				output, err := cmd.Output()
				if err == nil {
					pastedText := strings.TrimSpace(string(output))
					m.currentInput += pastedText
				}
			}
		default:
			if m.state == "setup" && len(msg.String()) >= 1 {
				m.currentInput += msg.String()
			}
		}
	case connectionResultMsg:
		m.isLoading = false
		if msg.success {
			m.state = "connected"
			m.connectionData.Connected = true
			m.connectionData.LastConnected = time.Now().Format(time.RFC3339)
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
			m.connectionData.Passphrase = m.currentInput
			m.inputStep = 3
			m.currentInput = ""
		case 3:
			m.connectionData.SecurityPhrase = m.currentInput
			// Generate device fingerprint for MITM prevention
			if m.connectionData.DeviceFingerprint == "" {
				m.connectionData.DeviceFingerprint = generateDeviceFingerprint()
			}
			m.isLoading = true
			return m, m.testConnection()
		}
	} else if m.state == "connected" {
		m.state = "menu"
		m.selectedOption = 0
	} else if m.state == "menu" {
		backgroundRunning := isBackgroundServiceRunning()
		
		switch m.selectedOption {
		case 0: // Stop Service / Stop Background Service
			if backgroundRunning {
				// Stop background service by killing the process
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
		case 2: // View Status
			m.status = fmt.Sprintf("Status: %s | Connected: %v", m.status, m.connectionData.Connected)
		case 3: // Exit
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
		
		// Register device with backend including fingerprint
		deviceData := map[string]interface{}{
			"device_id":    m.connectionData.DeviceID,
			"device_name":  m.connectionData.DeviceName,
			"fingerprint": m.connectionData.DeviceFingerprint,
			"type":         "desktop",
		}
		jsonData, _ := json.Marshal(deviceData)
		resp, err = http.Post(m.connectionData.BackendURL+"/register", "application/json", bytes.NewBuffer(jsonData))
		if err != nil {
			// Registration failed but connection succeeded
			return connectionResultMsg{success: true, message: "Connection successful (registration skipped)"}
		}
		defer resp.Body.Close()
		
		return connectionResultMsg{success: true, message: "Connection successful"}
	}
}

func (m model) startServer() tea.Cmd {
	return func() tea.Msg {
		go startHTTPServer(m.connectionData.Passphrase)

		go func(data ConnectionData) {
			for {
				addr := getNgrokPublicURL()
				if addr == "" {
					log.Println("ngrok URL not available yet (is ngrok running?)")
				} else if err := registerWithBackend(data, addr); err != nil {
					log.Printf("register error: %v", err)
				}
				time.Sleep(30 * time.Second)
			}
		}(m.connectionData)

		return serverStatusMsg{running: true}
	}
}

func (m model) stopServer() tea.Cmd {
	return func() tea.Msg {
		// Stop the HTTP server
		stopHTTPServer()
		return serverStatusMsg{running: false}
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
	}

	return m.wrapContent(content)
}

func (m model) setupView() string {
	var content strings.Builder

	content.WriteString(asciiArtStyle.Render(logoArt))
	content.WriteString("\n\n")
	content.WriteString(titleStyle.Render("Antigravity - Local Agent Setup"))
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
		content.WriteString("Passphrase: ")
		content.WriteString(inputStyle.Render(strings.Repeat("*", len(m.currentInput)) + "_"))
		content.WriteString("\n\n")
		content.WriteString(subtitleStyle.Render("Enter your secure passphrase"))
	case 3:
		content.WriteString("Backend URL: ")
		content.WriteString(successStyle.Render(m.connectionData.BackendURL))
		content.WriteString("\n\n")
		content.WriteString("Device Name: ")
		content.WriteString(successStyle.Render(m.connectionData.DeviceName))
		content.WriteString("\n\n")
		content.WriteString("Passphrase: ")
		content.WriteString(successStyle.Render(strings.Repeat("*", len(m.connectionData.Passphrase))))
		content.WriteString("\n\n")
		content.WriteString("Security Phrase: ")
		content.WriteString(inputStyle.Render(m.currentInput + "_"))
		content.WriteString("\n\n")
		content.WriteString(subtitleStyle.Render("Enter phrase to verify your identity"))
		content.WriteString("\n")
		content.WriteString(subtitleStyle.Render("This phrase will be required for new sessions"))
	}

	if m.isLoading {
		content.WriteString("\n\n")
		content.WriteString(warningStyle.Render(loadingArt))
	}

	if len(m.messages) > 0 {
		content.WriteString("\n\n")
		for _, msg := range m.messages {
			content.WriteString(msg + "\n")
		}
	}

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
	
	// Connection progress
	if m.connectionData.Connected {
		content.WriteString(successStyle.Render(progressBarConnected))
	} else {
		content.WriteString(errorStyle.Render(progressBarDisconnected))
	}
	content.WriteString("\n\n")
	
	content.WriteString(statusStyle.Render(fmt.Sprintf("Status: %s", m.status)))
	
	// Show background service status
	if isBackgroundServiceRunning() {
		content.WriteString("\n\n")
		content.WriteString(successStyle.Render("● Background service running"))
	}
	
	content.WriteString("\n\n")
	content.WriteString(separatorStyle.Render(separatorLine))
	content.WriteString("\n\n")

	options := []string{
		"⏯  Stop/Start Service",
		"🗑  Delete Connection",
		"📊 View Status",
		"🚪 Exit",
	}
	
	// Add option to stop background service if running
	if isBackgroundServiceRunning() {
		options = []string{
			"⏯  Stop Background Service",
			"🗑  Delete Connection",
			"📊 View Status",
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

// HTTP Server
var server *http.Server
var serverRunning bool


func getNgrokPublicURL() string {
	resp, err := http.Get("http://127.0.0.1:4040/api/tunnels")
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

func startHTTPServer(passphrase string) {
	if serverRunning {
		return
	}

	mux := http.NewServeMux()

	mux.HandleFunc("/auth", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req map[string]string
		json.NewDecoder(r.Body).Decode(&req)

		if req["passphrase"] == passphrase {
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]string{"status": "authenticated"})
		} else {
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{"status": "unauthorized"})
		}
	})

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "mode": "background"})
	})

	mux.HandleFunc("/execute", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req map[string]string
		json.NewDecoder(r.Body).Decode(&req)

		command := req["command"]
		output, err := executeCommand(command)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
			return
		}

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"output": output})
	})

	server = &http.Server{    
		Addr:    ":8088",
		Handler: mux,
	}

	serverRunning = true
	log.Println("Local agent server starting on :8088")
	server.ListenAndServe()
}

func stopHTTPServer() {
	if server != nil && serverRunning {
		server.Shutdown(nil)
		serverRunning = false
		log.Println("Local agent server stopped")
	}
}

func executeCommand(command string) (string, error) {
	var cmd *exec.Cmd

	if runtime.GOOS == "windows" {
		cmd = exec.Command("powershell", "-Command", command)
	} else {
		cmd = exec.Command("sh", "-c", command)
	}

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		return stderr.String(), err
	}

	return stdout.String(), nil
}

// Save/Load connection data
func saveConnectionData(data ConnectionData) error {
	file, err := os.Create("connection_data.json")
	if err != nil {
		return err
	}
	defer file.Close()

	return json.NewEncoder(file).Encode(data)
}

func registerWithBackend(data ConnectionData, publicAddress string) error {
	secret := os.Getenv("AGENT_REGISTER_SECRET")
	if secret == "" {
		// fallback: same secret you configured in agent setup / connection_data if you store it
		return fmt.Errorf("AGENT_REGISTER_SECRET not set")
	}

	body, _ := json.Marshal(map[string]string{
		"device_id":    data.DeviceID,
		"device_name":  data.DeviceName,
		"address":      publicAddress, // ngrok https URL, no trailing path
		"fingerprint":  data.DeviceFingerprint,
		"type":         "desktop",
	})

	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(data.BackendURL, "/")+"/register", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Agent-Secret", secret)
	
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
		return fmt.Errorf("register failed: %s", resp.Status)
	}
	log.Printf("Registered with backend as %s @ %s", data.DeviceID, publicAddress)
	return nil
}

func loadConnectionData() (ConnectionData, error) {
	file, err := os.Open("connection_data.json")
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
	exePath := filepath.Join(execDir, "antigravity")
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
	taskName := "AntigravityVoiceCLI"
	
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
    <string>com.voicecli.antigravity</string>
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
	
	plistPath := filepath.Join(launchAgentsDir, "com.voicecli.antigravity.plist")
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
Description=Antigravity Voice CLI Agent
After=network.target

[Service]
Type=simple
ExecStart=%s --background
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
`, exePath)
	
	servicePath := filepath.Join(systemdDir, "antigravity.service")
	if err := os.WriteFile(servicePath, []byte(serviceContent), 0644); err != nil {
		return fmt.Errorf("failed to create systemd service: %w", err)
	}
	
	// Enable and start the service
	exec.Command("systemctl", "--user", "daemon-reload").Run()
	exec.Command("systemctl", "--user", "enable", "antigravity.service").Run()
	
	log.Printf("Auto-start configured: %s", servicePath)
	return nil
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
	
	log.Printf("Starting Antigravity in background mode...")
	log.Printf("Backend: %s", data.BackendURL)
	log.Printf("Device: %s (%s)", data.DeviceName, data.DeviceID)
	
	// Start HTTP server
	go startHTTPServer(data.Passphrase)
	
	// Start ngrok registration loop
	go func(data ConnectionData) {
		for {
			addr := getNgrokPublicURL()
			if addr == "" {
				log.Println("ngrok URL not available yet (is ngrok running?)")
			} else if err := registerWithBackend(data, addr); err != nil {
				log.Printf("register error: %v", err)
			}
			time.Sleep(30 * time.Second)
		}
	}(data)
	
	// Start presence polling
	go func() {
		for {
			time.Sleep(20 * time.Second)
			healthURL := data.BackendURL + "/health"
			req, err := http.NewRequest("GET", healthURL, nil)
			if err == nil {
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
				} else {
					log.Printf("Presence: Backend unreachable")
				}
			} else {
				log.Printf("Presence: Backend unreachable")
			}
		}
	}()
	
	// Keep running indefinitely
	select {}
}

func stopBackgroundService() {
	if runtime.GOOS == "windows" {
		exec.Command("taskkill", "/F", "/IM", "antigravity.exe").Run()
	} else if runtime.GOOS == "darwin" {
		exec.Command("launchctl", "unload", filepath.Join(os.Getenv("HOME"), "Library", "LaunchAgents", "com.voicecli.antigravity.plist")).Run()
	} else {
		exec.Command("systemctl", "--user", "stop", "antigravity.service").Run()
	}
	log.Println("Background service stop command executed")
}

func isBackgroundServiceRunning() bool {
	// Simple check: try to connect to the local HTTP server
	resp, err := http.Get("http://localhost:8088/health")
	if err == nil && resp.StatusCode == 200 {
		resp.Body.Close()
		return true
	}
	return false
}

// Main
func main() {
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
	if isBackgroundServiceRunning() {
		log.Println("Background service already running. Launching TUI in management mode...")
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
		go startHTTPServer(data.Passphrase)
		go func(data ConnectionData) {
			for {
				addr := getNgrokPublicURL()
				if addr == "" {
					log.Println("ngrok URL not available yet (is ngrok running?)")
				} else if err := registerWithBackend(data, addr); err != nil {
					log.Printf("register error: %v", err)
				}
				time.Sleep(30 * time.Second)
			}
		}(data)
		go func() {
			for {
				time.Sleep(20 * time.Second)
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
					} else {
						log.Printf("Presence: Backend unreachable")
					}
				} else {
					log.Printf("Presence: Backend unreachable")
				}
			}
		}()
		p := tea.NewProgram(initialModel)
		if _, err := p.Run(); err != nil {
			log.Fatalf("Error running program: %v", err)
		}
		return
	} else {
		log.Printf("Setup required. Error: %v, Connected: %v, SecurityPhrase: %v", err, data.Connected, data.SecurityPhrase != "")
	}

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
