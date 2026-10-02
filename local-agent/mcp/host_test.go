package mcp

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestConfigLoad(t *testing.T) {
	cfg, err := LoadConfig("nonexistent.json")
	if err != nil {
		t.Fatalf("Expected no error for missing file, got: %v", err)
	}
	if len(cfg.Servers) != 0 {
		t.Fatalf("Expected empty config")
	}
}

func TestHostStartAndCall(t *testing.T) {
	mockSrc := filepath.Join("testdata", "mock_server.go")
	mockBin := filepath.Join("testdata", "mock_server.exe")
	
	cmd := exec.Command("go", "build", "-o", mockBin, mockSrc)
	if err := cmd.Run(); err != nil {
		t.Fatalf("Failed to build mock server: %v", err)
	}
	defer os.Remove(mockBin)

	cfg := &Config{
		Servers: []ServerConfig{
			{
				ID:          "mock",
				Command:     mockBin,
				Enabled:     true,
				ToolTimeout: 5,
			},
		},
	}

	host := &Host{
		servers: make(map[string]*mcpServerProcess),
	}
	err := host.StartEnabled(cfg)
	if err != nil {
		t.Fatalf("StartEnabled failed: %v", err)
	}
	defer host.StopAll()
	
	time.Sleep(200 * time.Millisecond)

	tools := host.ToolDefs()
	if len(tools) != 1 {
		t.Fatalf("Expected 1 tool, got %d", len(tools))
	}
	if tools[0].Function.Name != "mcp__mock__echo" {
		t.Fatalf("Unexpected tool name: %s", tools[0].Function.Name)
	}

	args := json.RawMessage(`{"message":"hello world"}`)
	res, err := host.Call(context.Background(), "mcp__mock__echo", args)
	if err != nil {
		t.Fatalf("Call failed: %v", err)
	}
	if res != "hello world" {
		t.Fatalf("Expected 'hello world', got '%s'", res)
	}
}
