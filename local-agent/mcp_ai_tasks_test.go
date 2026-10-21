package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"voila/mcp"
)

var openAIFuncNameRegex = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,64}$`)

// TestCloudAPISchemaConformance ensures all tools emitted by toolListForSession()
// strictly conform to Cloud API (OpenAI, Groq, Anthropic, Gemini) tool specifications.
func TestCloudAPISchemaConformance(t *testing.T) {
	initTestEnv(t)
	defer mcp.GlobalHost.StopAll()

	tools := toolListForSession()
	if len(tools) == 0 {
		t.Fatal("Expected tools to be non-empty")
	}

	for _, tool := range tools {
		if tool.Type != "function" {
			t.Errorf("Tool %s has invalid type %s, expected 'function'", tool.Function.Name, tool.Type)
		}

		name := tool.Function.Name
		if !openAIFuncNameRegex.MatchString(name) {
			t.Errorf("Tool name '%s' violates Cloud API regex ^[a-zA-Z0-9_-]{1,64}$", name)
		}
		if len(name) > 64 {
			t.Errorf("Tool name '%s' exceeds 64 characters (len=%d)", name, len(name))
		}

		params := tool.Function.Parameters
		if params == nil {
			t.Errorf("Tool %s has nil parameters", name)
			continue
		}

		// Cloud APIs require "type": "object"
		pType, ok := params["type"].(string)
		if !ok || pType != "object" {
			t.Errorf("Tool %s parameters.type must be 'object', got %v", name, params["type"])
		}

		// Cloud APIs require "properties" field
		if _, ok := params["properties"]; !ok {
			t.Errorf("Tool %s parameters missing 'properties' map", name)
		}

		// Cloud APIs (specifically Groq) reject meta-schema keys
		if _, ok := params["$schema"]; ok {
			t.Errorf("Tool %s contains '$schema' which is rejected by Groq API", name)
		}
		if _, ok := params["$id"]; ok {
			t.Errorf("Tool %s contains '$id' which is rejected by Cloud APIs", name)
		}
		if _, ok := params["$comment"]; ok {
			t.Errorf("Tool %s contains '$comment' which is rejected by Cloud APIs", name)
		}
	}
}

// TestAITask_GitHubLiveExecution verifies that an AI tool-call dispatched through
// dispatchMCPAndExtras cleanly executes on the GitHub MCP server and returns valid results.
func TestAITask_GitHubLiveExecution(t *testing.T) {
	cwd, _ := os.Getwd()
	realConfigPath := filepath.Join(cwd, "mcp_servers.json")
	if _, err := os.Stat(realConfigPath); err != nil {
		// Try parent or local-agent dir
		realConfigPath = filepath.Join(cwd, "local-agent", "mcp_servers.json")
	}

	cfg, err := mcp.LoadConfig(realConfigPath)
	if err != nil || len(cfg.Servers) == 0 {
		t.Skipf("mcp_servers.json not found at %s, skipping live test", realConfigPath)
	}

	// Verify GitHub server is configured
	hasGitHub := false
	for _, s := range cfg.Servers {
		if s.ID == "github" && s.Enabled {
			hasGitHub = true
			break
		}
	}
	if !hasGitHub {
		t.Skip("GitHub MCP server is not enabled in mcp_servers.json")
	}

	// Start MCP Host
	mcp.GlobalHost.StopAll()
	if err := mcp.GlobalHost.StartEnabled(cfg); err != nil {
		t.Fatalf("Failed to start MCP host: %v", err)
	}
	defer mcp.GlobalHost.StopAll()

	ctx := context.Background()

	// ---------------------------------------------------------
	// AI Task 1: Search Repositories
	// User prompt: "Find repository Voila_Voice owned by ojaswi1234"
	// Model emits tool call: mcp__github__search_repositories
	// ---------------------------------------------------------
	t.Run("Task1_SearchRepositories", func(t *testing.T) {
		args, _ := json.Marshal(map[string]interface{}{
			"query": "Voila_Voice user:ojaswi1234",
		})
		result, handled := dispatchMCPAndExtras(ctx, "mcp__github__search_repositories", args, nil)
		if !handled {
			t.Fatalf("Expected tool call to be handled by dispatchMCPAndExtras")
		}
		if strings.HasPrefix(result, "error:") {
			t.Fatalf("search_repositories failed: %s", result)
		}
		if !strings.Contains(result, "ojaswi1234/Voila_Voice") {
			t.Errorf("Expected result to contain 'ojaswi1234/Voila_Voice', got:\n%s", result[:minInt(len(result), 300)])
		}
	})

	// ---------------------------------------------------------
	// AI Task 2: Get File Contents
	// User prompt: "Inspect README.md of ojaswi1234/Voila_Voice"
	// Model emits tool call: mcp__github__get_file_contents
	// ---------------------------------------------------------
	t.Run("Task2_GetFileContents", func(t *testing.T) {
		args, _ := json.Marshal(map[string]interface{}{
			"owner": "ojaswi1234",
			"repo":  "Voila_Voice",
			"path":  "README.md",
		})
		result, handled := dispatchMCPAndExtras(ctx, "mcp__github__get_file_contents", args, nil)
		if !handled {
			t.Fatalf("Expected tool call to be handled by dispatchMCPAndExtras")
		}
		if strings.HasPrefix(result, "error:") {
			t.Fatalf("get_file_contents failed: %s", result)
		}
		if len(result) == 0 {
			t.Errorf("Expected README.md contents to be non-empty")
		}
	})

	// ---------------------------------------------------------
	// AI Task 3: List Commits
	// User prompt: "Check latest commits on ojaswi1234/Voila_Voice"
	// Model emits tool call: mcp__github__list_commits
	// ---------------------------------------------------------
	t.Run("Task3_ListCommits", func(t *testing.T) {
		args, _ := json.Marshal(map[string]interface{}{
			"owner": "ojaswi1234",
			"repo":  "Voila_Voice",
		})
		result, handled := dispatchMCPAndExtras(ctx, "mcp__github__list_commits", args, nil)
		if !handled {
			t.Fatalf("Expected tool call to be handled by dispatchMCPAndExtras")
		}
		if strings.HasPrefix(result, "error:") {
			t.Fatalf("list_commits failed: %s", result)
		}
		if !strings.Contains(result, "commit") && !strings.Contains(result, "sha") && !strings.Contains(result, "author") {
			t.Errorf("Expected commit list in output, got:\n%s", result[:minInt(len(result), 300)])
		}
	})
}

// TestAITask_ExpiredTokenGracefulDegradation verifies that when an expired or invalid
// token is provided, the tool call returns a clean error message back to the LLM
// without panicking or hanging.
func TestAITask_ExpiredTokenGracefulDegradation(t *testing.T) {
	// Create a separate host process with known expired token
	cfg := &mcp.Config{
		Servers: []mcp.ServerConfig{
			{
				ID:      "github_expired",
				Command: "npx",
				Args:    []string{"-y", "@modelcontextprotocol/server-github"},
				Env: map[string]string{
					"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_invalid_expired_token_for_testing_purposes",
					"GITHUB_TOKEN":                 "ghp_invalid_expired_token_for_testing_purposes",
				},
				Enabled:     true,
				ToolTimeout: 15,
			},
		},
	}

	host := &mcp.Host{}
	// Note: start may fail or tools fetch may fail, or tool call will fail with 401
	err := host.StartEnabled(cfg)
	if err != nil {
		// Server cleanly rejected invalid token on startup - this is valid graceful failure
		t.Logf("Server cleanly rejected invalid token on startup: %v", err)
		return
	}
	defer host.StopAll()

	// If it started, try calling a tool
	ctx := context.Background()
	args, _ := json.Marshal(map[string]interface{}{
		"query": "test",
	})
	_, callErr := host.Call(ctx, "mcp__github_expired__search_repositories", args)
	if callErr == nil {
		t.Errorf("Expected authentication error with invalid token, but got nil error")
	} else {
		t.Logf("Received expected graceful error: %v", callErr)
	}
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}


// TestAITask_YouTubeLiveExecution verifies that YouTube MCP tools run live without requiring
// authentication tokens and return valid video metadata.
func TestAITask_YouTubeLiveExecution(t *testing.T) {
	cwd, _ := os.Getwd()
	realConfigPath := filepath.Join(cwd, "mcp_servers.json")
	if _, err := os.Stat(realConfigPath); err != nil {
		realConfigPath = filepath.Join(cwd, "local-agent", "mcp_servers.json")
	}

	cfg, err := mcp.LoadConfig(realConfigPath)
	if err != nil || len(cfg.Servers) == 0 {
		t.Skipf("mcp_servers.json not found at %s, skipping live test", realConfigPath)
	}

	hasYouTube := false
	for _, s := range cfg.Servers {
		if s.ID == "youtube" && s.Enabled {
			hasYouTube = true
			break
		}
	}
	if !hasYouTube {
		t.Skip("YouTube MCP server is not enabled in mcp_servers.json")
	}

	mcp.GlobalHost.StopAll()
	if err := mcp.GlobalHost.StartEnabled(cfg); err != nil {
		t.Fatalf("Failed to start MCP host: %v", err)
	}
	defer mcp.GlobalHost.StopAll()

	ctx := context.Background()

	// ---------------------------------------------------------
	// AI Task: Fetch YouTube Video Metadata (Me at the zoo)
	// User prompt: "Fetch the metadata for YouTube video jNQXAC9IVRw"
	// Model emits tool call: mcp__youtube__get_metadata
	// ---------------------------------------------------------
	t.Run("Task_GetMetadata", func(t *testing.T) {
		args, _ := json.Marshal(map[string]interface{}{
			"url": "jNQXAC9IVRw",
		})
		result, handled := dispatchMCPAndExtras(ctx, "mcp__youtube__get_metadata", args, nil)
		if !handled {
			t.Fatalf("Expected tool call to be handled by dispatchMCPAndExtras")
		}
		if strings.HasPrefix(result, "error:") {
			t.Fatalf("get_metadata failed: %s", result)
		}
		if !strings.Contains(result, "Me at the zoo") || !strings.Contains(result, "jawed") {
			t.Errorf("Expected metadata to contain 'Me at the zoo' and 'jawed', got:\n%s", result[:minInt(len(result), 300)])
		}
	})
}
