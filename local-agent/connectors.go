package main

import (
	"encoding/json"
	"voila/mcp"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

type ConnectorEntry struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Description string   `json:"description"`
	AuthType    string   `json:"auth_type"`
	Free        bool     `json:"free"`
	MCPCommand  string   `json:"mcp_command"`
	MCPArgs     []string `json:"mcp_args"`
}

type ConnectorState struct {
	ID           string `json:"id"`
	Enabled      bool   `json:"enabled"`
	ConfiguredAt string `json:"configured_at"`
}


func appendConnectorAudit(action, details string) {
	f, err := os.OpenFile(filepath.Join(getLocalAgentDir(), "security_audit.jsonl"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		defer f.Close()
		f.WriteString(fmt.Sprintf("{\"timestamp\":\"%s\",\"action\":\"%s\",\"details\":\"%s\"}\n", time.Now().Format(time.RFC3339), action, details))
	}
}

func loadCatalog() ([]ConnectorEntry, error) {
	data, err := os.ReadFile(filepath.Join(getLocalAgentDir(), "connectors", "catalog.json"))
	if err != nil {
		return nil, err
	}
	var catalog []ConnectorEntry
	if err := json.Unmarshal(data, &catalog); err != nil {
		return nil, err
	}
	return catalog, nil
}

func loadConnectorStates() ([]ConnectorState, error) {
	data, err := os.ReadFile(filepath.Join(getLocalAgentDir(), "connectors", "connectors_state.json"))
	if err != nil {
		if os.IsNotExist(err) {
			return []ConnectorState{}, nil
		}
		return nil, err
	}
	var states []ConnectorState
	if err := json.Unmarshal(data, &states); err != nil {
		return nil, err
	}
	return states, nil
}

func saveConnectorStates(states []ConnectorState) error {
	data, err := json.MarshalIndent(states, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(getLocalAgentDir(), "connectors", "connectors_state.json"), data, 0644)
}

func connectorsConnect(id, token string) (string, error) {
	catalog, err := loadCatalog()
	if err != nil {
		return "", err
	}
	var entry *ConnectorEntry
	for i, c := range catalog {
		if c.ID == id {
			entry = &catalog[i]
			break
		}
	}
	if entry == nil {
		return "", fmt.Errorf("connector not found in catalog")
	}

	envMap := make(map[string]string)
	if token != "" {
		if id == "github" {
			envMap["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
		} else if id == "canvas_lms" {
			envMap["CANVAS_API_TOKEN"] = token
		} else {
			envMap["TOKEN"] = token
		}
	}

	cfg, _ := mcp.LoadConfig(filepath.Join(getLocalAgentDir(), "mcp_servers.json"))
	if cfg == nil {
		cfg = &mcp.Config{}
	}

	foundSrv := false
	for i, s := range cfg.Servers {
		if s.ID == id {
			cfg.Servers[i].Command = entry.MCPCommand
			cfg.Servers[i].Args = entry.MCPArgs
			cfg.Servers[i].Env = envMap
			cfg.Servers[i].Enabled = true
			if cfg.Servers[i].ToolTimeout <= 0 {
				cfg.Servers[i].ToolTimeout = 30
			}
			foundSrv = true
			break
		}
	}
	if !foundSrv {
		cfg.Servers = append(cfg.Servers, mcp.ServerConfig{
			ID:          id,
			Command:     entry.MCPCommand,
			Args:        entry.MCPArgs,
			Env:         envMap,
			Enabled:     true,
			ToolTimeout: 30,
		})
	}
	mcp.SaveConfig(filepath.Join(getLocalAgentDir(), "mcp_servers.json"), cfg)
	if mcp.GlobalHost != nil {
		mcp.GlobalHost.Reload(cfg)
	}

	states, _ := loadConnectorStates()
	foundState := false
	for i, s := range states {
		if s.ID == id {
			states[i].Enabled = true
			states[i].ConfiguredAt = time.Now().Format(time.RFC3339)
			foundState = true
			break
		}
	}
	if !foundState {
		states = append(states, ConnectorState{
			ID:           id,
			Enabled:      true,
			ConfiguredAt: time.Now().Format(time.RFC3339),
		})
	}
	saveConnectorStates(states)

	appendConnectorAudit("connector_connect", fmt.Sprintf("id: %s", id))
	return "connected", nil
}

func connectorsDisconnect(id string) (string, error) {
	cfg, _ := mcp.LoadConfig(filepath.Join(getLocalAgentDir(), "mcp_servers.json"))
	if cfg != nil {
		for i, s := range cfg.Servers {
			if s.ID == id {
				cfg.Servers[i].Enabled = false
				break
			}
		}
		mcp.SaveConfig(filepath.Join(getLocalAgentDir(), "mcp_servers.json"), cfg)
		if mcp.GlobalHost != nil {
			mcp.GlobalHost.Reload(cfg)
		}
	}

	states, _ := loadConnectorStates()
	for i, s := range states {
		if s.ID == id {
			states[i].Enabled = false
			break
		}
	}
	saveConnectorStates(states)
	return "disconnected", nil
}

func connectorsList() (string, error) {
	catalog, err := loadCatalog()
	if err != nil {
		return "", err
	}
	states, _ := loadConnectorStates()
	stateMap := make(map[string]bool)
	for _, s := range states {
		stateMap[s.ID] = s.Enabled
	}

	var results []map[string]interface{}
	for _, c := range catalog {
		results = append(results, map[string]interface{}{
			"id":        c.ID,
			"name":      c.Name,
			"free":      c.Free,
			"auth_type": c.AuthType,
			"connected": stateMap[c.ID],
		})
	}

	data, err := json.MarshalIndent(results, "", "  ")
	return string(data), err
}

func connectorsStatus(id string) (string, error) {
	states, _ := loadConnectorStates()
	for _, s := range states {
		if s.ID == id {
			if s.Enabled {
				appendConnectorAudit("connector_connect", fmt.Sprintf("id: %s", id))
	return "connected", nil
			}
			return "disconnected", nil
		}
	}
	return "unknown", nil
}
