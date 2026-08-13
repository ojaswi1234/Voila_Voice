import re

with open('main.go', 'r', encoding='utf-8') as f:
    code = f.read()

# Add stopCommand method to backend
stop_func = '''
func (b *Backend) stopCommand(deviceID string) (string, error) {
	b.mu.RLock()
	device, exists := b.devices[deviceID]
	if !exists {
		b.mu.RUnlock()
		return "", fmt.Errorf("device not found: %s", deviceID)
	}
	active := device.Active
	address := device.Address
	b.mu.RUnlock()

	if !active {
		return "", fmt.Errorf("device offline: %s", deviceID)
	}

	urlStr := address + "/stop"
	client := safeHTTPClient()
	req, err := http.NewRequest("POST", urlStr, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Exec-Secret", device.SecurityPhraseHash)

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
	
	if out, ok := result["output"]; ok {
		return out, nil
	}
	return "Command stopped", nil
}
'''
if "func (b *Backend) stopCommand" not in code:
    code = code.replace("func (b *Backend) forwardCommand", stop_func + "\nfunc (b *Backend) forwardCommand")

# Add handling in handleWebSocket
stop_case = '''
			case "stop_command":
				b.lockDevice(deviceID, clientID)
				result, err := b.stopCommand(deviceID)
				b.unlockDevice(deviceID, clientID)
				
				if err != nil {
					b.writeMessage(clientID, messageType, []byte("ERROR: "+err.Error()))
				} else {
					b.writeMessage(clientID, messageType, []byte("OK: "+result))
				}
'''
if "case \"stop_command\":" not in code:
    code = code.replace("\t\t\tcase \"switch_device\":", stop_case + "\n\t\t\tcase \"switch_device\":")

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched backend successfully")
