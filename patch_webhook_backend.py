import re

with open('main.go', 'r', encoding='utf-8') as f:
    backend_code = f.read()

# 1. Modify forwardCommand to pass clientID
backend_code = re.sub(
    r'func \(b \*Backend\) forwardCommand\(deviceID, command, mode string\) \(string, error\) {',
    r'func (b *Backend) forwardCommand(deviceID, command, mode, clientID string) (string, error) {',
    backend_code
)

backend_code = re.sub(
    r'payload := map\[string\]string\{\"command\": optimizedCommand, \"mode\": mode\}',
    r'payload := map[string]string{"command": optimizedCommand, "mode": mode, "client_id": clientID}',
    backend_code
)

# 2. Modify websocket to pass clientID
backend_code = re.sub(
    r'result, err := b\.forwardCommand\(dID, cmd, m\)',
    r'result, err := b.forwardCommand(dID, cmd, m, cID)',
    backend_code
)

# 3. Add webhook endpoint
webhook_code = """
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

		b.unlockDevice(deviceID, clientID)

		if clientID != "" {
			if errorMsg != "" {
				b.writeMessage(clientID, websocket.TextMessage, []byte("ERROR: "+errorMsg))
			} else {
				// We assume output is JSON string with summary, status, etc., or plain text
				b.writeMessage(clientID, websocket.TextMessage, []byte(output))
			}
		}
		w.WriteHeader(http.StatusOK)
	}
}
"""

if "func handleWebhookResult" not in backend_code:
    backend_code = backend_code.replace("func handleWebSocket(b *Backend)", webhook_code + "\nfunc handleWebSocket(b *Backend)")

backend_code = backend_code.replace('http.HandleFunc("/ws", handleWebSocket(backend))', 'http.HandleFunc("/ws", handleWebSocket(backend))\n\thttp.HandleFunc("/webhook/result", handleWebhookResult(backend))')

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(backend_code)

print("Backend patched for webhook.")
