package main

// ================================================================================
// MCP + Skills Marketplace + Connectors — Wiring Layer
// ================================================================================
// This file wires the MCP Host, Skills Marketplace, and Connectors into the
// existing tool dispatch system WITHOUT touching main.go.
//
// Key design decisions:
//  1. toolListForSession() merges availableTools + MCP tool defs. Both Groq and
//     Ollama request builders should call this instead of using availableTools directly.
//     Until main.go is updated to call toolListForSession(), the MCP tools are still
//     routed correctly via executeToolInner (the MCP host is still started on boot).
//  2. All new tools (mcp_*, skills_market_*, connectors_*) are added to
//     extraTools and returned from toolListForSession().
//  3. executeToolInner is extended via dispatchMCPAndExtras() which handles all
//     new tool names before the main switch falls through to "unknown tool".
// ================================================================================

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"voila/mcp"
)

// ---------------------------------------------------------------------------
// toolListForSession — merged tool list (native + MCP + extras)
// ---------------------------------------------------------------------------

// toolListForSession returns the complete list of tools to send to the LLM.
// It merges:
//   - availableTools (native Voila tools)
//   - MCP host tool definitions (mcp__<server>__<tool> namespaced)
//   - Extra meta tools for MCP management, skills marketplace, and connectors
func toolListForSession() []toolDef {
	tools := make([]toolDef, len(availableTools))
	copy(tools, availableTools)

	// Append MCP host tools (converting mcp.ToolDef → main toolDef)
	for _, td := range mcp.GlobalHost.ToolDefs() {
		var params map[string]interface{}
		if len(td.Function.Parameters) > 0 {
			_ = json.Unmarshal(td.Function.Parameters, &params)
		}
		if params == nil {
			params = map[string]interface{}{"type": "object", "properties": map[string]interface{}{}}
		}
		tools = append(tools, toolDef{
			Type: "function",
			Function: toolFuncDef{
				Name:        td.Function.Name,
				Description: td.Function.Description,
				Parameters:  params,
			},
		})
	}

	// Append extra management/marketplace/connector tools
	tools = append(tools, extraTools...)
	return tools
}

// ---------------------------------------------------------------------------
// Extra tool definitions (MCP meta + Marketplace + Connectors)
// ---------------------------------------------------------------------------

var extraTools = []toolDef{
	// --- MCP Management ---
	{Type: "function", Function: toolFuncDef{
		Name:        "mcp_list_servers",
		Description: "List all configured MCP servers and their status (running/stopped, tool count).",
		Parameters:  emptyParams(),
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "mcp_list_tools",
		Description: "List all tools currently exposed by running MCP servers.",
		Parameters:  emptyParams(),
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "mcp_reload",
		Description: "Reload mcp_servers.json and restart all enabled MCP servers. Use after adding/removing server configs.",
		Parameters:  emptyParams(),
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "mcp_add_server",
		Description: "Add a new MCP server entry to mcp_servers.json.",
		Parameters: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"id":           map[string]interface{}{"type": "string", "description": "Unique server ID (alphanumeric, underscores)"},
				"command":      map[string]interface{}{"type": "string", "description": "Command to run (e.g. 'npx')"},
				"args":         map[string]interface{}{"type": "string", "description": "JSON array of string args, e.g. '[\"-y\",\"@mcp/server-fs\"]'"},
				"enabled":      map[string]interface{}{"type": "boolean", "description": "Start server immediately"},
				"tool_timeout": map[string]interface{}{"type": "integer", "description": "Seconds per tool call (default 30)"},
			},
			"required": []string{"id", "command"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "mcp_remove_server",
		Description: "Remove a MCP server entry by ID.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"id": map[string]interface{}{"type": "string"}},
			"required":   []string{"id"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "mcp_enable_server",
		Description: "Enable and start a MCP server by ID.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"id": map[string]interface{}{"type": "string"}},
			"required":   []string{"id"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "mcp_disable_server",
		Description: "Disable and stop a MCP server by ID.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"id": map[string]interface{}{"type": "string"}},
			"required":   []string{"id"},
		},
	}},

	// --- Skills Marketplace ---
	{Type: "function", Function: toolFuncDef{
		Name:        "skills_market_search",
		Description: "Search the skills marketplace for skill packs matching a query.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"query": map[string]interface{}{"type": "string", "description": "Search terms"}},
			"required":   []string{"query"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "skills_market_info",
		Description: "Get detailed information about a marketplace skill by ID.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"id": map[string]interface{}{"type": "string"}},
			"required":   []string{"id"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "skills_market_install",
		Description: "Install a skill from the marketplace. Requires explicit user confirmation. Downloads SKILL.md only — no scripts executed.",
		Parameters: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"id":     map[string]interface{}{"type": "string", "description": "Skill ID"},
				"source": map[string]interface{}{"type": "string", "description": "HTTPS URL to the SKILL.md file"},
			},
			"required": []string{"id", "source"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "skills_market_uninstall",
		Description: "Uninstall a previously installed marketplace skill by ID.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"id": map[string]interface{}{"type": "string"}},
			"required":   []string{"id"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "skills_market_list_installed",
		Description: "List all marketplace skills currently installed.",
		Parameters:  emptyParams(),
	}},

	// --- Connectors ---
	{Type: "function", Function: toolFuncDef{
		Name:        "connectors_list",
		Description: "List all available connectors (Gmail, GitHub, YouTube, etc.) and whether each is connected.",
		Parameters:  emptyParams(),
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "connectors_status",
		Description: "Get the connection status of a specific connector.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"id": map[string]interface{}{"type": "string", "description": "Connector ID"}},
			"required":   []string{"id"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "connectors_connect",
		Description: "Connect to a service (e.g. github, gmail). Writes the token/credential and enables the MCP server entry. Never logs secrets.",
		Parameters: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"id":    map[string]interface{}{"type": "string", "description": "Connector ID from connectors_list"},
				"token": map[string]interface{}{"type": "string", "description": "API token or OAuth credential"},
			},
			"required": []string{"id", "token"},
		},
	}},
	{Type: "function", Function: toolFuncDef{
		Name:        "connectors_disconnect",
		Description: "Disconnect a connector and disable its MCP server entry.",
		Parameters: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{"id": map[string]interface{}{"type": "string"}},
			"required":   []string{"id"},
		},
	}},
}

func emptyParams() map[string]interface{} {
	return map[string]interface{}{"type": "object", "properties": map[string]interface{}{}, "required": []string{}}
}

// ---------------------------------------------------------------------------
// mcpServersPath — path to mcp_servers.json
// ---------------------------------------------------------------------------

func mcpServersPath() string {
	exe, _ := os.Executable()
	return filepath.Join(filepath.Dir(exe), "mcp_servers.json")
}

// ---------------------------------------------------------------------------
// initMCPHost — called once at agent startup
// ---------------------------------------------------------------------------

func initMCPHost() {
	p := mcpServersPath()
	if _, err := os.Stat(p); os.IsNotExist(err) {
		// No config yet — create empty config so the host starts cleanly
		empty := mcp.Config{}
		_ = mcp.SaveConfig(p, &empty)
		return
	}
	cfg, err := mcp.LoadConfig(p)
	if err != nil {
		debugLog.Printf("[MCP] Failed to load config: %v", err)
		return
	}
	if err := mcp.GlobalHost.StartEnabled(cfg); err != nil {
		debugLog.Printf("[MCP] StartEnabled error: %v", err)
	}
	debugLog.Printf("[MCP] Host started. Servers: %d, Tools: %d",
		len(mcp.GlobalHost.ListServers()), len(mcp.GlobalHost.ToolDefs()))
}

// ---------------------------------------------------------------------------
// dispatchMCPAndExtras — called from executeToolInner default branch
// ---------------------------------------------------------------------------

// dispatchMCPAndExtras handles all tool calls that are NOT in the main switch.
// Returns (result, handled). If handled=false the caller should return "unknown tool".
func dispatchMCPAndExtras(ctx context.Context, toolName string, argsJSON json.RawMessage, streamFileObj *os.File) (string, bool) {
	getString := func(key string) string {
		var m map[string]interface{}
		if json.Unmarshal(argsJSON, &m) == nil {
			if v, ok := m[key]; ok {
				if s, ok := v.(string); ok {
					return s
				}
				if b, err := json.Marshal(v); err == nil {
					return string(b)
				}
			}
		}
		return ""
	}
	getBool := func(key string, def bool) bool {
		var m map[string]interface{}
		if json.Unmarshal(argsJSON, &m) == nil {
			if v, ok := m[key]; ok {
				if b, ok := v.(bool); ok {
					return b
				}
			}
		}
		return def
	}
	getInt := func(key string, def int) int {
		var m map[string]interface{}
		if json.Unmarshal(argsJSON, &m) == nil {
			if v, ok := m[key]; ok {
				if f, ok := v.(float64); ok {
					return int(f)
				}
			}
		}
		return def
	}

	// --- MCP tool calls (namespaced mcp__<server>__<tool>) ---
	if strings.HasPrefix(toolName, "mcp__") {
		result, err := mcp.GlobalHost.Call(ctx, toolName, argsJSON)
		if err != nil {
			return fmt.Sprintf("error calling MCP tool %s: %v", toolName, err), true
		}
		return result, true
	}

	switch toolName {

	// -----------------------------------------------------------------------
	// MCP meta tools
	// -----------------------------------------------------------------------

	case "mcp_list_servers":
		servers := mcp.GlobalHost.ListServers()
		data, _ := json.MarshalIndent(servers, "", "  ")
		return string(data), true

	case "mcp_list_tools":
		tools := mcp.GlobalHost.ToolDefs()
		var names []map[string]string
		for _, t := range tools {
			names = append(names, map[string]string{"name": t.Function.Name, "description": t.Function.Description})
		}
		data, _ := json.MarshalIndent(names, "", "  ")
		return string(data), true

	case "mcp_reload":
		cfg, err := mcp.LoadConfig(mcpServersPath())
		if err != nil {
			return "error loading config: " + err.Error(), true
		}
		if err := mcp.GlobalHost.Reload(cfg); err != nil {
			return "error reloading: " + err.Error(), true
		}
		return fmt.Sprintf("Reloaded. Servers: %d, Tools: %d",
			len(mcp.GlobalHost.ListServers()), len(mcp.GlobalHost.ToolDefs())), true

	case "mcp_add_server":
		p := mcpServersPath()
		cfg, err := mcp.LoadConfig(p)
		if err != nil {
			cfg = &mcp.Config{}
		}
		id := getString("id")
		cmd := getString("command")
		if id == "" || cmd == "" {
			return "error: id and command required", true
		}
		var args []string
		argsStr := getString("args")
		if argsStr != "" {
			_ = json.Unmarshal([]byte(argsStr), &args)
		}
		timeout := getInt("tool_timeout", 30)
		enabled := getBool("enabled", false)
		cfg.Servers = append(cfg.Servers, mcp.ServerConfig{
			ID: id, Command: cmd, Args: args,
			Enabled: enabled, ToolTimeout: timeout,
		})
		if err := mcp.SaveConfig(p, cfg); err != nil {
			return "error saving config: " + err.Error(), true
		}
		if enabled {
			_ = mcp.GlobalHost.Reload(cfg)
		}
		return fmt.Sprintf("Added server '%s'", id), true

	case "mcp_remove_server":
		p := mcpServersPath()
		cfg, err := mcp.LoadConfig(p)
		if err != nil {
			return "error loading config: " + err.Error(), true
		}
		id := getString("id")
		var kept []mcp.ServerConfig
		for _, s := range cfg.Servers {
			if s.ID != id {
				kept = append(kept, s)
			}
		}
		cfg.Servers = kept
		_ = mcp.SaveConfig(p, cfg)
		_ = mcp.GlobalHost.Reload(cfg)
		return fmt.Sprintf("Removed server '%s'", id), true

	case "mcp_enable_server":
		p := mcpServersPath()
		cfg, err := mcp.LoadConfig(p)
		if err != nil {
			return "error: " + err.Error(), true
		}
		id := getString("id")
		for i := range cfg.Servers {
			if cfg.Servers[i].ID == id {
				cfg.Servers[i].Enabled = true
			}
		}
		_ = mcp.SaveConfig(p, cfg)
		_ = mcp.GlobalHost.Reload(cfg)
		return fmt.Sprintf("Enabled server '%s'", id), true

	case "mcp_disable_server":
		p := mcpServersPath()
		cfg, err := mcp.LoadConfig(p)
		if err != nil {
			return "error: " + err.Error(), true
		}
		id := getString("id")
		for i := range cfg.Servers {
			if cfg.Servers[i].ID == id {
				cfg.Servers[i].Enabled = false
			}
		}
		_ = mcp.SaveConfig(p, cfg)
		_ = mcp.GlobalHost.Reload(cfg)
		return fmt.Sprintf("Disabled server '%s'", id), true

	// -----------------------------------------------------------------------
	// Skills Marketplace tools
	// -----------------------------------------------------------------------

	case "skills_market_search":
		query := getString("query")
		results, err := skillsMarketSearch(query)
		if err != nil {
			return "search error: " + err.Error(), true
		}
		data, _ := json.MarshalIndent(results, "", "  ")
		return string(data), true

	case "skills_market_info":
		id := getString("id")
		installed, _ := skillsMarketListInstalled()
		for _, s := range installed {
			if s.ID == id {
				data, _ := json.MarshalIndent(s, "", "  ")
				return string(data), true
			}
		}
		// Try marketplace search
		results, err := skillsMarketSearch(id)
		if err != nil || len(results) == 0 {
			return fmt.Sprintf("No info found for skill '%s'", id), true
		}
		data, _ := json.MarshalIndent(results[0], "", "  ")
		return string(data), true

	case "skills_market_install":
		id := getString("id")
		source := getString("source")
		msg, err := skillsMarketInstall(id, source)
		if err != nil {
			return "install error: " + err.Error(), true
		}
		return msg, true

	case "skills_market_uninstall":
		id := getString("id")
		err := skillsMarketUninstall(id)
		if err != nil {
			return "uninstall error: " + err.Error(), true
		}
		return fmt.Sprintf("Uninstalled skill '%s'", id), true

	case "skills_market_list_installed":
		installed, err := skillsMarketListInstalled()
		if err != nil {
			return "error: " + err.Error(), true
		}
		data, _ := json.MarshalIndent(installed, "", "  ")
		return string(data), true

	// -----------------------------------------------------------------------
	// Connectors tools
	// -----------------------------------------------------------------------

	case "connectors_list":
		result, err := connectorsList()
		if err != nil {
			return "error: " + err.Error(), true
		}
		return result, true

	case "connectors_status":
		id := getString("id")
		result, err := connectorsStatus(id)
		if err != nil {
			return "error: " + err.Error(), true
		}
		return result, true

	case "connectors_connect":
		id := getString("id")
		token := getString("token")
		result, err := connectorsConnect(id, token)
		if err != nil {
			return "error: " + err.Error(), true
		}
		return result, true

	case "connectors_disconnect":
		id := getString("id")
		result, err := connectorsDisconnect(id)
		if err != nil {
			return "error: " + err.Error(), true
		}
		return result, true
	}

	return "", false
}
