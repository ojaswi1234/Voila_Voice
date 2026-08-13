import re

with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update forwardCommand to take mode
fc_old = """func (b *Backend) forwardCommand(deviceID, command string) (string, error) {"""
fc_new = """func (b *Backend) forwardCommand(deviceID, command, mode string) (string, error) {"""
content = content.replace(fc_old, fc_new)

# 2. Update response format in forwardCommand
resp_old = """	var result map[string]string
	json.NewDecoder(resp.Body).Decode(&result)
	
	summary := b.generateTaskSummary(command, result["output"])
	response := map[string]string{
		"output": result["output"],
		"summary": summary,
	}
	
	jsonResponse, _ := json.Marshal(response)
	return string(jsonResponse), nil
}"""
resp_new = """	var result map[string]string
	json.NewDecoder(resp.Body).Decode(&result)
	
	output := result["output"]
	status := "ok"
	if errOutput, ok := result["error"]; ok && errOutput != "" {
		output += "\\n" + errOutput
		status = "error"
	}
	if output == "" {
		output = "Command executed with no output."
	}
	
	summary := b.generateTaskSummary(command, output)
	
	if mode == "" {
		mode = "command"
	}
	
	response := map[string]string{
		"output": output,
		"summary": summary,
		"status": status,
		"mode": mode,
	}
	
	jsonResponse, _ := json.Marshal(response)
	return string(jsonResponse), nil
}"""
content = content.replace(resp_old, resp_new)

# 3. Update case "command" to pass mode
cmd_case_old = """			case "command":
				command, _ := msg["command"].(string)"""
cmd_case_new = """			case "command":
				command, _ := msg["command"].(string)
				mode, _ := msg["mode"].(string)"""
content = content.replace(cmd_case_old, cmd_case_new)

cmd_call_old = """				b.lockDevice(deviceID, clientID)
				result, err := b.forwardCommand(deviceID, command)
				b.unlockDevice(deviceID, clientID)"""
cmd_call_new = """				b.lockDevice(deviceID, clientID)
				result, err := b.forwardCommand(deviceID, command, mode)
				b.unlockDevice(deviceID, clientID)"""
content = content.replace(cmd_call_old, cmd_call_new)

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
