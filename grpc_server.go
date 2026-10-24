package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	voilav1 "voice-cli-system/proto/v1"
)

// DesktopTunnelManager tracks active bidirectional gRPC tunnel streams from connected desktop agents
type DesktopTunnelManager struct {
	mu      sync.RWMutex
	tunnels map[string]chan *voilav1.ExecutionCommand
	backend *Backend
}

var globalTunnelManager = &DesktopTunnelManager{
	tunnels: make(map[string]chan *voilav1.ExecutionCommand),
}

func (m *DesktopTunnelManager) Register(deviceID string, ch chan *voilav1.ExecutionCommand) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.tunnels[deviceID] = ch
	log.Printf("[gRPC Tunnel] Desktop connected and registered: %s", deviceID)
}

func (m *DesktopTunnelManager) Unregister(deviceID string, ch chan *voilav1.ExecutionCommand) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if currentCh, ok := m.tunnels[deviceID]; ok && currentCh == ch {
		delete(m.tunnels, deviceID)
		log.Printf("[gRPC Tunnel] Desktop disconnected: %s", deviceID)
	}
}

func (m *DesktopTunnelManager) HasTunnel(deviceID string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, ok := m.tunnels[deviceID]
	return ok
}

func (m *DesktopTunnelManager) GetTunnel(deviceID string) (chan *voilav1.ExecutionCommand, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	ch, ok := m.tunnels[deviceID]
	return ch, ok
}

func (m *DesktopTunnelManager) SendCommand(deviceID string, cmd *voilav1.ExecutionCommand) bool {
	ch, ok := m.GetTunnel(deviceID)
	if !ok {
		return false
	}
	select {
	case ch <- cmd:
		return true
	default:
		log.Printf("[gRPC Tunnel] Warning: Command buffer full for device %s", deviceID)
		return false
	}
}

// TunnelServer implements voilav1.DesktopTunnelServiceServer
type TunnelServer struct {
	voilav1.UnimplementedDesktopTunnelServiceServer
	backend *Backend
}

func (s *TunnelServer) EstablishTunnel(stream voilav1.DesktopTunnelService_EstablishTunnelServer) error {
	var deviceID string
	cmdChan := make(chan *voilav1.ExecutionCommand, 64)
	defer func() {
		if deviceID != "" {
			globalTunnelManager.Unregister(deviceID, cmdChan)
			if s.backend != nil {
				s.backend.mu.Lock()
				if d, ok := s.backend.devices[deviceID]; ok {
					d.Active = false
					d.Reachable = false
				}
				s.backend.mu.Unlock()
				go s.backend.broadcastDevices()
			}
		}
	}()

	// Outbound sender loop (Cloud -> Desktop)
	errChan := make(chan error, 1)
	go func() {
		for {
			select {
			case cmd, ok := <-cmdChan:
				if !ok {
					return
				}
				if err := stream.Send(cmd); err != nil {
					errChan <- err
					return
				}
			case <-stream.Context().Done():
				return
			}
		}
	}()

	// Inbound receiver loop (Desktop -> Cloud)
	for {
		telemetry, err := stream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			if status.Code(err) == codes.Canceled {
				return nil
			}
			return err
		}

		if deviceID == "" && telemetry.DeviceId != "" {
			deviceID = telemetry.DeviceId
			globalTunnelManager.Register(deviceID, cmdChan)

			if s.backend != nil {
				s.backend.mu.Lock()
				d, exists := s.backend.devices[deviceID]
				if !exists {
					d = &Device{ID: deviceID}
					s.backend.devices[deviceID] = d
					if s.backend.activeDevice == "" {
						s.backend.activeDevice = deviceID
					}
				}
				if telemetry.DeviceName != "" {
					d.Name = telemetry.DeviceName
				}
				d.Type = "desktop"
				d.Active = true
				d.Reachable = true
				d.LastSeen = time.Now()
				s.backend.mu.Unlock()
				go s.backend.broadcastDevices()
			}
		}

		// Update device heartbeat timestamp
		if deviceID != "" && s.backend != nil {
			s.backend.mu.Lock()
			if d, exists := s.backend.devices[deviceID]; exists {
				d.Active = true
				d.Reachable = true
				d.LastSeen = time.Now()
			}
			s.backend.mu.Unlock()
		}

		// Process telemetry payload
		switch p := telemetry.Payload.(type) {
		case *voilav1.AgentTelemetry_OutputChunk:
			chunk := p.OutputChunk
			resp := map[string]interface{}{
				"type":            "chunk",
				"command_id":      chunk.CommandId,
				"content":         chunk.Text,
				"is_error":        chunk.IsError,
				"is_final":        chunk.IsFinal,
				"tool":            chunk.ToolName,
				"conversation_id": chunk.ConversationId,
			}
			if b, err := json.Marshal(resp); err == nil && s.backend != nil {
				s.backend.broadcastToClients(websocket.TextMessage, b)
			}

		case *voilav1.AgentTelemetry_FinalResult:
			res := p.FinalResult
			if res.Summary == "conversations_list" {
				resp := map[string]interface{}{
					"type": "conversations_list",
					"data": json.RawMessage(res.Output),
				}
				if b, err := json.Marshal(resp); err == nil && s.backend != nil {
					s.backend.broadcastToClients(websocket.TextMessage, b)
				}
				continue
			} else if res.Summary == "conversation_messages" {
				resp := map[string]interface{}{
					"type":            "conversation_messages",
					"conversation_id": res.NewConversationId,
					"data":            json.RawMessage(res.Output),
				}
				if b, err := json.Marshal(resp); err == nil && s.backend != nil {
					s.backend.broadcastToClients(websocket.TextMessage, b)
				}
				continue
			} else if res.Summary == "conversation_deleted" {
				resp := map[string]interface{}{
					"type":            "conversation_deleted",
					"conversation_id": res.NewConversationId,
				}
				if b, err := json.Marshal(resp); err == nil && s.backend != nil {
					s.backend.broadcastToClients(websocket.TextMessage, b)
				}
				continue
			} else if res.Summary == "all_conversations_cleared" {
				resp := map[string]interface{}{
					"type": "all_conversations_cleared",
				}
				if b, err := json.Marshal(resp); err == nil && s.backend != nil {
					s.backend.broadcastToClients(websocket.TextMessage, b)
				}
				continue
			} else if res.Summary == "conversation_pinned" {
				resp := map[string]interface{}{
					"type":            "conversation_pinned",
					"conversation_id": res.NewConversationId,
				}
				if b, err := json.Marshal(resp); err == nil && s.backend != nil {
					s.backend.broadcastToClients(websocket.TextMessage, b)
				}
				continue
			} else if res.Summary == "conversation_forked" {
				resp := map[string]interface{}{
					"type":            "conversation_forked",
					"conversation_id": res.NewConversationId,
				}
				if b, err := json.Marshal(resp); err == nil && s.backend != nil {
					s.backend.broadcastToClients(websocket.TextMessage, b)
				}
				continue
			} else if res.Summary == "clipboard_suggestion" {
				resp := map[string]interface{}{
					"type": "clipboard_suggestion",
					"data": json.RawMessage(res.Output),
				}
				if b, err := json.Marshal(resp); err == nil && s.backend != nil {
					s.backend.broadcastToClients(websocket.TextMessage, b)
				}
				continue
			}

			resp := map[string]interface{}{
				"type":                "result",
				"command_id":          res.CommandId,
				"output":              res.Output,
				"summary":             res.Summary,
				"status":              res.Status,
				"artifact_path":       res.ArtifactPath,
				"mode":                telemetry.Status,
				"new_conversation_id": res.NewConversationId,
			}
			if b, err := json.Marshal(resp); err == nil && s.backend != nil {
				s.backend.broadcastToClients(websocket.TextMessage, b)
			}
			if s.backend != nil && deviceID != "" {
				s.backend.forceUnlockDevice(deviceID)
			}

		case *voilav1.AgentTelemetry_Screenshot:
			sc := p.Screenshot
			// Wrap raw binary into Base64 for mobile clients until mobile has native proto decoders
			b64 := base64.StdEncoding.EncodeToString(sc.ImageData)
			resp := map[string]interface{}{
				"type":       "result",
				"command_id": sc.CommandId,
				"output":     "__IMAGE__:" + b64,
				"status":     "ok",
				"mode":       "screenshot",
			}
			if b, err := json.Marshal(resp); err == nil && s.backend != nil {
				s.backend.broadcastToClients(websocket.TextMessage, b)
			}
			if s.backend != nil && deviceID != "" {
				s.backend.forceUnlockDevice(deviceID)
			}

		case *voilav1.AgentTelemetry_Progress:
			prog := p.Progress
			resp := map[string]interface{}{
				"type": "bg_task_update",
				"task": map[string]interface{}{
					"id":              prog.TaskId,
					"label":           prog.Label,
					"command":         prog.Command,
					"status":          prog.Status,
					"duration":        fmt.Sprintf("%ds", prog.ElapsedSeconds),
					"snapshot":        prog.LatestLogSnippet,
					"conversation_id": prog.ConversationId,
				},
			}
			if b, err := json.Marshal(resp); err == nil && s.backend != nil {
				s.backend.broadcastToClients(websocket.TextMessage, b)
			}

			// Proactive Watchdog: Dispatch FCM notification to mobile when task completes or fails
			if s.backend != nil && (prog.Status == "completed" || prog.Status == "failed") {
				targetDevice := deviceID
				if targetDevice == "" {
					targetDevice = telemetry.DeviceId
				}

				eventType := "task_finished"
				title := fmt.Sprintf("Build Succeeded: %s", prog.Label)
				body := fmt.Sprintf("Task %s completed in %ds.", prog.TaskId, prog.ElapsedSeconds)

				if prog.Status == "failed" {
					eventType = "task_failed"
					title = fmt.Sprintf("Build Failed: %s", prog.Label)
					body = fmt.Sprintf("Task %s failed after %ds.", prog.TaskId, prog.ElapsedSeconds)
					if idx := strings.Index(prog.LatestLogSnippet, "Root Cause:"); idx != -1 {
						snippet := prog.LatestLogSnippet[idx:]
						if end := strings.Index(snippet, "\n"); end != -1 {
							body = strings.TrimSpace(snippet[:end])
						}
					}
				}

				if targetDevice != "" {
					go s.backend.sendFCMTaskCompletion(targetDevice, eventType, title, body, prog.TaskId, prog.LatestLogSnippet, "")
				}
			}

		case *voilav1.AgentTelemetry_SurveillanceAlert:
			al := p.SurveillanceAlert
			resp := map[string]interface{}{
				"type": "surveillance_alert",
				"alert": map[string]interface{}{
					"alert_type": al.AlertType,
					"reason":     al.Reason,
					"timestamp":  al.TimestampMs,
				},
			}
			if b, err := json.Marshal(resp); err == nil && s.backend != nil {
				s.backend.broadcastToClients(websocket.TextMessage, b)
			}

		case *voilav1.AgentTelemetry_SurveillanceState:
			st := p.SurveillanceState
			resp := map[string]interface{}{
				"type": "surveillance_status",
				"data": map[string]interface{}{
					"armed":                   st.Armed,
					"locked":                  st.Locked,
					"last_alert_reason":       st.LastAlertReason,
					"last_alert_timestamp_ms": st.LastAlertTimestampMs,
				},
			}
			if b, err := json.Marshal(resp); err == nil && s.backend != nil {
				s.backend.broadcastToClients(websocket.TextMessage, b)
			}
		}
	}
}

// broadcastToClients sends message to all connected mobile WebSockets
func (b *Backend) broadcastToClients(msgType int, data []byte) {
	b.mu.RLock()
	clientIDs := make([]string, 0, len(b.clients))
	for cID := range b.clients {
		clientIDs = append(clientIDs, cID)
	}
	b.mu.RUnlock()

	for _, cID := range clientIDs {
		b.dispatcher.Dispatch(cID, msgType, data)
	}
}

// createMultiplexedHandler creates an HTTP/2 compatible handler that routes gRPC and standard HTTP/WS on the same port
func createMultiplexedHandler(grpcServer *grpc.Server, httpHandler http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.ProtoMajor == 2 && strings.HasPrefix(r.Header.Get("Content-Type"), "application/grpc") {
			grpcServer.ServeHTTP(w, r)
		} else {
			httpHandler.ServeHTTP(w, r)
		}
	})
}
