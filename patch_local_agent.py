import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    code = f.read()

# Add sync.Mutex and currentCmd variables
if "var currentCmd *exec.Cmd" not in code:
    code = code.replace(
        "var (", 
        "var (\n\tcmdMu      sync.Mutex\n\tcurrentCmd *exec.Cmd\n", 
    )

# Update executeCommand
exec_pattern = r"(func executeCommand\(command string, mode string\) \(string, error\) \{[\s\S]*?var stdout, stderr bytes\.Buffer\n\tcmd\.Stdout = &stdout\n\tcmd\.Stderr = &stderr\n)(\n\terr := cmd\.Run\(\))"
new_exec_logic = r"\1\n\tcmdMu.Lock()\n\tcurrentCmd = cmd\n\tcmdMu.Unlock()\n\n\terr := cmd.Run()\n\n\tcmdMu.Lock()\n\tcurrentCmd = nil\n\tcmdMu.Unlock()\n"
code = re.sub(exec_pattern, new_exec_logic, code)

# Add /stop endpoint
stop_endpoint = '''	mux.HandleFunc("/stop", func(w http.ResponseWriter, r *http.Request) {
		connData, err := loadConnectionData()
		if err != nil || connData.SecurityPhrase == "" {
			http.Error(w, "Agent not configured", http.StatusServiceUnavailable)
			return
		}
		
		secretHeader := r.Header.Get("X-Exec-Secret")
		if secretHeader != connData.SecurityPhraseHash {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		cmdMu.Lock()
		if currentCmd != nil && currentCmd.Process != nil {
			currentCmd.Process.Kill()
		}
		cmdMu.Unlock()

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"output": "Command execution stopped."})
	})
'''
if "/stop" not in code:
    code = code.replace("mux.HandleFunc(\"/execute\"", stop_endpoint + "\n\tmux.HandleFunc(\"/execute\"")

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched local-agent/main.go successfully")
