import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    code = f.read()

execute_handler = '''		var req map[string]string
		json.NewDecoder(r.Body).Decode(&req)

		command := req["command"]
		mode := req["mode"]
		clientID := req["client_id"]
		
		w.WriteHeader(http.StatusAccepted)
		
		go func() {
			output, err := executeCommand(command, mode)
			
			// Post the result back to backend
			backendURL := strings.TrimRight(connData.BackendURL, "/") + "/webhook/result"
			
			resultPayload := map[string]string{
				"client_id": clientID,
				"device_id": connData.DeviceID,
			}
			
			if err != nil {
				resultPayload["error"] = "Command failed:\\n" + err.Error()
			} else {
				resultPayload["output"] = output
			}
			
			payloadBytes, _ := json.Marshal(resultPayload)
			
			req, _ := http.NewRequest(http.MethodPost, backendURL, bytes.NewBuffer(payloadBytes))
			req.Header.Set("Content-Type", "application/json")
			if strings.Contains(connData.BackendURL, "ngrok") || strings.Contains(connData.BackendURL, "ngrok-free") {
				req.Header.Set("ngrok-skip-browser-warning", "true")
			}
			
			http.DefaultClient.Do(req)
		}()'''

# Find and replace the execute body
code = re.sub(
    r'var req map\[string\]string\n.*?w\.WriteHeader\(http\.StatusOK\)\n\t\tjson\.NewEncoder\(w\)\.Encode\(map\[string\]string\{"output": output\}\)\n\t\}\)',
    execute_handler + "\n\t})",
    code,
    flags=re.DOTALL
)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(code)

print("Local agent patched for webhook.")
