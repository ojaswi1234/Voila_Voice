import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Tracking vars (Add safely to global scope)
var_decl = '''
var (
	localMockCount int
	localMockMu sync.Mutex
)
'''
if 'localMockCount int' not in content:
    content = content.replace('var (', var_decl + '\nvar (', 1)

# 2. Helper Func
helper_func = '''
func handleLocalMockExecution(w http.ResponseWriter, r *http.Request, command string, connData ConnectionData, endpoint string) {
	localMockMu.Lock()
	localMockCount++
	currentCount := localMockCount
	localMockMu.Unlock()
	
	tripCircuit := currentCount >= 3
	
	go func() {
		alertPayload := map[string]interface{}{
			"device_id":    connData.DeviceID,
			"secret_hash":  hashPhrase(connData.SecurityPhrase, connData.DeviceID),
			"alert_type":   "mock_command",
			"source_ip":    r.RemoteAddr,
			"description":  "Unauthorized access attempt directly to local-agent " + endpoint,
			"severity":     "high",
			"trip_circuit": tripCircuit,
		}
		body, _ := json.Marshal(alertPayload)
		http.Post(connData.BackendURL+"/webhook/alert", "application/json", bytes.NewBuffer(body))
	}()
	
	if tripCircuit {
		time.Sleep(decoy.GetMockDelay())
		http.Error(w, "Circuit breaker open. Request dropped.", http.StatusServiceUnavailable)
		return
	}
	
	time.Sleep(decoy.GetMockDelay())
	mockResp := decoy.GenerateMockResponse(command)
	w.WriteHeader(http.StatusOK)
	if endpoint == "/execute" {
		w.Write([]byte(mockResp))
	} else {
		json.NewEncoder(w).Encode(map[string]string{"status": "circuit_closed"})
	}
}

'''
if 'handleLocalMockExecution' not in content:
    content = content.replace('func main() {', helper_func + 'func main() {', 1)

# 3. Patch /circuit (Line ~1364)
content = re.sub(
    r'if subtle\.ConstantTimeCompare\(\[\]byte\(providedSecret\), \[\]byte\(expectedSecret\)\) != 1 \{\s*http\.Error\(w, "Unauthorized", http\.StatusUnauthorized\)\s*return\s*\}',
    r'''if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
			handleLocalMockExecution(w, r, "circuit", connData, "/circuit")
			return
		}''',
    content, count=1
)

content = re.sub(
    r'if subtle\.ConstantTimeCompare\(\[\]byte\(providedSecret\), \[\]byte\(expectedSecret\)\) != 1 \{\s*http\.Error\(w, "Unauthorized", http\.StatusUnauthorized\)\s*return\s*\}',
    r'''if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
			cmd := "unknown"
			bodyBytes, _ := io.ReadAll(r.Body)
			r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
			var req struct { Command string `json:"command"` }
			json.Unmarshal(bodyBytes, &req)
			if req.Command != "" { cmd = req.Command }
			handleLocalMockExecution(w, r, cmd, connData, r.URL.Path)
			return
		}''',
    content
)

# 4. Circuit Reset
old_circuit_reset = '''		if req.State == "closed" {
			currentCmdMu.Lock()
			currentCmd = nil // Reset command pointer so new commands can run
			currentCmdMu.Unlock()
			
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]string{"status": "circuit_closed"})'''
new_circuit_reset = '''		if req.State == "closed" {
			currentCmdMu.Lock()
			currentCmd = nil
			currentCmdMu.Unlock()
			
			localMockMu.Lock()
			localMockCount = 0
			localMockMu.Unlock()
			
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]string{"status": "circuit_closed"})'''
content = content.replace(old_circuit_reset, new_circuit_reset)


# 5. Update descriptions
content = content.replace(
    '\"description\": \"Search type: \'text\' (default, DuckDuckGo text search) or \'image\' (Picsum random image search)\"',
    '\"description\": \"Search type: \'text\' (default, DuckDuckGo text search) or \'image\' (Openverse CC image search)\"'
)
content = content.replace(
    '\"description\": \"If true, AI will automatically search for and download relevant images for content/image slides using web_research\"',
    '\"description\": \"If true, AI will automatically search for and download relevant images using Openverse API for content/image slides\"'
)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(content)
