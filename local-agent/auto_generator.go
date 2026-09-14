package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
)

func autoGenerateGraphifyState(ctx context.Context, command string, connData ConnectionData) error {
	fmt.Printf("STATUS: SYSTEM_MSG:Auto-generating team topology using gemma4:31b...\n")
	os.Stdout.Sync()

	systemPrompt := `You are an elite multi-agent system architect. The user has given a task. 
You must break this task down into a directed acyclic graph (DAG) of specialized AI agent nodes.
Return EXACTLY AND ONLY a valid JSON object matching this schema:
{
  "nodes": [
    {
      "id": "node1", 
      "role": "Researcher", 
      "model": "openai/gpt-oss-120b\n(Groq)", 
      "prompt": "Specific instructions for this node.",
      "x": 150, "y": 150, "r": 20,
      "color": "#2563EB", "outline": "#60A5FA"
    }
  ],
  "edges": [
    ["node1", "node2"]
  ]
}
Rules:
1. "id" must be unique (e.g. node1, node2).
2. "model" MUST be exactly one of these 7 options. You MUST use a DIVERSE MIX — at minimum 2 Ollama nodes per team:
   Groq (fast cloud):   "openai/gpt-oss-120b\n(Groq)"  |  "openai/gpt-oss-20b\n(Groq)"  |  "qwen/qwen3.6-27b\n(Groq)"
   Ollama (local/cloud): "gemma4:31b\n(Ollama)"  |  "qwen2.5:14b\n(Ollama)"  |  "mistral:7b\n(Ollama)"  |  "llama3.2:3b\n(Ollama)"
   DO NOT assign more than 2 Groq models in a team of 4+ nodes. Spread workloads across both providers.
3. Distribute (x,y) coordinates logically (e.g. left to right, 100 to 700 for X, 100 to 400 for Y).
4. Assign nice distinct hex colors.
5. ARCHITECTURE: Create highly parallel, collaborative MESH/Graph topologies where multiple agents (e.g. 2-3 researchers or specialists) work concurrently on different parts of the problem before converging. DO NOT make a simple sequential chain if the task can be parallelized! Maximize parallel execution.
6. INSTRUCT THE NODES TO USE TOOLS: The nodes have access to powerful tools including: browser_automation (scrape/interact with websites), run_terminal (powershell), web_research (duckduckgo), read/write files, and create/modify documents (PDF, PPTX, Excel, CSV). Explicitly command the nodes in their 'prompt' to use these tools if the task requires it.
7. Provide NO markdown wrappers, ONLY raw JSON.`

	payload := map[string]interface{}{
		"model": "gemma4:31b",
		"messages": []map[string]string{
			{"role": "system", "content": systemPrompt},
			{"role": "user", "content": "Task: " + command},
		},
		"stream": false,
		"format": "json",
	}
	
	bodyBytes, _ := json.Marshal(payload)
	
	// Fallback mechanism: Ollama Primary -> Ollama Secondary -> Groq Primary -> Groq Secondary
	
	var rawJSON string
	var apiErr error

	// 1. Ollama Primary
	rawJSON, apiErr = tryOllamaConfig(ctx, connData.OllamaBaseURL, connData.OllamaAPIKey, bodyBytes)
	if apiErr != nil && connData.OllamaSecondaryAPIKey != "" {
		fmt.Printf("STATUS: SYSTEM_MSG:Primary Ollama failed/quota exhausted, trying secondary key...\n")
		os.Stdout.Sync()
		rawJSON, apiErr = tryOllamaConfig(ctx, connData.OllamaBaseURL, connData.OllamaSecondaryAPIKey, bodyBytes)
	}

	// If Ollama fails, fallback to Groq using llama3
	if apiErr != nil || rawJSON == "" {
		fmt.Printf("STATUS: SYSTEM_MSG:Ollama unavailable, falling back to Groq Llama-3...\n")
		os.Stdout.Sync()
		payload["model"] = "llama-3.1-70b-versatile"
		delete(payload, "format")
		bodyBytes, _ = json.Marshal(payload)
		
		rawJSON, apiErr = tryGroqConfig(ctx, connData.GroqAPIKey, bodyBytes)
		if apiErr != nil && connData.GroqSecondaryAPIKey != "" {
			fmt.Printf("STATUS: SYSTEM_MSG:Primary Groq failed/quota exhausted, trying secondary key...\n")
			os.Stdout.Sync()
			rawJSON, apiErr = tryGroqConfig(ctx, connData.GroqSecondaryAPIKey, bodyBytes)
		}
	}

	if apiErr != nil || rawJSON == "" {
		return fmt.Errorf("all AI providers exhausted or failed: %v", apiErr)
	}

	// Clean up JSON if Groq added markdown
	rawJSON = strings.TrimSpace(rawJSON)
	rawJSON = strings.TrimPrefix(rawJSON, "```json")
	rawJSON = strings.TrimPrefix(rawJSON, "```")
	rawJSON = strings.TrimSuffix(rawJSON, "```")
	rawJSON = strings.TrimSpace(rawJSON)

	var generatedState GraphState
	if err := json.Unmarshal([]byte(rawJSON), &generatedState); err != nil {
		return fmt.Errorf("failed to parse AI-generated team JSON: %v\nJSON was: %s", err, rawJSON)
	}

	generatedState.IsCustom = false
	
	// Safety net for Python UI: inject default visuals if LLM omitted them
	colors := []string{"#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899"}
	outlines := []string{"#93C5FD", "#34D399", "#FCD34D", "#FCA5A5", "#C4B5FD", "#F9A8D4"}
	
	for i := range generatedState.Nodes {
		if generatedState.Nodes[i].R == 0 {
			generatedState.Nodes[i].R = 25
		}
		if generatedState.Nodes[i].X == 0 {
			generatedState.Nodes[i].X = 100 + (i * 150)
		}
		if generatedState.Nodes[i].Y == 0 {
			generatedState.Nodes[i].Y = 200 + ((i % 2) * 50)
		}
		if generatedState.Nodes[i].Color == "" {
			generatedState.Nodes[i].Color = colors[i % len(colors)]
		}
		if generatedState.Nodes[i].Outline == "" {
			generatedState.Nodes[i].Outline = outlines[i % len(outlines)]
		}
	}

	outBytes, _ := json.MarshalIndent(generatedState, "", "  ")
	os.WriteFile("graphify_state.json", outBytes, 0644)

	return nil
}

func tryOllamaConfig(ctx context.Context, baseURL, apiKey string, body []byte) (string, error) {
	if baseURL == "" {
		baseURL = "http://localhost:11434"
	}
	req, _ := http.NewRequestWithContext(ctx, "POST", strings.TrimRight(baseURL, "/")+"/api/chat", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}
	
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("status %d: %s", resp.StatusCode, string(b))
	}
	
	var res struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	}
	json.NewDecoder(resp.Body).Decode(&res)
	return res.Message.Content, nil
}

func tryGroqConfig(ctx context.Context, apiKey string, body []byte) (string, error) {
	if apiKey == "" {
		return "", fmt.Errorf("no groq api key")
	}
	req, _ := http.NewRequestWithContext(ctx, "POST", "https://api.groq.com/openai/v1/chat/completions", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)
	
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("status %d: %s", resp.StatusCode, string(b))
	}
	
	var res struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	json.NewDecoder(resp.Body).Decode(&res)
	if len(res.Choices) > 0 {
		return res.Choices[0].Message.Content, nil
	}
	return "", fmt.Errorf("no choices returned")
}
