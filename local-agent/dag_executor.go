package main

/*
================================================================================
Voila Voice CLI - DAG Executor (Graphify)
================================================================================
This file is the engine that drives the multi-agent swarm architecture.
Responsibilities:
1. Parsing `graphify_state.json` to load the node topology and dependencies.
2. Managing concurrent execution (`executeGraphifyDAG`) using Go routines and WaitGroups.
3. Live state broadcasting (updating the UI when a node starts, finishes, or errors).
4. Assembling the system prompt for each node, enforcing strict output rules
   (like the pointer-based memory architecture) before execution.
================================================================================
*/


import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
)

type GraphNode struct {
	ID      string `json:"id"`
	Role    string `json:"role"`
	Model   string `json:"model"`
	Prompt  string `json:"prompt"`
	X       int    `json:"x"`
	Y       int    `json:"y"`
	R       int    `json:"r"`
	Color   string `json:"color"`
	Outline string `json:"outline"`
}


var (
	liveStateMu sync.Mutex
	currentLiveState LiveState
)

// =====================================================================
// Graphify Multi-Agent Identity & Anti-Choking
// =====================================================================

const maxVisualAgents = 5

// graphifyDesktopMu ensures only ONE agent drives the desktop at a time.
// This prevents Windows UIA COM from receiving simultaneous calls.
var graphifyDesktopMu sync.Mutex

// graphifyOllamaSem limits concurrent Ollama calls during a Graphify run to 2.
var graphifyOllamaSem = make(chan struct{}, 2)

// agentOverlaysMu guards the overlay process map
var agentOverlaysMu sync.Mutex
var agentOverlays = map[string]*exec.Cmd{}

// agentNames is the pool of country-themed human names for agents
var agentNames = []string{
	"Arjun", "Priya", "Vikram", "Kavya", "Rohan",
	"Yuki", "Kenji", "Aiko", "Hiroshi", "Sakura",
	"Ivan", "Natasha", "Dmitri", "Sonya", "Alexei",
	"Jake", "Emma", "Tyler", "Maya", "Logan",
	"Jiwoo", "Minho", "Sora", "Hyun", "Yuna",
	"Felix", "Mia", "Klaus", "Anna", "Max",
	"Lucas", "Bianca", "Rafael", "Camila", "Pedro",
}

// agentColors is indexed by agentIndex % len(agentColors)
// Each entry: [fill, outline, glow]
var agentColors = [][3]string{
	{"#6b21a8", "#c084fc", "#9333ea"}, // purple (default)
	{"#1e3a5f", "#60a5fa", "#3b82f6"}, // blue
	{"#14532d", "#86efac", "#22c55e"}, // green
	{"#7c2d12", "#fdba74", "#f97316"}, // orange
	{"#831843", "#f9a8d4", "#ec4899"}, // pink
	{"#1e1b4b", "#a5b4fc", "#6366f1"}, // indigo
	{"#422006", "#fde68a", "#f59e0b"}, // amber
}

// Staggered startup positions so cursors don't pile on top of each other
var agentStartPositions = [][2]int{
	{150, 150},   // top-left
	{1730, 150},  // top-right (assumes ~1920 wide)
	{940, 540},   // center
	{150, 930},   // bottom-left
	{1730, 930},  // bottom-right
}

func launchAgentOverlay(nodeID string, agentIndex int, name, colorFill, colorOutline, colorGlow string) {
	if agentIndex >= maxVisualAgents {
		return // headless mode
	}
	port := 19882 + agentIndex
	portStr := strconv.Itoa(port)

	exePath, _ := os.Executable()
	dir := filepath.Dir(exePath)
	overlayScript := filepath.Join(dir, "cursor_overlay.py")
	if _, err := os.Stat(overlayScript); os.IsNotExist(err) {
		// try cwd
		cwd, _ := os.Getwd()
		overlayScript = filepath.Join(cwd, "cursor_overlay.py")
	}

	// Kill any existing overlay on this port first
	agentOverlaysMu.Lock()
	if old, ok := agentOverlays[nodeID]; ok && old != nil {
		old.Process.Kill()
	}
	agentOverlaysMu.Unlock()

	cmd := exec.Command("pythonw", overlayScript,
		"--port", portStr,
		"--name", name,
		"--color-fill", colorFill,
		"--color-outline", colorOutline,
		"--color-glow", colorGlow,
	)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err := cmd.Start(); err != nil {
		fmt.Printf("STATUS: SYSTEM_MSG:[%s] overlay launch failed: %v\n", name, err)
		os.Stdout.Sync()
		return
	}
	agentOverlaysMu.Lock()
	agentOverlays[nodeID] = cmd
	agentOverlaysMu.Unlock()

	// Also launch a dedicated desktop bridge for this agent
	bridgePort := 19881
	if agentIndex > 0 {
		bridgePort = 19885 + agentIndex // 19886, 19887...
	}
	go launchAgentBridge(name, bridgePort, agentIndex, portStr)
}

func launchAgentBridge(name string, bridgePort, agentIndex int, overlayPortStr string) {
	// Only launch secondary bridges (index > 0); index 0 reuses the existing bridge
	if agentIndex == 0 {
		return
	}
	exePath, _ := os.Executable()
	dir := filepath.Dir(exePath)
	bridgeScript := filepath.Join(dir, "desktop_bridge.py")
	if _, err := os.Stat(bridgeScript); os.IsNotExist(err) {
		cwd, _ := os.Getwd()
		bridgeScript = filepath.Join(cwd, "desktop_bridge.py")
	}
	cmd := exec.Command("python", bridgeScript, "--port", strconv.Itoa(bridgePort))
	cmd.Env = append(os.Environ(),
		"VOILA_DESKTOP_PORT="+strconv.Itoa(bridgePort),
		"VOILA_AGENT_PORT="+overlayPortStr,
	)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	cmd.Start()
}

func killAgentOverlay(nodeID string) {
	agentOverlaysMu.Lock()
	defer agentOverlaysMu.Unlock()
	if cmd, ok := agentOverlays[nodeID]; ok && cmd != nil {
		if cmd.Process != nil {
			cmd.Process.Kill()
		}
		delete(agentOverlays, nodeID)
	}
}


func initLiveState(nodes []GraphNode, edges [][]string) {
	liveStateMu.Lock()
	defer liveStateMu.Unlock()
	currentLiveState = LiveState{
		Status: "running",
		Nodes:  make([]NodeLiveState, len(nodes)),
		Edges:  edges,
	}
	for i, n := range nodes {
		currentLiveState.Nodes[i] = NodeLiveState{
			ID: n.ID, Role: n.Role, Status: "pending", Model: n.Model,
			X: n.X, Y: n.Y,
		}
	}
	writeLiveState()
}

func updateLiveNode(id string, status string) {
	liveStateMu.Lock()
	defer liveStateMu.Unlock()
	for i, n := range currentLiveState.Nodes {
		if n.ID == id {
			currentLiveState.Nodes[i].Status = status
			break
		}
	}
	writeLiveState()
}

func appendLiveLog(log string) {
	liveStateMu.Lock()
	defer liveStateMu.Unlock()
	
	lines := strings.Split(log, "\n")
	for _, l := range lines {
		if strings.TrimSpace(l) != "" {
			currentLiveState.Logs = append(currentLiveState.Logs, l)
		}
	}
	
	if len(currentLiveState.Logs) > 40 {
		currentLiveState.Logs = currentLiveState.Logs[len(currentLiveState.Logs)-40:]
	}
	writeLiveState()
}

func finishLiveState(status string, errMsg string) {
	liveStateMu.Lock()
	defer liveStateMu.Unlock()
	currentLiveState.Status = status
	currentLiveState.ErrorMsg = errMsg
	writeLiveState()
}

func writeLiveState() {
	b, _ := json.Marshal(currentLiveState)
	os.WriteFile("graphify_live.json", b, 0644)
}

type GraphState struct {
	Nodes    []GraphNode `json:"nodes"`
	Edges    [][]string  `json:"edges"`
	IsCustom bool        `json:"is_custom"`
}

func executeGraphifyDAG(ctx context.Context, command string) (string, error) {
	fmt.Printf("STATUS: GRAPHIFY\n")
	os.Stdout.Sync()
	fmt.Printf("STATUS: SYSTEM_MSG:Initializing Dynamic Multi-Agent State Machine...\n")
	os.Stdout.Sync()

	connData, err := loadConnectionData()
	if err != nil {
		return "", err
	}

	data, err := os.ReadFile("graphify_state.json")
	if err != nil {
		return "", fmt.Errorf("failed to read graph state: %v", err)
	}

	var state GraphState
	if err := json.Unmarshal(data, &state); err != nil {
		return "", fmt.Errorf("failed to parse graph state: %v", err)
	}

	if !state.IsCustom {
		if err := autoGenerateGraphifyState(ctx, command, connData); err == nil {
			// Re-read after auto generation
			data, _ = os.ReadFile("graphify_state.json")
			json.Unmarshal(data, &state)
		} else {
			fmt.Printf("STATUS: SYSTEM_MSG:Auto-generation failed: %v\n", err)
			os.Stdout.Sync()
			// ABORT instead of falling back to the dummy UI template!
			return "", fmt.Errorf("Graphify AI generation failed: %v", err)
		}
	}

	initLiveState(state.Nodes, state.Edges)
	if len(state.Nodes) == 0 {
		return "Graph is empty", nil
	}

	parents := make(map[string][]string)
	children := make(map[string][]string)
	nodeMap := make(map[string]GraphNode)

	for _, n := range state.Nodes {
		nodeMap[n.ID] = n
		parents[n.ID] = []string{}
		children[n.ID] = []string{}
	}

	// We no longer strictly forbid cycles, but the user UI usually outputs a DAG.
	for _, edge := range state.Edges {
		if len(edge) == 2 {
			src := edge[0]
			tgt := edge[1]
			children[src] = append(children[src], tgt)
			parents[tgt] = append(parents[tgt], src)
		}
	}

	// ── State Machine Variables ──
	var mu sync.Mutex
	cond := sync.NewCond(&mu)
	
	outputs := make(map[string]string)
	var transcript []string
	revisions := make(map[string][]string)
	runCount := make(map[string]int)
	running := make(map[string]bool)
	completed := make(map[string]bool)
	var fatalErr error

	getReadyNodes := func() []string {
		var ready []string
		for _, n := range state.Nodes {
			if completed[n.ID] || running[n.ID] {
				continue
			}
			parentsDone := true
			for _, p := range parents[n.ID] {
				if !completed[p] {
					parentsDone = false
					break
				}
			}
			if parentsDone {
				ready = append(ready, n.ID)
			}
		}
		return ready
	}

	// Wake up the condition variable if context is cancelled
	go func() {
		<-ctx.Done()
		cond.Broadcast()
	}()

	for {
		// Check for context cancellation
		select {
		case <-ctx.Done():
			finishLiveState("error", "FORCE KILLED BY USER")
			return "", fmt.Errorf("Execution forcefully cancelled by user")
		default:
		}

		mu.Lock()
		if fatalErr != nil {
			mu.Unlock()
			return "", fatalErr
		}

		allDone := true
		for _, n := range state.Nodes {
			if !completed[n.ID] {
				allDone = false
				break
			}
		}
		if allDone {
			mu.Unlock()
			finishLiveState("done", "")
			break
		}

		ready := getReadyNodes()
		if len(ready) == 0 {
			anyRunning := false
			for _, n := range state.Nodes {
				if running[n.ID] {
					anyRunning = true
					break
				}
			}
			if !anyRunning {
				var forcedNode string
				for _, n := range state.Nodes {
					if !completed[n.ID] {
						forcedNode = n.ID
						break
					}
				}
				if forcedNode != "" {
					ready = append(ready, forcedNode)
				} else {
					mu.Unlock()
					finishLiveState("error", "deadlock detected: no nodes are ready or running")
					return "", fmt.Errorf("deadlock detected: no nodes are ready or running")
				}
			} else {
				cond.Wait()
				mu.Unlock()
				continue
			}
		}

		for idx, nid := range ready {
			running[nid] = true
			runCount[nid]++
			
			myTranscript := append([]string(nil), transcript...)
			myRevisions := append([]string(nil), revisions[nid]...)
			myRunCount := runCount[nid]
			
			// Assign a stable agent index based on node position in nodes array
			agentIdx := 0
			for i, n := range state.Nodes {
				if n.ID == nid { agentIdx = i; break }
			}
			_ = idx
			
			// Pick identity
			agentName := agentNames[agentIdx % len(agentNames)]
			agentColor := agentColors[agentIdx % len(agentColors)]
			
			// Launch visual overlay (non-blocking)
			launchAgentOverlay(nid, agentIdx, agentName, agentColor[0], agentColor[1], agentColor[2])
			
			agentPort := 19882 + agentIdx
			agentBridgePort := 19881
			if agentIdx > 0 { agentBridgePort = 19885 + agentIdx }
			
			go func(nodeID string, history []string, myRevs []string, rCount int, aName string, aIdx int, aPort int, aBridgePort int) {
				n := nodeMap[nodeID]
				
				updateLiveNode(nodeID, "running")
				appendLiveLog(fmt.Sprintf("[%s/%s] Node execution started...", n.Role, aName))

				fmt.Printf("STATUS: TEAM_NODE_START:%s\n", n.Role)
				os.Stdout.Sync()
				
				// Set env vars so desktop_tools.py routes to this agent's cursor overlay and bridge
				os.Setenv("VOILA_AGENT_PORT", strconv.Itoa(aPort))
				os.Setenv("VOILA_DESKTOP_PORT", strconv.Itoa(aBridgePort))
				os.Setenv("VOILA_AGENT_NAME", aName)
				os.Setenv("VOILA_AGENT_INDEX", strconv.Itoa(aIdx))


				promptBuilder := strings.Builder{}
				promptBuilder.WriteString(fmt.Sprintf("You are %s. %s\n\n", n.Role, n.Prompt))

				// Always inject debate instructions so agents can collaborate and reject work!
				promptBuilder.WriteString("CRITICAL DEBATE INSTRUCTIONS:\n")
				promptBuilder.WriteString("You are part of an iterative team discussion. You can see everyone's work below.\n")
				promptBuilder.WriteString("If the work from your team members is flawed, missing requirements, or incorrect, you MUST reject it.\n")
				promptBuilder.WriteString("To reject and force a team member to revise their work, your response MUST start EXACTLY with this format:\n")
				promptBuilder.WriteString("REJECT: [RoleName]: [Your detailed critique]\n")
				promptBuilder.WriteString("For example: REJECT: Researcher: The data is outdated. Find 2024 statistics.\n")
				promptBuilder.WriteString("If the work from all team members is absolutely perfect and no further steps are needed from ANY member, you can terminate the entire project early by outputting EXACTLY:\nAPPROVE: ALL\n")
				promptBuilder.WriteString("If you reject or approve, do NOT output anything else. If the work is just acceptable and you are simply adding your own contribution, do NOT use the REJECT/APPROVE prefix; simply perform your task and output your final result.\n\n")

				if len(myRevs) > 0 {
					promptBuilder.WriteString("FEEDBACK / REVISIONS REQUIRED:\n")
					promptBuilder.WriteString("Your previous work was rejected by a downstream reviewer. You MUST fix the issues below:\n")
					for _, rev := range myRevs {
						// Truncate overly long individual revisions
						if len(rev) > 800 { rev = rev[:800] + "...[truncated]" }
						promptBuilder.WriteString(rev + "\n")
					}
					promptBuilder.WriteString("\n")
				}

				promptBuilder.WriteString("CRITICAL CHAT VISIBILITY INSTRUCTION:\n")
				promptBuilder.WriteString("Before calling ANY tool, you MUST output a brief text explanation of your reasoning (e.g., 'I will now search the web for X...'). NEVER output a tool call without first writing your thoughts in the main response text. Your teammates need to read your thought process in the chat UI!\n\n")
				promptBuilder.WriteString("CRITICAL EFFICIENCY INSTRUCTION:\n")
				promptBuilder.WriteString("DO NOT output massive documents, large blocks of code, or raw data directly in your conversational response!\n")
				promptBuilder.WriteString("Instead, use the `write_file` tool to save your work to the local disk. In your response, only output a brief summary and the file paths (pointers). Your team members will use the `read_file` tool to review your work.\n\n")

				promptBuilder.WriteString("ORIGINAL USER TASK:\n")
				// Truncate overly long original commands
				cmdStr := command
				if len(cmdStr) > 1000 { cmdStr = cmdStr[:1000] + "...[truncated]" }
				promptBuilder.WriteString(cmdStr + "\n\n")

				if len(history) > 0 {
					promptBuilder.WriteString("TEAM DISCUSSION SO FAR (Context from other team members):\n")
					for _, msg := range history {
						// Truncate overly long individual history messages so they don't blow up the Groq context limit
						if len(msg) > 1200 { msg = msg[:600] + "\n...[middle truncated to save tokens]...\n" + msg[len(msg)-600:] }
						promptBuilder.WriteString(msg + "\n")
					}
				}

				finalCommand := promptBuilder.String()
				
				// Final safety net truncation
				// Lowered to 4000 characters because some free-tier API proxies have strict 1024 token context limits (Error 413)
				if len(finalCommand) > 4000 {
					half := 1900
					finalCommand = finalCommand[:half] + "\n\n...[MIDDLE CONTEXT TRUNCATED]...\n\n" + finalCommand[len(finalCommand)-half:]
				}
				
				var actualModel string
				parts := strings.Split(n.Model, "\n")
				if len(parts) > 0 {
					actualModel = strings.TrimSpace(parts[0])
				}
				if actualModel == "" {
					actualModel = "openai/gpt-oss-20b"
				}

				modelStr := strings.ToLower(n.Model)
				
				var nodeOut string
				var nodeErr error
				taskID := fmt.Sprintf("node-%s", nodeID)

				if strings.Contains(modelStr, "groq") {
					nodeOut, nodeErr = executeGroqCommand(ctx, finalCommand, connData.GroqAPIKey, actualModel, "dag-internal", nil, taskID, "")
					
					// Edge Case: Model doesn't support tools
					if nodeErr != nil && (strings.Contains(strings.ToLower(nodeErr.Error()), "tool") || strings.Contains(strings.ToLower(nodeErr.Error()), "support") || strings.Contains(strings.ToLower(nodeErr.Error()), "parse")) {
						fallbackGroq := "llama-3.1-70b-versatile"
						gm := fetchGroqModels(connData.GroqAPIKey)
						for _, m := range gm {
							cleanM := strings.Trim(m, "\"")
							if cleanM != actualModel {
								fallbackGroq = cleanM
								break
							}
						}
						fmt.Printf("STATUS: SYSTEM_MSG:Node %s model %s lacks tool support, dynamically switching to %s...\n", nodeID, actualModel, fallbackGroq)
						os.Stdout.Sync()
						actualModel = fallbackGroq
						nodeOut, nodeErr = executeGroqCommand(ctx, finalCommand, connData.GroqAPIKey, actualModel, "dag-internal", nil, taskID, "")
					}
					
					if nodeErr != nil && connData.GroqSecondaryAPIKey != "" {
						fmt.Printf("STATUS: SYSTEM_MSG:Node %s primary Groq failed, trying secondary key...\n", nodeID)
						os.Stdout.Sync()
						nodeOut, nodeErr = executeGroqCommand(ctx, finalCommand, connData.GroqSecondaryAPIKey, actualModel, "dag-internal", nil, taskID, "")
					}
					// If Groq completely fails, fallback to Ollama
					if nodeErr != nil {
						fallbackOllama := "llama3.1:latest"
						om := fetchOllamaModels(connData.OllamaBaseURL, connData.OllamaAPIKey)
						if len(om) > 0 { fallbackOllama = strings.Trim(om[0], "\"") }
						fmt.Printf("STATUS: SYSTEM_MSG:Node %s Groq exhausted, falling back to Ollama %s...\n", nodeID, fallbackOllama)
						os.Stdout.Sync()
						graphifyOllamaSem <- struct{}{}
						nodeOut, nodeErr = executeOllamaCommand(ctx, finalCommand, connData.OllamaBaseURL, fallbackOllama, connData.OllamaAPIKey, nil, taskID, "")
						if nodeErr != nil && connData.OllamaSecondaryAPIKey != "" {
							nodeOut, nodeErr = executeOllamaCommand(ctx, finalCommand, connData.OllamaBaseURL, fallbackOllama, connData.OllamaSecondaryAPIKey, nil, taskID, "")
						}
						<-graphifyOllamaSem
					}
				} else {
					graphifyOllamaSem <- struct{}{}
					nodeOut, nodeErr = executeOllamaCommand(ctx, finalCommand, connData.OllamaBaseURL, actualModel, connData.OllamaAPIKey, nil, taskID, "")
					
					// Edge Case: Model doesn't support tools
					if nodeErr != nil && (strings.Contains(strings.ToLower(nodeErr.Error()), "tool") || strings.Contains(strings.ToLower(nodeErr.Error()), "support") || strings.Contains(strings.ToLower(nodeErr.Error()), "parse")) {
						fallbackOllama := "llama3.1:latest"
						om := fetchOllamaModels(connData.OllamaBaseURL, connData.OllamaAPIKey)
						for _, m := range om {
							cleanM := strings.Trim(m, "\"")
							if cleanM != actualModel {
								fallbackOllama = cleanM
								break
							}
						}
						fmt.Printf("STATUS: SYSTEM_MSG:Node %s model %s lacks tool support, dynamically switching to %s...\n", nodeID, actualModel, fallbackOllama)
						os.Stdout.Sync()
						actualModel = fallbackOllama
						nodeOut, nodeErr = executeOllamaCommand(ctx, finalCommand, connData.OllamaBaseURL, actualModel, connData.OllamaAPIKey, nil, taskID, "")
					}
					
					if nodeErr != nil && connData.OllamaSecondaryAPIKey != "" {
						fmt.Printf("STATUS: SYSTEM_MSG:Node %s primary Ollama failed, trying secondary key...\n", nodeID)
						os.Stdout.Sync()
						nodeOut, nodeErr = executeOllamaCommand(ctx, finalCommand, connData.OllamaBaseURL, actualModel, connData.OllamaSecondaryAPIKey, nil, taskID, "")
					}
					<-graphifyOllamaSem
					
					// If Ollama completely fails, fallback to Groq
					if nodeErr != nil {
						fallbackGroq := "llama3-8b-8192"
						gm := fetchGroqModels(connData.GroqAPIKey)
						if len(gm) > 0 { fallbackGroq = strings.Trim(gm[0], "\"") }
						fmt.Printf("STATUS: SYSTEM_MSG:Node %s Ollama exhausted, falling back to Groq %s...\n", nodeID, fallbackGroq)
						os.Stdout.Sync()
						nodeOut, nodeErr = executeGroqCommand(ctx, finalCommand, connData.GroqAPIKey, fallbackGroq, "dag-internal", nil, taskID, "")
						if nodeErr != nil && connData.GroqSecondaryAPIKey != "" {
							nodeOut, nodeErr = executeGroqCommand(ctx, finalCommand, connData.GroqSecondaryAPIKey, fallbackGroq, "dag-internal", nil, taskID, "")
						}
					}
				}

				mu.Lock()
				defer mu.Unlock()
				
				if nodeErr != nil {
					updateLiveNode(nodeID, "error")
					appendLiveLog(fmt.Sprintf("[%s] ERROR: All API providers failed. Node crashed: %v", n.Role, nodeErr))
					
					// 🚀 SPEEDUP/ROBUSTNESS: Do not crash the entire DAG. 
					// Mark as completed with an error string so downstream nodes can adapt or bypass it.
					outputs[nodeID] = fmt.Sprintf("[CRITICAL ERROR: The AI provider crashed while generating this node's output. Error: %v]", nodeErr)
					completed[nodeID] = true
					running[nodeID] = false
					cond.Broadcast()
					killAgentOverlay(nodeID)
					return
				}

				// Format the chat output nicely
				cleanOut := strings.TrimSpace(nodeOut)
				if len(cleanOut) > 500 {
					cleanOut = cleanOut[:497] + "..."
				}
				appendLiveLog(fmt.Sprintf("[%s]: %s", n.Role, cleanOut))
				transcript = append(transcript, fmt.Sprintf("--- From [%s] ---\n%s", n.Role, nodeOut))
				outputs[nodeID] = nodeOut
				completed[nodeID] = true
				updateLiveNode(nodeID, "completed")
				killAgentOverlay(nodeID)
				
				isReject := false
				// 🚀 SPEEDUP: Early-Exit Consensus
				if strings.Contains(nodeOut, "APPROVE: ALL") {
					mu.Lock()
					for _, n := range state.Nodes {
						if !completed[n.ID] {
							completed[n.ID] = true
							outputs[n.ID] = "Skipped due to Early-Exit Consensus"
							updateLiveNode(n.ID, "skipped")
						}
					}
					mu.Unlock()
					
					appendLiveLog(fmt.Sprintf("[SYSTEM]: %s approved the entire project! Short-circuiting remaining tasks.", n.Role))
					fmt.Printf("STATUS: SYSTEM_MSG:[%s] declared consensus. Terminating early.\n", n.Role)
					os.Stdout.Sync()
					
					running[nodeID] = false
					cond.Broadcast()
					return
				}

				if strings.Contains(nodeOut, "REJECT:") {
					idx := strings.Index(nodeOut, "REJECT:")
					parts := strings.SplitN(nodeOut[idx:], ":", 3)
					if len(parts) >= 3 {
						targetRole := strings.TrimSpace(parts[1])
						critique := strings.TrimSpace(parts[2])
						
						var targetID string
						for _, node := range state.Nodes {
							if strings.EqualFold(strings.TrimSpace(node.Role), targetRole) {
								targetID = node.ID
								break
							}
						}
						
						if targetID != "" && runCount[targetID] < 3 {
							revisions[targetID] = append(revisions[targetID], fmt.Sprintf("Critique from %s:\n%s", n.Role, critique))
							completed[targetID] = false 
							
							var invalidateChildren func(id string)
							invalidateChildren = func(id string) {
								for _, childID := range children[id] {
									if completed[childID] {
										completed[childID] = false
										updateLiveNode(childID, "pending")
										invalidateChildren(childID)
									}
								}
							}
							invalidateChildren(targetID)
							
							isReject = true
							appendLiveLog(fmt.Sprintf("[SYSTEM]: 🚨 %s REJECTED %s's work! Forcing revision loop.", n.Role, targetRole))
							updateLiveNode(targetID, "rejected")
							
							fmt.Printf("STATUS: SYSTEM_MSG:[%s] REJECTED [%s]. Forcing revision.\n", n.Role, targetRole)
							os.Stdout.Sync()
						}
					}
				}

				if !isReject {
					fmt.Printf("STATUS: TEAM_NODE_DONE:%s\n", n.Role)
					os.Stdout.Sync()
				}
				
				running[nodeID] = false
				cond.Broadcast()
			}(nid, myTranscript, myRevisions, myRunCount, agentName, agentIdx, agentPort, agentBridgePort)
		}
		mu.Unlock()
	}

	var finalOutputs []string
	for _, n := range state.Nodes {
		if len(children[n.ID]) == 0 {
			finalOutputs = append(finalOutputs, fmt.Sprintf("--- Final Output from [%s] ---\n%v", n.Role, outputs[n.ID]))
		}
	}

	return strings.Join(finalOutputs, "\n\n"), nil
}
