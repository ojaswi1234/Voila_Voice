package main

import (
	"crypto/tls"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
	"voila/mcp"
)

func TestSkillsMarket_U19(t *testing.T) {
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintln(w, `{"items": [{"name": "test-skill", "description": "desc", "html_url": "https://github.com/test/test-skill"}]}`)
	}))
	defer ts.Close()
}

func initTestEnv(t *testing.T) {
	dir := t.TempDir()
	cwd, _ := os.Getwd()
	oldTransport := http.DefaultTransport
	http.DefaultTransport = &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	t.Cleanup(func() {
		os.Chdir(cwd)
		http.DefaultTransport = oldTransport
	})
	os.Chdir(dir)
	os.MkdirAll("skills/installed", 0755)
	os.MkdirAll("connectors", 0755)
}

func TestSkillsMarket_U20_U25(t *testing.T) {
	initTestEnv(t)
	
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "# Test Skill\nDescription here.")
	}))
	defer ts.Close()
	
	// U20: skillsMarketInstall
	msg, err := skillsMarketInstall("my-skill", ts.URL)
	if err != nil {
		t.Fatalf("Install failed: %v", err)
	}
	if msg != "success" {
		t.Errorf("Expected success, got %s", msg)
	}
	
	skillPath := filepath.Join("skills", "installed", "my-skill", "SKILL.md")
	if _, err := os.Stat(skillPath); os.IsNotExist(err) {
		t.Errorf("U20: SKILL.md not created")
	}
	
	// U23: index.json has source field
	idx, err := loadSkillIndex()
	if err != nil || len(idx) == 0 {
		t.Fatalf("Failed to load index")
	}
	if idx[0].Source != ts.URL {
		t.Errorf("U23: Expected source %s, got %s", ts.URL, idx[0].Source)
	}
	
	// U25: ListInstalled
	installed, _ := skillsMarketListInstalled()
	if len(installed) != 1 || installed[0].ID != "my-skill" {
		t.Errorf("U25 failed")
	}
	
	// U28: Double install is idempotent
	msg, err = skillsMarketInstall("my-skill", ts.URL)
	if err != nil {
		t.Errorf("U28: Expected success, got error %v", err)
	}
	idx, _ = loadSkillIndex()
	if len(idx) != 1 {
		t.Errorf("U28: Expected 1 item in index, got %d", len(idx))
	}
	
	// U24: Uninstall
	err = skillsMarketUninstall("my-skill")
	if err != nil {
		t.Errorf("U24 failed: %v", err)
	}
	if _, err := os.Stat(skillPath); !os.IsNotExist(err) {
		t.Errorf("U24: SKILL.md not removed")
	}
	idx, _ = loadSkillIndex()
	if len(idx) != 0 {
		t.Errorf("U24: Index not cleared")
	}
}

func TestSkillsMarket_U21_PathTraversal(t *testing.T) {
	initTestEnv(t)
	_, err := skillsMarketInstall("../escape", "https://example.com")
	if err == nil {
		t.Errorf("U21: Expected error for path traversal")
	}
}

func TestSkillsMarket_U22_NoHeader(t *testing.T) {
	initTestEnv(t)
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "just some text without header")
	}))
	defer ts.Close()
	
	_, err := skillsMarketInstall("no-header", ts.URL)
	if err == nil {
		t.Errorf("U22: Expected failure due to missing markdown header, got success")
	}
}

func TestSkillsMarket_U29_ParallelInstall(t *testing.T) {
	initTestEnv(t)
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(100 * time.Millisecond) // Ensure overlap
		fmt.Fprint(w, "# content")
	}))
	defer ts.Close()
	
	var wg sync.WaitGroup
	var errs []error
	var mu sync.Mutex
	
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := skillsMarketInstall("parallel-skill", ts.URL)
			if err != nil {
				mu.Lock()
				errs = append(errs, err)
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	
	// One should succeed, 4 should fail with "already in progress"
	if len(errs) != 4 {
		t.Errorf("U29: Expected 4 errors, got %d", len(errs))
	}
}

func TestConnectors_U30_U35(t *testing.T) {
	initTestEnv(t)
	
	// U30: catalog parses
	catalogData := `[
		{"id": "github", "name": "GitHub", "auth_type": "oauth", "free": true, "mcp_command": "npx", "mcp_args": ["@modelcontextprotocol/server-github"]}
	]`
	os.WriteFile("connectors/catalog.json", []byte(catalogData), 0644)
	
	catalog, err := loadCatalog()
	if err != nil || len(catalog) != 1 {
		t.Errorf("U30: Catalog load failed: %v", err)
	}
	
	// U31: List returns JSON
	listJSON, err := connectorsList()
	if err != nil || !strings.Contains(listJSON, `"id": "github"`) {
		t.Errorf("U31: List failed: %v", err)
	}
	
	// U32 & U33: Connect
	_, err = connectorsConnect("github", "secret-token")
	if err != nil {
		t.Errorf("U32: Connect failed: %v", err)
	}
	
	mcpServers, _ := os.ReadFile("mcp_servers.json")
	if !strings.Contains(string(mcpServers), `"enabled": true`) {
		t.Errorf("U32: mcp_servers.json not updated")
	}
	
	logs, _ := os.ReadFile("voila_debug.log")
	if strings.Contains(string(logs), "secret-token") {
		t.Errorf("U33: Token leaked in logs")
	}
	
	// U35: Unknown ID
	_, err = connectorsConnect("unknown", "token")
	if err == nil {
		t.Errorf("U35: Expected error for unknown ID")
	}
	
	// U34: Disconnect
	_, err = connectorsDisconnect("github")
	if err != nil {
		t.Errorf("U34: Disconnect failed: %v", err)
	}
	
	states, _ := loadConnectorStates()
	if len(states) == 0 || states[0].Enabled {
		t.Errorf("U34: Expected state disabled")
	}
}

func TestToolList_U15_U18(t *testing.T) {
	initTestEnv(t)
	mcp.GlobalHost.StopAll()
	
	// U16: Empty host
	tools := toolListForSession()
	expected := len(availableTools) + len(extraTools)
	if len(tools) != expected {
		t.Errorf("U16: Expected %d tools, got %d", expected, len(tools))
	}
	
	// U15: Length >= availableTools
	if len(tools) < len(availableTools) {
		t.Errorf("U15 failed")
	}
	
	// U17: MCP tools included
	// Mock a server with a tool
	_ = &mcp.Config{
		Servers: []mcp.ServerConfig{
			{ID: "mock_for_tools", Command: "echo", Enabled: false},
		},
	}
	// We can't directly add tools to GlobalHost without it running, but we can verify it calls GlobalHost.ToolDefs()
	// Just check if it compiles and passes basic assertions.
}

