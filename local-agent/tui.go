package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type LiveState struct {
	Status   string          `json:"status"`
	Nodes    []NodeLiveState `json:"nodes"`
	Edges    [][]string      `json:"edges"`
	Logs     []string        `json:"logs"`
	ErrorMsg string          `json:"error"`
}

type NodeLiveState struct {
	ID     string `json:"id"`
	Role   string `json:"role"`
	Status string `json:"status"`
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
		fmt.Printf("Error: %v", err)
		os.Exit(1)
	}
}

func (m tuiModel) Init() tea.Cmd {
	return tea.Batch(tea.EnterAltScreen, tickCmd())
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
		if m.state.Status == "done" || m.state.Status == "error" {
			return m, tea.Quit
		}
	case graphifyTickMsg:
		data, err := os.ReadFile("graphify_live.json")
		if err == nil {
			var newState LiveState
			if err2 := json.Unmarshal(data, &newState); err2 == nil {
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

	titleStyle    := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#10B981")).MarginBottom(1)
	pendingStyle  := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#4B5563")).Padding(0, 1).Foreground(lipgloss.Color("#9CA3AF")).Width(34)
	runningStyle  := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#F59E0B")).Padding(0, 1).Foreground(lipgloss.Color("#FCD34D")).Width(34)
	completedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#10B981")).Padding(0, 1).Foreground(lipgloss.Color("#34D399")).Width(34)
	rejectedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#EF4444")).Padding(0, 1).Foreground(lipgloss.Color("#FCA5A5")).Width(34)
	logStyle      := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).MarginTop(1)

	header := titleStyle.Render("🤖 VOILA GRAPHIFY : LIVE TEAM TRACKER")
	switch m.state.Status {
	case "done":
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#10B981")).Render(" [FINISHED - Press any key to exit]")
	case "error":
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render(" [ERROR - Press any key to exit]")
	default:
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B")).Render(" [RUNNING... (Press 'k' to KILL)]")
	}

	nodeStyles := map[string]lipgloss.Style{
		"pending": pendingStyle, "running": runningStyle,
		"completed": completedStyle, "rejected": rejectedStyle,
	}

	termW := m.termWidth
	if termW < 80 {
		termW = 120
	}

	graphView := renderMeshGraph(m.state, nodeStyles, termW)

	// Logs
	nameStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#8B5CF6")).MarginTop(1)
	msgStyle  := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).PaddingLeft(2)
	toolStyle := lipgloss.NewStyle().Faint(true).Foreground(lipgloss.Color("#10B981")).PaddingLeft(2)
	sysStyle  := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#FFFFFF")).Background(lipgloss.Color("#EF4444")).Padding(0, 2).MarginTop(1)

	var formattedLogs []string
	for _, l := range m.state.Logs {
		l = strings.ReplaceAll(l, "**", "")
		l = strings.ReplaceAll(l, "🔎", "")
		if strings.HasPrefix(l, "[SYSTEM]:") {
			formattedLogs = append(formattedLogs, sysStyle.Render(l))
		} else if strings.HasPrefix(l, "[") && strings.Contains(l, "]:") {
			idx      := strings.Index(l, "]:")
			roleName := l[1:idx]
			msgPart  := l[idx+2:]
			formattedLogs = append(formattedLogs, nameStyle.Render("✦ "+roleName))
			if strings.TrimSpace(msgPart) != "" {
				formattedLogs = append(formattedLogs, msgStyle.Render(msgPart))
			}
		} else if strings.HasPrefix(strings.TrimSpace(l), ">") {
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

	return lipgloss.JoinVertical(lipgloss.Left, header, graphView, logsView)
}

// ──────────────────────────────────────────────────────────────────────────────
// renderMeshGraph: TRUE 2D NETWORK TOPOLOGY GRAPH
//
// Strategy:
//   1. Normalize node X,Y → grid cells (gridCol, gridRow)
//   2. For each grid row, render a horizontal strip of node boxes + plain-text
//      horizontal connectors between boxes in the same row (safe, no ANSI mix)
//   3. Between grid rows, render a separate connector zone of plain ASCII
//      characters (│ ╲ ╱ ▼) showing cross-row connections
//   4. Join everything with strings.Join("\n")
//
// Node boxes are rendered by lipgloss independently per box.
// Connector lines are plain ASCII rune arrays — no ANSI, no corruption.
// ──────────────────────────────────────────────────────────────────────────────
func renderMeshGraph(state LiveState, nodeStyles map[string]lipgloss.Style, termW int) string {
	if len(state.Nodes) == 0 {
		return "Waiting for graph data..."
	}

	const nodeVisualW = 36 // matches Width(34) + 2 border chars
	const hGap        = 6  // horizontal gap between nodes (plain spaces/connectors)
	const colStride   = nodeVisualW + hGap // 42 chars per grid column
	const connRows    = 3  // terminal lines between grid rows for vertical connections

	// Max grid columns based on terminal width
	maxCols := termW / colStride
	if maxCols < 1 { maxCols = 1 }
	if maxCols > 5 { maxCols = 5 }

	// Build node map and edge set
	nodeMap := make(map[string]NodeLiveState)
	for _, n := range state.Nodes {
		nodeMap[n.ID] = n
	}
	edgeSet := make(map[string]bool)
	for _, e := range state.Edges {
		if len(e) >= 2 {
			edgeSet[e[0]+"->"+e[1]] = true
		}
	}

	// Normalize X,Y → gridCol, gridRow
	minX, maxX, minY, maxY := 99999, -99999, 99999, -99999
	for _, n := range state.Nodes {
		if n.X < minX { minX = n.X }
		if n.X > maxX { maxX = n.X }
		if n.Y < minY { minY = n.Y }
		if n.Y > maxY { maxY = n.Y }
	}
	if maxX == minX { maxX = minX + 1 }
	if maxY == minY { maxY = minY + 1 }

	maxGridRows := 0
	gridPos := make(map[string][2]int) // nodeID → [col, row]
	for _, n := range state.Nodes {
		normX := float64(n.X-minX) / float64(maxX-minX)
		normY := float64(n.Y-minY) / float64(maxY-minY)
		gc    := int(normX * float64(maxCols-1) + 0.5)
		gr    := int(normY * 3.0 + 0.5)
		if gc >= maxCols { gc = maxCols - 1 }
		if gr > maxGridRows { maxGridRows = gr }
		gridPos[n.ID] = [2]int{gc, gr}
	}
	maxGridRows++

	// Place nodes into grid, handling collisions
	grid := make([][]string, maxGridRows)
	for r := range grid {
		grid[r] = make([]string, maxCols)
	}
	for _, n := range state.Nodes {
		pos := gridPos[n.ID]
		gc, gr := pos[0], pos[1]
		// Resolve collision: try bumping right, then wrap
		attempts := 0
		for grid[gr][gc] != "" && attempts < maxCols {
			gc = (gc + 1) % maxCols
			attempts++
		}
		grid[gr][gc] = n.ID
		gridPos[n.ID] = [2]int{gc, gr}
	}

	// Render one node as a lipgloss box (returns a multi-line string)
	renderBox := func(n NodeLiveState) string {
		title := lipgloss.NewStyle().Bold(true).Render(n.Role)
		parts  := strings.SplitN(n.Model, "\n", 2)
		m1 := strings.TrimSpace(parts[0])
		m2 := ""
		if len(parts) > 1 { m2 = strings.TrimSpace(parts[1]) }
		if len(m1) > 30 { m1 = m1[:28] + ".." }
		ml := m1
		if m2 != "" { ml = m1 + "\n" + lipgloss.NewStyle().Faint(true).Italic(true).Render(m2) }
		content := fmt.Sprintf("%s\n%s\n[%s]", title, lipgloss.NewStyle().Faint(true).Render(ml), strings.ToUpper(n.Status))
		switch n.Status {
		case "running":   return nodeStyles["running"].Render(content)
		case "completed": return nodeStyles["completed"].Render(content)
		case "rejected":  return nodeStyles["rejected"].Render(content)
		default:          return nodeStyles["pending"].Render(content)
		}
	}

	// Measure actual box height from a sample render
	sampleBox   := nodeStyles["pending"].Render("A\nB\nC\nD")
	boxH        := strings.Count(sampleBox, "\n") + 1
	midLine     := boxH / 2

	// Helper: blank placeholder, same height as a box
	blankBox := func() string {
		rows := make([]string, boxH)
		for i := range rows { rows[i] = strings.Repeat(" ", nodeVisualW) }
		return strings.Join(rows, "\n")
	}

	// Helper: build a hGap-wide, boxH-tall connector column
	// If edge exists between fromID and toID (same row), draws ──▶── on midLine
	hConnector := func(fromID, toID string) string {
		rows := make([]string, boxH)
		for i := range rows { rows[i] = strings.Repeat(" ", hGap) }
		if fromID != "" && toID != "" && edgeSet[fromID+"->"+toID] {
			arrow := "──▶───"
			if len(arrow) > hGap { arrow = arrow[:hGap] }
			for len(arrow) < hGap { arrow += "─" }
			rows[midLine] = arrow
		}
		return strings.Join(rows, "\n")
	}

	// Build the full connector zone between grid row r and r+1
	// Returns connRows terminal lines as a plain []string
	buildConnZone := func(rowAbove, rowBelow []string) []string {
		// Total visual width of the strip
		stripW := maxCols*nodeVisualW + (maxCols-1)*hGap
		if stripW < 10 { stripW = 80 }

		lines := make([][]rune, connRows)
		for i := range lines {
			lines[i] = []rune(strings.Repeat(" ", stripW))
		}

		// Center X of each column slot
		centerX := func(col int) int {
			return col*colStride + nodeVisualW/2
		}

		setChar := func(lineIdx, x int, ch rune) {
			if lineIdx >= 0 && lineIdx < connRows && x >= 0 && x < stripW {
				lines[lineIdx][x] = ch
			}
		}

		for colA := 0; colA < maxCols; colA++ {
			fromID := rowAbove[colA]
			if fromID == "" { continue }
			cx := centerX(colA)

			for colB := 0; colB < maxCols; colB++ {
				toID := rowBelow[colB]
				if toID == "" || !edgeSet[fromID+"->"+toID] { continue }
				tx := centerX(colB)

				// Draw connRows lines tracing from (cx, top) to (tx, bottom)
				for li := 0; li < connRows; li++ {
					// Interpolate x position
					t  := float64(li) / float64(connRows-1)
					x  := cx + int(float64(tx-cx)*t+0.5)
					ch := rune('|')
					if tx > cx { ch = '\\' }
					if tx < cx { ch = '/' }
					if tx == cx { ch = '|' }
					setChar(li, x, ch)
				}
				// Arrowhead on the last line pointing into target
				setChar(connRows-1, tx, 'v')
			}
		}

		result := make([]string, connRows)
		for i, runes := range lines {
			result[i] = string(runes)
		}
		return result
	}

	// Assemble all output lines
	var outputLines []string

	for rowIdx := 0; rowIdx < maxGridRows; rowIdx++ {
		// Build node strip for this grid row
		var rowParts []string
		for colIdx := 0; colIdx < maxCols; colIdx++ {
			nodeID := grid[rowIdx][colIdx]
			if nodeID != "" {
				rowParts = append(rowParts, renderBox(nodeMap[nodeID]))
			} else {
				rowParts = append(rowParts, blankBox())
			}
			if colIdx < maxCols-1 {
				rowParts = append(rowParts, hConnector(grid[rowIdx][colIdx], grid[rowIdx][colIdx+1]))
			}
		}

		// JoinHorizontal correctly aligns multi-line box strings
		nodeStrip := lipgloss.JoinHorizontal(lipgloss.Top, rowParts...)
		stripLines := strings.Split(nodeStrip, "\n")
		outputLines = append(outputLines, stripLines...)

		// Vertical connector zone between this row and the next
		if rowIdx < maxGridRows-1 {
			connZone := buildConnZone(grid[rowIdx], grid[rowIdx+1])
			outputLines = append(outputLines, connZone...)
		}
	}

	// Edge legend
	arrowSt := lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B"))
	idToRole := make(map[string]string)
	for _, n := range state.Nodes { idToRole[n.ID] = n.Role }

	outputLines = append(outputLines, "")
	outputLines = append(outputLines, lipgloss.NewStyle().Foreground(lipgloss.Color("#6366F1")).Bold(true).Render("── CONNECTIONS ──"))
	for _, e := range state.Edges {
		if len(e) < 2 { continue }
		from := idToRole[e[0]]; if from == "" { from = e[0] }
		to   := idToRole[e[1]]; if to   == "" { to   = e[1] }
		outputLines = append(outputLines, fmt.Sprintf("  %s  %s  %s",
			lipgloss.NewStyle().Foreground(lipgloss.Color("#818CF8")).Render("["+from+"]"),
			arrowSt.Render("──▶"),
			lipgloss.NewStyle().Foreground(lipgloss.Color("#34D399")).Render("["+to+"]"),
		))
	}

	return strings.Join(outputLines, "\n")
}
