import re
with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

new_endpoint = '''func handleWebhookAlert(b *Backend) http.HandlerFunc {
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
		
		deviceID, _ := req["device_id"].(string)
		secretHash, _ := req["secret_hash"].(string)
		
		b.mu.RLock()
		device, exists := b.devices[deviceID]
		b.mu.RUnlock()
		
		if !exists || subtle.ConstantTimeCompare([]byte(device.SecurityPhraseHash), []byte(secretHash)) != 1 {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		
		alertType, _ := req["alert_type"].(string)
		sourceIp, _ := req["source_ip"].(string)
		desc, _ := req["description"].(string)
		sev, _ := req["severity"].(string)
		
		b.addSecurityAlert(alertType, sourceIp, deviceID, "local-agent", desc, sev)
		
		trip, _ := req["trip_circuit"].(bool)
		if trip {
			b.tripCircuitBreaker(deviceID)
		}
		
		w.WriteHeader(http.StatusOK)
	}
}

func handleWebhookResult(b *Backend) http.HandlerFunc {'''

content = content.replace('func handleWebhookResult(b *Backend) http.HandlerFunc {', new_endpoint)
content = content.replace('http.HandleFunc("/webhook/result", handleWebhookResult(backend))', 'http.HandleFunc("/webhook/result", handleWebhookResult(backend))\n\thttp.HandleFunc("/webhook/alert", handleWebhookAlert(backend))')

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
