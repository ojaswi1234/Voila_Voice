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
	Status   string          `json:"status"` // "running", "done", "error"
	Nodes    []NodeLiveState `json:"nodes"`
	Edges    [][]string      `json:"edges"`  // e.g. [["node1","node2"],["node1","node3"]]
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
	state     LiveState
	err       error
	termWidth int
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
	
	pendingStyle   := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#4B5563")).Padding(0, 1).Foreground(lipgloss.Color("#9CA3AF")).Width(38)
	runningStyle   := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#F59E0B")).Padding(0, 1).Foreground(lipgloss.Color("#FCD34D")).Width(38)
	completedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#10B981")).Padding(0, 1).Foreground(lipgloss.Color("#34D399")).Width(38)
	rejectedStyle  := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#EF4444")).Padding(0, 1).Foreground(lipgloss.Color("#FCA5A5")).Width(38)

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

	teamView := renderSpatialGraph(m, nodeStyles)
	connectionsView := "" // Replaced by true 2D edges in canvas


	// Render logs
	var formattedLogs []string
	
	// Discord-like styling
	nameStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#8B5CF6")).MarginTop(1) // Purple discord-ish names
	msgStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).PaddingLeft(2) // Indented text
	toolStyle := lipgloss.NewStyle().Faint(true).Foreground(lipgloss.Color("#10B981")).PaddingLeft(2) // Green for tools
	sysStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#FFFFFF")).Background(lipgloss.Color("#EF4444")).Padding(0, 2).MarginTop(1)

	for _, l := range m.state.Logs {
		l = strings.ReplaceAll(l, "**", "")
		l = strings.ReplaceAll(l, "🔎", "")
		if strings.HasPrefix(l, "[SYSTEM]:") {
			formattedLogs = append(formattedLogs, sysStyle.Render(l))
		} else if strings.HasPrefix(l, "[") && strings.Contains(l, "]:") {
			idx := strings.Index(l, "]:")
			roleName := l[1:idx]
			msgPart := l[idx+2:]
			
			// Name on one line, message indented below
			formattedLogs = append(formattedLogs, nameStyle.Render("✦ "+roleName))
			if strings.TrimSpace(msgPart) != "" {
				formattedLogs = append(formattedLogs, msgStyle.Render(msgPart))
			}
		} else if strings.HasPrefix(strings.TrimSpace(l), "> Executed tool:") || strings.HasPrefix(strings.TrimSpace(l), ">") {
			formattedLogs = append(formattedLogs, toolStyle.Render(l))
		} else {
			// Continuation line
			formattedLogs = append(formattedLogs, msgStyle.Render(l))
		}
	}
	
	logs := strings.Join(formattedLogs, "\n")
	if m.state.ErrorMsg != "" {
		logs += "\n" + lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render("FATAL ERROR: "+m.state.ErrorMsg)
	}
	logsView := logStyle.Render(logs)

	return lipgloss.JoinVertical(lipgloss.Left, header, teamView, connectionsView, logsView)
}



// ── 2D GRAPH RENDERER ───────────────────────────────────────────────────────
func renderSpatialGraph(m tuiModel, nodeStyles map[string]lipgloss.Style) string {
	state := m.state
	if len(state.Nodes) == 0 {
		return "Loading graph..."
	}

	termW := m.termWidth
	if termW < 80 { termW = 80 }
	termH := m.termHeight
	if termH < 20 { termH = 30 }

	canvasW := termW
	canvasH := termH - 18 // Reserve space for header and logs
	if canvasH < 15 { canvasH = 15 }

	// Normalize X,Y bounds
	minX, maxX, minY, maxY := 99999, -99999, 99999, -99999
	for _, n := range state.Nodes {
		if n.X < minX { minX = n.X }
		if n.X > maxX { maxX = n.X }
		if n.Y < minY { minY = n.Y }
		if n.Y > maxY { maxY = n.Y }
	}
	if maxX-minX < 10 { maxX = minX + 100 }
	if maxY-minY < 10 { maxY = minY + 100 }

	nodeW, nodeH := 38, 5

	// Create 2D canvas of runes (blank spaces)
	canvas := make([][]rune, canvasH)
	for r := 0; r < canvasH; r++ {
		canvas[r] = make([]rune, canvasW)
		for c := 0; c < canvasW; c++ {
			canvas[r][c] = ' '
		}
	}

	// Map node ID to canvas coordinates (center of box)
	type Coord struct { x, y int }
	positions := make(map[string]Coord)

	for _, n := range state.Nodes {
		// Normalize to 0-1
		normX := float64(n.X-minX) / float64(maxX-minX)
		normY := float64(n.Y-minY) / float64(maxY-minY)

		// Map to canvas (leaving margin for box width/height)
		cx := int(normX * float64(canvasW-nodeW-4)) + (nodeW/2) + 2
		cy := int(normY * float64(canvasH-nodeH-2)) + (nodeH/2) + 1
		
		positions[n.ID] = Coord{x: cx, y: cy}
	}

	// Draw Edges using Bresenham's line algorithm
	for _, edge := range state.Edges {
		if len(edge) < 2 { continue }
		p1, ok1 := positions[edge[0]]
		p2, ok2 := positions[edge[1]]
		if !ok1 || !ok2 { continue }

		x0, y0 := p1.x, p1.y
		x1, y1 := p2.x, p2.y
		
		dx := x1 - x0
		if dx < 0 { dx = -dx }
		dy := y1 - y0
		if dy < 0 { dy = -dy }
		
		sx := 1
		if x0 > x1 { sx = -1 }
		sy := 1
		if y0 > y1 { sy = -1 }
		
		err := dx - dy
		
		for {
			if y0 >= 0 && y0 < canvasH && x0 >= 0 && x0 < canvasW {
				// Use arrows based on direction
				ch := '·'
				if sx > 0 && sy == 0 { ch = '─' }
				if sx < 0 && sy == 0 { ch = '─' }
				if sx == 0 && sy > 0 { ch = '│' }
				if sx == 0 && sy < 0 { ch = '│' }
				if sx > 0 && sy > 0 { ch = '╲' }
				if sx < 0 && sy < 0 { ch = '╲' }
				if sx > 0 && sy < 0 { ch = '╱' }
				if sx < 0 && sy > 0 { ch = '╱' }
				canvas[y0][x0] = ch
			}
			if x0 == x1 && y0 == y1 { break }
			e2 := 2 * err
			if e2 > -dy {
				err -= dy
				x0 += sx
			}
			if e2 < dx {
				err += dx
				y0 += sy
			}
		}
		// Draw Arrow head at target
		if y1 >= 0 && y1 < canvasH && x1 >= 0 && x1 < canvasW {
			canvas[y1][x1] = '▶'
			if sx < 0 { canvas[y1][x1] = '◀' }
			if sy > 0 && sx == 0 { canvas[y1][x1] = '▼' }
			if sy < 0 && sx == 0 { canvas[y1][x1] = '▲' }
		}
	}

	// Now we construct the lines as string arrays to prevent ANSI length corruption
	stringCanvas := make([][][]string, canvasH)
	for r := 0; r < canvasH; r++ {
		stringCanvas[r] = make([][]string, canvasW)
		for c := 0; c < canvasW; c++ {
			stringCanvas[r][c] = []string{string(canvas[r][c])}
		}
	}

	// Now embed the styled boxes at their coordinates
	// Sort nodes by Z-index or just render them
	for _, n := range state.Nodes {
		pos := positions[n.ID]
		left := pos.x - (nodeW/2)
		top := pos.y - (nodeH/2)

		// Generate the lipgloss box
		title := lipgloss.NewStyle().Bold(true).Render(n.Role)
		modelParts := strings.SplitN(n.Model, "\n", 2)
		modelLine1 := strings.TrimSpace(modelParts[0])
		modelLine2 := ""
		if len(modelParts) > 1 { modelLine2 = strings.TrimSpace(modelParts[1]) }
		if len(modelLine1) > 34 { modelLine1 = modelLine1[:32] + ".." }
		
		modelLabel := modelLine1
		if modelLine2 != "" { modelLabel = modelLine1 + "\n" + lipgloss.NewStyle().Faint(true).Italic(true).Render(modelLine2) }
		sub := lipgloss.NewStyle().Faint(true).Render(modelLabel)
		
		content := fmt.Sprintf("%s\n%s\n[%s]", title, sub, strings.ToUpper(n.Status))
		
		var box string
		switch n.Status {
		case "running":   box = nodeStyles["running"].Render(content)
		case "completed": box = nodeStyles["completed"].Render(content)
		case "rejected":  box = nodeStyles["rejected"].Render(content)
		default:          box = nodeStyles["pending"].Render(content)
		}

		boxLines := strings.Split(box, "\n")
		for r, bline := range boxLines {
			rIdx := top + r
			if rIdx >= 0 && rIdx < canvasH {
				blineWidth := lipgloss.Width(bline)
				if left >= 0 && left < canvasW {
					stringCanvas[rIdx][left] = []string{bline}
					// Clear the cells visually occluded by this box
					for i := 1; i < blineWidth; i++ {
						if left+i < canvasW {
							stringCanvas[rIdx][left+i] = []string{""}
						}
					}
				}
			}
		}
	}

	var finalLines []string
	for r := 0; r < canvasH; r++ {
		var rowStr string
		for c := 0; c < canvasW; c++ {
			if len(stringCanvas[r][c]) > 0 {
				rowStr += stringCanvas[r][c][0]
			}
		}
		finalLines = append(finalLines, rowStr)
	}

	return strings.Join(finalLines, "\n")
}
