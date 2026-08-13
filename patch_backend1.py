import re
import os

with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Imports
imports = """import (
	"bytes"
	"crypto/hmac"
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
)"""
content = re.sub(r'import \((.*?)\)', imports, content, flags=re.DOTALL)

# 2. Device struct and Backend struct
device_struct = """type Device struct {
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
}"""
content = re.sub(r'type Device struct \{.*?type Backend struct \{.*?\}', device_struct, content, flags=re.DOTALL)

# Update NewBackend
new_backend = """func NewBackend() *Backend {
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
}"""
content = re.sub(r'func NewBackend\(\) \*Backend \{.*?return b\n\}', new_backend, content, flags=re.DOTALL)


# 3. Add helper functions
helpers = """
func safeHTTPClient() *http.Client {
	return &http.Client{
		Timeout: 10 * time.Second,
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

func createSessionToken(deviceID, clientID string) string {
	secret := os.Getenv("SESSION_SIGNING_KEY")
	if secret == "" {
		secret = "default_unsafe_secret"
	}
	payload := map[string]interface{}{
		"sid": fmt.Sprintf("sess-%d", time.Now().UnixNano()),
		"device_id": deviceID,
		"client_device_id": clientID,
		"iat": time.Now().Unix(),
		"exp": time.Now().Add(15 * time.Minute).Unix(),
	}
	payloadBytes, _ := json.Marshal(payload)
	payloadB64 := base64.URLEncoding.EncodeToString(payloadBytes)
	
	mac := hmac.New(sha256.New, []byte(secret))
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
	
	secret := os.Getenv("SESSION_SIGNING_KEY")
	if secret == "" {
		secret = "default_unsafe_secret"
	}
	mac := hmac.New(sha256.New, []byte(secret))
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
		suffixes = ".ngrok-free.app,.ngrok.app,.ngrok.io"
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
"""
content = content.replace('func (b *Backend) markStaleDevices() {', helpers + '\nfunc (b *Backend) markStaleDevices() {')

# 4. Modify pingDevice
ping_device = """func (b *Backend) pingDevice(device *Device) {
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
}"""
content = re.sub(r'func \(b \*Backend\) pingDevice.*?\}\n\}', ping_device, content, flags=re.DOTALL)


# 5. Modify forwardCommand
forward_cmd = """func (b *Backend) forwardCommand(deviceID, command string) (string, error) {
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
	payload := map[string]string{"command": optimizedCommand}
	jsonPayload, _ := json.Marshal(payload)

	client := safeHTTPClient()
	req, err := http.NewRequest("POST", urlStr, bytes.NewBuffer(jsonPayload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if execSecret := os.Getenv("AGENT_EXEC_SECRET"); execSecret != "" {
		req.Header.Set("X-Exec-Secret", execSecret)
	}

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
	
	summary := b.generateTaskSummary(command, result["output"])
	response := map[string]string{
		"output": result["output"],
		"summary": summary,
	}
	
	jsonResponse, _ := json.Marshal(response)
	return string(jsonResponse), nil
}"""
content = re.sub(r'func \(b \*Backend\) forwardCommand.*?return string\(jsonResponse\), nil\n\}', forward_cmd, content, flags=re.DOTALL)


with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
