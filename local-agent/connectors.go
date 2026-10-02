package main

import (
	"encoding/json"
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
	f, err := os.OpenFile("security_audit.jsonl", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		defer f.Close()
		f.WriteString(fmt.Sprintf("{\"timestamp\":\"%s\",\"action\":\"%s\",\"details\":\"%s\"}\n", time.Now().Format(time.RFC3339), action, details))
	}
}

func loadCatalog() ([]ConnectorEntry, error) {
	data, err := os.ReadFile(filepath.Join("connectors", "catalog.json"))
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
	data, err := os.ReadFile(filepath.Join("connectors", "connectors_state.json"))
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
	return os.WriteFile(filepath.Join("connectors", "connectors_state.json"), data, 0644)
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

	mcpPath := "mcp_servers.json"
	var mcpServers map[string]interface{}
	data, err := os.ReadFile(mcpPath)
	if err == nil {
		json.Unmarshal(data, &mcpServers)
	} else {
		mcpServers = make(map[string]interface{})
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

	mcpServers[id] = map[string]interface{}{
		"command": entry.MCPCommand,
		"args":    entry.MCPArgs,
		"env":     envMap,
		"enabled": true,
	}


	mData, _ := json.MarshalIndent(mcpServers, "", "  ")
	os.WriteFile(mcpPath, mData, 0644)

	states, _ := loadConnectorStates()
	found := false
	for i, s := range states {
		if s.ID == id {
			states[i].Enabled = true
			states[i].ConfiguredAt = time.Now().Format(time.RFC3339)
			found = true
			break
		}
	}
	if !found {
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
	mcpPath := "mcp_servers.json"
	var mcpServers map[string]interface{}
	data, err := os.ReadFile(mcpPath)
	if err == nil {
		if err := json.Unmarshal(data, &mcpServers); err == nil {
			if srv, ok := mcpServers[id].(map[string]interface{}); ok {
				srv["enabled"] = false
				mcpServers[id] = srv
				mData, _ := json.MarshalIndent(mcpServers, "", "  ")
				os.WriteFile(mcpPath, mData, 0644)
			}
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
