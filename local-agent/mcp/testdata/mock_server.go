package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
)

type Request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      int             `json:"id"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params"`
}

type Response struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      int         `json:"id"`
	Result  interface{} `json:"result,omitempty"`
	Error   interface{} `json:"error,omitempty"`
}

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		var req Request
		if err := json.Unmarshal(scanner.Bytes(), &req); err != nil {
			continue
		}

		if req.Method == "initialize" {
			resp := Response{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result: map[string]interface{}{
					"protocolVersion": "2024-11-05",
				},
			}
			b, _ := json.Marshal(resp)
			fmt.Println(string(b))
		} else if req.Method == "tools/list" {
			resp := Response{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result: map[string]interface{}{
					"tools": []map[string]interface{}{
						{
							"name":        "echo",
							"description": "Echoes input",
							"inputSchema": map[string]interface{}{
								"type": "object",
								"properties": map[string]interface{}{
									"message": map[string]string{"type": "string"},
								},
							},
						},
					},
				},
			}
			b, _ := json.Marshal(resp)
			fmt.Println(string(b))
		} else if req.Method == "tools/call" {
			var params struct {
				Name      string `json:"name"`
				Arguments struct {
					Message string `json:"message"`
				} `json:"arguments"`
			}
			json.Unmarshal(req.Params, &params)
			
			resp := Response{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result: map[string]interface{}{
					"content": []map[string]string{
						{
							"type": "text",
							"text": params.Arguments.Message,
						},
					},
					"isError": false,
				},
			}
			b, _ := json.Marshal(resp)
			fmt.Println(string(b))
		}
	}
}
