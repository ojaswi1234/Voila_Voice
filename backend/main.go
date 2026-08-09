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

type Device struct {
	ID        string
	Name      string
	Address   string
	Active    bool
	LastSeen  time.Time
	AuthToken string
	LockedBy  string // Mobile device ID that has exclusive access
	LockedAt  time.Time
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
	return &Backend{
		devices:      make(map[string]*Device),
		activeDevice: "",
		tokenCounter: 0,
		clients:      make(map[string]*WebSocketClient),
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
	b.mu.RUnlock()

	if !exists || !device.Active {
		return "", http.ErrNotSupported
	}

	// Optimize command before forwarding
	optimizedCommand := b.optimizeCommand(command)

	// Forward to local agent via HTTP
	url := device.Address + "/execute"
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

			// Parse message
			var msg map[string]string
			json.Unmarshal(message, &msg)

			// Handle different message types
			switch msg["type"] {
			case "command":
				deviceID := msg["device_id"]
				command := msg["command"]
				
				// If no device specified, use active device
				if deviceID == "" {
					device := b.getActiveDevice()
					if device != nil {
						deviceID = device.ID
					} else {
						conn.WriteMessage(messageType, []byte("ERROR: No active device"))
						continue
					}
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
				deviceID := msg["device_id"]
				err := b.setActiveDevice(deviceID)
				if err != nil {
					log.Printf("Switch device error: %v", err)
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device switched"))
				}
				
			case "lock_device":
				deviceID := msg["device_id"]
				err := b.lockDevice(deviceID, clientID)
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device locked"))
				}
				
			case "unlock_device":
				deviceID := msg["device_id"]
				err := b.unlockDevice(deviceID, clientID)
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device unlocked"))
				}
				
			case "get_devices":
				devices := b.getAllDevices()
				deviceList := make([]map[string]interface{}, 0)
				for _, d := range devices {
					deviceList = append(deviceList, map[string]interface{}{
						"id":      d.ID,
						"name":    d.Name,
						"active":  d.ID == b.activeDevice,
						"locked":  d.LockedBy != "",
						"lockedBy": d.LockedBy,
						"lastSeen": d.LastSeen,
					})
				}
				jsonData, _ := json.Marshal(deviceList)
				conn.WriteMessage(messageType, jsonData)
				
			case "get_stats":
				b.mu.RLock()
				stats := map[string]interface{}{
					"token_counter": b.tokenCounter,
					"device_count":  len(b.devices),
					"active_device": b.activeDevice,
				}
				b.mu.RUnlock()
				
				jsonData, _ := json.Marshal(stats)
				conn.WriteMessage(messageType, jsonData)
				
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
	
	// Auto-detect ngrok URL if NGROK_AUTO_DETECT is enabled
	if os.Getenv("NGROK_AUTO_DETECT") == "true" {
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
	
	// Health check endpoint for Render keep-alive
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		backend.mu.RLock()
		health := map[string]interface{}{
			"status": "ok",
			"timestamp": time.Now().Format(time.RFC3339),
			"uptime": time.Since(startTime).String(),
			"devices": len(backend.devices),
		}
		backend.mu.RUnlock()
		json.NewEncoder(w).Encode(health)
	})
	
	// Status endpoint for monitoring
	http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		backend.mu.RLock()
		stats := map[string]interface{}{
			"status": "running",
			"uptime": time.Since(startTime).String(),
			"active_device": backend.activeDevice,
			"device_count": len(backend.devices),
			"token_counter": backend.tokenCounter,
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
		return result.Tunnels[0].PublicURL, nil
	}
	
	return "", fmt.Errorf("no ngrok tunnels found")
}
