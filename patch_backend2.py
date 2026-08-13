import re
import os

with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update /register SSRF and phrase hashing
register_ssrf = """	if !isValidAddress(req.Address) {
		log.Printf("Registration failed: invalid or disallowed address: %s", req.Address)
		http.Error(w, "Invalid address", http.StatusBadRequest)
		return
	}

	if req.Type == "" {
		req.Type = "desktop"
	}

	log.Printf("Registration request: device_id=%s, name=%s, address=%s, type=%s", req.DeviceID, req.DeviceName, req.Address, req.Type)

	backend.mu.Lock()
	defer backend.mu.Unlock()

	d, exists := backend.devices[req.DeviceID]
	if !exists {
		d = &Device{ID: req.DeviceID}
		backend.devices[req.DeviceID] = d
		if backend.activeDevice == "" {
			backend.activeDevice = req.DeviceID
		}
	}
	d.Name = req.DeviceName
	d.Address = strings.TrimRight(req.Address, "/")
	d.Fingerprint = req.Fingerprint
	d.Type = req.Type
	d.Active = true
	d.LastSeen = time.Now()
	if d.AuthToken == "" {
		d.AuthToken = generateAuthToken()
	}
	
	if req.SecurityPhrase != "" {
		d.SecurityPhraseHash = hashPhrase(strings.TrimSpace(req.SecurityPhrase), req.DeviceID)
		log.Printf("Device registered with hashed security phrase")
	}"""
content = re.sub(r'	if req\.Type == "".*?log\.Printf\("Device registered with security phrase for data clearing"\)\n	\}', register_ssrf, content, flags=re.DOTALL)

# 2. Update WebSocket handling (adding unlock and token check)
# It's better to just write the whole handleWebSocket function and replace it.
ws_code = """func handleWebSocket(b *Backend) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("WebSocket upgrade error: %v", err)
			return
		}
		defer conn.Close()

		clientID := fmt.Sprintf("client-%d", time.Now().UnixNano())
		clientIP := r.RemoteAddr
		
		b.mu.Lock()
		b.clients[clientID] = &WebSocketClient{
			conn:        conn,
			clientID:    clientID,
			connectedAt: time.Now(),
		}
		b.mu.Unlock()

		log.Printf("Mobile client connected: %s", clientID)

		for {
			messageType, message, err := conn.ReadMessage()
			if err != nil {
				break
			}

			var msg map[string]interface{}
			if err := json.Unmarshal(message, &msg); err != nil {
				conn.WriteMessage(messageType, []byte("ERROR: Invalid message format"))
				continue
			}

			msgType, _ := msg["type"].(string)
			deviceID, _ := msg["device_id"].(string)
			sessionToken, _ := msg["session_token"].(string)

			// Require token for sensitive operations
			requiresAuth := msgType == "command" || msgType == "lock_device" || msgType == "unlock_device" || msgType == "switch_device" || msgType == "clear_all_devices"
			if requiresAuth {
				// Special check for clear_all_devices which didn't use device_id originally
				targetDeviceID := deviceID
				if targetDeviceID == "" && msgType != "clear_all_devices" {
					device := b.getActiveDevice()
					if device != nil {
						targetDeviceID = device.ID
					}
				}
				
				// For clear_all, if token is valid for ANY device, we might let it through, or require the phrase inside the msg as before.
				// For now, if no token, fail. If command/lock and token invalid, fail.
				if msgType != "clear_all_devices" && !verifySessionToken(sessionToken, targetDeviceID) {
					conn.WriteMessage(messageType, []byte("ERROR: Unauthorized (missing, invalid, or expired session_token)"))
					continue
				}
			}

			switch msgType {
			case "unlock":
				phrase, _ := msg["security_phrase"].(string)
				cID, _ := msg["client_device_id"].(string)
				if cID == "" {
					cID = clientID
				}
				if deviceID == "" {
					conn.WriteMessage(messageType, []byte("ERROR: device_id required"))
					continue
				}

				b.mu.Lock()
				failures := b.ipRateLimits[clientIP]
				if failures > 5 {
					b.mu.Unlock()
					conn.WriteMessage(messageType, []byte("ERROR: Rate limited"))
					continue
				}
				device, exists := b.devices[deviceID]
				if !exists {
					b.ipRateLimits[clientIP]++
					b.mu.Unlock()
					conn.WriteMessage(messageType, []byte("ERROR: Invalid device"))
					continue
				}
				
				expectedHash := device.SecurityPhraseHash
				gotHash := hashPhrase(phrase, deviceID)
				
				if expectedHash != "" && gotHash == expectedHash {
					b.ipRateLimits[clientIP] = 0 // reset
					b.mu.Unlock()
					
					token := createSessionToken(deviceID, cID)
					resp := map[string]string{
						"type": "session",
						"session_token": token,
						"device_id": deviceID,
					}
					jResp, _ := json.Marshal(resp)
					conn.WriteMessage(messageType, jResp)
				} else {
					b.ipRateLimits[clientIP]++
					b.mu.Unlock()
					conn.WriteMessage(messageType, []byte("ERROR: Invalid security phrase"))
				}

			case "command":
				command, _ := msg["command"].(string)
				if deviceID == "" {
					device := b.getActiveDevice()
					if device != nil && device.Active {
						deviceID = device.ID
					} else {
						conn.WriteMessage(messageType, []byte("ERROR: No active online desktop device"))
						continue
					}
				}
				
				b.mu.RLock()
				device, exists := b.devices[deviceID]
				isOnline := exists && device.Active
				b.mu.RUnlock()
				
				if !exists {
					conn.WriteMessage(messageType, []byte("ERROR: device not found"))
					continue
				}
				if !isOnline {
					conn.WriteMessage(messageType, []byte("ERROR: device offline"))
					continue
				}
				if b.isDeviceLocked(deviceID, clientID) {
					conn.WriteMessage(messageType, []byte("ERROR: Device locked by another mobile device"))
					continue
				}
				
				b.lockDevice(deviceID, clientID)
				result, err := b.forwardCommand(deviceID, command)
				b.unlockDevice(deviceID, clientID)
				
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
					continue
				}
				conn.WriteMessage(messageType, []byte(result))
				
			case "switch_device":
				err := b.setActiveDevice(deviceID)
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device switched"))
				}
				
			case "lock_device":
				err := b.lockDevice(deviceID, clientID)
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device locked"))
				}
				
			case "unlock_device":
				err := b.unlockDevice(deviceID, clientID)
				if err != nil {
					conn.WriteMessage(messageType, []byte("ERROR: "+err.Error()))
				} else {
					conn.WriteMessage(messageType, []byte("OK: Device unlocked"))
				}
				
			case "get_devices":
				b.markStaleDevices()
				devices := b.getAllDevices()
				deviceList := make([]map[string]interface{}, 0)
				for _, d := range devices {
					deviceList = append(deviceList, map[string]interface{}{
						"id":          d.ID,
						"name":        d.Name,
						"active":      d.ID == b.activeDevice,
						"online":      d.Active,
						"reachable":   d.Reachable,
						"locked":      d.LockedBy != "",
						"lockedBy":    d.LockedBy,
						"lastSeen":    d.LastSeen,
						"lastPing":    d.LastPing,
						"fingerprint": d.Fingerprint,
						"type":        d.Type,
					})
				}
				jsonData, _ := json.Marshal(deviceList)
				conn.WriteMessage(messageType, jsonData)
				
			case "get_stats":
				b.mu.RLock()
				stats := map[string]interface{}{
					"token_counter": b.tokenCounter,
					"device_count": len(b.devices),
					"active_device": b.activeDevice,
				}
				b.mu.RUnlock()
				jsonData, _ := json.Marshal(stats)
				conn.WriteMessage(messageType, jsonData)
				
			case "clear_all_devices":
				var req struct {
					SecurityPhrase string `json:"security_phrase"`
				}
				if err := json.Unmarshal(message, &req); err == nil {
					phrase := strings.TrimSpace(req.SecurityPhrase)
					if phrase == "" {
						conn.WriteMessage(messageType, []byte("ERROR: Security phrase required"))
						continue
					}
					
					adminSecret := os.Getenv("CLEAR_DATA_SECRET")
					if adminSecret != "" && phrase == adminSecret {
						b.clearAllDevices()
						conn.WriteMessage(messageType, []byte("OK: All devices cleared (admin)"))
						continue
					}
					
					b.mu.Lock()
					failures := b.ipRateLimits[clientIP]
					if failures > 5 {
						b.mu.Unlock()
						conn.WriteMessage(messageType, []byte("ERROR: Rate limited"))
						continue
					}
					if len(b.devices) == 0 {
						b.mu.Unlock()
						conn.WriteMessage(messageType, []byte("ERROR: No registered devices to verify phrase"))
						continue
					}
					
					validPhrase := false
					for devID, device := range b.devices {
						if device.SecurityPhraseHash == hashPhrase(phrase, devID) {
							validPhrase = true
							break
						}
					}
					if validPhrase {
						b.ipRateLimits[clientIP] = 0
						b.mu.Unlock()
						b.clearAllDevices()
						conn.WriteMessage(messageType, []byte("OK: All devices cleared"))
					} else {
						b.ipRateLimits[clientIP]++
						b.mu.Unlock()
						conn.WriteMessage(messageType, []byte("ERROR: Invalid security phrase"))
					}
				}
			default:
				conn.WriteMessage(messageType, message)
			}
		}
		
		b.mu.Lock()
		delete(b.clients, clientID)
		for _, device := range b.devices {
			if device.LockedBy == clientID {
				device.LockedBy = ""
				device.LockedAt = time.Time{}
			}
		}
		b.mu.Unlock()
	}
}"""
content = re.sub(r'func handleWebSocket.*?\}\n\}\n', ws_code + '\n', content, flags=re.DOTALL)

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
