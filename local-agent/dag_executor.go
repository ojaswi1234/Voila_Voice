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
				return "", fmt.Errorf("deadlock detected: no nodes are ready or running")
			}
			cond.Wait()
			mu.Unlock()
			continue
		}

		for _, nid := range ready {
			running[nid] = true
			runCount[nid]++
			
			// Copy state safely for the goroutine
			parentOutputs := make(map[string]string)
			for _, p := range parents[nid] {
				parentOutputs[p] = outputs[p]
			}
			myRevisions := append([]string(nil), revisions[nid]...)
			myRunCount := runCount[nid]
			
			go func(nodeID string, pOuts map[string]string, myRevs []string, rCount int) {
				n := nodeMap[nodeID]

				fmt.Printf("STATUS: TEAM_NODE_START:%s\n", n.Role)
				os.Stdout.Sync()

				promptBuilder := strings.Builder{}
				promptBuilder.WriteString(fmt.Sprintf("You are %s. %s\n\n", n.Role, n.Prompt))

				parentIDs := parents[nodeID]
				if len(parentIDs) > 0 {
					promptBuilder.WriteString("TEAM MEMBER CONTEXT (You are reviewing/continuing their work):\n")
					for _, pid := range parentIDs {
						promptBuilder.WriteString(fmt.Sprintf("--- From [%s] ---\n%v\n\n", nodeMap[pid].Role, pOuts[pid]))
					}
					
					promptBuilder.WriteString("CRITICAL DEBATE INSTRUCTIONS:\n")
					promptBuilder.WriteString("You are part of an iterative review loop. If the work from your team members is flawed, missing requirements, or incorrect, you MUST reject it.\n")
					promptBuilder.WriteString("To reject and force a team member to revise their work, your response MUST start EXACTLY with this format:\n")
					promptBuilder.WriteString("REJECT: [RoleName]: [Your detailed critique]\n")
					promptBuilder.WriteString("For example: REJECT: Researcher: The data is outdated. Find 2024 statistics.\n")
					promptBuilder.WriteString("If you reject, do NOT output anything else. If the work is acceptable, do NOT use the REJECT prefix; simply perform your task and output your final result.\n\n")
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
					actualModel = "llama-3.1-8b-instant"
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
			}(nid, parentOutputs, myRevisions, myRunCount)
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
