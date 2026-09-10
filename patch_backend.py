with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

fcm_task_completion = '''
func (b *Backend) sendFCMTaskCompletion(deviceID, title, body string) {
	b.mu.RLock()
	device, exists := b.devices[deviceID]
	if !exists || len(device.FCMTokens) == 0 {
		b.mu.RUnlock()
		return
	}
	tokens := make([]string, 0, len(device.FCMTokens))
	for token := range device.FCMTokens {
		tokens = append(tokens, token)
	}
	b.mu.RUnlock()

	ctx := context.Background()
	for _, token := range tokens {
		msg := &messaging.Message{
			Token: token,
			Notification: &messaging.Notification{
				Title: title,
				Body:  body,
			},
			Data: map[string]string{
				"type": "task_finished",
			},
		}
		
		_, err := b.fcmClient.Send(ctx, msg)
		if err != nil {
			log.Printf("FCM task_finished send failed for token %s: %v", token, err)
			if messaging.IsUnregistered(err) || strings.Contains(err.Error(), "not registered") || strings.Contains(err.Error(), "invalid-argument") {
				b.mu.Lock()
				if dev, ok := b.devices[deviceID]; ok {
					delete(dev.FCMTokens, token)
				}
				b.mu.Unlock()
			}
		}
	}
}
'''

if 'func (b *Backend) sendFCMTaskCompletion' not in content:
    content = content.replace('func (b *Backend) sendFCMAlert', fcm_task_completion + '\nfunc (b *Backend) sendFCMAlert')

content = content.replace('b.unlockDevice(deviceID, clientID)', 'b.unlockDevice(deviceID, clientID)\n\n\t\tif b.fcmClient != nil {\n\t\t\tgo b.sendFCMTaskCompletion(deviceID, "Task Finished", "Your executed command has finished.")\n\t\t}')

content = content.replace('b.addSecurityAlert("mock_command", clientIP, deviceID, clientID, fmt.Sprintf("Unauthorized command attempt (mock count: %d)", mockCount), "medium")', 'b.addSecurityAlert("mock_command", clientIP, deviceID, clientID, fmt.Sprintf("Unauthorized command attempt (mock count: %d)", mockCount), "high")')

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
