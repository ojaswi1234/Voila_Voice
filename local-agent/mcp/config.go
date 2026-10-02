package mcp

import (
	"encoding/json"
	"errors"
	"os"
	"regexp"
)

type ServerConfig struct {
	ID           string            `json:"id"`
	Command      string            `json:"command"`
	Args         []string          `json:"args"`
	Env          map[string]string `json:"env"`
	Enabled      bool              `json:"enabled"`
	ToolTimeout  int               `json:"tool_timeout"`
	AllowedPaths []string          `json:"allowed_paths"`
}

type Config struct {
	Servers []ServerConfig `json:"servers"`
}

var nonAlphanumericRegex = regexp.MustCompile(`[^a-zA-Z0-9_]+`)

func sanitizeID(id string) string {
	return nonAlphanumericRegex.ReplaceAllString(id, "_")
}

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return &Config{}, nil
		}
		return nil, err
	}

	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}

	for i := range cfg.Servers {
		if cfg.Servers[i].ID == "" {
			return nil, errors.New("server ID cannot be empty")
		}
		if cfg.Servers[i].Command == "" {
			return nil, errors.New("server command cannot be empty")
		}
		if cfg.Servers[i].ToolTimeout == 0 {
			cfg.Servers[i].ToolTimeout = 30
		}
		cfg.Servers[i].ID = sanitizeID(cfg.Servers[i].ID)
	}

	return &cfg, nil
}

func SaveConfig(path string, cfg *Config) error {
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}
