package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
	"github.com/gorilla/websocket"
)

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
	Fingerprint string // NEW
	Type        string // "desktop" | etc.
	Reachable   bool // NEW: direct ping result
	LastPing    time.Time // NEW: last time backend pinged this device
	SecurityPhrase string // NEW: user's security phrase for clearing data
}

type Backend struct {
	devices      map[string]*Device
	activeDevice string
	tokenCounter int
	mu           sync.RWMutex
	clients      map[string]*WebSocketClient // Track connected mobile clients
}

type WebSocketClient struct {
	conn        *websocket.Conn
	clientID    string
	connectedAt time.Time
}

func NewBackend() *Backend {
	b := &Backend{
		devices:      make(map[string]*Device),
		activeDevice: "",
		tokenCounter: 0,
		clients:      make(map[string]*WebSocketClient),
	}
	
	// Start presence ticker
	go b.startPresenceTicker()
	
	return b
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
	client := &http.Client{Timeout: 5 * time.Second}
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
		log.Printf("Command optimized: '%s' -> '%s'", command, optimized)
		return optimized
	}
	
	// Simple substring matching
	for pattern, replacement := range optimizations {
		if len(command) >= len(pattern) {
			// Check if pattern is contained in command
			for i := 0; i <= len(command)-len(pattern); i++ {
				if command[i:i+len(pattern)] == pattern {
					log.Printf("Command partially optimized: '%s' -> '%s'", command, replacement)
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

func (b *Backend) forwardCommand(deviceID, command string) (string, error) {
	b.mu.RLock()
	device, exists := b.devices[deviceID]
	active := device.Active
	address := device.Address
	b.mu.RUnlock()

	if !exists {
		log.Printf("forwardCommand failed: device not found - %s", deviceID)
		return "", fmt.Errorf("device not found: %s", deviceID)
	}

	if !active {
		log.Printf("forwardCommand failed: device offline - %s (last seen stale or not registered)", deviceID)
		return "", fmt.Errorf("device offline: %s (last seen stale or not registered)", deviceID)
	}

	// Optimize command before forwarding
	optimizedCommand := b.optimizeCommand(command)

	// Forward to local agent via HTTP
	url := address + "/execute"
	payload := map[string]string{"command": optimizedCommand}
	jsonPayload, _ := json.Marshal(payload)

	resp, err := http.Post(url, "application/json", bytes.NewBuffer(jsonPayload))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	var result map[string]string
	json.NewDecoder(resp.Body).Decode(&result)
	
	// Generate AI-powered summary
	summary := b.generateTaskSummary(command, result["output"])
	
	// Return both output and summary
	response := map[string]string{
		"output": result["output"],
		"summary": summary,
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

func handleWebSocket(b *Backend) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("WebSocket upgrade error: %v", err)
			return
		}
		defer conn.Close()

		// Generate unique client ID
		clientID := fmt.Sprintf("client-%d", time.Now().UnixNano())
		
		// Register client
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
				log.Printf("Read error: %v", err)
				break
			}

			log.Printf("Received from %s: %s", clientID, message)

			// Parse message - use interface{} to handle mixed types
			var msg map[string]interface{}
			if err := json.Unmarshal(message, &msg); err != nil {
				log.Printf("Parse error: %v", err)
				conn.WriteMessage(messageType, []byte("ERROR: Invalid message format"))
				continue
			}

			// Handle different message types
			msgType, _ := msg["type"].(string)
			switch msgType {
			case "command":
				deviceID, _ := msg["device_id"].(string)
				command, _ := msg["command"].(string)
				
				// If no device specified, use active device if online
				if deviceID == "" {
					device := b.getActiveDevice()
					if device != nil && device.Active {
						deviceID = device.ID
					} else {
						// List online desktop devices
						b.mu.RLock()
						onlineDesktops := []string{}
						for id, d := range b.devices {
							if d.Active && d.Type == "desktop" {
								onlineDesktops = append(onlineDesktops, id)
							}
						}
						b.mu.RUnlock()
						
						if len(onlineDesktops) == 0 {
							conn.WriteMessage(messageType, []byte("ERROR: No online desktop devices available"))
						} else {
							conn.WriteMessage(messageType, []byte("ERROR: No device specified. Online desktops: "+strings.Join(onlineDesktops, ", ")))
						}
						continue
					}
				}
				
				// Check if device exists and is online before locking
				b.mu.RLock()
				device, exists := b.devices[deviceID]
				isOnline := exists && device.Active
				b.mu.RUnlock()
				
				if !exists {
					conn.WriteMessage(messageType, []byte("ERROR: device not found: "+deviceID))
					continue
				}
				
				if !isOnline {
					conn.WriteMessage(messageType, []byte("ERROR: device offline: "+deviceID+" (last seen stale or not registered)"))
					continue
				}
				
				// Check if device is locked by another client
				if b.isDeviceLocked(deviceID, clientID) {
					conn.WriteMessage(messageType, []byte("ERROR: Device is locked by another mobile device"))
					continue
				}
				
				// Lock device for this command
				b.lockDevice(deviceID, clientID)
				
				result, err := b.forwardCommand(deviceID, command)
				
				// Unlock device after command
				b.unlockDevice(deviceID, clientID)
				
				if err != nil {
					log.Printf("Forward error: %v", err)
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
					continue
				}
				conn.WriteMessage(messageType, []byte(result))
				
			case "switch_device":
				deviceID, _ := msg["device_id"].(string)
				err := b.setActiveDevice(deviceID)
				if err != nil {
					log.Printf("Switch device error: %v", err)
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device switched"))
				}
				
			case "lock_device":
				deviceID, _ := msg["device_id"].(string)
				err := b.lockDevice(deviceID, clientID)
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device locked"))
				}
				
			case "unlock_device":
				deviceID, _ := msg["device_id"].(string)
				err := b.unlockDevice(deviceID, clientID)
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device unlocked"))
				}
				
			case "get_devices":
				// Mark stale devices before returning device list
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
						"fingerprint":  d.Fingerprint,
						"type":        d.Type,
					})
				}
				jsonData, _ := json.Marshal(deviceList)
				conn.WriteMessage(messageType, jsonData)
				
			case "get_stats":
				b.mu.RLock()
				stats := map[string]interface{}{
					"token_counter": b.tokenCounter,
					"device_count": len(b.devices),
					"active_device": b.activeDevice,
				}
				b.mu.RUnlock()
				
				jsonData, _ := json.Marshal(stats)
				conn.WriteMessage(messageType, jsonData)
				
			case "clear_all_devices":
				var req struct {
					SecurityPhrase string `json:"security_phrase"`
				}
				if err := json.Unmarshal(message, &req); err == nil {
					phrase := strings.TrimSpace(req.SecurityPhrase)
					
					if phrase == "" {
						conn.WriteMessage(messageType, []byte("ERROR: Security phrase required"))
						break
					}
					
					// Check for admin secret override
					adminSecret := os.Getenv("CLEAR_DATA_SECRET")
					if adminSecret != "" && phrase == adminSecret {
						b.clearAllDevices()
						conn.WriteMessage(messageType, []byte("OK: All devices cleared (admin)"))
						break
					}
					
					b.mu.RLock()
					if len(b.devices) == 0 {
						b.mu.RUnlock()
						conn.WriteMessage(messageType, []byte("ERROR: No registered devices to verify phrase"))
						break
					}
					
					validPhrase := false
					for _, device := range b.devices {
						if device.SecurityPhrase == phrase {
							validPhrase = true
							break
						}
					}
					b.mu.RUnlock()
					
					if validPhrase {
						b.clearAllDevices()
						conn.WriteMessage(messageType, []byte("OK: All devices cleared"))
					} else {
						conn.WriteMessage(messageType, []byte("ERROR: Invalid security phrase"))
					}
				} else {
					conn.WriteMessage(messageType, []byte("ERROR: Invalid request format"))
				}
				
			default:
				// Echo for PoC compatibility
				conn.WriteMessage(messageType, message)
			}
		}
		
		// Client disconnected - cleanup
		b.mu.Lock()
		delete(b.clients, clientID)
		
		// Unlock all devices locked by this client
		for deviceID, device := range b.devices {
			if device.LockedBy == clientID {
				device.LockedBy = ""
				device.LockedAt = time.Time{}
				log.Printf("Device %s unlocked (client %s disconnected)", deviceID, clientID)
			}
		}
		b.mu.Unlock()
		
		log.Printf("Mobile client disconnected: %s", clientID)
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
		for _, device := range backend.devices {
			if device.SecurityPhrase == phrase {
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

	// Shared secret so random internet clients can't register devices
	expected := os.Getenv("AGENT_REGISTER_SECRET")
	if expected == "" {
		http.Error(w, "Registration disabled", http.StatusServiceUnavailable)
		return
	}
	if r.Header.Get("X-Agent-Secret") != expected {
		log.Printf("Registration denied: invalid or missing X-Agent-Secret header")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

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
	
	// Store security phrase separately for clear-backend authentication
	if req.SecurityPhrase != "" {
		d.SecurityPhrase = strings.TrimSpace(req.SecurityPhrase)
		log.Printf("Device registered with security phrase for data clearing")
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
		
		// Count online devices
		devicesOnline := 0
		onlineDevices := []map[string]interface{}{}
		for _, device := range backend.devices {
			if device.Active {
				devicesOnline++
				onlineDevices = append(onlineDevices, map[string]interface{}{
					"id":          device.ID,
					"name":        device.Name,
					"lastSeen":    device.LastSeen.Format(time.RFC3339),
					"online":      device.Active,
					"reachable":   device.Reachable,
					"lastPing":    device.LastPing.Format(time.RFC3339),
					"fingerprint":  device.Fingerprint,
					"type":        device.Type,
				})
			}
		}
		
		health := map[string]interface{}{
			"status":          "ok",
			"timestamp":       time.Now().Format(time.RFC3339),
			"uptime":          time.Since(startTime).String(),
			"devices_registered": len(backend.devices),
			"devices_online":   devicesOnline,
			"online_devices":   onlineDevices,
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
		
		// Build online device list
		onlineDevices := []map[string]interface{}{}
		for _, device := range backend.devices {
			if device.Active {
				onlineDevices = append(onlineDevices, map[string]interface{}{
					"id":          device.ID,
					"name":        device.Name,
					"lastSeen":    device.LastSeen.Format(time.RFC3339),
					"online":      device.Active,
					"fingerprint":  device.Fingerprint,
					"type":        device.Type,
				})
			}
		}
		
		stats := map[string]interface{}{
			"status":          "running",
			"uptime":          time.Since(startTime).String(),
			"active_device":   backend.activeDevice,
			"device_count":    len(backend.devices),
			"devices_online":  len(onlineDevices),
			"online_devices":  onlineDevices,
			"mobile_clients":  len(backend.clients),
			"token_counter":   backend.tokenCounter,
		}
		backend.mu.RUnlock()
		json.NewEncoder(w).Encode(stats)
	})
	
	// Update device address endpoint
	http.HandleFunc("/update-device", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		
		var req struct {
			DeviceID string `json:"device_id"`
			Address  string `json:"address"`
		}
		json.NewDecoder(r.Body).Decode(&req)
		
		backend.mu.Lock()
		if device, exists := backend.devices[req.DeviceID]; exists {
			device.Address = req.Address
			device.LastSeen = time.Now()
			log.Printf("Updated device %s address to %s", req.DeviceID, req.Address)
		}
		backend.mu.Unlock()
		
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
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
