package main

import (
	"bytes"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
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

const deviceOnlineTTL = 60 * time.Second

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
}

type Backend struct {
	devices      map[string]*Device
	activeDevice string
	tokenCounter int
	mu           sync.RWMutex
	clients      map[string]*WebSocketClient
	ipRateLimits map[string]int // IP -> failures
}

type WebSocketClient struct {
	conn        *websocket.Conn
	clientID    string
	connectedAt time.Time
	writeMu     sync.Mutex
}

func NewBackend() *Backend {
	b := &Backend{
		devices:      make(map[string]*Device),
		activeDevice: "",
		tokenCounter: 0,
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]int),
	}
	
	// Start presence ticker
	go b.startPresenceTicker()
	
	return b
}


func safeHTTPClient() *http.Client {
	return &http.Client{
		Timeout: 120 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

func hashPhrase(phrase, deviceID string) string {
	h := sha256.New()
	h.Write([]byte(phrase + ":" + deviceID))
	return hex.EncodeToString(h.Sum(nil))
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

func createSessionToken(deviceID, clientID string) string {
	secret := getSessionSigningKey()
	payload := map[string]interface{}{
		"sid": fmt.Sprintf("sess-%d", time.Now().UnixNano()),
		"device_id": deviceID,
		"client_device_id": clientID,
		"iat": time.Now().Unix(),
		"exp": time.Now().Add(15 * time.Minute).Unix(),
	}
	payloadBytes, _ := json.Marshal(payload)
	payloadB64 := base64.URLEncoding.EncodeToString(payloadBytes)
	
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(payloadB64))
	sig := hex.EncodeToString(mac.Sum(nil))
	
	return payloadB64 + "." + sig
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
	for _, device := range b.devices {
		if device.Type == "desktop" || strings.HasPrefix(device.ID, "desktop-") {
			// Desktop devices are online only if they've heartbeated within TTL
			wasActive := device.Active
			device.Active = now.Sub(device.LastSeen) < deviceOnlineTTL
			if wasActive && !device.Active {
				log.Printf("Device marked offline: %s (%s) - last seen %v ago", device.Name, device.ID, now.Sub(device.LastSeen))
			}
		}
	}
}

func (b *Backend) startPresenceTicker() {
	ticker := time.NewTicker(15 * time.Second)
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
	
	// Ping all devices concurrently
	var wg sync.WaitGroup
	for _, device := range devices {
		wg.Add(1)
		go func(d *Device) {
			defer wg.Done()
			b.pingDevice(d)
		}(device)
	}
	wg.Wait()
}

func (b *Backend) pingDevice(device *Device) {
	if device.Address == "" {
		return
	}
	
	// Ping device's HTTP endpoint
	client := safeHTTPClient()
	client.Timeout = 5 * time.Second
	resp, err := client.Get(strings.TrimRight(device.Address, "/") + "/health")
	
	b.mu.Lock()
	defer b.mu.Unlock()
	
	if d, exists := b.devices[device.ID]; exists {
		d.LastPing = time.Now()
		if err == nil && resp.StatusCode == 200 {
			d.Reachable = true
			resp.Body.Close()
		} else {
			d.Reachable = false
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
}

func (b *Backend) setActiveDevice(deviceID string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	
	if _, exists := b.devices[deviceID]; !exists {
		return fmt.Errorf("device not found")
	}
	
	b.activeDevice = deviceID
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

func (b *Backend) forwardCommand(deviceID, command, mode, clientID string) (string, error) {
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

	optimizedCommand := b.optimizeCommand(command)

	urlStr := address + "/execute"
	payload := map[string]string{"command": optimizedCommand, "mode": mode, "client_id": clientID}
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
		mode = "command"
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

		if !exists || device.SecurityPhraseHash != secretHash {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		b.unlockDevice(deviceID, clientID)

		if clientID != "" {
			if errorMsg != "" {
				b.writeMessage(clientID, websocket.TextMessage, []byte("ERROR: "+errorMsg))
			} else {
				summary := ""
				if strings.ToLower(mode) == "ask" {
					summary = output
				} else {
					summary = b.generateTaskSummary("Command", output)
				}
				
				if mode == "" {
					mode = "command"
				}
				
				response := map[string]string{
					"output": output,
					"summary": summary,
					"status": "ok",
					"mode": mode,
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
		defer conn.Close()

		clientID := fmt.Sprintf("client-%d", time.Now().UnixNano())
		clientIP := r.RemoteAddr
		
		b.mu.Lock()
		b.clients[clientID] = &WebSocketClient{
			conn:        conn,
			clientID:    clientID,
			connectedAt: time.Now(),
		}
		b.mu.Unlock()

		log.Printf("Mobile client connected: %s", clientID)

		for {
			messageType, message, err := conn.ReadMessage()
			if err != nil {
				break
			}

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
					b.writeMessage(clientID, messageType, []byte("ERROR: Rate limited"))
					continue
				}
				device, exists := b.devices[deviceID]
				if !exists {
					b.ipRateLimits[clientIP]++
					b.mu.Unlock()
					b.writeMessage(clientID, messageType, []byte("ERROR: Invalid device"))
					continue
				}
				
				expectedHash := device.SecurityPhraseHash
				gotHash := hashPhrase(phrase, deviceID)
				
				if expectedHash != "" && gotHash == expectedHash {
					b.ipRateLimits[clientIP] = 0 // reset
					b.mu.Unlock()
					
					token := createSessionToken(deviceID, cID)
					resp := map[string]string{
						"type": "session",
						"session_token": token,
						"device_id": deviceID,
					}
					jResp, _ := json.Marshal(resp)
					b.writeMessage(clientID, messageType, jResp)
				} else {
					b.ipRateLimits[clientIP]++
					b.mu.Unlock()
					b.writeMessage(clientID, messageType, []byte("ERROR: Invalid security phrase"))
				}

			case "command":
				command, _ := msg["command"].(string)
				mode, _ := msg["mode"].(string)
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
				b.mu.RUnlock()
				
				if !exists {
					b.writeMessage(clientID, messageType, []byte("ERROR: device not found"))
					continue
				}
				if !isOnline {
					b.writeMessage(clientID, messageType, []byte("ERROR: device offline"))
					continue
				}
				if b.isDeviceLocked(deviceID, clientID) {
					b.writeMessage(clientID, messageType, []byte("ERROR: Device locked by another mobile device"))
					continue
				}
				
				// Run in goroutine to not block websocket read loop (and pings)
				go func(dID, cmd, m string, msgType int, cID string) {
					b.lockDevice(dID, cID)
					result, err := b.forwardCommand(dID, cmd, m, cID)
					
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
				}(deviceID, command, mode, messageType, clientID)
				

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

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":    "ok",
		"device_id": d.ID,
	})
})
	// Health check endpoint for Render keep-alive
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		// Mark stale devices before serving health
		backend.markStaleDevices()
		
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		backend.mu.RLock()
		
		// Count online devices securely (no PII or IDs leaked)
		devicesOnline := 0
		for _, device := range backend.devices {
			if device.Active {
				devicesOnline++
			}
		}
		
		health := map[string]interface{}{
			"status":          "ok",
			"timestamp":       time.Now().Format(time.RFC3339),
			"uptime":          time.Since(startTime).String(),
			"devices_registered": len(backend.devices),
			"devices_online":   devicesOnline,
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
		
		// Count online devices securely
		devicesOnline := 0
		for _, device := range backend.devices {
			if device.Active {
				devicesOnline++
			}
		}
		
		stats := map[string]interface{}{
			"status":          "running",
			"uptime":          time.Since(startTime).String(),
			"device_count":    len(backend.devices),
			"devices_online":  devicesOnline,
			"mobile_clients":  len(backend.clients),
			"token_counter":   backend.tokenCounter,
		}
		backend.mu.RUnlock()
		json.NewEncoder(w).Encode(stats)
	})
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
