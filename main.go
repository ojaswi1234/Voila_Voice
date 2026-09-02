package main

import (
	"bytes"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"
	"github.com/gorilla/websocket"
)

var sessionSigningKey []byte

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

const (
	// Time allowed to write a message to the peer.
	writeWait = 10 * time.Second

	// Time allowed to read the next pong message from the peer.
	pongWait = 60 * time.Second

	// Send pings to peer with this period. Must be less than pongWait.
	pingPeriod = (pongWait * 9) / 10

	// Maximum message size allowed from peer (512KB — AI responses can be large).
	maxMessageSize = 512 * 1024
)

const deviceOnlineTTL = 60 * time.Second
const mockCommandThreshold = 3 // Trip breaker after N mock commands
const maxAlerts = 100 // Ring buffer size

type SecurityAlert struct {
	ID        string
	Type      string // mock_command | auth_fail | rate_limit | breaker_open | breaker_close
	Timestamp time.Time
	IP        string
	Geo       string // optional
	DeviceID  string
	ClientID  string
	Detail    string
	Severity  string // low|medium|high
}

type Device struct {
	ID        string
	Name      string
	Address   string
	Active    bool
	LastSeen  time.Time
	AuthToken string
	LockedBy  string // Mobile device ID that has exclusive access
	LockedAt  time.Time
	Fingerprint string
	Type        string
	Reachable   bool
	LastPing    time.Time
	SecurityPhraseHash string // Hashed security phrase
	UnlockFailures int
	ClearFailures  int
	CircuitOpen bool // Circuit breaker state
}

type Backend struct {
	devices      map[string]*Device
	activeDevice string
	tokenCounter int
	mu           sync.RWMutex
	clients      map[string]*WebSocketClient
	ipRateLimits map[string]int // IP -> failures
	// Bug #17 Fix: True circular ring buffer - no O(N) reallocation
	securityAlerts    [maxAlerts]SecurityAlert
	alertHead         int // index of oldest alert
	alertCount        int // how many slots are filled
	mockCommandCounts map[string]int // deviceID -> count
}

type WebSocketClient struct {
	conn        *websocket.Conn
	clientID    string
	connectedAt time.Time
	writeMu     sync.Mutex
}

func NewBackend() *Backend {
	b := &Backend{
		devices:           make(map[string]*Device),
		activeDevice:      "",
		tokenCounter:      0,
		clients:           make(map[string]*WebSocketClient),
		ipRateLimits:      make(map[string]int),
		mockCommandCounts: make(map[string]int),
	}
	
	// Start presence ticker
	go b.startPresenceTicker()
	
	return b
}


func safeHTTPClient() *http.Client {
	return &http.Client{
		Timeout: 10 * time.Second, // Reduced from 120s for faster failure detection
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
		Transport: &http.Transport{
			MaxIdleConns:        100,
			IdleConnTimeout:     90 * time.Second,
			DisableCompression: true,
		},
	}
}

func hashPhrase(phrase, deviceID string) string {
	h := sha256.New()
	h.Write([]byte(phrase + ":" + deviceID))
	return hex.EncodeToString(h.Sum(nil))
}

func stripPort(ip string) string {
	host, _, err := net.SplitHostPort(ip)
	if err != nil {
		return ip
	}
	return host
}

func (b *Backend) addSecurityAlert(alertType, ip, deviceID, clientID, detail, severity string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	alert := SecurityAlert{
		ID:        fmt.Sprintf("alert-%d", time.Now().UnixNano()),
		Type:      alertType,
		Timestamp: time.Now(),
		IP:        stripPort(ip),
		Geo:       "", // Empty unless geo service added
		DeviceID:  deviceID,
		ClientID:  clientID,
		Detail:    detail,
		Severity:  severity,
	}
	
	// Bug #17 Fix: True O(1) circular ring buffer write — no slice reallocation
	writeIdx := (b.alertHead + b.alertCount) % maxAlerts
	b.securityAlerts[writeIdx] = alert
	if b.alertCount < maxAlerts {
		b.alertCount++
	} else {
		// Buffer full — advance head to overwrite oldest
		b.alertHead = (b.alertHead + 1) % maxAlerts
	}
	
	// Push to all connected mobile clients
	b.broadcastSecurityAlert(alert)
}

func (b *Backend) broadcastSecurityAlert(alert SecurityAlert) {
	alertBytes, _ := json.Marshal(map[string]interface{}{
		"type": "security_alert",
		"alert": alert,
	})
	
	for clientID := range b.clients {
		b.writeMessage(clientID, websocket.TextMessage, alertBytes)
	}
}

func (b *Backend) broadcastDevices() {
	b.mu.RLock()
	devices := make([]*Device, 0, len(b.devices))
	for _, d := range b.devices {
		devices = append(devices, d)
	}
	
	// Safely collect client IDs while locked
	var clientIDs []string
	for cid := range b.clients {
		clientIDs = append(clientIDs, cid)
	}
	b.mu.RUnlock()

	deviceList := make([]map[string]interface{}, 0)
	for _, d := range devices {
		deviceList = append(deviceList, map[string]interface{}{
			"id":          d.ID,
			"name":        d.Name,
			"active":      d.ID == b.activeDevice,
			"online":      d.Active,
			"reachable":   d.Reachable,
			"locked":      d.LockedBy != "",
			"lockedBy":    d.LockedBy,
			"lastSeen":    d.LastSeen,
			"lastPing":    d.LastPing,
			"fingerprint": d.Fingerprint,
			"type":        d.Type,
		})
	}
	jsonData, _ := json.Marshal(deviceList)

	// Send concurrently so one slow/blocked client doesn't stall the rest
	var wg sync.WaitGroup
	for _, clientID := range clientIDs {
		wg.Add(1)
		go func(cid string) {
			defer wg.Done()
			b.writeMessage(cid, websocket.TextMessage, jsonData)
		}(clientID)
	}
	wg.Wait()
}

func (b *Backend) tripCircuitBreaker(deviceID string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	if device, exists := b.devices[deviceID]; exists {
		if !device.CircuitOpen {
			device.CircuitOpen = true
			b.addSecurityAlert("breaker_open", "", deviceID, "", fmt.Sprintf("Circuit breaker tripped for device %s", deviceID), "high")
			
			// Notify agent via HTTP POST
			go b.notifyAgentCircuit(device.Address, "open")
		}
	}
}

func (b *Backend) notifyAgentCircuit(agentAddress, state string) {
	client := safeHTTPClient()
	reqBody := map[string]string{"state": state}
	bodyBytes, _ := json.Marshal(reqBody)
	
	req, _ := http.NewRequest(http.MethodPost, agentAddress+"/circuit", bytes.NewBuffer(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	
	// Find device by address to get secret hash
	b.mu.RLock()
	var secret string
	for _, device := range b.devices {
		if device.Address == agentAddress {
			secret = device.SecurityPhraseHash
			break
		}
	}
	b.mu.RUnlock()
	
	if secret != "" {
		req.Header.Set("X-Exec-Secret", secret)
	}
	
	client.Do(req)
}

func (b *Backend) resetCircuitBreaker(deviceID string) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	if device, exists := b.devices[deviceID]; exists {
		if device.CircuitOpen {
			device.CircuitOpen = false
			b.mockCommandCounts[deviceID] = 0 // Reset mock count
			b.addSecurityAlert("breaker_close", "", deviceID, "", fmt.Sprintf("Circuit breaker reset for device %s", deviceID), "medium")
			return true
		}
	}
	return false
}

func (b *Backend) generateMockResponse(command string) string {
	// Plausible fake shell responses
	cmdLower := strings.ToLower(strings.TrimSpace(command))
	
	if strings.Contains(cmdLower, "whoami") {
		return "user\\voila-desktop"
	}
	if strings.Contains(cmdLower, "dir") || strings.Contains(cmdLower, "ls") {
		return "Documents  Downloads  Desktop  Pictures  Music  Videos"
	}
	if strings.Contains(cmdLower, "pwd") {
		return "C:\\Users\\voila"
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


func getSessionSigningKey() []byte {
	if len(sessionSigningKey) > 0 {
		return sessionSigningKey
	}
	key := os.Getenv("SESSION_SIGNING_KEY")
	if key != "" {
		sessionSigningKey = []byte(key)
		return sessionSigningKey
	}
	// Generate random 32-byte key
	sessionSigningKey = make([]byte, 32)
	rand.Read(sessionSigningKey)
	return sessionSigningKey
}

func createSessionToken(deviceID, clientID string) (string, int64) {
	secret := getSessionSigningKey()
	expiryTime := time.Now().Add(15 * time.Minute)
	payload := map[string]interface{}{
		"sid": fmt.Sprintf("sess-%d", time.Now().UnixNano()),
		"device_id": deviceID,
		"client_device_id": clientID,
		"iat": time.Now().Unix(),
		"exp": expiryTime.Unix(),
	}
	payloadBytes, _ := json.Marshal(payload)
	payloadB64 := base64.URLEncoding.EncodeToString(payloadBytes)
	
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(payloadB64))
	sig := hex.EncodeToString(mac.Sum(nil))
	
	return payloadB64 + "." + sig, expiryTime.Unix()
}

func verifySessionToken(token, expectedDeviceID string) bool {
	if token == "" {
		return false
	}
	parts := strings.Split(token, ".")
	if len(parts) != 2 {
		return false
	}
	payloadB64 := parts[0]
	sig := parts[1]
	
	secret := getSessionSigningKey()
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(payloadB64))
	expectedSig := hex.EncodeToString(mac.Sum(nil))
	
	if !hmac.Equal([]byte(sig), []byte(expectedSig)) {
		return false
	}
	
	payloadBytes, err := base64.URLEncoding.DecodeString(payloadB64)
	if err != nil {
		return false
	}
	var payload map[string]interface{}
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		return false
	}
	
	exp, ok := payload["exp"].(float64)
	if !ok || time.Now().Unix() > int64(exp) {
		return false // expired
	}
	
	devID, ok := payload["device_id"].(string)
	if !ok || devID != expectedDeviceID {
		return false
	}
	return true
}

func isValidAddress(addr string) bool {
	u, err := url.Parse(addr)
	if err != nil {
		return false
	}
	if u.Scheme != "https" && u.Scheme != "http" {
		return false
	}
	host := u.Hostname()
	
	// Deny local / private
	if host == "localhost" || host == "127.0.0.1" || strings.HasPrefix(host, "192.168.") || strings.HasPrefix(host, "10.") || strings.HasPrefix(host, "169.254.") {
		if os.Getenv("NGROK_AUTO_DETECT") != "true" {
			return false
		}
	}
	
	suffixes := os.Getenv("ALLOWED_AGENT_HOST_SUFFIXES")
	if suffixes == "" {
		suffixes = ".ngrok-free.dev,.ngrok-free.app,.ngrok.app,.ngrok.io"
	}
	allowed := strings.Split(suffixes, ",")
	for _, suffix := range allowed {
		if strings.HasSuffix(host, strings.TrimSpace(suffix)) {
			return true
		}
	}
	if os.Getenv("NGROK_AUTO_DETECT") == "true" && (host == "localhost" || host == "127.0.0.1") {
		return true
	}
	return false
}

func (b *Backend) markStaleDevices() {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	now := time.Now()
	changed := false
	for id, device := range b.devices {
		if device.Type == "desktop" || strings.HasPrefix(device.ID, "desktop-") {
			wasActive := device.Active
			device.Active = now.Sub(device.LastSeen) < deviceOnlineTTL
			if wasActive && !device.Active {
				log.Printf("Device marked offline: %s (%s) - last seen %v ago", device.Name, device.ID, now.Sub(device.LastSeen))
				changed = true
			}
			// Bug #3 Fix: Evict devices that have been offline for more than 24h to prevent map memory leak
			if !device.Active && now.Sub(device.LastSeen) > 24*time.Hour {
				log.Printf("Evicting stale device from memory: %s (%s)", device.Name, id)
				delete(b.devices, id)
				changed = true
			}
		}
	}
	
	// Bug #3 Fix: Evict stale IP rate limit entries (reset after 1h) to prevent map growth
	for ip, failures := range b.ipRateLimits {
		if failures == 0 {
			delete(b.ipRateLimits, ip)
		}
	}
	
	if changed {
		go b.broadcastDevices()
	}
}

func (b *Backend) startPresenceTicker() {
	ticker := time.NewTicker(30 * time.Second) // Reduced from 15s to reduce load
	defer ticker.Stop()
	
	for range ticker.C {
		b.markStaleDevices()
		b.pingAllDevices()
	}
}

func (b *Backend) pingAllDevices() {
	b.mu.RLock()
	devices := make([]*Device, 0, len(b.devices))
	for _, d := range b.devices {
		devices = append(devices, d)
	}
	b.mu.RUnlock()

	// Bug #2 Fix: Use a semaphore to cap concurrency at 50 to prevent port exhaustion
	const maxConcurrentPings = 50
	sem := make(chan struct{}, maxConcurrentPings)
	var wg sync.WaitGroup
	for _, device := range devices {
		wg.Add(1)
		sem <- struct{}{} // acquire slot
		go func(d *Device) {
			defer wg.Done()
			defer func() { <-sem }() // release slot
			b.pingDevice(d)
		}(device)
	}
	wg.Wait()
}

func (b *Backend) pingDevice(device *Device) {
	if device.Address == "" {
		return
	}
	
	// Ping device's HTTP endpoint with timeout
	client := safeHTTPClient()
	
	req, err := http.NewRequest("GET", strings.TrimRight(device.Address, "/") + "/health", nil)
	if err == nil {
		req.Header.Set("ngrok-skip-browser-warning", "true")
	}
	
	resp, err := client.Do(req)
	if err != nil {
		// Fast failure - don't lock if request failed
		b.mu.Lock()
		if d, exists := b.devices[device.ID]; exists {
			d.LastPing = time.Now()
			wasReachable := d.Reachable
			d.Reachable = false
			if wasReachable {
				go b.broadcastDevices()
			}
		}
		b.mu.Unlock()
		return
	}
	defer resp.Body.Close()
	
	b.mu.Lock()
	defer b.mu.Unlock()
	
	if d, exists := b.devices[device.ID]; exists {
		d.LastPing = time.Now()
		wasReachable := d.Reachable
		if resp.StatusCode == 200 {
			d.Reachable = true
		} else {
			d.Reachable = false
		}
		if wasReachable != d.Reachable {
			go b.broadcastDevices()
		}
	}
}

func (b *Backend) optimizeCommand(command string) string {
	b.mu.Lock()
	b.tokenCounter++
	b.mu.Unlock()
	
	// Simple command optimization patterns
	optimizations := map[string]string{
		"start the local development server": "npm run dev",
		"start dev server":                  "npm run dev",
		"run tests":                         "npm test",
		"build project":                     "npm run build",
		"check status":                      "git status",
		"pull latest":                       "git pull",
		"push changes":                      "git push",
	}
	
	// Check for exact matches
	if optimized, exists := optimizations[command]; exists {
		// log.Printf("Command optimized: '%s' -> '%s'", command, optimized)
		return optimized
	}
	
	// Simple substring matching
	for pattern, replacement := range optimizations {
		if len(command) >= len(pattern) {
			// Check if pattern is contained in command
			for i := 0; i <= len(command)-len(pattern); i++ {
				if command[i:i+len(pattern)] == pattern {
					// log.Printf("Command partially optimized: '%s' -> '%s'", command, replacement)
					return replacement
				}
			}
		}
	}
	
	return command
}

func (b *Backend) registerDevice(id, name, address string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	device := &Device{
		ID:        id,
		Name:      name,
		Address:   address,
		Active:    true,
		LastSeen:  time.Now(),
		AuthToken: generateAuthToken(),
	}
	
	b.devices[id] = device
	
	// Set as active if first device
	if b.activeDevice == "" {
		b.activeDevice = id
	}
	
	log.Printf("Device registered: %s (%s) at %s", name, id, address)
	go b.broadcastDevices()
}

func (b *Backend) setActiveDevice(deviceID string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	if _, exists := b.devices[deviceID]; !exists {
		return fmt.Errorf("device not found")
	}
	
	b.activeDevice = deviceID
		go b.broadcastDevices()
log.Printf("Active device switched to: %s", deviceID)
	return nil
}

func (b *Backend) getActiveDevice() *Device {
	b.mu.RLock()
	defer b.mu.RUnlock()
	
	if b.activeDevice == "" {
		return nil
	}
	return b.devices[b.activeDevice]
}

func (b *Backend) getAllDevices() []*Device {
	b.mu.RLock()
	defer b.mu.RUnlock()
	
	devices := make([]*Device, 0, len(b.devices))
	for _, device := range b.devices {
		devices = append(devices, device)
	}
	return devices
}

func (b *Backend) clearAllDevices() {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	count := len(b.devices)
	b.devices = make(map[string]*Device)
	b.activeDevice = ""
	b.tokenCounter = 0
	log.Printf("Cleared all devices and data (%d devices removed)", count)
	go b.broadcastDevices()
}

func (b *Backend) lockDevice(deviceID, clientID string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	device, exists := b.devices[deviceID]
	if !exists {
		return fmt.Errorf("device not found")
	}
	
	// Check if already locked by another client
	if device.LockedBy != "" && device.LockedBy != clientID {
		return fmt.Errorf("device already locked by another mobile device")
	}
	
	// Lock the device
	device.LockedBy = clientID
	device.LockedAt = time.Now()
	log.Printf("Device %s locked by client %s", deviceID, clientID)
	return nil
}

func (b *Backend) unlockDevice(deviceID, clientID string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	device, exists := b.devices[deviceID]
	if !exists {
		return fmt.Errorf("device not found")
	}
	
	// Only the client that locked can unlock
	if device.LockedBy != "" && device.LockedBy != clientID {
		return fmt.Errorf("device locked by another client")
	}
	
	device.LockedBy = ""
	device.LockedAt = time.Time{}
	log.Printf("Device %s unlocked by client %s", deviceID, clientID)
	return nil
}

func (b *Backend) isDeviceLocked(deviceID, clientID string) bool {
	b.mu.RLock()
	defer b.mu.RUnlock()
	
	device, exists := b.devices[deviceID]
	if !exists {
		return false
	}
	
	// Device is locked and client doesn't have the lock
	return device.LockedBy != "" && device.LockedBy != clientID
}

func generateAuthToken() string {
	return fmt.Sprintf("token-%d", time.Now().UnixNano())
}


func (b *Backend) stopCommand(deviceID string) (string, error) {
	b.mu.RLock()
	device, exists := b.devices[deviceID]
	if !exists {
		b.mu.RUnlock()
		return "", fmt.Errorf("device not found: %s", deviceID)
	}
	active := device.Active
	address := device.Address
	b.mu.RUnlock()

	if !active {
		return "", fmt.Errorf("device offline: %s", deviceID)
	}

	urlStr := address + "/stop"
	client := safeHTTPClient()
	req, err := http.NewRequest("POST", urlStr, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Exec-Secret", device.SecurityPhraseHash)

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("agent returned status %d", resp.StatusCode)
	}

	var result map[string]string
	json.NewDecoder(resp.Body).Decode(&result)
	
	if out, ok := result["output"]; ok {
		return out, nil
	}
	return "Command stopped", nil
}

func (b *Backend) forwardCommand(deviceID, command, mode, clientID, conversationID string) (string, error) {
	b.mu.RLock()
	device, exists := b.devices[deviceID]
	if !exists {
		b.mu.RUnlock()
		log.Printf("forwardCommand failed: device not found - %s", deviceID)
		return "", fmt.Errorf("device not found: %s", deviceID)
	}
	active := device.Active
	address := device.Address
	b.mu.RUnlock()

	if !active {
		log.Printf("forwardCommand failed: device offline - %s", deviceID)
		return "", fmt.Errorf("device offline: %s", deviceID)
	}

	// Only apply command optimization for plain SHELL mode.
	// AGENT/GROQ/OLLAMA modes send natural language — we must NOT rewrite them.
	optimizedCommand := command
	if strings.ToUpper(mode) == "SHELL" || mode == "" {
		optimizedCommand = b.optimizeCommand(command)
	}

	urlStr := address + "/execute"
	// Mode forwarding rules (preserve original design intent):
	//   "agent" from mobile → "" (desktop badge decides the AI engine)
	//   "shell" from mobile → "SHELL" (direct raw PowerShell, no AI, no visible terminal)
	//   "groq" / "ollama"  → forwarded as explicit cloud AI override
	modeUp := strings.ToUpper(mode)
	forwardMode := ""
	switch modeUp {
	case "SHELL":
		forwardMode = "SHELL"
	case "GROQ", "OLLAMA":
		forwardMode = modeUp
	// "AGENT" and anything else → "" → local agent uses desktop badge
	}
	payload := map[string]string{"command": optimizedCommand, "mode": forwardMode, "client_id": clientID, "conversation_id": conversationID}
	jsonPayload, _ := json.Marshal(payload)

	client := safeHTTPClient()
	req, err := http.NewRequest("POST", urlStr, bytes.NewBuffer(jsonPayload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Exec-Secret", device.SecurityPhraseHash)

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusAccepted {
		return "TASK_QUEUED", nil
	}
	
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("agent returned status %d", resp.StatusCode)
	}

	var result map[string]string
	json.NewDecoder(resp.Body).Decode(&result)
	
	output := result["output"]
	status := "ok"
	if errOutput, ok := result["error"]; ok && errOutput != "" {
		output += "\n" + errOutput
		status = "error"
	}
	if output == "" {
		output = "Command executed with no output."
	}
	
	summary := b.generateTaskSummary(command, output)
	
	if mode == "" {
		mode = "shell"
	}
	
	response := map[string]string{
		"output": output,
		"summary": summary,
		"status": status,
		"mode": mode,
	}
	
	jsonResponse, _ := json.Marshal(response)
	return string(jsonResponse), nil
}

func (b *Backend) generateTaskSummary(command, output string) string {
	// Simple rule-based summarization (can be enhanced with actual AI)
	summary := ""
	
	// Analyze output for success/failure patterns
	if strings.Contains(output, "ERROR") {
		summary = "❌ Command failed. Check error details above."
	} else if strings.Contains(output, "done") || strings.Contains(output, "completed") || strings.Contains(output, "success") {
		summary = "✅ Command completed successfully."
	} else if strings.Contains(command, "npm") && strings.Contains(command, "dev") {
		summary = "🚀 Development server started successfully."
	} else if strings.Contains(command, "test") {
		summary = "🧪 Tests executed. Check output for results."
	} else if strings.Contains(command, "build") {
		summary = "🔨 Build process completed."
	} else if strings.Contains(command, "git") {
		summary = "📝 Git operation completed."
	} else {
		summary = "✓ Command executed. Review output for details."
	}
	
	// Add execution context
	if len(output) > 0 {
		summary += fmt.Sprintf(" Output size: %d characters.", len(output))
	}
	
	return summary
}


func (b *Backend) writeMessage(clientID string, messageType int, data []byte) error {
	b.mu.RLock()
	client, exists := b.clients[clientID]
	b.mu.RUnlock()
	if !exists {
		return fmt.Errorf("client not found")
	}
	client.writeMu.Lock()
	defer client.writeMu.Unlock()
	return client.conn.WriteMessage(messageType, data)
}


func handleWebhookResult(b *Backend) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req map[string]interface{}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Bad request", http.StatusBadRequest)
			return
		}

		clientID, _ := req["client_id"].(string)
		deviceID, _ := req["device_id"].(string)
		output, _ := req["output"].(string)
		errorMsg, _ := req["error"].(string)
		secretHash, _ := req["secret_hash"].(string)
		mode, _ := req["mode"].(string)

		b.mu.RLock()
		device, exists := b.devices[deviceID]
		b.mu.RUnlock()

		if !exists || subtle.ConstantTimeCompare([]byte(device.SecurityPhraseHash), []byte(secretHash)) != 1 {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		b.unlockDevice(deviceID, clientID)

		outputEnc, _ := req["output_enc"].(string)
		errorEnc, _ := req["error_enc"].(string)
		newConvID, _ := req["new_conversation_id"].(string)

		if clientID != "" {
			if outputEnc != "" || errorEnc != "" {
				response := map[string]string{
					"output_enc": outputEnc,
					"error_enc":  errorEnc,
					"status":     "encrypted",
					"mode":       mode,
					"new_conversation_id": newConvID,
				}
				jsonResponse, _ := json.Marshal(response)
				b.writeMessage(clientID, websocket.TextMessage, jsonResponse)
			} else if errorMsg != "" {
				b.writeMessage(clientID, websocket.TextMessage, []byte("ERROR: "+errorMsg))
			} else {
				summary := ""
				if strings.ToLower(mode) == "agent" {
					summary = output
				} else {
					summary = b.generateTaskSummary("Command", output)
				}
				
				if mode == "" {
					mode = "shell"
				}
				
				response := map[string]string{
					"output": output,
					"summary": summary,
					"status": "ok",
					"mode": mode,
					"new_conversation_id": newConvID,
				}
				jsonResponse, _ := json.Marshal(response)
				b.writeMessage(clientID, websocket.TextMessage, jsonResponse)
			}
		}
		w.WriteHeader(http.StatusOK)
	}
}

func handleWebSocket(b *Backend) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("WebSocket upgrade error: %v", err)
			return
		}
		clientID := fmt.Sprintf("client-%d", time.Now().UnixNano())
		clientIP := r.RemoteAddr
		
		defer func() {
			conn.Close()
			// Clean up client from map
			b.mu.Lock()
			delete(b.clients, clientID)
			b.mu.Unlock()
			log.Printf("Mobile client disconnected: %s", clientID)
		}()
		
		b.mu.Lock()
		b.clients[clientID] = &WebSocketClient{
			conn:        conn,
			clientID:    clientID,
			connectedAt: time.Now(),
		}
		b.mu.Unlock()

		log.Printf("Mobile client connected: %s", clientID)

		// Set up ping/pong mechanism following gorilla websocket best practices
		conn.SetReadLimit(maxMessageSize)
		conn.SetReadDeadline(time.Now().Add(pongWait))
		conn.SetPongHandler(func(string) error {
			conn.SetReadDeadline(time.Now().Add(pongWait))
			return nil
		})

		// Create done channel for graceful shutdown
		done := make(chan struct{})

		// Start ping goroutine
		go func() {
			ticker := time.NewTicker(pingPeriod)
			defer ticker.Stop()
			for {
				select {
				case <-ticker.C:
					if err := conn.WriteControl(websocket.PingMessage, []byte{}, time.Now().Add(writeWait)); err != nil {
						log.Printf("Ping failed for %s: %v", clientID, err)
						return
					}
				case <-done:
					return
				}
			}
		}()

		for {
			messageType, message, err := conn.ReadMessage()
			if err != nil {
				log.Printf("WebSocket connection dropped/timeout for %s: %v", clientID, err)
				close(done)
				break
			}
			// Reset read deadline after each successful message
			conn.SetReadDeadline(time.Now().Add(pongWait))

			var msg map[string]interface{}
			if err := json.Unmarshal(message, &msg); err != nil {
				b.writeMessage(clientID, messageType, []byte("ERROR: Invalid message format"))
				continue
			}

			msgType, _ := msg["type"].(string)
			deviceID, _ := msg["device_id"].(string)
			sessionToken, _ := msg["session_token"].(string)

			// Require token for sensitive operations
			requiresAuth := msgType == "command" || msgType == "lock_device" || msgType == "unlock_device" || msgType == "clear_all_devices"
			if requiresAuth {
				// Special check for clear_all_devices which didn't use device_id originally
				targetDeviceID := deviceID
				if targetDeviceID == "" && msgType != "clear_all_devices" {
					device := b.getActiveDevice()
					if device != nil {
						targetDeviceID = device.ID
					}
				}
				
				// For clear_all, if token is valid for ANY device, we might let it through, or require the phrase inside the msg as before.
				// For now, if no token, fail. If command/lock and token invalid, fail.
				if msgType != "clear_all_devices" && !verifySessionToken(sessionToken, targetDeviceID) {
					b.writeMessage(clientID, messageType, []byte("ERROR: Unauthorized (missing, invalid, or expired session_token)"))
					continue
				}
			}

			switch msgType {
			case "ping":
				b.writeMessage(clientID, messageType, []byte(`{"type":"pong"}`))
				continue
			case "unlock":
				phrase, _ := msg["security_phrase"].(string)
				cID, _ := msg["client_device_id"].(string)
				if cID == "" {
					cID = clientID
				}
				if deviceID == "" {
					b.writeMessage(clientID, messageType, []byte("ERROR: device_id required"))
					continue
				}

				b.mu.Lock()
				failures := b.ipRateLimits[clientIP]
				if failures > 5 {
					b.mu.Unlock()
					b.addSecurityAlert("rate_limit", clientIP, deviceID, cID, "Unlock rate limit exceeded", "medium")
					b.writeMessage(clientID, messageType, []byte("ERROR: Rate limited"))
					continue
				}
				device, exists := b.devices[deviceID]
				if !exists {
					b.ipRateLimits[clientIP]++
					b.mu.Unlock()
					b.addSecurityAlert("auth_fail", clientIP, deviceID, cID, "Unlock attempt on non-existent device", "medium")
					b.writeMessage(clientID, messageType, []byte("ERROR: Invalid device"))
					continue
				}
				
				expectedHash := device.SecurityPhraseHash
				gotHash := hashPhrase(phrase, deviceID)
				
				if expectedHash != "" && gotHash == expectedHash {
					b.ipRateLimits[clientIP] = 0 // reset
					b.mu.Unlock()
					
					token, expiresAt := createSessionToken(deviceID, cID)
					ttlSec := int64(15 * 60) // 900 seconds (was incorrectly dividing by time.Second)
					resp := map[string]interface{}{
						"type": "session",
						"session_token": token,
						"device_id": deviceID,
						"expires_at": expiresAt,
						"ttl_sec": ttlSec,
					}
					jResp, _ := json.Marshal(resp)
					b.writeMessage(clientID, messageType, jResp)
				} else {
					b.ipRateLimits[clientIP]++
					b.mu.Unlock()
					b.addSecurityAlert("auth_fail", clientIP, deviceID, cID, "Invalid security phrase", "high")
					b.writeMessage(clientID, messageType, []byte("ERROR: Invalid security phrase"))
				}

			case "get_models":
				if deviceID == "" {
					device := b.getActiveDevice()
					if device != nil && device.Active {
						deviceID = device.ID
					} else {
						b.writeMessage(clientID, messageType, []byte("ERROR: No active online desktop device"))
						continue
					}
				}
				
				b.mu.RLock()
				device, exists := b.devices[deviceID]
				b.mu.RUnlock()
				
				if !exists || !device.Active {
					b.writeMessage(clientID, messageType, []byte("ERROR: device not found or offline"))
					continue
				}
				
				go func(dID string, cID string, addr string, hash string, msgType int) {
					client := safeHTTPClient()
					req, err := http.NewRequest("GET", addr+"/models", nil)
					if err != nil {
						b.writeMessage(cID, msgType, []byte("ERROR: Failed to create models request"))
						return
					}
					req.Header.Set("X-Exec-Secret", hash)
					
					resp, err := client.Do(req)
					if err != nil {
						b.writeMessage(cID, msgType, []byte("ERROR: Failed to fetch models"))
						return
					}
					defer resp.Body.Close()
					
					if resp.StatusCode == http.StatusOK {
						var models []string
						if err := json.NewDecoder(resp.Body).Decode(&models); err == nil {
							response := map[string]interface{}{
								"type": "models_list",
								"models": models,
							}
							responseBytes, _ := json.Marshal(response)
							b.writeMessage(cID, msgType, responseBytes)
						} else {
							b.writeMessage(cID, msgType, []byte("ERROR: Failed to parse models"))
						}
					}
				}(deviceID, clientID, device.Address, device.SecurityPhraseHash, messageType)
			case "get_conversations":
				if deviceID == "" {
					device := b.getActiveDevice()
					if device != nil && device.Active {
						deviceID = device.ID
					} else {
						b.writeMessage(clientID, messageType, []byte("ERROR: No active online desktop device"))
						continue
					}
				}
				
				b.mu.RLock()
				device, exists := b.devices[deviceID]
				b.mu.RUnlock()
				
				if !exists || !device.Active {
					b.writeMessage(clientID, messageType, []byte("ERROR: device not found or offline"))
					continue
				}
				
				go func(dID string, cID string, addr string, hash string, msgType int) {
					client := safeHTTPClient()
					req, err := http.NewRequest("GET", addr+"/conversations", nil)
					if err == nil {
						req.Header.Set("X-Exec-Secret", hash)
						resp, err := client.Do(req)
						if err == nil {
							defer resp.Body.Close()
							body, _ := io.ReadAll(resp.Body)
							
							// Wrap in a response object
							respObj := map[string]interface{}{
								"type": "conversations_list",
								"data": json.RawMessage(body),
							}
							respJson, _ := json.Marshal(respObj)
							b.writeMessage(cID, msgType, respJson)
							return
						}
					}
					b.writeMessage(cID, msgType, []byte("ERROR: failed to fetch conversations"))
				}(deviceID, clientID, device.Address, device.SecurityPhraseHash, messageType)
				
			case "command":
				command, _ := msg["command"].(string)
				mode, _ := msg["mode"].(string)
				conversationID, _ := msg["conversation_id"].(string)
				if deviceID == "" {
					device := b.getActiveDevice()
					if device != nil && device.Active {
						deviceID = device.ID
					} else {
						b.writeMessage(clientID, messageType, []byte("ERROR: No active online desktop device"))
						continue
					}
				}
				
				b.mu.RLock()
				device, exists := b.devices[deviceID]
				isOnline := exists && device.Active
				circuitOpen := exists && device.CircuitOpen
				b.mu.RUnlock()
				
				if !exists {
					b.writeMessage(clientID, messageType, []byte("ERROR: device not found"))
					continue
				}
				if !isOnline {
					b.writeMessage(clientID, messageType, []byte("ERROR: device offline"))
					continue
				}
				if circuitOpen {
					b.writeMessage(clientID, messageType, []byte("ERROR: Circuit breaker open - device locked"))
					continue
				}
				if b.isDeviceLocked(deviceID, clientID) {
					b.writeMessage(clientID, messageType, []byte("ERROR: Device locked by another mobile device"))
					continue
				}
				
				// Verify session token - strict REAL vs MOCK split
				tokenValid := verifySessionToken(sessionToken, deviceID)
				if !tokenValid {
					// MOCK path for unauthorized commands
					b.mu.Lock()
					b.mockCommandCounts[deviceID]++
					mockCount := b.mockCommandCounts[deviceID]
					b.mu.Unlock()
					
					b.addSecurityAlert("mock_command", clientIP, deviceID, clientID, fmt.Sprintf("Unauthorized command attempt (mock count: %d)", mockCount), "medium")
					
					// Trip breaker after threshold
					if mockCount >= mockCommandThreshold {
						b.tripCircuitBreaker(deviceID)
					}
					
					// Return fake response with small delay
					go func(cmd string, mt int, cid string) {
						time.Sleep(time.Duration(50 + time.Now().UnixNano()%250) * time.Millisecond) // 50-300ms delay
						mockResp := b.generateMockResponse(cmd)
						b.writeMessage(cid, mt, []byte(mockResp))
					}(command, messageType, clientID)
					continue
				}
				
				// REAL path - valid token
				// Run in goroutine to not block websocket read loop (and pings)
				go func(dID, cmd, m string, msgType int, cID string, convID string) {
					b.lockDevice(dID, cID)
					result, err := b.forwardCommand(dID, cmd, m, cID, convID)
					
					if err != nil {
						b.unlockDevice(dID, cID)
						b.writeMessage(cID, msgType, []byte("ERROR: "+err.Error()))
						return
					}
					
					if result == "TASK_QUEUED" {
						// Don't unlock device yet, webhook will unlock it
						// Don't write result to websocket, webhook will write it
						return
					}
					
					b.unlockDevice(dID, cID)
					b.writeMessage(cID, msgType, []byte(result))
				}(deviceID, command, mode, messageType, clientID, conversationID)
				

			case "stop_command":
				b.lockDevice(deviceID, clientID)
				result, err := b.stopCommand(deviceID)
				b.unlockDevice(deviceID, clientID)
				
				if err != nil {
					b.writeMessage(clientID, messageType, []byte("ERROR: "+err.Error()))
				} else {
					b.writeMessage(clientID, messageType, []byte("OK: "+result))
				}

			case "switch_device":
				err := b.setActiveDevice(deviceID)
				if err != nil {
					b.writeMessage(clientID, messageType, []byte("ERROR: "+err.Error()))
				} else {
					b.writeMessage(clientID, messageType, []byte("OK: Device switched"))
				}
				
			case "lock_device":
				err := b.lockDevice(deviceID, clientID)
				if err != nil {
					b.writeMessage(clientID, messageType, []byte("ERROR: "+err.Error()))
				} else {
					b.writeMessage(clientID, messageType, []byte("OK: Device locked"))
				}
				
			case "unlock_device":
				err := b.unlockDevice(deviceID, clientID)
				if err != nil {
					b.writeMessage(clientID, messageType, []byte("ERROR: "+err.Error()))
				} else {
					b.writeMessage(clientID, messageType, []byte("OK: Device unlocked"))
				}
				
			case "get_devices":
				b.markStaleDevices()
				devices := b.getAllDevices()
				deviceList := make([]map[string]interface{}, 0)
				for _, d := range devices {
					deviceList = append(deviceList, map[string]interface{}{
						"id":          d.ID,
						"name":        d.Name,
						"active":      d.ID == b.activeDevice,
						"online":      d.Active,
						"reachable":   d.Reachable,
						"locked":      d.LockedBy != "",
						"lockedBy":    d.LockedBy,
						"lastSeen":    d.LastSeen,
						"lastPing":    d.LastPing,
						"fingerprint": d.Fingerprint,
						"type":        d.Type,
					})
				}
				jsonData, _ := json.Marshal(deviceList)
				b.writeMessage(clientID, messageType, jsonData)
				
			case "get_stats":
				b.mu.RLock()
				stats := map[string]interface{}{
					"token_counter": b.tokenCounter,
					"device_count": len(b.devices),
					"active_device": b.activeDevice,
				}
				b.mu.RUnlock()
				jsonData, _ := json.Marshal(stats)
				b.writeMessage(clientID, messageType, jsonData)
				
			case "get_security_alerts":
				// Require valid session token
				if !verifySessionToken(sessionToken, deviceID) {
					b.writeMessage(clientID, messageType, []byte("ERROR: Unauthorized"))
					continue
				}
				
				b.mu.RLock()
				// Bug #17 Fix: Read circular buffer in chronological order
				alertsCopy := make([]SecurityAlert, b.alertCount)
				for i := 0; i < b.alertCount; i++ {
					alertsCopy[i] = b.securityAlerts[(b.alertHead+i)%maxAlerts]
				}
				b.mu.RUnlock()
				
				jsonData, _ := json.Marshal(map[string]interface{}{
					"type": "security_alerts_list",
					"alerts": alertsCopy,
				})
				b.writeMessage(clientID, messageType, jsonData)
				
			case "circuit_reset":
				// Require valid session token + security phrase re-check
				if !verifySessionToken(sessionToken, deviceID) {
					b.writeMessage(clientID, messageType, []byte("ERROR: Unauthorized"))
					continue
				}
				
				phrase, _ := msg["security_phrase"].(string)
				b.mu.RLock()
				device, exists := b.devices[deviceID]
				b.mu.RUnlock()
				
				if !exists {
					b.writeMessage(clientID, messageType, []byte("ERROR: Device not found"))
					continue
				}
				
				expectedHash := device.SecurityPhraseHash
				gotHash := hashPhrase(phrase, deviceID)
				
				if expectedHash != "" && gotHash == expectedHash {
					if b.resetCircuitBreaker(deviceID) {
						b.writeMessage(clientID, messageType, []byte("OK: Circuit breaker reset"))
					} else {
						b.writeMessage(clientID, messageType, []byte("OK: Circuit breaker already closed"))
					}
				} else {
					b.writeMessage(clientID, messageType, []byte("ERROR: Invalid security phrase"))
				}
				
			case "clear_all_devices":
				var req struct {
					SecurityPhrase string `json:"security_phrase"`
				}
				if err := json.Unmarshal(message, &req); err == nil {
					phrase := strings.TrimSpace(req.SecurityPhrase)
					if phrase == "" {
						b.writeMessage(clientID, messageType, []byte("ERROR: Security phrase required"))
						continue
					}
					
					adminSecret := os.Getenv("CLEAR_DATA_SECRET")
					if adminSecret != "" && phrase == adminSecret {
						b.clearAllDevices()
						b.writeMessage(clientID, messageType, []byte("OK: All devices cleared (admin)"))
						continue
					}
					
					b.mu.Lock()
					failures := b.ipRateLimits[clientIP]
					if failures > 5 {
						b.mu.Unlock()
						b.writeMessage(clientID, messageType, []byte("ERROR: Rate limited"))
						continue
					}
					if len(b.devices) == 0 {
						b.mu.Unlock()
						b.writeMessage(clientID, messageType, []byte("ERROR: No registered devices to verify phrase"))
						continue
					}
					
					validPhrase := false
					for devID, device := range b.devices {
						if device.SecurityPhraseHash == hashPhrase(phrase, devID) {
							validPhrase = true
							break
						}
					}
					if validPhrase {
						b.ipRateLimits[clientIP] = 0
						b.mu.Unlock()
						b.clearAllDevices()
						b.writeMessage(clientID, messageType, []byte("OK: All devices cleared"))
					} else {
						b.ipRateLimits[clientIP]++
						b.mu.Unlock()
						b.writeMessage(clientID, messageType, []byte("ERROR: Invalid security phrase"))
					}
				}
			default:
				b.writeMessage(clientID, messageType, message)
			}
		}
		
		b.mu.Lock()
		delete(b.clients, clientID)
		for _, device := range b.devices {
			if device.LockedBy == clientID {
				device.LockedBy = ""
				device.LockedAt = time.Time{}
			}
		}
		b.mu.Unlock()
	}
}

var startTime time.Time

func main() {
	startTime = time.Now()
	backend := NewBackend()
	
	// Auto-detect ngrok URL if NGROK_AUTO_DETECT is enabled (local dev only)
	// On Render, this localhost:4040 check won't work since ngrok runs on user's PC
	if os.Getenv("NGROK_AUTO_DETECT") == "true" {
		log.Println("NGROK_AUTO_DETECT enabled (local dev mode only)")
		go autoDetectNgrokURL(backend)
	}
	
	// Register devices from environment variables or defaults
	device1Name := os.Getenv("DEVICE_1_NAME")
	if device1Name == "" {
		device1Name = "Development Laptop"
	}
	device1Addr := os.Getenv("DEVICE_1_ADDRESS")
	if device1Addr == "" {
		device1Addr = "http://localhost:8088"
	}
	backend.registerDevice("laptop-1", device1Name, device1Addr)
	
	device2Name := os.Getenv("DEVICE_2_NAME")
	if device2Name == "" {
		device2Name = "Production Server"
	}
	device2Addr := os.Getenv("DEVICE_2_ADDRESS")
	if device2Addr == "" {
		device2Addr = "http://localhost:8091"
	}
	backend.registerDevice("laptop-2", device2Name, device2Addr)

	log.Printf("Registered devices: %s (%s), %s (%s)", device1Name, device1Addr, device2Name, device2Addr)

	http.HandleFunc("/ws", handleWebSocket(backend))
	http.HandleFunc("/webhook/result", handleWebhookResult(backend))
	http.HandleFunc("/test_optimize", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		
		var req map[string]string
		json.NewDecoder(r.Body).Decode(&req)
		
		optimized := backend.optimizeCommand(req["command"])
		response := map[string]string{
			"original": req["command"],
			"optimized": optimized,
		}
		
		json.NewEncoder(w).Encode(response)
	})
	
	// Clear all devices endpoint (requires security phrase)
	http.HandleFunc("/clear-all-devices", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		
		var req struct {
			SecurityPhrase string `json:"security_phrase"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			log.Printf("Clear devices failed: bad request - %v", err)
			http.Error(w, "Bad request", http.StatusBadRequest)
			return
		}
		
		phrase := strings.TrimSpace(req.SecurityPhrase)
		
		if phrase == "" {
			log.Printf("Clear devices failed: missing security phrase")
			http.Error(w, "Security phrase required", http.StatusBadRequest)
			return
		}
		
		// Check for admin secret override
		adminSecret := os.Getenv("CLEAR_DATA_SECRET")
		if adminSecret != "" && phrase == adminSecret {
			log.Printf("Clear data approved via admin secret")
			backend.clearAllDevices()
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]string{"status": "ok", "message": "All devices cleared"})
			return
		}
		
		// Verify security phrase matches registered devices
		backend.mu.RLock()
		if len(backend.devices) == 0 {
			backend.mu.RUnlock()
			log.Printf("Clear devices denied: no registered devices to verify phrase")
			http.Error(w, "No registered devices; cannot verify phrase", http.StatusForbidden)
			return
		}
		
		validPhrase := false
		for devID, device := range backend.devices {
			if device.SecurityPhraseHash == hashPhrase(phrase, devID) {
				validPhrase = true
				break
			}
		}
		backend.mu.RUnlock()
		
		if !validPhrase {
			log.Printf("Clear devices denied: invalid security phrase")
			http.Error(w, "Unauthorized: Invalid security phrase", http.StatusUnauthorized)
			return
		}
		
		count := len(backend.devices)
		backend.clearAllDevices()
		log.Printf("Backend data cleared by client with valid security phrase (%d devices removed)", count)
		
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "message": "All devices cleared"})
	})

	http.HandleFunc("/register", func(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// AGENT_REGISTER_SECRET removed for zero-friction mode. Open registration.

	var req struct {
		DeviceID    string `json:"device_id"`
		DeviceName  string `json:"device_name"`
		Address     string `json:"address"` // e.g. https://xxxx.ngrok-free.app
		Fingerprint string `json:"fingerprint"`
		Type        string `json:"type"`
		SecurityPhrase string `json:"security_phrase"` // NEW: client's security phrase
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		log.Printf("Registration failed: bad request - %v", err)
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}
	if req.DeviceID == "" || req.Address == "" {
		log.Printf("Registration failed: missing required fields (device_id=%s, address=%s)", req.DeviceID, req.Address)
		http.Error(w, "device_id and address required", http.StatusBadRequest)
		return
	}
	if !isValidAddress(req.Address) {
		log.Printf("Registration failed: invalid or disallowed address: %s", req.Address)
		http.Error(w, "Invalid address", http.StatusBadRequest)
		return
	}

	if req.Type == "" {
		req.Type = "desktop"
	}

	log.Printf("Registration request: device_id=%s, name=%s, address=%s, type=%s", req.DeviceID, req.DeviceName, req.Address, req.Type)

	backend.mu.Lock()
	defer backend.mu.Unlock()

	d, exists := backend.devices[req.DeviceID]
	if !exists {
		d = &Device{ID: req.DeviceID}
		backend.devices[req.DeviceID] = d
		if backend.activeDevice == "" {
			backend.activeDevice = req.DeviceID
		}
	}
	wasActive := false
	oldAddress := ""
	if exists {
		wasActive = d.Active
		oldAddress = d.Address
	}

	d.Name = req.DeviceName
	d.Address = strings.TrimRight(req.Address, "/")
	d.Fingerprint = req.Fingerprint
	d.Type = req.Type
	d.Active = true
	d.LastSeen = time.Now()
	if d.AuthToken == "" {
		d.AuthToken = generateAuthToken()
	}
	
	if req.SecurityPhrase != "" {
		d.SecurityPhraseHash = hashPhrase(strings.TrimSpace(req.SecurityPhrase), req.DeviceID)
		log.Printf("Device registered with hashed security phrase")
	}

	wasNew := !exists
	log.Printf("Device registered: %s (%s) @ %s (online: %v, new: %v, total devices: %d)", d.Name, d.ID, d.Address, d.Active, wasNew, len(backend.devices))
	
	if wasNew || !wasActive || oldAddress != d.Address {
		go backend.broadcastDevices()
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":    "ok",
		"device_id": d.ID,
	})
})

// Heartbeat endpoint for local agents to keep device marked as online
http.HandleFunc("/heartbeat", func(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		DeviceID string `json:"device_id"`
		Address  string `json:"address"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}

	backend.mu.Lock()
	defer backend.mu.Unlock()

	device, exists := backend.devices[req.DeviceID]
	if !exists {
		http.Error(w, "Device not found", http.StatusNotFound)
		return
	}

	// Update device LastSeen and address if changed
	wasActive := device.Active
	device.LastSeen = time.Now()
	if req.Address != "" && device.Address != req.Address {
		device.Address = req.Address
		log.Printf("Device address updated: %s -> %s", device.ID, req.Address)
	}
	device.Active = true

	// Broadcast if device just came online
	if !wasActive {
		go backend.broadcastDevices()
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
})

// Health check endpoint for Render keep-alive
http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
	// Fast response - don't mark stale devices here to avoid blocking
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	
	backend.mu.RLock()
	health := map[string]interface{}{
		"status":          "ok",
		"timestamp":       time.Now().Format(time.RFC3339),
		"uptime":          time.Since(startTime).String(),
		"devices_registered": len(backend.devices),
		"mobile_clients":   len(backend.clients),
	}
	backend.mu.RUnlock()
	json.NewEncoder(w).Encode(health)
})

// Status endpoint for monitoring
http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
	// Mark stale devices before serving status
	backend.markStaleDevices()
	
	w.Header().Set("Content-Type", "application/json")
	backend.mu.RLock()
	
	// Build online devices list for mobile app
	onlineDevices := make([]map[string]interface{}, 0)
	for _, device := range backend.devices {
		if device.Active {
			onlineDevices = append(onlineDevices, map[string]interface{}{
				"id":        device.ID,
				"name":      device.Name,
				"online":    true,
				"reachable": device.Reachable,
			})
		}
	}
	
	stats := map[string]interface{}{
		"status":          "running",
		"uptime":          time.Since(startTime).String(),
		"device_count":    len(backend.devices),
		"devices_online":  len(onlineDevices),
		"online_devices":  onlineDevices,
		"mobile_clients":  len(backend.clients),
		"token_counter":   backend.tokenCounter,
	}
	backend.mu.RUnlock()
	json.NewEncoder(w).Encode(stats)
})
	
	port := os.Getenv("PORT")
	if port == "" {
		port = "8090"
	}
	
	log.Printf("Backend server starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}

func autoDetectNgrokURL(backend *Backend) {
	// Check ngrok API every 30 seconds
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	
	for range ticker.C {
		ngrokURL, err := getNgrokURL()
		if err != nil {
			log.Printf("Failed to get ngrok URL: %v", err)
			continue
		}
		
		if ngrokURL != "" {
			// Update device 1 address with ngrok URL
			backend.mu.Lock()
			if device, exists := backend.devices["laptop-1"]; exists {
				if device.Address != ngrokURL {
					device.Address = ngrokURL
					device.LastSeen = time.Now()
					log.Printf("Auto-updated device 1 address to ngrok URL: %s", ngrokURL)
				}
			}
			backend.mu.Unlock()
		}
	}
}

func getNgrokURL() (string, error) {
	// Try to get ngrok URL from local ngrok API
	resp, err := http.Get("http://localhost:4040/api/tunnels")
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	
	var result struct {
		Tunnels []struct {
			PublicURL string `json:"public_url"`
			Proto     string `json:"proto"`
		} `json:"tunnels"`
	}
	
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	
	if err := json.Unmarshal(body, &result); err != nil {
		return "", err
	}
	
	if len(result.Tunnels) > 0 {
		// Prefer HTTPS tunnel
		for _, tunnel := range result.Tunnels {
			if strings.HasPrefix(tunnel.PublicURL, "https://") {
				return tunnel.PublicURL, nil
			}
		}
		// Fallback to first tunnel if no HTTPS found
		return result.Tunnels[0].PublicURL, nil
	}
	
	return "", fmt.Errorf("no ngrok tunnels found")
}
