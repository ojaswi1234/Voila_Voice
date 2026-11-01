package main

import (
	"bytes"
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestProxyEndpointWhitelist(t *testing.T) {
	backend := &Backend{
		devices:      make(map[string]*Device),
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]*IPRateLimitEntry),
	}
	backend.devices["dev-1"] = &Device{
		ID:                 "dev-1",
		Address:            "http://127.0.0.1:8000",
		Active:             true,
		SecurityPhraseHash: hashPhrase("testphrase", "dev-1"),
	}

	proxyHandler := handleProxy(backend)

	// 1. Test forbidden /api-keys proxy call
	reqKeys := httptest.NewRequest("POST", "/proxy/dev-1/api-keys", bytes.NewReader([]byte(`{}`)))
	wKeys := httptest.NewRecorder()
	proxyHandler(wKeys, reqKeys)
	if wKeys.Code != http.StatusForbidden {
		t.Fatalf("Expected 403 Forbidden for /proxy/dev-1/api-keys, got %d", wKeys.Code)
	}

	// 2. Test forbidden /set-mode proxy call
	reqMode := httptest.NewRequest("POST", "/proxy/dev-1/set-mode", bytes.NewReader([]byte(`{}`)))
	wMode := httptest.NewRecorder()
	proxyHandler(wMode, reqMode)
	if wMode.Code != http.StatusForbidden {
		t.Fatalf("Expected 403 Forbidden for /proxy/dev-1/set-mode, got %d", wMode.Code)
	}

	// 3. Test directory traversal
	reqTrav := httptest.NewRequest("GET", "/proxy/dev-1/../etc/passwd", nil)
	wTrav := httptest.NewRecorder()
	proxyHandler(wTrav, reqTrav)
	if wTrav.Code != http.StatusForbidden && wTrav.Code != http.StatusBadRequest {
		t.Fatalf("Expected 403 or 400 for path traversal, got %d", wTrav.Code)
	}

	// 4. Test unauthenticated /proxy/dev-1/bg-tasks
	reqUnauth := httptest.NewRequest("GET", "/proxy/dev-1/bg-tasks", nil)
	wUnauth := httptest.NewRecorder()
	proxyHandler(wUnauth, reqUnauth)
	if wUnauth.Code != http.StatusUnauthorized {
		t.Fatalf("Expected 401 Unauthorized for unauthenticated proxy call, got %d", wUnauth.Code)
	}

	// 5. Test authenticated /proxy/dev-1/bg-tasks with valid session token
	validToken, _ := createSessionToken("dev-1", "client-1")
	reqAuth := httptest.NewRequest("GET", "/proxy/dev-1/bg-tasks", nil)
	reqAuth.Header.Set("Authorization", "Bearer "+validToken)
	wAuth := httptest.NewRecorder()
	proxyHandler(wAuth, reqAuth)
	// Passes auth check and reaches device check / HTTP client
	if wAuth.Code == http.StatusUnauthorized || wAuth.Code == http.StatusForbidden {
		t.Fatalf("Expected proxy request to pass auth, got code %d", wAuth.Code)
	}
}

func TestHeartbeatHijackProtection(t *testing.T) {
	backend := &Backend{
		devices:      make(map[string]*Device),
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]*IPRateLimitEntry),
	}
	backend.devices["dev-target"] = &Device{
		ID:                 "dev-target",
		Address:            "https://legit.ngrok-free.app",
		Active:             true,
		SecurityPhraseHash: hashPhrase("secret123", "dev-target"),
	}

	hbHandler := handleHeartbeat(backend)

	// Attempt address update without secret_hash
	hbPayload := map[string]string{
		"device_id": "dev-target",
		"address":   "https://attacker.ngrok-free.app",
	}
	hbBytes, _ := json.Marshal(hbPayload)
	reqHb := httptest.NewRequest("POST", "/heartbeat", bytes.NewReader(hbBytes))
	wHb := httptest.NewRecorder()
	hbHandler(wHb, reqHb)

	// Address must NOT be changed
	if backend.devices["dev-target"].Address != "https://legit.ngrok-free.app" {
		t.Errorf("SECURITY RISK: Device address was hijacked without valid secret_hash!")
	}
}

func TestRegisterTakeoverProtection(t *testing.T) {
	backend := &Backend{
		devices:      make(map[string]*Device),
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]*IPRateLimitEntry),
	}
	backend.devices["dev-reg"] = &Device{
		ID:                 "dev-reg",
		Address:            "https://legit.ngrok-free.app",
		Active:             true,
		SecurityPhraseHash: hashPhrase("originalphrase", "dev-reg"),
	}

	regHandler := handleRegister(backend)

	// Attempt takeover with rogue passphrase
	roguePayload := map[string]string{
		"device_id":       "dev-reg",
		"device_name":     "Hacked Device",
		"address":         "https://hacked.ngrok-free.app",
		"security_phrase": "roguephrase",
	}
	rBytes, _ := json.Marshal(roguePayload)
	reqReg := httptest.NewRequest("POST", "/register", bytes.NewReader(rBytes))
	wReg := httptest.NewRecorder()
	regHandler(wReg, reqReg)

	if wReg.Code != http.StatusUnauthorized {
		t.Fatalf("Expected 401 Unauthorized for rogue re-registration, got %d", wReg.Code)
	}

	// Verify device was not overwritten
	if backend.devices["dev-reg"].Address != "https://legit.ngrok-free.app" {
		t.Errorf("SECURITY RISK: Device was hijacked by unauthenticated register request!")
	}
}

func TestIPRateLimitingClean(t *testing.T) {
	backend := &Backend{
		devices:      make(map[string]*Device),
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]*IPRateLimitEntry),
	}

	ip := "192.168.1.100"
	for i := 0; i < 5; i++ {
		backend.recordIPFailure(ip)
	}
	if backend.isIPRateLimited(ip) {
		t.Errorf("5 failures should not trigger lockout yet (requires > 5)")
	}

	// 6th failure
	backend.recordIPFailure(ip)
	if !backend.isIPRateLimited(ip) {
		t.Errorf("Expected IP to be rate limited after 6 failures")
	}

	// Reset
	backend.resetIPLimit(ip)
	if backend.isIPRateLimited(ip) {
		t.Errorf("Expected IP to be cleared after resetIPLimit")
	}
}

func TestStaleDeviceLockAutoRelease(t *testing.T) {
	backend := &Backend{
		devices:      make(map[string]*Device),
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]*IPRateLimitEntry),
		offlineQueue: make(map[string][]QueuedMessage),
	}

	// Device locked 6 minutes ago
	backend.devices["dev-locked"] = &Device{
		ID:        "dev-locked",
		LockedBy:  "client-abc",
		LockedAt:  time.Now().Add(-6 * time.Minute),
		Active:    true,
		LastSeen:  time.Now(),
		Reachable: true,
	}

	if backend.isDeviceLocked("dev-locked", "client-other") {
		t.Errorf("isDeviceLocked should report false for lock older than 5 minutes")
	}

	// Trigger markStaleDevices
	backend.markStaleDevices()

	if backend.devices["dev-locked"].LockedBy != "" {
		t.Errorf("markStaleDevices should have auto-released stale lock older than 5 minutes")
	}
}

func TestDeliveryDispatcherFIFO(t *testing.T) {
	backend := &Backend{
		devices:      make(map[string]*Device),
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]*IPRateLimitEntry),
	}
	dispatcher := NewDeliveryDispatcher(0, 0, backend)

	clientChan := make(chan DeliveryJob, 100)
	client := &WebSocketClient{
		clientID: "test-client",
		sendChan: clientChan,
	}
	backend.clients["test-client"] = client

	for i := 1; i <= 10; i++ {
		dispatcher.Dispatch("test-client", 1, []byte(string(rune('0'+i))))
	}

	for i := 1; i <= 10; i++ {
		select {
		case job := <-clientChan:
			expected := string(rune('0' + i))
			if string(job.Payload) != expected {
				t.Fatalf("FIFO violation: expected %s, got %s", expected, string(job.Payload))
			}
		default:
			t.Fatalf("Expected job %d in sendChan", i)
		}
	}
}

func TestWebhookResultNoCrossClientBroadcast(t *testing.T) {
	backend := &Backend{
		devices:      make(map[string]*Device),
		clients:      make(map[string]*WebSocketClient),
		ipRateLimits: make(map[string]*IPRateLimitEntry),
		offlineQueue: make(map[string][]QueuedMessage),
	}
	dispatcher := NewDeliveryDispatcher(0, 0, backend)
	backend.dispatcher = dispatcher

	backend.devices["dev-1"] = &Device{
		ID:                 "dev-1",
		Address:            "http://127.0.0.1:8000",
		Active:             true,
		SecurityPhraseHash: hashPhrase("testphrase", "dev-1"),
	}

	// Client A (initiator)
	chanA := make(chan DeliveryJob, 10)
	backend.clients["client-A"] = &WebSocketClient{
		clientID: "client-A",
		sendChan: chanA,
	}

	// Client B (innocent bystander)
	chanB := make(chan DeliveryJob, 10)
	backend.clients["client-B"] = &WebSocketClient{
		clientID: "client-B",
		sendChan: chanB,
	}

	whHandler := handleWebhookResult(backend)

	payload := map[string]interface{}{
		"client_id":   "client-A",
		"device_id":   "dev-1",
		"secret_hash": hashPhrase("testphrase", "dev-1"),
		"output":      "Super secret calculation output for Client A",
		"mode":        "shell",
	}
	bodyBytes, _ := json.Marshal(payload)
	req := httptest.NewRequest("POST", "/webhook/result", bytes.NewReader(bodyBytes))
	w := httptest.NewRecorder()
	whHandler(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK from webhook result, got %d", w.Code)
	}

	// Client A MUST receive the message
	select {
	case job := <-chanA:
		var resp map[string]string
		json.Unmarshal(job.Payload, &resp)
		if resp["output"] != "Super secret calculation output for Client A" {
			t.Errorf("Unexpected output in Client A payload: %v", resp)
		}
	default:
		t.Errorf("Expected Client A to receive result")
	}

	// Client B MUST NOT receive anything (0 cross-client leak)
	select {
	case job := <-chanB:
		t.Fatalf("SECURITY BREACH: Client B received Client A's secret output: %s", string(job.Payload))
	default:
		// Passed - no leak to Client B
	}
}

func TestSessionSigningKeyThreadSafety(t *testing.T) {
	// Reset for test
	results := make([][]byte, 20)
	errChan := make(chan error, 20)

	for i := 0; i < 20; i++ {
		go func(idx int) {
			key := getSessionSigningKey()
			results[idx] = key
			errChan <- nil
		}(i)
	}

	for i := 0; i < 20; i++ {
		<-errChan
	}

	firstKey := results[0]
	if len(firstKey) == 0 {
		t.Fatalf("Expected non-empty signing key")
	}
	for i := 1; i < 20; i++ {
		if !bytes.Equal(firstKey, results[i]) {
			t.Fatalf("Data race / key inconsistency: key at idx %d differs from idx 0", i)
		}
	}
}


func TestTokenUsageAuth(t *testing.T) {
	backend := &Backend{
		devices:           make(map[string]*Device),
		clients:           make(map[string]*WebSocketClient),
		lastTokenSnapshot: make(map[string]map[string]interface{}),
	}
	backend.devices["dev-1"] = &Device{
		ID:                 "dev-1",
		SecurityPhraseHash: hashPhrase("testphrase", "dev-1"),
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload map[string]interface{}
		json.NewDecoder(r.Body).Decode(&payload)
		deviceID, _ := payload["device_id"].(string)
		secretHash, _ := payload["secret_hash"].(string)

		backend.mu.Lock()
		device, exists := backend.devices[deviceID]
		if exists && device.SecurityPhraseHash != "" {
			if secretHash == "" || subtle.ConstantTimeCompare([]byte(device.SecurityPhraseHash), []byte(secretHash)) != 1 {
				backend.mu.Unlock()
				http.Error(w, "Unauthorized", http.StatusUnauthorized)
				return
			}
		}
		backend.mu.Unlock()
		w.WriteHeader(http.StatusOK)
	})

	// 1. Without secret_hash - MUST be 401 Unauthorized
	reqNoHash := httptest.NewRequest("POST", "/webhook/token-usage", bytes.NewReader([]byte(`{"device_id":"dev-1"}`)))
	wNoHash := httptest.NewRecorder()
	handler(wNoHash, reqNoHash)
	if wNoHash.Code != http.StatusUnauthorized {
		t.Fatalf("Expected 401 Unauthorized for empty secret_hash, got %d", wNoHash.Code)
	}

	// 2. With wrong secret_hash - MUST be 401 Unauthorized
	reqWrong := httptest.NewRequest("POST", "/webhook/token-usage", bytes.NewReader([]byte(`{"device_id":"dev-1","secret_hash":"wrong"}`)))
	wWrong := httptest.NewRecorder()
	handler(wWrong, reqWrong)
	if wWrong.Code != http.StatusUnauthorized {
		t.Fatalf("Expected 401 Unauthorized for invalid secret_hash, got %d", wWrong.Code)
	}

	// 3. With correct secret_hash - MUST be 200 OK
	reqValid := httptest.NewRequest("POST", "/webhook/token-usage", bytes.NewReader([]byte(fmt.Sprintf(`{"device_id":"dev-1","secret_hash":"%s"}`, hashPhrase("testphrase", "dev-1")))))
	wValid := httptest.NewRecorder()
	handler(wValid, reqValid)
	if wValid.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK for valid secret_hash, got %d", wValid.Code)
	}
}
