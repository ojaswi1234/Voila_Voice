import re

with open('main.go', 'r', encoding='utf-8') as f:
    backend_code = f.read()

# Fix forwardCommand handling 202
backend_code = backend_code.replace(
'''	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	var result map[string]string
	if err := json.Unmarshal(body, &result); err != nil {
		return string(body), nil
	}

	if out, ok := result["output"]; ok {
		return out, nil
	}
	return "Command stopped", nil''',
'''	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusAccepted {
		return "TASK_QUEUED", nil
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	var result map[string]string
	if err := json.Unmarshal(body, &result); err != nil {
		return string(body), nil
	}

	if out, ok := result["output"]; ok {
		return out, nil
	}
	return "Command stopped", nil'''
)

# Fix goroutine to handle TASK_QUEUED
backend_code = backend_code.replace(
'''				// Run in goroutine to not block websocket read loop (and pings)
				go func(dID, cmd, m string, msgType int, cID string) {
					b.lockDevice(dID, cID)
					result, err := b.forwardCommand(dID, cmd, m, cID)
					b.unlockDevice(dID, cID)
					
					if err != nil {
						b.writeMessage(cID, msgType, []byte("ERROR: "+err.Error()))
						return
					}
					b.writeMessage(cID, msgType, []byte(result))
				}(deviceID, command, mode, messageType, clientID)''',
'''				// Run in goroutine to not block websocket read loop (and pings)
				go func(dID, cmd, m string, msgType int, cID string) {
					b.lockDevice(dID, cID)
					result, err := b.forwardCommand(dID, cmd, m, cID)
					
					if err != nil {
						b.unlockDevice(dID, cID)
						b.writeMessage(cID, msgType, []byte("ERROR: "+err.Error()))
						return
					}
					
					if result == "TASK_QUEUED" {
						// Don't unlock device yet, webhook will unlock it
						// Don't write result to websocket, webhook will write it
						return
					}
					
					b.unlockDevice(dID, cID)
					b.writeMessage(cID, msgType, []byte(result))
				}(deviceID, command, mode, messageType, clientID)'''
)

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(backend_code)

print("Backend patched for 202 Accepted handling.")
