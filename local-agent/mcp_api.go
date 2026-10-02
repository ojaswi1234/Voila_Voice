package main

import (
	"encoding/json"
	"net/http"
	"strings"
	"voila/mcp"
)

func mcpApiHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Content-Type", "application/json")

	if r.Method == http.MethodGet {
		cfg, _ := mcp.LoadConfig(mcpServersPath())
		catalog, _ := loadCatalog()
		states, _ := loadConnectorStates()
		skills, _ := skillsMarketListInstalled()

		stateMap := map[string]bool{}
		for _, s := range states {
			stateMap[s.ID] = s.Enabled
		}

		resp := map[string]interface{}{
			"servers":          cfg.Servers,
			"catalog":          catalog,
			"connector_states": stateMap,
			"skills":           skills,
		}
		json.NewEncoder(w).Encode(resp)
		return
	}

	if r.Method == http.MethodPost {
		var req struct {
			Action       string `json:"action"`
			ID           string `json:"id"`
			Command      string `json:"command"`
			Args         string `json:"args"`
			EnvJSON      string `json:"env_json"`
			AllowedPaths string `json:"allowed_paths"`
			Timeout      int    `json:"timeout"`
			Token        string `json:"token"`
			SourceURL    string `json:"source_url"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}

		switch req.Action {
		case "toggle_server":
			cfg, _ := mcp.LoadConfig(mcpServersPath())
			for i, s := range cfg.Servers {
				if s.ID == req.ID {
					cfg.Servers[i].Enabled = !cfg.Servers[i].Enabled
					break
				}
			}
			mcp.SaveConfig(mcpServersPath(), cfg)
			mcp.GlobalHost.Reload(cfg)

		case "add_server", "edit_server":
			args := strings.Fields(strings.TrimSpace(req.Args))
			envMap := map[string]string{}
			if req.EnvJSON != "" {
				json.Unmarshal([]byte(req.EnvJSON), &envMap)
			}
			var paths []string
			for _, p := range strings.Split(req.AllowedPaths, ",") {
				p = strings.TrimSpace(p)
				if p != "" {
					paths = append(paths, p)
				}
			}
			timeout := req.Timeout
			if timeout <= 0 {
				timeout = 30
			}
			newSrv := mcp.ServerConfig{
				ID:           req.ID,
				Command:      req.Command,
				Args:         args,
				Env:          envMap,
				Enabled:      true,
				ToolTimeout:  timeout,
				AllowedPaths: paths,
			}
			cfg, _ := mcp.LoadConfig(mcpServersPath())
			fresh := []mcp.ServerConfig{}
			for _, s := range cfg.Servers {
				if s.ID != req.ID {
					fresh = append(fresh, s)
				}
			}
			cfg.Servers = append(fresh, newSrv)
			mcp.SaveConfig(mcpServersPath(), cfg)
			mcp.GlobalHost.Reload(cfg)

		case "remove_server":
			cfg, _ := mcp.LoadConfig(mcpServersPath())
			fresh := []mcp.ServerConfig{}
			for _, s := range cfg.Servers {
				if s.ID != req.ID {
					fresh = append(fresh, s)
				}
			}
			cfg.Servers = fresh
			mcp.SaveConfig(mcpServersPath(), cfg)
			mcp.GlobalHost.Reload(cfg)

		case "connect_connector":
			_, err := connectorsConnect(req.ID, req.Token)
			if err != nil {
				http.Error(w, err.Error(), 500)
				return
			}
		case "disconnect_connector":
			connectorsDisconnect(req.ID)

		case "install_skill":
			_, err := skillsMarketInstall(req.ID, req.SourceURL)
			if err != nil {
				http.Error(w, err.Error(), 500)
				return
			}
		case "uninstall_skill":
			err := skillsMarketUninstall(req.ID)
			if err != nil {
				http.Error(w, err.Error(), 500)
				return
			}
		}

		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	}
}
