package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
)

type GraphNode struct {
	ID     string `json:"id"`
	Role   string `json:"role"`
	Model  string `json:"model"`
	Prompt string `json:"prompt"`
}


var (
	liveStateMu sync.Mutex
	currentLiveState LiveState
)

func initLiveState(nodes []GraphNode) {
	liveStateMu.Lock()
	defer liveStateMu.Unlock()
	currentLiveState = LiveState{
		Status: "running",
		Nodes: make([]NodeLiveState, len(nodes)),
	}
	for i, n := range nodes {
		currentLiveState.Nodes[i] = NodeLiveState{
			ID: n.ID, Role: n.Role, Status: "pending", Model: n.Model,
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
	Nodes []GraphNode `json:"nodes"`
	Edges [][]string  `json:"edges"`
}

func executeGraphifyDAG(ctx context.Context, command string) (string, error) {
	fmt.Printf("STATUS: GRAPHIFY\n")
	os.Stdout.Sync()
	fmt.Printf("STATUS: SYSTEM_MSG:Initializing Dynamic Multi-Agent State Machine...\n")
	os.Stdout.Sync()

	data, err := os.ReadFile("graphify_state.json")
	if err != nil {
		return "", fmt.Errorf("failed to read graph state: %v", err)
	}

	var state GraphState
	if err := json.Unmarshal(data, &state); err != nil {
		return "", fmt.Errorf("failed to parse graph state: %v", err)
	}

	initLiveState(state.Nodes)
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

	connData, err := loadConnectionData()
	if err != nil {
		return "", err
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

	for {
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
				mu.Unlock()
				finishLiveState("error", "deadlock detected: no nodes are ready or running")
				return "", fmt.Errorf("deadlock detected: no nodes are ready or running")
			}
			cond.Wait()
			mu.Unlock()
			continue
		}

		for _, nid := range ready {
			running[nid] = true
			runCount[nid]++
			
			myTranscript := append([]string(nil), transcript...)
			myRevisions := append([]string(nil), revisions[nid]...)
			myRunCount := runCount[nid]
			
			go func(nodeID string, history []string, myRevs []string, rCount int) {
				n := nodeMap[nodeID]
				
				updateLiveNode(nodeID, "running")
				appendLiveLog(fmt.Sprintf("[%s] Node execution started...", n.Role))

				fmt.Printf("STATUS: TEAM_NODE_START:%s\n", n.Role)
				os.Stdout.Sync()

				promptBuilder := strings.Builder{}
				promptBuilder.WriteString(fmt.Sprintf("You are %s. %s\n\n", n.Role, n.Prompt))

				if len(history) > 0 {
					promptBuilder.WriteString("TEAM DISCUSSION SO FAR (Context from other team members):\n")
					for _, msg := range history {
						promptBuilder.WriteString(msg + "\n")
					}
					
					promptBuilder.WriteString("CRITICAL DEBATE INSTRUCTIONS:\n")
					promptBuilder.WriteString("You are part of an iterative team discussion. You can see everyone's work above.\n")
					promptBuilder.WriteString("If the work from your team members is flawed, missing requirements, or incorrect, you MUST reject it.\n")
					promptBuilder.WriteString("To reject and force a team member to revise their work, your response MUST start EXACTLY with this format:\n")
					promptBuilder.WriteString("REJECT: [RoleName]: [Your detailed critique]\n")
					promptBuilder.WriteString("For example: REJECT: Researcher: The data is outdated. Find 2024 statistics.\n")
					promptBuilder.WriteString("If you reject, do NOT output anything else. If the work is acceptable, or if you are just adding your own contribution, do NOT use the REJECT prefix; simply perform your task and output your final result.\n\n")
				}

				if len(myRevs) > 0 {
					promptBuilder.WriteString("FEEDBACK / REVISIONS REQUIRED:\n")
					promptBuilder.WriteString("Your previous work was rejected by a downstream reviewer. You MUST fix the issues below:\n")
					for _, rev := range myRevs {
						promptBuilder.WriteString(rev + "\n")
					}
					promptBuilder.WriteString("\n")
				}

				promptBuilder.WriteString("ORIGINAL USER TASK:\n")
				promptBuilder.WriteString(command)

				finalCommand := promptBuilder.String()
				
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
				} else {
					ollamaSemaphore <- struct{}{}
					nodeOut, nodeErr = executeOllamaCommand(ctx, finalCommand, connData.OllamaBaseURL, actualModel, connData.OllamaAPIKey, nil, taskID, "")
					<-ollamaSemaphore
				}

				mu.Lock()
				defer mu.Unlock()
				
				if nodeErr != nil {
					updateLiveNode(nodeID, "error")
					appendLiveLog(fmt.Sprintf("[%s] ERROR: %v", n.Role, nodeErr))
				} else {
					updateLiveNode(nodeID, "completed")
					
					// Format the chat output nicely
					cleanOut := strings.TrimSpace(nodeOut)
					if len(cleanOut) > 500 {
						cleanOut = cleanOut[:497] + "..."
					}
					appendLiveLog(fmt.Sprintf("[%s]: %s\n", n.Role, cleanOut))
					
					outputs[nodeID] = nodeOut
					transcript = append(transcript, fmt.Sprintf("--- From [%s] ---\n%s\n", n.Role, nodeOut))
				}
				defer cond.Broadcast()
				
				running[nodeID] = false

				if nodeErr != nil {
					fatalErr = fmt.Errorf("node %s failed: %v", n.Role, nodeErr)
					return
				}

				isReject := false
				trimmedOut := strings.TrimSpace(nodeOut)
				if strings.HasPrefix(trimmedOut, "REJECT:") {
					parts := strings.SplitN(trimmedOut, ":", 3)
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
										invalidateChildren(childID)
									}
								}
							}
							invalidateChildren(targetID)
							
							isReject = true
							fmt.Printf("STATUS: SYSTEM_MSG:[%s] REJECTED [%s]. Forcing revision.\n", n.Role, targetRole)
							os.Stdout.Sync()
						}
					}
				}

				if !isReject {
					outputs[nodeID] = nodeOut
					completed[nodeID] = true
					fmt.Printf("STATUS: TEAM_NODE_DONE:%s\n", n.Role)
					os.Stdout.Sync()
				}
			}(nid, myTranscript, myRevisions, myRunCount)
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
