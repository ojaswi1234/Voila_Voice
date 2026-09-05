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
	fmt.Printf("STATUS: SYSTEM_MSG:Initializing Distributed DAG Execution...\n")
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

	// Build adjacency maps
	parents := make(map[string][]string)
	children := make(map[string][]string)
	nodeMap := make(map[string]GraphNode)

	for _, n := range state.Nodes {
		nodeMap[n.ID] = n
		parents[n.ID] = []string{}
		children[n.ID] = []string{}
	}

	for _, edge := range state.Edges {
		if len(edge) == 2 {
			src := edge[0]
			tgt := edge[1]
			children[src] = append(children[src], tgt)
			parents[tgt] = append(parents[tgt], src)
		}
	}

	// Calculate Layers (Topological Sort + Leveling)
	layers := make(map[string]int)
	var calcLayer func(id string, visited map[string]bool) (int, error)
	calcLayer = func(id string, visited map[string]bool) (int, error) {
		if visited[id] {
			return 0, fmt.Errorf("cycle detected in graph at node %s", nodeMap[id].Role)
		}
		if l, ok := layers[id]; ok {
			return l, nil
		}

		visited[id] = true
		maxParentLayer := -1
		for _, p := range parents[id] {
			pl, err := calcLayer(p, visited)
			if err != nil {
				return 0, err
			}
			if pl > maxParentLayer {
				maxParentLayer = pl
			}
		}
		visited[id] = false

		layers[id] = maxParentLayer + 1
		return layers[id], nil
	}

	maxLayer := 0
	layerNodes := make(map[int][]string)
	for _, n := range state.Nodes {
		l, err := calcLayer(n.ID, make(map[string]bool))
		if err != nil {
			return "", err
		}
		layerNodes[l] = append(layerNodes[l], n.ID)
		if l > maxLayer {
			maxLayer = l
		}
	}

	connData, err := loadConnectionData()
	if err != nil {
		return "", err
	}

	// Execution State
	outputs := sync.Map{}
	
	// Execute Layer by Layer
	for i := 0; i <= maxLayer; i++ {
		nodesToRun := layerNodes[i]
		if len(nodesToRun) == 0 {
			continue
		}

		fmt.Printf("STATUS: SYSTEM_MSG:Executing DAG Layer %d (%d parallel nodes)\n", i, len(nodesToRun))
		os.Stdout.Sync()

		var wg sync.WaitGroup
		errs := make(chan error, len(nodesToRun))

		for _, nid := range nodesToRun {
			wg.Add(1)
			go func(nodeID string) {
				defer wg.Done()
				n := nodeMap[nodeID]

				fmt.Printf("STATUS: TEAM_NODE_START:%s\n", n.Role)
				os.Stdout.Sync()

				// Build Context Prompt
				promptBuilder := strings.Builder{}
				promptBuilder.WriteString(fmt.Sprintf("You are %s. %s\n\n", n.Role, n.Prompt))

				parentIDs := parents[nodeID]
				if len(parentIDs) > 0 {
					promptBuilder.WriteString("CONTEXT FROM PREVIOUS TEAM MEMBERS:\n")
					for _, pid := range parentIDs {
						parentOut, _ := outputs.Load(pid)
						promptBuilder.WriteString(fmt.Sprintf("--- From [%s] ---\n%v\n\n", nodeMap[pid].Role, parentOut))
					}
				}

				promptBuilder.WriteString("ORIGINAL USER TASK:\n")
				promptBuilder.WriteString(command)

				finalCommand := promptBuilder.String()
				
				// Model Routing
				modelStr := strings.ReplaceAll(n.Model, "\n", " ")
				modelStr = strings.ToLower(modelStr)
				
				var nodeOut string
				var nodeErr error
				
				taskID := fmt.Sprintf("node-%s", nodeID)

				if strings.Contains(modelStr, "groq") {
					actualModel := "llama3-70b-8192" // default fallback
					if strings.Contains(modelStr, "8b") {
						actualModel = "llama3-8b-8192"
					}
					nodeOut, nodeErr = executeGroqCommand(ctx, finalCommand, connData.GroqAPIKey, actualModel, "dag-internal", nil, taskID)
				} else {
					actualModel := "gemma-2b" // default fallback
					if strings.Contains(modelStr, "llama3") {
						actualModel = "llama3:8b"
					}
					ollamaSemaphore <- struct{}{}
					nodeOut, nodeErr = executeOllamaCommand(ctx, finalCommand, connData.OllamaBaseURL, actualModel, connData.OllamaAPIKey, nil, taskID)
					<-ollamaSemaphore
				}

				if nodeErr != nil {
					errs <- fmt.Errorf("node %s failed: %v", n.Role, nodeErr)
					return
				}

				outputs.Store(nodeID, nodeOut)
				fmt.Printf("STATUS: TEAM_NODE_DONE:%s\n", n.Role)
				os.Stdout.Sync()

			}(nid)
		}
		
		wg.Wait()
		close(errs)
		
		for e := range errs {
			if e != nil {
				return "", e
			}
		}
	}

	// Gather output from sink nodes (nodes with no children)
	var finalOutputs []string
	for _, n := range state.Nodes {
		if len(children[n.ID]) == 0 {
			out, _ := outputs.Load(n.ID)
			finalOutputs = append(finalOutputs, fmt.Sprintf("--- Final Output from [%s] ---\n%v", n.Role, out))
		}
	}

	finalResult := strings.Join(finalOutputs, "\n\n")
	return finalResult, nil
}
