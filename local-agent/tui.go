package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type LiveState struct {
	Status   string          `json:"status"` // "running", "done", "error"
	Nodes    []NodeLiveState `json:"nodes"`
	Edges    [][]string      `json:"edges"` // e.g. [["node1","node2"],["node1","node3"]]
	Logs     []string        `json:"logs"`
	ErrorMsg string          `json:"error"`
}

type NodeLiveState struct {
	ID     string `json:"id"`
	Role   string `json:"role"`
	Status string `json:"status"` // "pending", "running", "completed", "rejected"
	Model  string `json:"model"`
	X      int    `json:"x"`
	Y      int    `json:"y"`
}

type tuiModel struct {
	state      LiveState
	err        error
	termWidth  int
	termHeight int
}

type graphifyTickMsg time.Time

func runGraphifyTUI() {
	p := tea.NewProgram(tuiModel{}, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Printf("Alas, there's been an error: %v", err)
		os.Exit(1)
	}
}

func (m tuiModel) Init() tea.Cmd {
	return tea.Batch(
		tea.EnterAltScreen,
		tickCmd(),
	)
}

func tickCmd() tea.Cmd {
	return tea.Tick(time.Millisecond*200, func(t time.Time) tea.Msg {
		return graphifyTickMsg(t)
	})
}

func (m tuiModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.termWidth = msg.Width
		m.termHeight = msg.Height
		return m, nil
	case tea.KeyMsg:
		if msg.String() == "k" {
			go func() {
				connData, err := loadConnectionData()
				if err == nil && connData.SecurityPhrase != "" {
					expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
					req, _ := http.NewRequest("POST", "http://127.0.0.1:8080/stop", nil)
					req.Header.Set("X-Exec-Secret", expectedSecret)
					client := &http.Client{Timeout: 2 * time.Second}
					client.Do(req)
				}
			}()
			m.state.ErrorMsg = "FORCE KILLED BY USER"
			m.state.Status = "error"
			return m, nil
		}
		if msg.String() == "q" || msg.String() == "ctrl+c" || msg.String() == "esc" {
			return m, tea.Quit
		}
		// If done, any key quits
		if m.state.Status == "done" || m.state.Status == "error" {
			return m, tea.Quit
		}

	case graphifyTickMsg:
		// Read live state
		data, err := os.ReadFile("graphify_live.json")
		if err == nil {
			var newState LiveState
			if err := json.Unmarshal(data, &newState); err == nil {
				m.state = newState
			}
		}
		return m, tickCmd()
	}

	return m, nil
}

func (m tuiModel) View() string {
	if m.err != nil {
		return fmt.Sprintf("Error: %v\nPress q to quit.", m.err)
	}

	// Styles
	titleStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#10B981")).MarginBottom(1)

	pendingStyle   := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#4B5563")).Padding(0, 1).Foreground(lipgloss.Color("#9CA3AF")).Width(36)
	runningStyle   := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#F59E0B")).Padding(0, 1).Foreground(lipgloss.Color("#FCD34D")).Width(36)
	completedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#10B981")).Padding(0, 1).Foreground(lipgloss.Color("#34D399")).Width(36)
	rejectedStyle  := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#EF4444")).Padding(0, 1).Foreground(lipgloss.Color("#FCA5A5")).Width(36)

	logStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).MarginTop(1)

	header := titleStyle.Render("🤖 VOILA GRAPHIFY : LIVE TEAM TRACKER")
	if m.state.Status == "done" {
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#10B981")).Render(" [FINISHED - Press any key to exit]")
	} else if m.state.Status == "error" {
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render(" [ERROR - Press any key to exit]")
	} else {
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B")).Render(" [RUNNING... (Press 'k' to KILL)]")
	}

	nodeStyles := map[string]lipgloss.Style{
		"pending":   pendingStyle,
		"running":   runningStyle,
		"completed": completedStyle,
		"rejected":  rejectedStyle,
	}

	teamView := renderDAGGraph(m.state, nodeStyles, m.termWidth)

	// Render logs
	var formattedLogs []string

	// Discord-like styling
	nameStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#8B5CF6")).MarginTop(1)
	msgStyle  := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).PaddingLeft(2)
	toolStyle := lipgloss.NewStyle().Faint(true).Foreground(lipgloss.Color("#10B981")).PaddingLeft(2)
	sysStyle  := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#FFFFFF")).Background(lipgloss.Color("#EF4444")).Padding(0, 2).MarginTop(1)

	for _, l := range m.state.Logs {
		l = strings.ReplaceAll(l, "**", "")
		l = strings.ReplaceAll(l, "🔎", "")
		if strings.HasPrefix(l, "[SYSTEM]:") {
			formattedLogs = append(formattedLogs, sysStyle.Render(l))
		} else if strings.HasPrefix(l, "[") && strings.Contains(l, "]:") {
			idx := strings.Index(l, "]:")
			roleName := l[1:idx]
			msgPart  := l[idx+2:]
			formattedLogs = append(formattedLogs, nameStyle.Render("✦ "+roleName))
			if strings.TrimSpace(msgPart) != "" {
				formattedLogs = append(formattedLogs, msgStyle.Render(msgPart))
			}
		} else if strings.HasPrefix(strings.TrimSpace(l), "> Executed tool:") || strings.HasPrefix(strings.TrimSpace(l), ">") {
			formattedLogs = append(formattedLogs, toolStyle.Render(l))
		} else {
			formattedLogs = append(formattedLogs, msgStyle.Render(l))
		}
	}

	logs := strings.Join(formattedLogs, "\n")
	if m.state.ErrorMsg != "" {
		logs += "\n" + lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render("FATAL ERROR: "+m.state.ErrorMsg)
	}
	logsView := logStyle.Render(logs)

	return lipgloss.JoinVertical(lipgloss.Left, header, teamView, logsView)
}

// ── DAG TOPOLOGY GRAPH RENDERER ──────────────────────────────────────────────
// This renders the graph as a proper layered DAG:
//   Layer 0 (roots) → Layer 1 → Layer 2 → ... (sinks)
// Each layer is a column of nodes rendered side-by-side with lipgloss.
// Between columns, directional ASCII arrows are drawn.
// This avoids all ANSI string compositing issues.
func renderDAGGraph(state LiveState, nodeStyles map[string]lipgloss.Style, termW int) string {
	if len(state.Nodes) == 0 {
		return "Loading graph..."
	}

	// Build adjacency maps
	nodeMap  := make(map[string]NodeLiveState)
	children := make(map[string][]string)
	parents  := make(map[string][]string)
	for _, n := range state.Nodes {
		nodeMap[n.ID]   = n
		children[n.ID]  = []string{}
		parents[n.ID]   = []string{}
	}
	for _, e := range state.Edges {
		if len(e) < 2 { continue }
		from, to := e[0], e[1]
		children[from] = append(children[from], to)
		parents[to]    = append(parents[to], from)
	}

	// BFS to assign depth levels (topological layering)
	depth := make(map[string]int)
	for id := range nodeMap {
		depth[id] = -1
	}
	// Start from roots (nodes with no parents)
	queue := []string{}
	for _, n := range state.Nodes {
		if len(parents[n.ID]) == 0 {
			depth[n.ID] = 0
			queue = append(queue, n.ID)
		}
	}
	// If no roots (cycle), assign all depth 0
	if len(queue) == 0 {
		for _, n := range state.Nodes {
			depth[n.ID] = 0
			queue = append(queue, n.ID)
		}
	}
	for len(queue) > 0 {
		cur := queue[0]
		queue = queue[1:]
		for _, child := range children[cur] {
			if depth[child] < depth[cur]+1 {
				depth[child] = depth[cur]+1
				queue = append(queue, child)
			}
		}
	}
	// Assign any unvisited nodes
	for id := range nodeMap {
		if depth[id] == -1 { depth[id] = 0 }
	}

	// Group nodes by layer
	maxDepth := 0
	for _, d := range depth {
		if d > maxDepth { maxDepth = d }
	}
	layers := make([][]string, maxDepth+1)
	for id, d := range depth {
		layers[d] = append(layers[d], id)
	}
	// Sort each layer for stable rendering
	for i := range layers {
		sort.Strings(layers[i])
	}

	// Render each node as a styled box
	renderNode := func(n NodeLiveState) string {
		title := lipgloss.NewStyle().Bold(true).Render(n.Role)
		modelParts := strings.SplitN(n.Model, "\n", 2)
		modelLine1 := strings.TrimSpace(modelParts[0])
		modelLine2 := ""
		if len(modelParts) > 1 { modelLine2 = strings.TrimSpace(modelParts[1]) }
		if len(modelLine1) > 32 { modelLine1 = modelLine1[:30] + ".." }
		modelLabel := modelLine1
		if modelLine2 != "" {
			modelLabel = modelLine1 + "\n" + lipgloss.NewStyle().Faint(true).Italic(true).Render(modelLine2)
		}
		sub     := lipgloss.NewStyle().Faint(true).Render(modelLabel)
		content := fmt.Sprintf("%s\n%s\n[%s]", title, sub, strings.ToUpper(n.Status))
		switch n.Status {
		case "running":   return nodeStyles["running"].Render(content)
		case "completed": return nodeStyles["completed"].Render(content)
		case "rejected":  return nodeStyles["rejected"].Render(content)
		default:          return nodeStyles["pending"].Render(content)
		}
	}

	// Build column views and connector arrows
	// connectorStyle for the arrow column between layers
	arrowStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B")).Bold(true)
	connStyle  := lipgloss.NewStyle().Foreground(lipgloss.Color("#4B5563"))

	var columns []string
	for layerIdx, layerIDs := range layers {
		// Stack all nodes in this layer vertically
		var nodeBoxes []string
		for _, id := range layerIDs {
			if n, ok := nodeMap[id]; ok {
				nodeBoxes = append(nodeBoxes, renderNode(n))
			}
		}
		col := lipgloss.JoinVertical(lipgloss.Left, nodeBoxes...)
		columns = append(columns, col)

		// Add connector column between this layer and next
		if layerIdx < len(layers)-1 {
			// Find all edges crossing this gap
			var edgeLines []string
			for _, fromID := range layerIDs {
				for _, toID := range children[fromID] {
					if depth[toID] == layerIdx+1 {
						fromRole := nodeMap[fromID].Role
						toRole   := nodeMap[toID].Role
						if len(fromRole) > 12 { fromRole = fromRole[:10] + ".." }
						if len(toRole) > 12   { toRole   = toRole[:10] + ".." }
						edgeLines = append(edgeLines, connStyle.Render("·"))
						edgeLines = append(edgeLines, arrowStyle.Render("──▶"))
						_ = fromRole
						_ = toRole
					}
				}
			}
			// Build the arrow connector column
			// Height matches the taller of the two adjacent columns
			arrowBlock := arrowStyle.Render("  ──▶  ")
			connector  := lipgloss.NewStyle().Padding(3, 0).Render(arrowBlock)
			columns = append(columns, connector)
		}
	}

	if len(columns) == 0 {
		return "No graph to display"
	}

	// Join all columns horizontally
	graphView := lipgloss.JoinHorizontal(lipgloss.Center, columns...)

	// Add edge relationship legend below graph
	connHeaderStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#6366F1")).Bold(true).MarginTop(1)
	edgeLegendLines := []string{connHeaderStyle.Render("── CONNECTIONS & RELATIONSHIPS ──")}

	idToRole := make(map[string]string)
	for _, n := range state.Nodes {
		idToRole[n.ID] = n.Role
	}
	for _, e := range state.Edges {
		if len(e) < 2 { continue }
		fromRole := idToRole[e[0]]
		toRole   := idToRole[e[1]]
		if fromRole == "" { fromRole = e[0] }
		if toRole   == "" { toRole   = e[1] }
		line := fmt.Sprintf("  %s  %s  %s",
			lipgloss.NewStyle().Foreground(lipgloss.Color("#818CF8")).Render("["+fromRole+"]"),
			arrowStyle.Render("──▶"),
			lipgloss.NewStyle().Foreground(lipgloss.Color("#34D399")).Render("["+toRole+"]"),
		)
		edgeLegendLines = append(edgeLegendLines, line)
	}
	edgeLegend := strings.Join(edgeLegendLines, "\n")

	return lipgloss.JoinVertical(lipgloss.Left, graphView, edgeLegend)
}
