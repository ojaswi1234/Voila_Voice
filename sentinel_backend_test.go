package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestThreatIntelCache(t *testing.T) {
	cache := NewThreatIntelCache()

	// Verify seed indicator
	seed, exists := cache.CheckIndicator("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
	if !exists {
		t.Fatalf("Expected seed indicator to exist")
	}
	if seed.Source != "sentinel_seed" {
		t.Errorf("Expected source sentinel_seed, got %s", seed.Source)
	}

	// Add dynamic test indicator
	testHash := "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
	cache.AddIndicator(ThreatItem{
		Indicator:   testHash,
		Type:        "sha256",
		Description: "Simulated ransomware dropper",
		Severity:    "high",
		FirstSeen:   time.Now(),
		Source:      "local_agent_pe",
	})

	item, found := cache.CheckIndicator(testHash)
	if !found {
		t.Fatalf("Expected dynamic test indicator to be found")
	}
	if item.Severity != "high" {
		t.Errorf("Expected severity high, got %s", item.Severity)
	}

	list := cache.ListIndicators()
	if len(list) < 2 {
		t.Errorf("Expected at least 2 indicators, got %d", len(list))
	}
}

func TestCSWSHOriginCheck(t *testing.T) {
	// Authorized origins: empty header (mobile app / native), localhost, 127.0.0.1
	reqNative := httptest.NewRequest("GET", "http://localhost:8090/ws", nil)
	if !upgrader.CheckOrigin(reqNative) {
		t.Errorf("Expected native request with empty Origin to be accepted")
	}

	reqLocalhost := httptest.NewRequest("GET", "http://localhost:8090/ws", nil)
	reqLocalhost.Header.Set("Origin", "http://localhost:3000")
	if !upgrader.CheckOrigin(reqLocalhost) {
		t.Errorf("Expected localhost:3000 to be accepted")
	}

	reqLoopback := httptest.NewRequest("GET", "http://localhost:8090/ws", nil)
	reqLoopback.Header.Set("Origin", "http://127.0.0.1:8080")
	if !upgrader.CheckOrigin(reqLoopback) {
		t.Errorf("Expected 127.0.0.1:8080 to be accepted")
	}

	// Unauthorized rogue browser origin
	reqMalicious := httptest.NewRequest("GET", "http://localhost:8090/ws", nil)
	reqMalicious.Header.Set("Origin", "https://evil-attacker-site.com")
	if upgrader.CheckOrigin(reqMalicious) {
		t.Errorf("SECURITY RISK: Evil origin https://evil-attacker-site.com should be rejected by CSWSH check")
	}
}

func TestSentinelEndpoints(t *testing.T) {
	backend := NewBackend()

	// 1. Test GET /sentinel/threat-intel
	reqGet := httptest.NewRequest("GET", "/sentinel/threat-intel", nil)
	wGet := httptest.NewRecorder()
	handleSentinelThreatIntel(backend)(wGet, reqGet)

	if wGet.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", wGet.Code)
	}

	var getResp map[string]interface{}
	if err := json.Unmarshal(wGet.Body.Bytes(), &getResp); err != nil {
		t.Fatalf("Failed to parse json: %v", err)
	}
	if getResp["status"] != "OK" {
		t.Errorf("Expected status OK, got %v", getResp["status"])
	}

	// 2. Test POST /sentinel/threat-intel
	payload := map[string]interface{}{
		"indicator":   "bad_actor_ip_198.51.100.23",
		"type":        "c2_ip",
		"description": "Observed C2 exfiltration node",
		"severity":    "critical",
	}
	bodyBytes, _ := json.Marshal(payload)
	reqPost := httptest.NewRequest("POST", "/sentinel/threat-intel", bytes.NewReader(bodyBytes))
	wPost := httptest.NewRecorder()
	handleSentinelThreatIntel(backend)(wPost, reqPost)

	if wPost.Code != http.StatusOK {
		t.Fatalf("Expected status 200 from POST, got %d", wPost.Code)
	}

	// 3. Test GET /sentinel/incidents
	reqInc := httptest.NewRequest("GET", "/sentinel/incidents", nil)
	wInc := httptest.NewRecorder()
	handleSentinelIncidents(backend)(wInc, reqInc)

	if wInc.Code != http.StatusOK {
		t.Fatalf("Expected status 200 from incidents, got %d", wInc.Code)
	}
}

func TestLeakPatterns(t *testing.T) {
	testSamples := []struct {
		Text     string
		Expected bool
	}{
		{string([]byte{'A', 'I', 'z', 'a'}) + "SyD-1234567890abcdefghijklmnopqrstu", true},
		{string([]byte{'A', 'K', 'I', 'A'}) + "IOSFODNN7EXAMPLE", true},
		{string([]byte{'x', 'o', 'x', 'b', '-'}) + "123456789012-1234567890123-456789abcdefghijklmnopqrst", true},
		{string([]byte{'g', 'h', 'p', '_'}) + "1234567890abcdefghijklmnopqrstuvwxyz", true},
		{"-----BEGIN " + "RSA PRIVATE KEY-----", true},
		{"This is a normal commit message with no secrets", false},
	}

	for _, sample := range testSamples {
		matched := false
		for _, re := range leakPatterns {
			if re.MatchString(sample.Text) {
				matched = true
				break
			}
		}
		if matched != sample.Expected {
			t.Errorf("Sample %q: expected match=%v, got %v", sample.Text, sample.Expected, matched)
		}
	}
}
