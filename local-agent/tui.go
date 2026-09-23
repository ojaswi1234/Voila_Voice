package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/viewport"
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
	vp         viewport.Model
	ready      bool
}

type graphifyTickMsg time.Time

func runGraphifyTUI() {
	vp := viewport.New(120, 40)
	vp.YPosition = 0
	
	p := tea.NewProgram(tuiModel{
		vp:         vp,
		ready:      true,
		termWidth:  120,
		termHeight: 40,
	}, tea.WithAltScreen(), tea.WithMouseCellMotion())
	if _, err := p.Run(); err != nil {
		fmt.Printf("Error: %v", err)
		os.Exit(1)
	}
}

func (m tuiModel) Init() tea.Cmd {
	return tickCmd()
}

func tickCmd() tea.Cmd {
	return tea.Tick(time.Millisecond*200, func(t time.Time) tea.Msg {
		return graphifyTickMsg(t)
	})
}

func (m tuiModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var (
		cmd  tea.Cmd
		cmds []tea.Cmd
	)

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		if msg.Width == 0 || msg.Height == 0 {
			return m, nil
		}
		m.termWidth = msg.Width
		m.termHeight = msg.Height
		
		if !m.ready {
			m.vp = viewport.New(msg.Width, msg.Height)
			m.ready = true
		} else {
			m.vp.Width = msg.Width
			m.vp.Height = msg.Height
		}
		m.vp.SetContent(m.generateContent())
		return m, nil
	case tea.KeyMsg:
		if msg.String() == "k" {
			go func() {
				connData, err := loadConnectionData()
				if err == nil && connData.SecurityPhrase != "" {
					secret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
					req, _ := http.NewRequest("POST", "http://127.0.0.1:8080/stop", nil)
					req.Header.Set("X-Exec-Secret", secret)
					(&http.Client{Timeout: 2 * time.Second}).Do(req)
				}
			}()
			m.state.ErrorMsg = "FORCE KILLED BY USER"
			m.state.Status = "error"
			return m, nil
		}
		if msg.String() == "q" || msg.String() == "ctrl+c" || msg.String() == "esc" {
			return m, tea.Quit
		}
	case graphifyTickMsg:
		data, err := os.ReadFile("graphify_live.json")
		if err == nil {
			var s LiveState
			if err2 := json.Unmarshal(data, &s); err2 == nil {
				wasAtBottom := m.vp.AtBottom()
				m.state = s
				m.vp.SetContent(m.generateContent())
				if wasAtBottom {
					m.vp.GotoBottom()
				}
			}
		}
		return m, tickCmd()
	}
	
	if m.ready {
		m.vp, cmd = m.vp.Update(msg)
		cmds = append(cmds, cmd)
	}
	
	return m, tea.Batch(cmds...)
}

func (m tuiModel) generateContent() string {
	titleStyle    := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#10B981")).MarginBottom(1)
	pendingStyle  := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#4B5563")).Padding(0, 1).Foreground(lipgloss.Color("#9CA3AF")).Width(30)
	runningStyle  := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#F59E0B")).Padding(0, 1).Foreground(lipgloss.Color("#FCD34D")).Width(30)
	completedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#10B981")).Padding(0, 1).Foreground(lipgloss.Color("#34D399")).Width(30)
	rejectedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#EF4444")).Padding(0, 1).Foreground(lipgloss.Color("#FCA5A5")).Width(30)

	header := titleStyle.Render("🤖 VOILA GRAPHIFY : LIVE TEAM TRACKER")
	switch m.state.Status {
	case "done":
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#10B981")).Render(" [FINISHED - Press 'q' to exit]")
	case "error":
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render(" [ERROR - Press 'q' to exit]")
	default:
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B")).Render(" [RUNNING... (Press 'k' to KILL)]")
	}

	nodeStyles := map[string]lipgloss.Style{
		"pending": pendingStyle, "running": runningStyle,
		"completed": completedStyle, "rejected": rejectedStyle,
	}
	termW := m.termWidth
	if termW < 80 { termW = 120 }

	graphView := renderMeshGraph(m.state, nodeStyles, termW, m.termHeight)

	nameStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#8B5CF6")).MarginTop(1)
	msgStyle  := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).PaddingLeft(2)
	toolStyle := lipgloss.NewStyle().Faint(true).Foreground(lipgloss.Color("#10B981")).PaddingLeft(2)
	sysStyle  := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#FFFFFF")).Background(lipgloss.Color("#EF4444")).Padding(0, 2).MarginTop(1)

	var logLines []string
	for _, l := range m.state.Logs {
		l = strings.ReplaceAll(l, "**", "")
		l = strings.ReplaceAll(l, "🔎", "")
		if strings.HasPrefix(l, "[SYSTEM]:") {
			logLines = append(logLines, sysStyle.Render(l))
		} else if strings.HasPrefix(l, "[") && strings.Contains(l, "]:") {
			idx := strings.Index(l, "]:")
			logLines = append(logLines, nameStyle.Render("✦ "+l[1:idx]))
			if p := strings.TrimSpace(l[idx+2:]); p != "" {
				logLines = append(logLines, msgStyle.Render(p))
			}
		} else if strings.HasPrefix(strings.TrimSpace(l), ">") {
			logLines = append(logLines, toolStyle.Render(l))
		} else {
			logLines = append(logLines, msgStyle.Render(l))
		}
	}
	logs := strings.Join(logLines, "\n")
	if m.state.ErrorMsg != "" {
		logs += "\n" + lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render("FATAL ERROR: "+m.state.ErrorMsg)
	}
	logsView := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).MarginTop(1).Render(logs)

	return header + "\n" + graphView + "\n" + logsView
}

func (m tuiModel) View() string {
	if m.err != nil {
		return fmt.Sprintf("Error: %v\nPress q to quit.", m.err)
	}
	if !m.ready {
		return "Initializing..."
	}
	return m.vp.View()
}

// ─────────────────────────────────────────────────────────────────────────────
// MESH GRAPH RENDERER — Pure 2D grid with rich ASCII connector art
//
// Layout: nodes placed in a 2D grid based on their (x,y) coordinates.
// Connections rendered as ASCII art WITHOUT overlapping node boxes:
//
//   • Same-row adjacent nodes:  connector in the gap between boxes
//   • Same-row non-adjacent:    bypass U-arc routed BELOW the row
//   • Cross-row same-col:       vertical line in connector zone
//   • Cross-row diagonal:       diagonal line in connector zone
//   • Bidirectional (A↔B):      ◀══▶  (double thick)
//   • Many:Many fanout/fanin:   ──▷   (open arrowhead)
//   • 1:1 simple:               ──▶   (solid arrowhead)
//   • Curved corners:           ╭╮╰╯  on bends and bypasses
// ─────────────────────────────────────────────────────────────────────────────

const (
	nodeVisW = 32 // visual width of node box (matches Width(30) + 2 border)
	hGap     = 8  // horizontal gap chars between nodes
	colW     = 40 // nodeVisW + hGap
	vConnH   = 4  // vertical connector zone height (lines between grid rows)
	bypassH  = 2  // bypass arc height (for same-row non-adjacent connections)
)

func renderMeshGraph(state LiveState, styles map[string]lipgloss.Style, termW int, termH int) string {
	if len(state.Nodes) == 0 {
		return "  Waiting for graph data..."
	}

	maxStrLen := 16
	for _, n := range state.Nodes {
		if len(n.Role) > maxStrLen { maxStrLen = len(n.Role) }
		parts := strings.SplitN(n.Model, "\n", 2)
		m1 := strings.TrimSpace(parts[0])
		if len(m1) > maxStrLen { maxStrLen = len(m1) }
	}
	
	nodeVisW := maxStrLen + 4 // padding + borders
	if nodeVisW > 46 { nodeVisW = 46 } // hard cap
	
	mode := "FULL"
	if len(state.Nodes) > 12 || termW < 90 {
		mode = "NANO"
		nodeVisW = 16
		if maxStrLen+2 > 16 && maxStrLen+2 < 30 { nodeVisW = maxStrLen+2 }
	} else if len(state.Nodes) > 6 || termW < 130 {
		mode = "COMPACT"
		if nodeVisW > 32 { nodeVisW = 32 }
	}

	hGap := 6
	colW := nodeVisW + hGap
	boxH := 5
	if mode == "NANO" { boxH = 3 }
	if mode == "COMPACT" { boxH = 5 }

	vGap := 6 
	topMargin := 2
	
	type NodeRect struct {
		X, Y, W, H int
		ID string
		Rendered []string
	}
	
	nodeMap := make(map[string]NodeLiveState)
	for _, n := range state.Nodes { nodeMap[n.ID] = n }

	// 1. Calculate Ranks (Levels) using BFS ignoring reverse edges
	inDegree := make(map[string]int)
	adj := make(map[string][]string)
	
	edgeMap := make(map[string]bool)
	bidirMap := make(map[string]bool)
	for _, e := range state.Edges {
		if len(e) >= 2 { 
			forward := e[0]+"->"+e[1]
			backward := e[1]+"->"+e[0]
			if edgeMap[backward] {
				bidirMap[forward] = true
				bidirMap[backward] = true
			} else {
				edgeMap[forward] = true 
			}
		}
	}

	for _, n := range state.Nodes {
		inDegree[n.ID] = 0
	}
	for srcToDst := range edgeMap {
		parts := strings.Split(srcToDst, "->")
		src, dst := parts[0], parts[1]
		if bidirMap[srcToDst] && src > dst { 
			continue 
		}
		adj[src] = append(adj[src], dst)
		inDegree[dst]++
	}
	
	levelMap := make(map[string]int)
	var queue []string
	for id, deg := range inDegree {
		if deg == 0 {
			queue = append(queue, id)
			levelMap[id] = 0
		}
	}
	
	if len(queue) == 0 && len(state.Nodes) > 0 {
		queue = append(queue, state.Nodes[0].ID)
		levelMap[state.Nodes[0].ID] = 0
	}
	
	maxLevel := 0
	for len(queue) > 0 {
		curr := queue[0]
		queue = queue[1:]
		currLevel := levelMap[curr]
		if currLevel > maxLevel { maxLevel = currLevel }
		
		for _, neighbor := range adj[curr] {
			if currLevel+1 > levelMap[neighbor] {
				levelMap[neighbor] = currLevel + 1
			}
			inDegree[neighbor]--
			if inDegree[neighbor] == 0 {
				queue = append(queue, neighbor)
			}
		}
	}

	// Recalculate maxLevel in case cycle/unvisited nodes pushed a level beyond queue max
	maxLevel = 0
	for _, lvl := range levelMap {
		if lvl > maxLevel {
			maxLevel = lvl
		}
	}

	levelNodes := make([][]string, maxLevel+1)
	for _, n := range state.Nodes {
		lvl, ok := levelMap[n.ID]
		if !ok { lvl = 0 }
		levelNodes[lvl] = append(levelNodes[lvl], n.ID)
	}

	maxNodesInLevel := 0
	for _, nodes := range levelNodes {
		if len(nodes) > maxNodesInLevel { maxNodesInLevel = len(nodes) }
	}
	
	if maxNodesInLevel * colW > termW {
		mode = "NANO"
		nodeVisW = 16
		boxH = 3
		colW = nodeVisW + hGap
	}
	
	canvasW := maxNodesInLevel * colW
	if canvasW < termW-4 { canvasW = termW-4 } 
	canvasH := topMargin + len(levelNodes) * (boxH + vGap)
	
	rects := make(map[string]*NodeRect)
	
	for lvl, nodes := range levelNodes {
		levelW := len(nodes) * colW
		startX := (canvasW - levelW) / 2
		if startX < 0 { startX = 0 }
		
		for i, id := range nodes {
			n := nodeMap[id]
			rect := &NodeRect{
				ID: n.ID,
				W: nodeVisW,
				H: boxH,
				X: startX + i*colW,
				Y: topMargin + lvl*(boxH + vGap),
			}
			
			title := n.Role
			if title == "" { title = "Unknown" }
			
			var content string
			if mode == "FULL" || mode == "COMPACT" {
				maxT := nodeVisW - 4
				if len(title) > maxT { title = title[:maxT-3] + "..." }
				tStr := lipgloss.NewStyle().Bold(true).Render(title)
				parts  := strings.Split(n.Model, "\n")
				m1 := strings.TrimSpace(parts[0])
				if len(parts) > 1 {
				    m1 += " " + strings.TrimSpace(parts[1])
				}
				if len(m1) > maxT { m1 = m1[:maxT-3] + "..." }
				content = fmt.Sprintf("%s\n%s\n[%s]", tStr, lipgloss.NewStyle().Faint(true).Render(m1), strings.ToUpper(n.Status))
			} else {
				maxT := nodeVisW - 2
				if len(title) > maxT { title = title[:maxT-3] + "..." }
				content = lipgloss.NewStyle().Bold(true).Render(title)
			}
			
			st, ok := styles[n.Status]
			if !ok { st = styles["pending"] }
			
			var renderedBox string
			if mode == "NANO" {
				c := ""
				if n.Status == "completed" { c = "#10B981" } else if n.Status == "running" { c = "#F59E0B" } else if n.Status == "error" { c = "#EF4444" } else { c = "#9CA3AF" }
				renderedBox = lipgloss.NewStyle().Background(lipgloss.Color(c)).Foreground(lipgloss.Color("#000000")).Padding(0, 1).Width(nodeVisW).Render(content)
			} else {
				renderedBox = st.Copy().Width(nodeVisW-2).Render(content)
			}
			
			rect.Rendered = strings.Split(renderedBox, "\n")
			rect.H = len(rect.Rendered) 
			rects[n.ID] = rect
		}
	}
	
	canvas := make([][]rune, canvasH)
	for i := range canvas {
		canvas[i] = make([]rune, canvasW)
		for j := range canvas[i] { canvas[i][j] = ' ' }
	}
	
	setR := func(x, y int, r rune) {
		if y >= 0 && y < canvasH && x >= 0 && x < canvasW {
			canvas[y][x] = r
		}
	}

	nodeIndex := make(map[string]int)
	for i, n := range state.Nodes { nodeIndex[n.ID] = i }

	processedEdges := make(map[string]bool)

	for srcToDst := range edgeMap {
		parts := strings.Split(srcToDst, "->")
		src, dst := parts[0], parts[1]
		
		if bidirMap[srcToDst] {
			if processedEdges[dst+"->"+src] { continue }
			processedEdges[srcToDst] = true
		}
		
		rSrc, ok1 := rects[src]
		rDst, ok2 := rects[dst]
		if !ok1 || !ok2 { continue }
		
		fx := rSrc.X + rSrc.W/2
		fy := rSrc.Y + rSrc.H
		
		tx := rDst.X + rDst.W/2
		ty := rDst.Y - 1 
		
		busOffset := (nodeIndex[dst] % (vGap - 2)) + 1
		busY := rSrc.Y + rSrc.H + busOffset
		if busY >= rDst.Y {
			busY = rDst.Y - 1
		}
		
		if rDst.Y > rSrc.Y {
			for y := fy; y < busY; y++ { 
				if canvas[y][fx] == ' ' || canvas[y][fx] == '─' { setR(fx, y, '│') }
			}
			setR(fx, busY, '│') 
			
			lx, rx := fx, tx
			if lx > rx { lx, rx = rx, lx }
			for x := lx + 1; x < rx; x++ { 
				if canvas[busY][x] == ' ' || canvas[busY][x] == '│' { setR(x, busY, '─') }
			}
			
			for y := busY; y < ty; y++ {
				if canvas[y][tx] == ' ' || canvas[y][tx] == '─' { setR(tx, y, '│') }
			}
			setR(tx, ty, '│')
			
			if fx != tx {
				if tx > fx { setR(fx, busY, '╰'); setR(tx, busY, '╮') } 
				if tx < fx { setR(fx, busY, '╯'); setR(tx, busY, '╭') } 
			}
			setR(tx, ty, '▼')
			
			if bidirMap[srcToDst] {
				setR(fx, fy, '▲')
				label := []rune(" <==> ")
				midX := lx + (rx - lx)/2 - len(label)/2
				if midX > lx && midX+len(label) < rx {
					for i, r := range label { setR(midX+i, busY, r) }
				}
			}
		}
	}

	for y := 0; y < canvasH; y++ {
		for x := 0; x < canvasW; x++ {
			curr := canvas[y][x]
			if curr == '─' || curr == '│' || curr == '╮' || curr == '╭' || curr == '╰' || curr == '╯' {
				hasUp := y > 0 && (canvas[y-1][x] == '│' || canvas[y-1][x] == '┼' || canvas[y-1][x] == '┴' || canvas[y-1][x] == '┬' || canvas[y-1][x] == '╰' || canvas[y-1][x] == '╯' || canvas[y-1][x] == '▲' || canvas[y-1][x] == '▼')
				hasDown := y < canvasH-1 && (canvas[y+1][x] == '│' || canvas[y+1][x] == '┼' || canvas[y+1][x] == '┴' || canvas[y+1][x] == '┬' || canvas[y+1][x] == '╭' || canvas[y+1][x] == '╮' || canvas[y+1][x] == '▲' || canvas[y+1][x] == '▼')
				hasLeft := x > 0 && (canvas[y][x-1] == '─' || canvas[y][x-1] == '┼' || canvas[y][x-1] == '┴' || canvas[y][x-1] == '┬' || canvas[y][x-1] == '╭' || canvas[y][x-1] == '╰' || canvas[y][x-1] == '=' || canvas[y][x-1] == '<')
				hasRight := x < canvasW-1 && (canvas[y][x+1] == '─' || canvas[y][x+1] == '┼' || canvas[y][x+1] == '┴' || canvas[y][x+1] == '┬' || canvas[y][x+1] == '╮' || canvas[y][x+1] == '╯' || canvas[y][x+1] == '=' || canvas[y][x+1] == '>')
				
				if hasUp && hasDown && hasLeft && hasRight { setR(x, y, '┼')
				} else if hasUp && hasDown && hasLeft { setR(x, y, '┤')
				} else if hasUp && hasDown && hasRight { setR(x, y, '├')
				} else if hasLeft && hasRight && hasUp { setR(x, y, '┴')
				} else if hasLeft && hasRight && hasDown { setR(x, y, '┬')
				} else if hasUp && hasDown { setR(x, y, '│')
				} else if hasLeft && hasRight { setR(x, y, '─')
				} else if hasUp && hasRight { setR(x, y, '╰')
				} else if hasUp && hasLeft { setR(x, y, '╯')
				} else if hasDown && hasRight { setR(x, y, '╭')
				} else if hasDown && hasLeft { setR(x, y, '╮')
				}
			}
		}
	}

	type Cell struct {
		Char string 
		W    int    
		Color string
	}

	cells := make([][]Cell, canvasH)
	for y := 0; y < canvasH; y++ {
		cells[y] = make([]Cell, canvasW)
		for x := 0; x < canvasW; x++ {
			cells[y][x] = Cell{Char: string(canvas[y][x]), W: 1, Color: "#10B981"}
		}
	}
	
	for _, rect := range rects {
		for i, lineStr := range rect.Rendered {
			y := rect.Y + i
			x := rect.X
			if y >= 0 && y < canvasH && x >= 0 && x < canvasW {
				cells[y][x] = Cell{Char: lineStr, W: rect.W, Color: ""}
				for dx := 1; dx < rect.W; dx++ {
					if x+dx < canvasW {
						cells[y][x+dx] = Cell{Char: "", W: 0, Color: ""}
					}
				}
			}
		}
	}

	var sb strings.Builder
	for y := 0; y < canvasH; y++ {
		for x := 0; x < canvasW; x++ {
			c := cells[y][x]
			if c.W == 0 { continue }
			if c.Color != "" {
				if c.Char == " " {
					sb.WriteString(c.Char)
				} else {
					sb.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color(c.Color)).Render(c.Char))
				}
			} else {
				sb.WriteString(c.Char)
			}
		}
		sb.WriteString("\n")
	}

	return sb.String()
}
