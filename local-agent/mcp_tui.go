package main

// ============================================================
// MCP / Connectors / Skills TUI page
// ============================================================

import (
	"encoding/json"
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"voila/mcp"
)

// ────────────────────────────────────────────────────────────
// Styles
// ────────────────────────────────────────────────────────────

var (
	mcpTitleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("6"))
	mcpTabActive     = lipgloss.NewStyle().Bold(true).Underline(true).Foreground(lipgloss.Color("14"))
	mcpTabInactive   = lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
	mcpRowActive     = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("10")).Background(lipgloss.Color("236"))
	mcpRowInactive   = lipgloss.NewStyle().Foreground(lipgloss.Color("7"))
	mcpBadgeOnStr    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("2")).Render("●")
	mcpBadgeOffStr   = lipgloss.NewStyle().Foreground(lipgloss.Color("1")).Render("○")
	mcpFieldActiveS  = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("14"))
	mcpFieldInactive = lipgloss.NewStyle().Foreground(lipgloss.Color("7"))
	mcpInputBox      = lipgloss.NewStyle().Foreground(lipgloss.Color("15")).Background(lipgloss.Color("235")).Padding(0, 1)
	mcpDivider       = lipgloss.NewStyle().Foreground(lipgloss.Color("8")).Render(strings.Repeat("-", 68))
)

// ────────────────────────────────────────────────────────────
// Form helpers
// ────────────────────────────────────────────────────────────

var mcpFormFieldKeys = map[string][]string{
	"add_server":        {"id", "command", "args", "env_json", "allowed_paths", "timeout"},
	"edit_server":       {"id", "command", "args", "env_json", "allowed_paths", "timeout"},
	"connect_connector": {"token"},
	"add_skill":         {"id", "source_url"},
}

var mcpFormFieldLabels = map[string][]string{
	"add_server":        {"Server ID", "Command (e.g. npx)", "Args (space-separated)", "Env JSON", "Allowed Paths (comma)", "Timeout sec"},
	"edit_server":       {"Server ID", "Command (e.g. npx)", "Args (space-separated)", "Env JSON", "Allowed Paths (comma)", "Timeout sec"},
	"connect_connector": {"Auth Token / API Key"},
	"add_skill":         {"Skill ID", "SKILL.md URL"},
}

func mcpFormFieldCount(subState string) int {
	return len(mcpFormFieldKeys[subState])
}

func mcpGetField(buf map[string]string, subState string, idx int) string {
	if buf == nil {
		return ""
	}
	keys := mcpFormFieldKeys[subState]
	if idx >= len(keys) {
		return ""
	}
	return buf[keys[idx]]
}

func mcpSetField(buf map[string]string, subState string, idx int, val string) {
	if buf == nil {
		return
	}
	keys := mcpFormFieldKeys[subState]
	if idx >= len(keys) {
		return
	}
	buf[keys[idx]] = val
}

func mcpFieldLabel(subState string, idx int) string {
	labels := mcpFormFieldLabels[subState]
	if idx < len(labels) {
		return labels[idx]
	}
	return "Value"
}

// ────────────────────────────────────────────────────────────
// mcpToolsView — main render
// ────────────────────────────────────────────────────────────

func (m model) mcpToolsView() string {
	var sb strings.Builder

	sb.WriteString(mcpTitleStyle.Render("MCP Servers, Connectors & Skills"))
	sb.WriteString("\n")
	sb.WriteString(mcpDivider)
	sb.WriteString("\n")

	// Status messages
	if len(m.messages) > 0 {
		for _, msg := range m.messages {
			sb.WriteString(msg + "\n")
		}
		sb.WriteString("\n")
	}

	// Form overlay
	if m.mcpSubState != "" {
		sb.WriteString(m.mcpFormView())
		sb.WriteString("\n\n")
		sb.WriteString(subtitleStyle.Render("[Up/Down] field  [Enter] save  [Esc] cancel  [Ctrl+V] paste"))
		return sb.String()
	}

	// Tab bar
	tabs := []string{"  Servers  ", "  Connectors  ", "  Skills  "}
	sb.WriteString("  ")
	for i, t := range tabs {
		if i == m.mcpTab {
			sb.WriteString(mcpTabActive.Render(t))
		} else {
			sb.WriteString(mcpTabInactive.Render(t))
		}
		if i < len(tabs)-1 {
			sb.WriteString(mcpTabInactive.Render(" | "))
		}
	}
	sb.WriteString("\n")
	sb.WriteString(mcpDivider)
	sb.WriteString("\n\n")

	switch m.mcpTab {
	case 0:
		sb.WriteString(m.mcpServersTab())
	case 1:
		sb.WriteString(m.mcpConnectorsTab())
	case 2:
		sb.WriteString(m.mcpSkillsTab())
	}

	sb.WriteString("\n")
	sb.WriteString(mcpDivider)
	sb.WriteString("\n")
	sb.WriteString(subtitleStyle.Render("[Tab] switch tabs  [Up/Down] navigate  [Enter] toggle  [A]dd [E]dit [X] remove  [Esc] back"))
	return sb.String()
}

// ── Servers Tab ─────────────────────────────────────────────

func (m model) mcpServersTab() string {
	var sb strings.Builder
	cfg, _ := mcp.LoadConfig(mcpServersPath())
	servers := cfg.Servers

	if len(servers) == 0 {
		sb.WriteString(mcpRowInactive.Render("  No MCP servers configured yet.") + "\n")
	} else {
		for i, s := range servers {
			badge := mcpBadgeOffStr
			if s.Enabled {
				badge = mcpBadgeOnStr
			}
			// Count tools from mcp.GlobalHost
			toolCount := 0
			for _, td := range mcp.GlobalHost.ToolDefs() {
				if strings.HasPrefix(td.Function.Name, "mcp__"+s.ID+"__") {
					toolCount++
				}
			}
			line := fmt.Sprintf("  %s  %-22s  %-14s  %d tools  timeout:%ds",
				badge, s.ID, s.Command, toolCount, s.ToolTimeout)
			if i == m.mcpSelectedItem {
				sb.WriteString(mcpRowActive.Render(line) + "\n")
			} else {
				sb.WriteString(mcpRowInactive.Render(line) + "\n")
			}
		}
	}

	sb.WriteString("\n  ")
	sb.WriteString(activeButtonStyle.Render("[A] Add Server"))
	if len(servers) > 0 {
		sb.WriteString("  " + menuStyle.Render("[E] Edit") + "  " + menuStyle.Render("[X] Remove") + "  " + menuStyle.Render("[Enter] Toggle Enable"))
	}
	return sb.String()
}

// ── Connectors Tab ──────────────────────────────────────────

func (m model) mcpConnectorsTab() string {
	var sb strings.Builder
	catalog, _ := loadCatalog()
	states, _ := loadConnectorStates()
	stateMap := map[string]bool{}
	for _, s := range states {
		stateMap[s.ID] = s.Enabled
	}

	if len(catalog) == 0 {
		sb.WriteString(mcpRowInactive.Render("  No connectors in catalog.") + "\n")
	} else {
		for i, c := range catalog {
			badge := mcpBadgeOffStr
			if stateMap[c.ID] {
				badge = mcpBadgeOnStr
			}
			authTag := "none"
			switch c.AuthType {
			case "token":
				authTag = "token"
			case "oauth2":
				authTag = "OAuth2"
			}
			freeTag := "paid"
			if c.Free {
				freeTag = "free"
			}
			line := fmt.Sprintf("  %s  %-20s  auth:%-6s  %-4s  %s",
				badge, c.Name, authTag, freeTag, c.Description)
			if i == m.mcpSelectedItem {
				sb.WriteString(mcpRowActive.Render(line) + "\n")
			} else {
				sb.WriteString(mcpRowInactive.Render(line) + "\n")
			}
		}
	}

	sb.WriteString("\n  ")
	if len(catalog) > 0 {
		if stateMap[catalog[m.mcpSelectedItem].ID] {
			sb.WriteString(menuStyle.Render("[D] Disconnect"))
		} else {
			sb.WriteString(activeButtonStyle.Render("[C] Connect  (Enter token if required)"))
		}
	}
	return sb.String()
}

// ── Skills Tab ──────────────────────────────────────────────

func (m model) mcpSkillsTab() string {
	var sb strings.Builder
	skills, _ := skillsMarketListInstalled()

	if len(skills) == 0 {
		sb.WriteString(mcpRowInactive.Render("  No marketplace skills installed yet.") + "\n")
	} else {
		for i, s := range skills {
			src := s.Source
			if len(src) > 40 {
				src = src[:37] + "..."
			}
			line := fmt.Sprintf("  %-20s  %s  [%s]", s.ID, src, s.InstalledAt[:10])
			if i == m.mcpSelectedItem {
				sb.WriteString(mcpRowActive.Render(line) + "\n")
			} else {
				sb.WriteString(mcpRowInactive.Render(line) + "\n")
			}
		}
	}

	sb.WriteString("\n  ")
	sb.WriteString(activeButtonStyle.Render("[A] Install from URL"))
	if len(skills) > 0 {
		sb.WriteString("  " + menuStyle.Render("[X] Uninstall"))
	}
	return sb.String()
}

// ── Inline form ──────────────────────────────────────────────

func (m model) mcpFormView() string {
	var sb strings.Builder
	titles := map[string]string{
		"add_server":        "+ Add MCP Server",
		"edit_server":       "* Edit MCP Server",
		"connect_connector": "@ Connect Connector",
		"add_skill":         "# Install Skill from Marketplace",
	}
	sb.WriteString(mcpTitleStyle.Render(titles[m.mcpSubState]) + "\n\n")

	keys := mcpFormFieldKeys[m.mcpSubState]
	for i := range keys {
		label := mcpFieldLabel(m.mcpSubState, i)
		val := ""
		if m.mcpEditBuffer != nil {
			val = m.mcpEditBuffer[keys[i]]
		}
		if i == m.mcpEditField {
			cursor := val + "_"
			sb.WriteString(mcpFieldActiveS.Render(fmt.Sprintf("  > %-28s", label+":")))
			sb.WriteString(" " + mcpInputBox.Render(cursor) + "\n")
		} else {
			display := val
			if display == "" {
				display = "(empty)"
			}
			sb.WriteString(mcpFieldInactive.Render(fmt.Sprintf("    %-28s", label+":")))
			sb.WriteString(" " + mcpFieldInactive.Render(display) + "\n")
		}
	}

	if m.mcpSubState == "add_server" || m.mcpSubState == "edit_server" {
		sb.WriteString("\n")
		sb.WriteString(subtitleStyle.Render(`  Args example:  -y @modelcontextprotocol/server-filesystem .`))
		sb.WriteString("\n")
		sb.WriteString(subtitleStyle.Render(`  Env  example:  {"GITHUB_TOKEN":"ghp_abc123"}`))
		sb.WriteString("\n")
		sb.WriteString(subtitleStyle.Render(`  Paths example: C:/Users/me/projects, C:/data`))
	}

	sb.WriteString("\n\n  ")
	sb.WriteString(activeButtonStyle.Render("[ Enter ] Save") + "  " + menuStyle.Render("[ Esc ] Cancel"))
	return sb.String()
}

// ────────────────────────────────────────────────────────────
// handleMCPEnter
// ────────────────────────────────────────────────────────────

func (m model) handleMCPEnter() (tea.Model, tea.Cmd) {
	if m.mcpSubState != "" {
		return m.mcpSaveForm()
	}

	switch m.mcpTab {
	case 0: // Toggle enable/disable
		cfg, _ := mcp.LoadConfig(mcpServersPath())
		if m.mcpSelectedItem < len(cfg.Servers) {
			cfg.Servers[m.mcpSelectedItem].Enabled = !cfg.Servers[m.mcpSelectedItem].Enabled
			mcp.SaveConfig(mcpServersPath(), cfg)
			mcp.GlobalHost.Reload(cfg)
			label := "disabled"
			if cfg.Servers[m.mcpSelectedItem].Enabled {
				label = "enabled"
			}
			m.messages = []string{successStyle.Render(fmt.Sprintf("Server '%s' %s.", cfg.Servers[m.mcpSelectedItem].ID, label))}
		}

	case 1: // Connect or disconnect
		catalog, _ := loadCatalog()
		states, _ := loadConnectorStates()
		stateMap := map[string]bool{}
		for _, s := range states {
			stateMap[s.ID] = s.Enabled
		}
		if m.mcpSelectedItem < len(catalog) {
			sel := catalog[m.mcpSelectedItem]
			if stateMap[sel.ID] {
				connectorsDisconnect(sel.ID)
				m.messages = []string{successStyle.Render(fmt.Sprintf("Disconnected '%s'.", sel.ID))}
			} else if sel.AuthType == "none" {
				result, err := connectorsConnect(sel.ID, "")
				if err != nil {
					m.messages = []string{errorStyle.Render(err.Error())}
				} else {
					m.messages = []string{successStyle.Render(result)}
				}
			} else {
				m.mcpSubState = "connect_connector"
				m.mcpEditBuffer = map[string]string{"_connector_id": sel.ID}
				m.mcpEditField = 0
				m.currentInput = ""
			}
		}

	case 2: // nothing on Enter for skills
	}
	return m, nil
}

// ── Save form ────────────────────────────────────────────────

func (m model) mcpSaveForm() (tea.Model, tea.Cmd) {
	buf := m.mcpEditBuffer
	if buf == nil {
		buf = map[string]string{}
	}

	switch m.mcpSubState {
	case "add_server", "edit_server":
		id := strings.TrimSpace(buf["id"])
		cmd := strings.TrimSpace(buf["command"])
		if id == "" || cmd == "" {
			m.messages = []string{errorStyle.Render("Server ID and Command are required.")}
			return m, nil
		}
		args := strings.Fields(strings.TrimSpace(buf["args"]))
		envMap := map[string]string{}
		if ej := strings.TrimSpace(buf["env_json"]); ej != "" {
			json.Unmarshal([]byte(ej), &envMap)
		}
		var paths []string
		for _, p := range strings.Split(buf["allowed_paths"], ",") {
			p = strings.TrimSpace(p)
			if p != "" {
				paths = append(paths, p)
			}
		}
		timeout := 30
		fmt.Sscanf(buf["timeout"], "%d", &timeout)
		if timeout <= 0 {
			timeout = 30
		}
		newSrv := mcp.ServerConfig{
			ID:           id,
			Command:      cmd,
			Args:         args,
			Env:          envMap,
			Enabled:      true,
			ToolTimeout:  timeout,
			AllowedPaths: paths,
		}
		cfg, _ := mcp.LoadConfig(mcpServersPath())
		// Remove old entry with same ID
		fresh := []mcp.ServerConfig{}
		for _, s := range cfg.Servers {
			if s.ID != id {
				fresh = append(fresh, s)
			}
		}
		cfg.Servers = append(fresh, newSrv)
		mcp.SaveConfig(mcpServersPath(), cfg)
		mcp.GlobalHost.Reload(cfg)
		m.messages = []string{successStyle.Render(fmt.Sprintf("Server '%s' saved & reloaded.", id))}

	case "connect_connector":
		token := strings.TrimSpace(buf["token"])
		connID := buf["_connector_id"]
		result, err := connectorsConnect(connID, token)
		if err != nil {
			m.messages = []string{errorStyle.Render("Connect error: " + err.Error())}
		} else {
			m.messages = []string{successStyle.Render(result)}
		}

	case "add_skill":
		skillID := strings.TrimSpace(buf["id"])
		source := strings.TrimSpace(buf["source_url"])
		if skillID == "" || source == "" {
			m.messages = []string{errorStyle.Render("Skill ID and URL are required.")}
			return m, nil
		}
		msg, err := skillsMarketInstall(skillID, source)
		if err != nil {
			m.messages = []string{errorStyle.Render(err.Error())}
		} else {
			m.messages = []string{successStyle.Render(msg)}
		}
	}

	m.mcpSubState = ""
	m.mcpEditBuffer = nil
	m.mcpEditField = 0
	m.currentInput = ""
	return m, nil
}

// ────────────────────────────────────────────────────────────
// handleMCPShortcut — called from Update() default: key handler
// ────────────────────────────────────────────────────────────

func (m model) handleMCPShortcut(key string) (model, tea.Cmd) {
	k := strings.ToLower(key)
	switch m.mcpTab {
	case 0: // Servers
		cfg, _ := mcp.LoadConfig(mcpServersPath())
		switch k {
		case "a":
			m.mcpSubState = "add_server"
			m.mcpEditBuffer = map[string]string{"timeout": "30"}
			m.mcpEditField = 0
			m.currentInput = ""
		case "e":
			if m.mcpSelectedItem < len(cfg.Servers) {
				s := cfg.Servers[m.mcpSelectedItem]
				argsStr := strings.Join(s.Args, " ")
				envB, _ := json.Marshal(s.Env)
				allowedStr := strings.Join(s.AllowedPaths, ", ")
				m.mcpSubState = "edit_server"
				m.mcpEditBuffer = map[string]string{
					"id":            s.ID,
					"command":       s.Command,
					"args":          argsStr,
					"env_json":      string(envB),
					"allowed_paths": allowedStr,
					"timeout":       fmt.Sprintf("%d", s.ToolTimeout),
				}
				m.mcpEditField = 0
				m.currentInput = s.ID
			}
		case "x":
			if m.mcpSelectedItem < len(cfg.Servers) {
				delID := cfg.Servers[m.mcpSelectedItem].ID
				fresh := []mcp.ServerConfig{}
				for _, s := range cfg.Servers {
					if s.ID != delID {
						fresh = append(fresh, s)
					}
				}
				cfg.Servers = fresh
				mcp.SaveConfig(mcpServersPath(), cfg)
				mcp.GlobalHost.Reload(cfg)
				if m.mcpSelectedItem > 0 && m.mcpSelectedItem >= len(fresh) {
					m.mcpSelectedItem--
				}
				m.messages = []string{warningStyle.Render(fmt.Sprintf("Server '%s' removed.", delID))}
			}
		}
	case 1: // Connectors
		catalog, _ := loadCatalog()
		if m.mcpSelectedItem >= len(catalog) {
			break
		}
		sel := catalog[m.mcpSelectedItem]
		switch k {
		case "c":
			if sel.AuthType == "none" {
				result, err := connectorsConnect(sel.ID, "")
				if err != nil {
					m.messages = []string{errorStyle.Render(err.Error())}
				} else {
					m.messages = []string{successStyle.Render(result)}
				}
			} else {
				m.mcpSubState = "connect_connector"
				m.mcpEditBuffer = map[string]string{"_connector_id": sel.ID}
				m.mcpEditField = 0
				m.currentInput = ""
			}
		case "d":
			connectorsDisconnect(sel.ID)
			m.messages = []string{successStyle.Render(fmt.Sprintf("Disconnected '%s'.", sel.ID))}
		}
	case 2: // Skills
		skills, _ := skillsMarketListInstalled()
		switch k {
		case "a":
			m.mcpSubState = "add_skill"
			m.mcpEditBuffer = map[string]string{}
			m.mcpEditField = 0
			m.currentInput = ""
		case "x":
			if m.mcpSelectedItem < len(skills) {
				delID := skills[m.mcpSelectedItem].ID
				err := skillsMarketUninstall(delID)
				if err != nil {
					m.messages = []string{errorStyle.Render(err.Error())}
				} else {
					m.messages = []string{successStyle.Render(fmt.Sprintf("Uninstalled '%s'.", delID))}
				}
				if m.mcpSelectedItem > 0 {
					m.mcpSelectedItem--
				}
			}
		}
	}
	return m, nil
}

