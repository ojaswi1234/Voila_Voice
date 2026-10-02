package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"os/exec"
	"sync"
	"strings"
	"time"
)

type JSONRPCRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      int         `json:"id"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
}

type JSONRPCResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      int             `json:"id"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *JSONRPCError   `json:"error,omitempty"`
}

type JSONRPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type ToolDef struct {
	Type     string `json:"type"`
	Function struct {
		Name        string          `json:"name"`
		Description string          `json:"description"`
		Parameters  json.RawMessage `json:"parameters"`
	} `json:"function"`
}

type ServerStatus struct {
	ID        string
	Running   bool
	PID       int
	ToolCount int
}

type mcpServerProcess struct {
	config  ServerConfig
	cmd     *exec.Cmd
	stdin   io.WriteCloser
	stdout  io.ReadCloser
	stderr  io.ReadCloser
	reader  *bufio.Reader
	mu      sync.Mutex
	reqID   int
	pending map[int]chan JSONRPCResponse
	tools   []ToolDef
	running bool
	sem     chan struct{}
}

type Host struct {
	mu      sync.RWMutex
	servers map[string]*mcpServerProcess
}

var GlobalHost = &Host{
	servers: make(map[string]*mcpServerProcess),
}

func (h *Host) StartEnabled(cfg *Config) error {
	h.mu.Lock()
	defer h.mu.Unlock()

	for _, scfg := range cfg.Servers {
		if !scfg.Enabled {
			continue
		}
		if _, exists := h.servers[scfg.ID]; exists {
			continue
		}

		if strings.Contains(strings.ToLower(scfg.Command), "filesystem") || strings.Contains(strings.Join(scfg.Args, " "), "server-filesystem") {
			if len(scfg.AllowedPaths) == 0 {
				log.Printf("MCP Server %s (filesystem) refused to start: no allowed_paths configured (fail closed)", scfg.ID)
				continue
			}
		}

		srv := &mcpServerProcess{
			config:  scfg,
			pending: make(map[int]chan JSONRPCResponse),
			sem:     make(chan struct{}, 3),
		}
		if err := srv.start(); err != nil {
			log.Printf("MCP Server %s failed to start: %v", scfg.ID, err)
			continue
		}
		h.servers[scfg.ID] = srv
	}
	return nil
}

func (h *Host) StopAll() {
	h.mu.Lock()
	defer h.mu.Unlock()

	for _, srv := range h.servers {
		srv.stop()
	}
	h.servers = make(map[string]*mcpServerProcess)
}

func (h *Host) Reload(cfg *Config) error {
	h.StopAll()
	return h.StartEnabled(cfg)
}

func (h *Host) ToolDefs() []ToolDef {
	h.mu.RLock()
	defer h.mu.RUnlock()

	var allTools []ToolDef
	for _, srv := range h.servers {
		allTools = append(allTools, srv.tools...)
	}
	return allTools
}

func (h *Host) Call(ctx context.Context, namespacedName string, args json.RawMessage) (string, error) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	for _, srv := range h.servers {
		for _, tool := range srv.tools {
			if tool.Function.Name == namespacedName {
				return srv.callTool(ctx, tool.Function.Name, args)
			}
		}
	}
	return "", fmt.Errorf("tool %s not found", namespacedName)
}

func (h *Host) ListServers() []ServerStatus {
	h.mu.RLock()
	defer h.mu.RUnlock()

	var statuses []ServerStatus
	for id, srv := range h.servers {
		srv.mu.Lock()
		pid := 0
		if srv.cmd != nil && srv.cmd.Process != nil {
			pid = srv.cmd.Process.Pid
		}
		status := ServerStatus{
			ID:        id,
			Running:   srv.running,
			PID:       pid,
			ToolCount: len(srv.tools),
		}
		srv.mu.Unlock()
		statuses = append(statuses, status)
	}
	return statuses
}

func (p *mcpServerProcess) start() error {
	p.cmd = exec.Command(p.config.Command, p.config.Args...)

	env := os.Environ()
	for k, v := range p.config.Env {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}
	p.cmd.Env = env

	stdin, err := p.cmd.StdinPipe()
	if err != nil {
		return err
	}
	stdout, err := p.cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := p.cmd.StderrPipe()
	if err != nil {
		return err
	}

	p.stdin = stdin
	p.stdout = stdout
	p.stderr = stderr
	p.reader = bufio.NewReader(stdout)

	if err := p.cmd.Start(); err != nil {
		return err
	}

	p.running = true

	go p.readLoop()
	go p.stderrLoop()
	go func() {
		p.cmd.Wait()
		p.mu.Lock()
		p.running = false
		p.mu.Unlock()
	}()

	if err := p.initialize(); err != nil {
		p.stop()
		return fmt.Errorf("initialization failed: %w", err)
	}

	if err := p.fetchTools(); err != nil {
		p.stop()
		return fmt.Errorf("fetching tools failed: %w", err)
	}

	return nil
}

func (p *mcpServerProcess) stop() {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.cmd != nil && p.cmd.Process != nil {
		p.cmd.Process.Kill()
	}
	p.running = false
}

func (p *mcpServerProcess) stderrLoop() {
	scanner := bufio.NewScanner(p.stderr)
	for scanner.Scan() {
		log.Printf("[MCP %s] %s", p.config.ID, scanner.Text())
	}
}

func (p *mcpServerProcess) readLoop() {
	for {
		line, err := p.reader.ReadBytes('\n')
		if err != nil {
			break
		}

		var resp JSONRPCResponse
		if err := json.Unmarshal(line, &resp); err != nil {
			continue
		}

		p.mu.Lock()
		ch, ok := p.pending[resp.ID]
		if ok {
			delete(p.pending, resp.ID)
		}
		p.mu.Unlock()

		if ok {
			ch <- resp
		}
	}
}

func (p *mcpServerProcess) sendRequest(method string, params interface{}) (JSONRPCResponse, error) {
	p.mu.Lock()
	p.reqID++
	id := p.reqID
	ch := make(chan JSONRPCResponse, 1)
	p.pending[id] = ch
	p.mu.Unlock()

	req := JSONRPCRequest{
		JSONRPC: "2.0",
		ID:      id,
		Method:  method,
		Params:  params,
	}

	data, err := json.Marshal(req)
	if err != nil {
		p.mu.Lock()
		delete(p.pending, id)
		p.mu.Unlock()
		return JSONRPCResponse{}, err
	}

	data = append(data, '\n')

	_, err = p.stdin.Write(data)
	if err != nil {
		p.mu.Lock()
		delete(p.pending, id)
		p.mu.Unlock()
		return JSONRPCResponse{}, err
	}

	timeout := time.Duration(p.config.ToolTimeout) * time.Second
	select {
	case resp := <-ch:
		return resp, nil
	case <-time.After(timeout):
		p.mu.Lock()
		delete(p.pending, id)
		p.mu.Unlock()
		return JSONRPCResponse{}, errors.New("request timeout")
	}
}

func (p *mcpServerProcess) initialize() error {
	params := map[string]interface{}{
		"protocolVersion": "2024-11-05",
		"clientInfo": map[string]interface{}{
			"name":    "voila-voice",
			"version": "1.0",
		},
		"capabilities": map[string]interface{}{},
	}
	resp, err := p.sendRequest("initialize", params)
	if err != nil {
		return err
	}
	if resp.Error != nil {
		return fmt.Errorf("initialize error: %s", resp.Error.Message)
	}

	notif := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "notifications/initialized",
	}
	b, _ := json.Marshal(notif)
	b = append(b, '\n')
	p.stdin.Write(b)

	return nil
}

func (p *mcpServerProcess) fetchTools() error {
	resp, err := p.sendRequest("tools/list", map[string]interface{}{})
	if err != nil {
		return err
	}
	if resp.Error != nil {
		return fmt.Errorf("tools/list error: %s", resp.Error.Message)
	}

	var result struct {
		Tools []struct {
			Name        string          `json:"name"`
			Description string          `json:"description"`
			InputSchema json.RawMessage `json:"inputSchema"`
		} `json:"tools"`
	}

	if err := json.Unmarshal(resp.Result, &result); err != nil {
		return err
	}

	p.mu.Lock()
	defer p.mu.Unlock()

	p.tools = make([]ToolDef, 0, len(result.Tools))
	for _, t := range result.Tools {
		namespaced := fmt.Sprintf("mcp__%s__%s", p.config.ID, t.Name)
		def := ToolDef{
			Type: "function",
		}
		def.Function.Name = namespaced
		def.Function.Description = t.Description
		def.Function.Parameters = t.InputSchema
		p.tools = append(p.tools, def)
	}
	return nil
}

func (p *mcpServerProcess) callTool(ctx context.Context, namespacedName string, args json.RawMessage) (string, error) {
	var originalName string
	prefix := fmt.Sprintf("mcp__%s__", p.config.ID)
	if len(namespacedName) > len(prefix) && namespacedName[:len(prefix)] == prefix {
		originalName = namespacedName[len(prefix):]
	} else {
		return "", errors.New("invalid tool name format")
	}

	p.sem <- struct{}{}
	defer func() { <-p.sem }()

	var argsMap map[string]interface{}
	if len(args) > 0 {
		if err := json.Unmarshal(args, &argsMap); err != nil {
			return "", err
		}
	}

	
	// Policy Hook / Path Allowlist Enforcement
	if len(p.config.AllowedPaths) > 0 {
		// Basic heuristic: check all string values in arguments for path traversal outside allowed
		for _, v := range argsMap {
			if strVal, ok := v.(string); ok {
				// If it looks like a path (contains / or \)
				if strings.Contains(strVal, "/") || strings.Contains(strVal, "\\") {
					absPath, err := filepath.Abs(strVal)
					if err == nil {
						allowed := false
						for _, ap := range p.config.AllowedPaths {
							absAllowed, _ := filepath.Abs(ap)
							if strings.HasPrefix(absPath, absAllowed) {
								allowed = true
								break
							}
						}
						if !allowed && filepath.IsAbs(strVal) {
							return "", fmt.Errorf("security policy: path %s is outside allowed_paths", strVal)
						}
					}
				}
			}
		}
	}

	params := map[string]interface{}{
		"name":      originalName,
		"arguments": argsMap,
	}

	type resultStruct struct {
		resp JSONRPCResponse
		err  error
	}

	respCh := make(chan resultStruct, 1)
	go func() {
		r, err := p.sendRequest("tools/call", params)
		respCh <- resultStruct{r, err}
	}()

	select {
	case <-ctx.Done():
		return "", ctx.Err()
	case res := <-respCh:
		if res.err != nil {
			return "", res.err
		}
		if res.resp.Error != nil {
			return "", fmt.Errorf("tool error: %s", res.resp.Error.Message)
		}

		var callResult struct {
			Content []struct {
				Type string `json:"type"`
				Text string `json:"text"`
			} `json:"content"`
			IsError bool `json:"isError"`
		}

		if err := json.Unmarshal(res.resp.Result, &callResult); err != nil {
			return string(res.resp.Result), nil
		}

		var output string
		for _, c := range callResult.Content {
			if c.Type == "text" {
				output += c.Text
			}
		}

		if callResult.IsError {
			return "", errors.New(output)
		}

		if len(output) > 65536 {
			output = output[:65536] + "\n...[truncated]"
		}

		return output, nil
	}
}
