package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

func autoGenerateGraphifyState(ctx context.Context, command string, connData ConnectionData) error {
	fmt.Printf("STATUS: SYSTEM_MSG:Auto-generating team topology using gemma4:31b...\n")
	os.Stdout.Sync()

		groqModels := fetchGroqModels(connData.GroqAPIKey)
	if len(groqModels) == 0 {
		groqModels = []string{"\"llama-3.1-70b-versatile\"", "\"mixtral-8x7b-32768\"", "\"gemma2-9b-it\"", "\"llama3-8b-8192\""}
	}
	
	ollamaModels := fetchOllamaModels(connData.OllamaBaseURL, connData.OllamaAPIKey)
	if len(ollamaModels) == 0 {
		ollamaModels = []string{"\"llama3.1:latest\"", "\"gemma:7b\"", "\"mistral:latest\""}
	}

	groqModelStr := strings.Join(groqModels, ", ")
	ollamaModelStr := strings.Join(ollamaModels, ", ")

	systemPrompt := fmt.Sprintf(`You are an elite multi-agent system architect. The user has given a task. 
You must break this task down into a directed acyclic graph (DAG) of specialized AI agent nodes.
Return EXACTLY AND ONLY a valid JSON object matching this schema:
{
  "nodes": [
    {
      "id": "node1", 
      "role": "Researcher", 
      "model": "llama-3.1-70b-versatile
(Groq)", 
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
2. "model" MUST be exactly one of these options based on the provider (Groq or Ollama). You MUST use a DIVERSE MIX to avoid API limits (e.g., minimum 2 Ollama nodes per team of 4+):
   Available Groq models (append "
(Groq)"): %s
   Available Ollama models (append "
(Ollama)"): %s
   DO NOT hallucinate models! Only use the models explicitly listed above.
3. Distribute (x,y) coordinates logically (e.g. left to right, 100 to 700 for X, 100 to 400 for Y).
4. Assign nice distinct hex colors.
5. ARCHITECTURE & RELATIONSHIPS: Create a highly collaborative, bidirectional MESH topology reflecting a professional cross-functional team (e.g., Product, Frontend, Backend, Database, Security, Testing, DevOps). 
   - Agents MUST verify each other's work (e.g., Testing verifies Frontend/Backend; Security verifies Database/Backend). 
   - Connections SHOULD include feedback loops (e.g., if you have ["frontend", "testing"], you MUST also have ["testing", "frontend"] for the feedback loop). 
   - Map this out as a 2D spatial diagram where nodes are placed in a circular or star layout, NOT just top-down. 
   - Use (X,Y) coordinates between X:0-800 and Y:0-500 to arrange them spatially (e.g. Product at top Y:50, Database at bottom right X:700, Y:400).
6. INSTRUCT THE NODES TO USE TOOLS: The nodes have access to powerful tools including: browser_automation (scrape/interact with websites), run_terminal (powershell), web_research (duckduckgo), read/write files, and create/modify documents (PDF, PPTX, Excel, CSV). Explicitly command the nodes in their 'prompt' to use these tools if the task requires it.
7. Provide NO markdown wrappers, ONLY raw JSON.`, groqModelStr, ollamaModelStr)

	taskCmd := command
	if len(taskCmd) > 2000 {
		taskCmd = taskCmd[:2000] + "...[TRUNCATED]"
	}

	payload := map[string]interface{}{
		"model": "gemma4:31b",
		"messages": []map[string]string{
			{"role": "system", "content": systemPrompt},
			{"role": "user", "content": "Task: " + taskCmd},
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


type CachedModels struct {
	Timestamp time.Time `json:"timestamp"`
	Models    []string  `json:"models"`
}

func fetchGroqModels(apiKey string) []string {
	configDir := getConfigDir()
	cachePath := filepath.Join(configDir, "groq_models_cache.json")
	
	// Check cache first (valid for 24h)
	if data, err := os.ReadFile(cachePath); err == nil {
		var cache CachedModels
		if json.Unmarshal(data, &cache) == nil {
			if time.Since(cache.Timestamp) < 24*time.Hour {
				return cache.Models
			}
		}
	}

	req, _ := http.NewRequest("GET", "https://api.groq.com/openai/v1/models", nil)
	req.Header.Set("Authorization", "Bearer "+apiKey)
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != 200 { return nil }
	defer resp.Body.Close()
	
	var res struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	json.NewDecoder(resp.Body).Decode(&res)
	
	var allModels []string
	for _, m := range res.Data {
		allModels = append(allModels, m.ID)
	}

	// Test models concurrently
	var validModels []string
	var mu sync.Mutex
	var wg sync.WaitGroup
	
	payloadBytes := []byte(`{"model":"", "messages":[{"role":"user", "content":"Hi"}], "tools":[{"type":"function","function":{"name":"test","description":"test","parameters":{"type":"object","properties":{}}}}], "max_tokens":10}`)
	
	for _, modelID := range allModels {
		// Hardcoded explicit blacklist
		mLower := strings.ToLower(modelID)
		if strings.Contains(mLower, "safeguard") || strings.Contains(mLower, "safegaurd") {
			continue
		}

		wg.Add(1)
		go func(mID string) {
			defer wg.Done()
			
			// Replace model ID in payload
			payload := strings.Replace(string(payloadBytes), `"model":""`, fmt.Sprintf(`"model":"%s"`, mID), 1)
			
			testReq, _ := http.NewRequest("POST", "https://api.groq.com/openai/v1/chat/completions", bytes.NewBuffer([]byte(payload)))
			testReq.Header.Set("Authorization", "Bearer "+apiKey)
			testReq.Header.Set("Content-Type", "application/json")
			testClient := &http.Client{Timeout: 10 * time.Second}
			testResp, testErr := testClient.Do(testReq)
			
			if testErr == nil {
				defer testResp.Body.Close()
				if testResp.StatusCode == 200 {
					mu.Lock()
					validModels = append(validModels, fmt.Sprintf("%q", mID))
					mu.Unlock()
				}
			}
		}(modelID)
	}
	wg.Wait()
	
	if len(validModels) > 0 {
		cache := CachedModels{Timestamp: time.Now(), Models: validModels}
		cacheBytes, _ := json.Marshal(cache)
		os.WriteFile(cachePath, cacheBytes, 0644)
	}
	
	return validModels
}

func fetchOllamaModels(baseURL string, apiKey string) []string {
	configDir := getConfigDir()
	cachePath := filepath.Join(configDir, "ollama_models_cache.json")
	
	if data, err := os.ReadFile(cachePath); err == nil {
		var cache CachedModels
		if json.Unmarshal(data, &cache) == nil {
			if time.Since(cache.Timestamp) < 24*time.Hour {
				return cache.Models
			}
		}
	}

	if baseURL == "" || baseURL == "http://localhost:11434" || baseURL == "https://ollama.com" {
		if apiKey != "" {
			baseURL = "https://api.ollama.com"
		} else {
			baseURL = "http://localhost:11434"
		}
	}
	req, _ := http.NewRequest("GET", strings.TrimRight(baseURL, "/")+"/api/tags", nil)
	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != 200 { return nil }
	defer resp.Body.Close()
	
	var res struct {
		Models []struct {
			Name string `json:"name"`
		} `json:"models"`
	}
	json.NewDecoder(resp.Body).Decode(&res)
	
	var allModels []string
	for _, m := range res.Models {
		allModels = append(allModels, m.Name)
	}

	var validModels []string
	var mu sync.Mutex
	var wg sync.WaitGroup
	
	payloadBytes := []byte(`{"model":"", "messages":[{"role":"user", "content":"Hi"}], "tools":[{"type":"function","function":{"name":"test","description":"test","parameters":{"type":"object","properties":{}}}}], "stream":false}`)
	
	for _, modelID := range allModels {
		// Hardcoded explicit blacklist
		mLower := strings.ToLower(modelID)
		if strings.Contains(mLower, "safeguard") || strings.Contains(mLower, "safegaurd") {
			continue
		}

		wg.Add(1)
		go func(mID string) {
			defer wg.Done()
			
			payload := strings.Replace(string(payloadBytes), `"model":""`, fmt.Sprintf(`"model":"%s"`, mID), 1)
			
			testReq, _ := http.NewRequest("POST", strings.TrimRight(baseURL, "/")+"/api/chat", bytes.NewBuffer([]byte(payload)))
			if apiKey != "" {
				testReq.Header.Set("Authorization", "Bearer "+apiKey)
			}
			testReq.Header.Set("Content-Type", "application/json")
			testClient := &http.Client{Timeout: 10 * time.Second}
			testResp, testErr := testClient.Do(testReq)
			
			if testErr == nil {
				defer testResp.Body.Close()
				if testResp.StatusCode == 200 {
					mu.Lock()
					validModels = append(validModels, fmt.Sprintf("%q", mID))
					mu.Unlock()
				}
			}
		}(modelID)
	}
	wg.Wait()
	
	if len(validModels) > 0 {
		cache := CachedModels{Timestamp: time.Now(), Models: validModels}
		cacheBytes, _ := json.Marshal(cache)
		os.WriteFile(cachePath, cacheBytes, 0644)
	}
	
	return validModels
}
