package main

import (
	"context"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"

	voilav1 "voice-cli-system/proto/v1"
)

var agentBootTime = time.Now()

// GRPCTunnelClient maintains a persistent bidirectional gRPC stream to the cloud backend
type GRPCTunnelClient struct {
	mu           sync.Mutex
	conn         *grpc.ClientConn
	stream       voilav1.DesktopTunnelService_EstablishTunnelClient
	streamCtx    context.Context
	streamCancel context.CancelFunc
	outChan      chan *voilav1.AgentTelemetry
	isConnected  atomic.Bool
	stopChan     chan struct{}
}

var (
	globalGRPCTunnelClient *GRPCTunnelClient
	grpcClientOnce         sync.Once
)

// InitGRPCTunnel initializes and starts the persistent gRPC tunnel client in a background goroutine
func InitGRPCTunnel() {
	grpcClientOnce.Do(func() {
		globalGRPCTunnelClient = &GRPCTunnelClient{
			outChan:  make(chan *voilav1.AgentTelemetry, 128),
			stopChan: make(chan struct{}),
		}

		// Register background tasks progress hook to stream progress via gRPC
		onBGTaskProgressUpdate = func(id, label, command, status string, elapsedSeconds int64, logSnippet, conversationID string) {
			SendTelemetry(&voilav1.AgentTelemetry{
				DeviceId:    getDeviceID(),
				Status:      "RUNNING",
				TimestampMs: time.Now().UnixMilli(),
				Payload: &voilav1.AgentTelemetry_Progress{
					Progress: &voilav1.TaskProgressUpdate{
						TaskId:            id,
						Label:             label,
						Command:           command,
						Status:            status,
						ElapsedSeconds:    elapsedSeconds,
						LatestLogSnippet:  logSnippet,
						ConversationId:    conversationID,
					},
				},
			})
		}

		go globalGRPCTunnelClient.runPersistentLoop()
	})
}

// SendTelemetry queues an outgoing telemetry message to be sent to the backend
func SendTelemetry(t *voilav1.AgentTelemetry) {
	if globalGRPCTunnelClient == nil || !globalGRPCTunnelClient.isConnected.Load() {
		return
	}
	select {
	case globalGRPCTunnelClient.outChan <- t:
	default:
		log.Printf("[gRPC Client] Warning: Outgoing telemetry buffer full, dropping message")
	}
}

// runPersistentLoop runs the dial and reconnect loop
func (c *GRPCTunnelClient) runPersistentLoop() {
	backoff := 1 * time.Second
	const maxBackoff = 15 * time.Second

	for {
		select {
		case <-c.stopChan:
			return
		default:
		}

		connData, err := loadConnectionData()
		if err != nil || !connData.Connected || connData.BackendURL == "" || connData.SecurityPhrase == "" {
			time.Sleep(3 * time.Second)
			continue
		}

		log.Printf("[gRPC Client] Connecting to backend: %s", connData.BackendURL)
		err = c.connectAndServe(connData)
		if err != nil {
			log.Printf("[gRPC Client] Tunnel disconnected: %v (reconnecting in %v)", err, backoff)
			time.Sleep(backoff)
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
		} else {
			backoff = 1 * time.Second
		}
	}
}

// connectAndServe establishes the connection and executes the streaming loop
func (c *GRPCTunnelClient) connectAndServe(connData ConnectionData) error {
	rawURL := connData.BackendURL
	rawURL = strings.TrimSuffix(rawURL, "/")
	rawURL = strings.TrimSuffix(rawURL, "/ws")

	var targetHost string
	var useTLS bool

	if strings.HasPrefix(rawURL, "https://") {
		useTLS = true
		targetHost = strings.TrimPrefix(rawURL, "https://")
	} else if strings.HasPrefix(rawURL, "http://") {
		useTLS = false
		targetHost = strings.TrimPrefix(rawURL, "http://")
	} else if strings.HasPrefix(rawURL, "wss://") {
		useTLS = true
		targetHost = strings.TrimPrefix(rawURL, "wss://")
	} else if strings.HasPrefix(rawURL, "ws://") {
		useTLS = false
		targetHost = strings.TrimPrefix(rawURL, "ws://")
	} else {
		useTLS = true
		targetHost = rawURL
	}

	// Parse host and port
	if !strings.Contains(targetHost, ":") {
		if useTLS {
			targetHost += ":443"
		} else {
			targetHost += ":80"
		}
	}

	var dialCreds grpc.DialOption
	if useTLS {
		// Render and modern cloud providers use TLS on port 443
		hostOnly := targetHost
		if h, _, err := net.SplitHostPort(targetHost); err == nil {
			hostOnly = h
		}
		tlsConfig := &tls.Config{
			ServerName: hostOnly,
		}
		dialCreds = grpc.WithTransportCredentials(credentials.NewTLS(tlsConfig))
	} else {
		dialCreds = grpc.WithTransportCredentials(insecure.NewCredentials())
	}

	keepaliveParams := keepalive.ClientParameters{
		Time:                15 * time.Second,
		Timeout:             5 * time.Second,
		PermitWithoutStream: true,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	conn, err := grpc.DialContext(ctx, targetHost, dialCreds, grpc.WithKeepaliveParams(keepaliveParams), grpc.WithBlock())
	cancel()
	if err != nil {
		return fmt.Errorf("dial failed to %s: %w", targetHost, err)
	}
	defer conn.Close()

	tunnelServiceClient := voilav1.NewDesktopTunnelServiceClient(conn)
	streamCtx, streamCancel := context.WithCancel(context.Background())
	defer streamCancel()

	stream, err := tunnelServiceClient.EstablishTunnel(streamCtx)
	if err != nil {
		return fmt.Errorf("failed to establish tunnel stream: %w", err)
	}

	c.mu.Lock()
	c.conn = conn
	c.stream = stream
	c.streamCtx = streamCtx
	c.streamCancel = streamCancel
	c.isConnected.Store(true)
	c.mu.Unlock()

	defer func() {
		c.mu.Lock()
		c.isConnected.Store(false)
		c.stream = nil
		c.conn = nil
		c.mu.Unlock()
	}()

	log.Printf("[gRPC Client] Tunnel established successfully to %s! Registering device %s...", targetHost, connData.DeviceID)

	// Send initial registration and heartbeat
	initialTelemetry := &voilav1.AgentTelemetry{
		DeviceId:    connData.DeviceID,
		DeviceName:  connData.DeviceName,
		Status:      "IDLE",
		TimestampMs: time.Now().UnixMilli(),
		Payload: &voilav1.AgentTelemetry_Heartbeat{
			Heartbeat: &voilav1.HeartbeatPing{
				UptimeSeconds:    int64(time.Since(agentBootTime).Seconds()),
				ActiveTasksCount: int32(getActiveBGTaskCount()),
			},
		},
	}
	if err := stream.Send(initialTelemetry); err != nil {
		return fmt.Errorf("initial registration failed: %w", err)
	}

	// Stream initial surveillance state immediately upon connection
	go broadcastSurveillanceState()

	// Broadcast any existing background tasks upon connection
	go func() {
		bgTasksMu.RLock()
		defer bgTasksMu.RUnlock()
		for _, t := range bgTasks {
			if onBGTaskProgressUpdate != nil {
				onBGTaskProgressUpdate(t.ID, t.Label, t.Command, t.Status, int64(time.Since(t.StartTime).Seconds()), "", t.ConversationID)
			}
		}
	}()

	// Goroutine: Sender loop (Desktop -> Cloud)
	sendErrChan := make(chan error, 1)
	go func() {
		ticker := time.NewTicker(15 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-streamCtx.Done():
				return
			case t, ok := <-c.outChan:
				if !ok {
					return
				}
				if err := stream.Send(t); err != nil {
					sendErrChan <- err
					return
				}
			case <-ticker.C:
				ping := &voilav1.AgentTelemetry{
					DeviceId:    connData.DeviceID,
					DeviceName:  connData.DeviceName,
					Status:      "IDLE",
					TimestampMs: time.Now().UnixMilli(),
					Payload: &voilav1.AgentTelemetry_Heartbeat{
						Heartbeat: &voilav1.HeartbeatPing{
							UptimeSeconds:    int64(time.Since(agentBootTime).Seconds()),
							ActiveTasksCount: int32(getActiveBGTaskCount()),
						},
					},
				}
				if err := stream.Send(ping); err != nil {
					sendErrChan <- err
					return
				}
			}
		}
	}()

	// Inbound receiver loop (Cloud -> Desktop)
	for {
		select {
		case err := <-sendErrChan:
			return fmt.Errorf("send error: %w", err)
		default:
		}

		cmd, err := stream.Recv()
		if err == io.EOF {
			return fmt.Errorf("stream closed by server (EOF)")
		}
		if err != nil {
			return fmt.Errorf("recv error: %w", err)
		}

		if cmd == nil {
			continue
		}

		// Handle emergency cancellation / stop immediately out-of-band
		if cmd.IsCancelSignal {
			go handleCancelSignalViaGRPC(cmd, connData)
			continue
		}

		// Handle surveillance control action
		if cmd.SurveillanceAction != "" {
			go handleSurveillanceActionViaGRPC(cmd.SurveillanceAction)
			continue
		}

		// Handle execution commands in a separate goroutine so stream receiver never blocks
		go handleIncomingCommandViaGRPC(cmd, connData)
	}
}

var (
	sessionCancelsMu sync.Mutex
	sessionCancels   = make(map[string]context.CancelFunc)
)

// handleCancelSignalViaGRPC handles stop / kill requests received via gRPC tunnel
func handleCancelSignalViaGRPC(cmd *voilav1.ExecutionCommand, connData ConnectionData) {
	if freshData, err := loadConnectionData(); err == nil {
		connData = freshData
	}
	log.Printf("[gRPC Client] Received out-of-band STOP signal for task: %s, job: %s, conv: %s", cmd.TargetTaskId, cmd.TargetJobId, cmd.ConversationId)

	// Cancel targeted session or all active sessions
	sessionCancelsMu.Lock()
	if cmd.ConversationId != "" {
		if cancel, exists := sessionCancels[cmd.ConversationId]; exists {
			log.Printf("[gRPC Client] Cancelling session %s", cmd.ConversationId)
			cancel()
			delete(sessionCancels, cmd.ConversationId)
		}
	} else {
		for cID, cancel := range sessionCancels {
			log.Printf("[gRPC Client] Cancelling session %s", cID)
			cancel()
			delete(sessionCancels, cID)
		}
	}
	sessionCancelsMu.Unlock()

	cmdMu.Lock()
	if cmd.ConversationId == "" && currentCancel != nil {
		currentCancel()
	}
	if currentCmd != nil && currentCmd.Process != nil && cmd.ConversationId == "" {
		if runtime.GOOS == "windows" {
			exec.Command("taskkill", "/F", "/T", "/PID", fmt.Sprintf("%d", currentCmd.Process.Pid)).Run()
		} else {
			currentCmd.Process.Kill()
		}
		currentCmd = nil
	}
	if cmd.ConversationId == "" {
		for _, pid := range activeToolPids {
			if runtime.GOOS == "windows" {
				exec.Command("taskkill", "/F", "/T", "/PID", fmt.Sprintf("%d", pid)).Run()
			}
		}
		activeToolPids = nil
		if graphifyTuiPid != 0 {
			if runtime.GOOS == "windows" {
				exec.Command("taskkill", "/F", "/T", "/PID", fmt.Sprintf("%d", graphifyTuiPid)).Run()
			}
			graphifyTuiPid = 0
			fmt.Print("\r\n\x1b[0m\x1b[?25h\x1b[?1049l\x1b[2J\x1b[H")
		}
	}
	cmdMu.Unlock()

	// 1. Force kill persistent terminal session if alive (only if full stop)
	if cmd.ConversationId == "" && cmd.TargetTaskId == "" {
		forceKillTerminalSession()
	}

	// 2. Kill background tasks
	if cmd.TargetTaskId != "" {
		killBGTask(cmd.TargetTaskId)
	} else if cmd.ConversationId != "" {
		// Stop any bg task running in this conversation
		bgTasksMu.RLock()
		var toKill []string
		for id, t := range bgTasks {
			if t.ConversationID == cmd.ConversationId && t.Status == "running" {
				toKill = append(toKill, id)
			}
		}
		bgTasksMu.RUnlock()
		for _, id := range toKill {
			killBGTask(id)
		}
	} else {
		stopAllBGTasks()
	}

	// 3. Send final cancelled result back via gRPC so caller unlocks immediately
	SendTelemetry(&voilav1.AgentTelemetry{
		DeviceId:    connData.DeviceID,
		Status:      "IDLE",
		TimestampMs: time.Now().UnixMilli(),
		Payload: &voilav1.AgentTelemetry_FinalResult{
			FinalResult: &voilav1.ExecutionResult{
				CommandId:         cmd.CommandId,
				Output:            "Execution forcibly cancelled by user via gRPC signal.",
				Summary:           "🛑 Cancelled",
				Status:            "cancelled",
				NewConversationId: cmd.ConversationId,
			},
		},
	})
}

// handleIncomingCommandViaGRPC executes a command received via the gRPC tunnel
func handleIncomingCommandViaGRPC(cmd *voilav1.ExecutionCommand, connData ConnectionData) {
	// Always reload latest configuration dynamically from disk so model/key updates take effect immediately
	if freshData, err := loadConnectionData(); err == nil {
		connData = freshData
	}
	if cmd.Command == "__SCREENSHOT__" {
		handleScreenshotViaGRPC(cmd, connData)
		return
	}

	if cmd.Command == "__GET_CONVERSATIONS__" {
		convs := listConversationsInternal()
		jsonData, _ := json.Marshal(convs)
		SendTelemetry(&voilav1.AgentTelemetry{
			DeviceId:    connData.DeviceID,
			Status:      "IDLE",
			TimestampMs: time.Now().UnixMilli(),
			Payload: &voilav1.AgentTelemetry_FinalResult{
				FinalResult: &voilav1.ExecutionResult{
					CommandId: cmd.CommandId,
					Output:    string(jsonData),
					Summary:   "conversations_list",
					Status:    "conversations_list",
				},
			},
		})
		return
	}

	if strings.HasPrefix(cmd.Command, "__GET_CONVERSATION_MESSAGES__:") {
		targetConvID := strings.TrimPrefix(cmd.Command, "__GET_CONVERSATION_MESSAGES__:")
		payload := getConversationMessagesInternal(targetConvID)
		jsonData, _ := json.Marshal(payload)
		SendTelemetry(&voilav1.AgentTelemetry{
			DeviceId:    connData.DeviceID,
			Status:      "IDLE",
			TimestampMs: time.Now().UnixMilli(),
			Payload: &voilav1.AgentTelemetry_FinalResult{
				FinalResult: &voilav1.ExecutionResult{
					CommandId:         cmd.CommandId,
					Output:            string(jsonData),
					Summary:           "conversation_messages",
					Status:            "conversation_messages",
					NewConversationId: targetConvID,
				},
			},
		})
		return
	}

	if strings.HasPrefix(cmd.Command, "__DELETE_CONVERSATION__:") {
		targetConvID := strings.TrimPrefix(cmd.Command, "__DELETE_CONVERSATION__:")
		deleteConversationInternal(targetConvID)
		SendTelemetry(&voilav1.AgentTelemetry{
			DeviceId:    connData.DeviceID,
			Status:      "IDLE",
			TimestampMs: time.Now().UnixMilli(),
			Payload: &voilav1.AgentTelemetry_FinalResult{
				FinalResult: &voilav1.ExecutionResult{
					CommandId:         cmd.CommandId,
					Summary:           "conversation_deleted",
					Status:            "conversation_deleted",
					NewConversationId: targetConvID,
				},
			},
		})
		return
	}

	if cmd.Command == "__CLEAR_ALL_CONVERSATIONS__" {
		clearAllConversationsInternal()
		SendTelemetry(&voilav1.AgentTelemetry{
			DeviceId:    connData.DeviceID,
			Status:      "IDLE",
			TimestampMs: time.Now().UnixMilli(),
			Payload: &voilav1.AgentTelemetry_FinalResult{
				FinalResult: &voilav1.ExecutionResult{
					CommandId: cmd.CommandId,
					Summary:   "all_conversations_cleared",
					Status:    "all_conversations_cleared",
				},
			},
		})
		return
	}

	if strings.HasPrefix(cmd.Command, "__PIN_CONVERSATION__:") {
		parts := strings.Split(strings.TrimPrefix(cmd.Command, "__PIN_CONVERSATION__:"), ":")
		if len(parts) >= 2 {
			convID := parts[0]
			isPinned := parts[1] == "true" || parts[1] == "1"
			pinConversationInternal(convID, isPinned)
			SendTelemetry(&voilav1.AgentTelemetry{
				DeviceId:    connData.DeviceID,
				Status:      "IDLE",
				TimestampMs: time.Now().UnixMilli(),
				Payload: &voilav1.AgentTelemetry_FinalResult{
					FinalResult: &voilav1.ExecutionResult{
						CommandId:         cmd.CommandId,
						Summary:           "conversation_pinned",
						Status:            "conversation_pinned",
						NewConversationId: convID,
					},
				},
			})
			return
		}
	}

	if strings.HasPrefix(cmd.Command, "__FORK_CONVERSATION__:") {
		parts := strings.Split(strings.TrimPrefix(cmd.Command, "__FORK_CONVERSATION__:"), ":")
		if len(parts) >= 3 {
			parentID := parts[0]
			newID := parts[1]
			model := parts[2]
			forkConversationInternal(parentID, newID, model)
			SendTelemetry(&voilav1.AgentTelemetry{
				DeviceId:    connData.DeviceID,
				Status:      "IDLE",
				TimestampMs: time.Now().UnixMilli(),
				Payload: &voilav1.AgentTelemetry_FinalResult{
					FinalResult: &voilav1.ExecutionResult{
						CommandId:         cmd.CommandId,
						Summary:           "conversation_forked",
						Status:            "conversation_forked",
						NewConversationId: newID,
					},
				},
			})
			return
		}
	}

	effectiveConvID := getOrCreateConversationID(cmd.ConversationId)

	currentModeMu.Lock()
	globalMode := strings.ToUpper(currentMode)
	currentModeMu.Unlock()

	reqMode := strings.ToUpper(cmd.Mode)
	var effectiveMode string
	if reqMode == "SHELL" {
		effectiveMode = "SHELL"
	} else if reqMode == "GROQ" || reqMode == "OLLAMA" {
		effectiveMode = reqMode
	} else {
		// In AGENT mode, check if the session was forked with a specific model type
		meta, _ := loadConversationMetadata(effectiveConvID)
		if meta.ModelType != "" {
			effectiveMode = meta.ModelType
		} else {
			effectiveMode = globalMode
			if effectiveMode == "" {
				effectiveMode = "LOCAL"
			}
		}
	}

	if cmd.GraphifyEnabled {
		effectiveMode = "AGENT"
	}

	// Cancel any previously running task IN THIS SPECIFIC SESSION ONLY (allowing multi-session parallelism)
	sessionCancelsMu.Lock()
	if prevCancel, exists := sessionCancels[effectiveConvID]; exists {
		prevCancel()
		delete(sessionCancels, effectiveConvID)
	}
	sessionCancelsMu.Unlock()

	// Acquire execution semaphore with timeout
	select {
	case execSemaphore <- struct{}{}:
	case <-time.After(10 * time.Second):
		SendTelemetry(&voilav1.AgentTelemetry{
			DeviceId:    connData.DeviceID,
			Status:      "IDLE",
			TimestampMs: time.Now().UnixMilli(),
			Payload: &voilav1.AgentTelemetry_FinalResult{
				FinalResult: &voilav1.ExecutionResult{
					CommandId:         cmd.CommandId,
					Output:            "Agent execution capacity reached, please retry momentarily",
					Status:            "error",
					NewConversationId: effectiveConvID,
				},
			},
		})
		return
	}

	ctx, cancel := context.WithCancel(context.Background())
	sessionCancelsMu.Lock()
	sessionCancels[effectiveConvID] = cancel
	sessionCancelsMu.Unlock()
	cmdMu.Lock()
	currentCancel = cancel
	cmdMu.Unlock()

	defer func() {
		<-execSemaphore
		sessionCancelsMu.Lock()
		delete(sessionCancels, effectiveConvID)
		sessionCancelsMu.Unlock()
		cmdMu.Lock()
		if currentCancel != nil {
			currentCancel = nil
		}
		cmdMu.Unlock()
		cancel()
	}()

	wakeScreen()

	// Wait for global AI rate limiter token before firing LLM / execution
	if globalAIRateLimiter != nil {
		_ = globalAIRateLimiter.Wait(ctx, 1.0)
	}

	// Update telemetry to RUNNING
	SendTelemetry(&voilav1.AgentTelemetry{
		DeviceId:    connData.DeviceID,
		Status:      "RUNNING",
		TimestampMs: time.Now().UnixMilli(),
	})

	startTime := time.Now()
	var output string
	var newConvID string
	var err error

	taskID := fmt.Sprintf("Agent-%x", time.Now().UnixNano()%0xFFFF)

	if cmd.GraphifyEnabled {
		output, err = executeGraphifyDAG(ctx, cmd.Command)
		newConvID = effectiveConvID
		if err == nil && output != "" {
			saveCloudHistory(effectiveConvID, cmd.Command, output)
		}
	} else {
		switch effectiveMode {
		case "GROQ":
			m := connData.GroqModel
			if m == "" {
				m = "openai/gpt-oss-120b"
			}
			output, err = executeGroqCommand(ctx, cmd.Command, connData.GroqAPIKey, m, cmd.ClientId, nil, taskID, effectiveConvID)
			newConvID = effectiveConvID
		case "OLLAMA":
			ollamaModel := connData.OllamaModel
			if ollamaModel == "" {
				ollamaModel = "gemma4:31b"
			}
			ollamaSemaphore <- struct{}{}
			output, err = executeOllamaCommand(ctx, cmd.Command, connData.OllamaBaseURL, ollamaModel, connData.OllamaAPIKey, nil, taskID, effectiveConvID)
			<-ollamaSemaphore
			newConvID = effectiveConvID
		default:
			output, newConvID, err = executeCommand(ctx, cmd.Command, effectiveMode, effectiveConvID, "")
		}
	}

	latencyMs := time.Since(startTime).Milliseconds()
	status := "ok"
	if err != nil {
		status = "error"
		output = "Command failed:\n" + err.Error()
	}

	summary := cmd.Command
	if len(summary) > 60 {
		summary = summary[:60] + "..."
	}

	artifactPath := ""
	artifactRe := regexp.MustCompile("(?i)([A-Z]:\\\\[^\\n*|<>\\'\\`\"]+\\.(?:pdf|png|docx|pptx|html))")
	if match := artifactRe.FindStringSubmatch(output); len(match) > 1 {
		artifactPath = match[1]
	}

	// Send final execution result via gRPC
	SendTelemetry(&voilav1.AgentTelemetry{
		DeviceId:    connData.DeviceID,
		Status:      "IDLE",
		TimestampMs: time.Now().UnixMilli(),
		Payload: &voilav1.AgentTelemetry_FinalResult{
			FinalResult: &voilav1.ExecutionResult{
				CommandId:         cmd.CommandId,
				Output:            output,
				Summary:           summary,
				Status:            status,
				NewConversationId: newConvID,
				LatencyMs:         latencyMs,
				ArtifactPath:      artifactPath,
			},
		},
	})
}

// handleScreenshotViaGRPC captures screen, blanks plasma overlay, and sends pure binary JPEG via gRPC
func handleScreenshotViaGRPC(cmd *voilav1.ExecutionCommand, connData ConnectionData) {
	// Plasma overlay exclusion: blank the overlay before capturing so it doesn't appear
	sendPlasmaIPC := func(msg string) {
		if conn, e2 := net.Dial("udp", "127.0.0.1:19885"); e2 == nil {
			conn.Write([]byte(msg))
			conn.Close()
		}
	}

	prevPlasmaState := "IDLE"
	settingsPath := filepath.Join(getLocalAgentDir(), "plasma_settings.json")
	if raw, e2 := os.ReadFile(settingsPath); e2 == nil {
		var ps struct {
			State string `json:"state"`
		}
		if json.Unmarshal(raw, &ps) == nil && ps.State != "" {
			prevPlasmaState = ps.State
		}
	}

	sendPlasmaIPC("STATE:OFF")
	time.Sleep(90 * time.Millisecond) // Wait for render frame blanking

	psCode := `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$stream = New-Object System.IO.MemoryStream
$bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Jpeg)
$bytes = $stream.ToArray()
$base64 = [Convert]::ToBase64String($bytes)
$graphics.Dispose()
$bitmap.Dispose()
$stream.Dispose()
Write-Output $base64
`
	out, err := exec.Command("powershell", "-NoProfile", "-Command", psCode).CombinedOutput()
	sendPlasmaIPC("STATE:" + prevPlasmaState)

	if err != nil {
		SendTelemetry(&voilav1.AgentTelemetry{
			DeviceId:    connData.DeviceID,
			Status:      "IDLE",
			TimestampMs: time.Now().UnixMilli(),
			Payload: &voilav1.AgentTelemetry_FinalResult{
				FinalResult: &voilav1.ExecutionResult{
					CommandId: cmd.CommandId,
					Output:    "Screenshot failed: " + err.Error(),
					Status:    "error",
				},
			},
		})
		return
	}

	// Decode Base64 from powershell into raw binary bytes
	cleanOut := strings.TrimSpace(string(out))
	imgBytes, decErr := base64.StdEncoding.DecodeString(cleanOut)
	if decErr != nil {
		// Fallback to raw string bytes if decoding fails
		imgBytes = []byte(cleanOut)
	}

	// Send binary screen capture over gRPC
	SendTelemetry(&voilav1.AgentTelemetry{
		DeviceId:    connData.DeviceID,
		Status:      "IDLE",
		TimestampMs: time.Now().UnixMilli(),
		Payload: &voilav1.AgentTelemetry_Screenshot{
			Screenshot: &voilav1.ScreenCapture{
				CommandId:   cmd.CommandId,
				ImageData:   imgBytes,
				Format:      "jpeg",
				TimestampMs: time.Now().UnixMilli(),
			},
		},
	})
}

// Helper to get device ID safely
func getDeviceID() string {
	if connData, err := loadConnectionData(); err == nil && connData.DeviceID != "" {
		return connData.DeviceID
	}
	return "desktop-unknown"
}

// Helper to count active background tasks
func getActiveBGTaskCount() int {
	bgTasksMu.RLock()
	defer bgTasksMu.RUnlock()
	count := 0
	for _, t := range bgTasks {
		if t.Status == "running" {
			count++
		}
	}
	return count
}
