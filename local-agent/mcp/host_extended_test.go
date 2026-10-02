package mcp_test

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"voila/mcp"
)

func TestMCPConfig_U1_ValidConfig(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mcp_servers.json")
	content := `{
		"servers": [
			{
				"id": "server1",
				"command": "node",
				"args": ["app.js"],
				"enabled": true
			}
		]
	}`
	os.WriteFile(path, []byte(content), 0644)

	cfg, err := mcp.LoadConfig(path)
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}
	if len(cfg.Servers) != 1 || cfg.Servers[0].ID != "server1" {
		t.Errorf("Unexpected config loaded: %+v", cfg)
	}
}

func TestMCPConfig_U2_DisabledServer(t *testing.T) {
	mcp.GlobalHost.StopAll()
	cfg := &mcp.Config{
		Servers: []mcp.ServerConfig{
			{ID: "disabled_srv", Command: "echo", Enabled: false},
		},
	}
	mcp.GlobalHost.StartEnabled(cfg)
	list := mcp.GlobalHost.ListServers()
	if len(list) != 0 {
		t.Errorf("Expected 0 servers, got %d", len(list))
	}
}

func TestMCPConfig_U3_EnableDisable(t *testing.T) {
	mcp.GlobalHost.StopAll()
	dir := t.TempDir()
	scriptPath := writeMockServer(t, dir)
	
	cfg := &mcp.Config{
		Servers: []mcp.ServerConfig{
			{ID: "test_srv", Command: scriptPath, Args: []string{}, Enabled: true, ToolTimeout: 5},
		},
	}
	mcp.GlobalHost.StartEnabled(cfg)
	list := mcp.GlobalHost.ListServers()
	if len(list) == 0 {
		t.Errorf("Expected 1 server")
	}

	cfg.Servers[0].Enabled = false
	mcp.GlobalHost.Reload(cfg)
	if len(mcp.GlobalHost.ListServers()) != 0 {
		t.Errorf("Expected 0 servers after disable")
	}
}

func TestMCPConfig_U4_SanitizeID(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "cfg.json")
	os.WriteFile(path, []byte(`{"servers": [{"id": "my-server", "command": "cmd"}]}`), 0644)
	cfg, err := mcp.LoadConfig(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Servers[0].ID != "my_server" {
		t.Errorf("Expected my_server, got %s", cfg.Servers[0].ID)
	}
}

func TestMCPConfig_U5_EmptyID(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "cfg.json")
	os.WriteFile(path, []byte(`{"servers": [{"id": "", "command": "cmd"}]}`), 0644)
	_, err := mcp.LoadConfig(path)
	if err == nil {
		t.Error("Expected error for empty ID")
	}
}

func TestMCPConfig_U6_DefaultTimeout(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "cfg.json")
	os.WriteFile(path, []byte(`{"servers": [{"id": "s1", "command": "cmd"}]}`), 0644)
	cfg, err := mcp.LoadConfig(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Servers[0].ToolTimeout != 30 {
		t.Errorf("Expected 30 timeout, got %d", cfg.Servers[0].ToolTimeout)
	}
}

// Need a mock server to test U10-U14 properly.
func writeMockServer(t *testing.T, dir string) string {
	path := filepath.Join(dir, "mock_server.go")
	script := `package main
import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"time"
)

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		line := scanner.Text()
		var req map[string]interface{}
		json.Unmarshal([]byte(line), &req)
		
		method, _ := req["method"].(string)
		id := req["id"]
		
		if method == "initialize" {
			resp := map[string]interface{}{"jsonrpc": "2.0", "id": id, "result": map[string]interface{}{}}
			b, _ := json.Marshal(resp)
			fmt.Println(string(b))
		} else if method == "tools/list" {
			resp := map[string]interface{}{
				"jsonrpc": "2.0", "id": id, 
				"result": map[string]interface{}{
					"tools": []map[string]interface{}{
						{"name": "hello", "description": "says hello", "inputSchema": map[string]interface{}{}},
					},
				},
			}
			b, _ := json.Marshal(resp)
			fmt.Println(string(b))
		} else if method == "tools/call" {
			params := req["params"].(map[string]interface{})
			name := params["name"].(string)
			if name == "hello" {
				// sleep check for U13 timeout? Check args
				args, ok := params["arguments"].(map[string]interface{})
				if ok && args["sleep"] != nil {
					time.Sleep(5 * time.Second)
				}
				if ok && args["die"] != nil {
					os.Exit(1)
				}
				resp := map[string]interface{}{
					"jsonrpc": "2.0", "id": id,
					"result": map[string]interface{}{
						"content": []map[string]interface{}{{"type": "text", "text": "world"}},
					},
				}
				b, _ := json.Marshal(resp)
				fmt.Println(string(b))
			}
		}
	}
}
`
	os.WriteFile(path, []byte(script), 0644)
	
	exePath := filepath.Join(dir, "mock_server.exe")
	cmd := exec.Command("go", "build", "-o", exePath, path)
	if err := cmd.Run(); err != nil {
		t.Fatalf("failed to build mock server: %v", err)
	}
	return exePath
}

func TestMCPExtended_U10_U14(t *testing.T) {
	dir := t.TempDir()
	scriptPath := writeMockServer(t, dir)
	
	cfg := &mcp.Config{
		Servers: []mcp.ServerConfig{
			{ID: "mock", Command: scriptPath, Args: []string{}, Enabled: true, ToolTimeout: 2},
		},
	}
	mcp.GlobalHost.StopAll()
	err := mcp.GlobalHost.StartEnabled(cfg)
	if err != nil {
		t.Fatalf("StartEnabled failed: %v", err)
	}
	
	// Wait a bit for server to start
	time.Sleep(1 * time.Second)
	
	// U11: Tool list has mcp__mock__hello
	tools := mcp.GlobalHost.ToolDefs()
	found := false
	for _, td := range tools {
		if td.Function.Name == "mcp__mock__hello" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("U11 failed: tool not found")
	}
	
	// U12: Concurrent Call
	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			res, err := mcp.GlobalHost.Call(context.Background(), "mcp__mock__hello", []byte(`{}`))
			if err != nil {
				t.Errorf("Concurrent call err: %v", err)
			}
			if res != "world" {
				t.Errorf("Expected world, got %s", res)
			}
		}()
	}
	wg.Wait()
	
	// U13: Timeout
	_, err = mcp.GlobalHost.Call(context.Background(), "mcp__mock__hello", []byte(`{"sleep": true}`))
	if err == nil {
		t.Errorf("U13 failed: Expected timeout error")
	} else if !strings.Contains(err.Error(), "timeout") {
		t.Errorf("U13 failed: Expected timeout error, got %v", err)
	}
	
	// U10: Server killed mid-flight
	_, err = mcp.GlobalHost.Call(context.Background(), "mcp__mock__hello", []byte(`{"die": true}`))
	if err == nil {
		t.Errorf("U10 failed: Expected error on server die")
	}
	
	// U14: StopAll
	mcp.GlobalHost.StopAll()
	time.Sleep(500 * time.Millisecond)
	list := mcp.GlobalHost.ListServers()
	if len(list) != 0 {
		t.Errorf("U14 failed: Expected 0 servers")
	}
}
