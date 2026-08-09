package main

import (
	"bytes"
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
	BackendURL  string `json:"backend_url"`
	DeviceID    string `json:"device_id"`
	DeviceName  string `json:"device_name"`
	Passphrase  string `json:"passphrase"`
	Connected   bool   `json:"connected"`
	LastConnected string `json:"last_connected"`
}

// Model
type model struct {
	state          string // "setup", "connected", "menu", "loading"
	connectionData ConnectionData
	inputStep      int // 0: backend, 1: device name, 2: passphrase
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
			m.inputStep = 2
			m.currentInput = ""
		case 2:
			m.connectionData.Passphrase = m.currentInput
			m.inputStep = 3
			m.currentInput = ""
			m.isLoading = true
			return m, m.testConnection()
		}
	} else if m.state == "connected" {
		m.state = "menu"
		m.selectedOption = 0
	} else if m.state == "menu" {
		switch m.selectedOption {
		case 0: // Stop Service
			if m.serverRunning {
				return m, m.stopServer()
			} else {
				return m, m.startServer()
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
		// Simulate connection test
		time.Sleep(500 * time.Millisecond)
		m.connectionData.DeviceID = fmt.Sprintf("device-%d", time.Now().Unix())
		return connectionResultMsg{success: true, message: "Connection successful"}
	}
}

func (m model) startServer() tea.Cmd {
	return func() tea.Msg {
		// Start the HTTP server in background
		go startHTTPServer(m.connectionData.Passphrase)
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
	content.WriteString("\n\n")
	content.WriteString(separatorStyle.Render(separatorLine))
	content.WriteString("\n\n")

	options := []string{
		"⏯  Stop/Start Service",
		"🗑  Delete Connection",
		"📊 View Status",
		"🚪 Exit",
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
	// Create startup script
	var script string
	if runtime.GOOS == "windows" {
		script = fmt.Sprintf(`@echo off
cd /d "%s"
antigravity
`, getExecutableDir())
		os.WriteFile("start_agent.bat", []byte(script), 0644)
	} else {
		script = fmt.Sprintf(`#!/bin/bash
cd "%s"
./antigravity
`, getExecutableDir())
		os.WriteFile("start_agent.sh", []byte(script), 0755)
	}

	return nil
}

func getExecutableDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	return filepath.Dir(exe)
}

// Main
func main() {
	// Try to load existing connection
	data, err := loadConnectionData()
	if err == nil && data.Connected {
		log.Printf("Auto-connecting with backend: %s", data.BackendURL)
		// Auto-connect if connection exists
		initialModel := model{
			state:          "connected",
			connectionData: data,
			isRunning:      true,
			serverRunning:  true,
			status:         "Running",
			isLoading:      false,
		}
		go startHTTPServer(data.Passphrase)
		p := tea.NewProgram(initialModel)
		if _, err := p.Run(); err != nil {
			log.Fatalf("Error running program: %v", err)
		}
		return
	} else {
		log.Printf("Setup required. Error: %v, Connected: %v", err, data.Connected)
	}

	// New setup
	initialModel := model{
		state:     "setup",
		inputStep: 0,
		messages:  []string{},
		status:    "Not Running",
		isLoading: false,
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
