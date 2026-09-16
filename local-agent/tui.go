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

	return lipgloss.JoinVertical(lipgloss.Left, header, graphView, logsView)
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

	mode := "FULL"
	if len(state.Nodes) > 12 || termW < 90 {
		mode = "NANO"
	} else if len(state.Nodes) > 6 || termW < 130 {
		mode = "COMPACT"
	}

	nodeVisW := 32
	if mode == "COMPACT" { nodeVisW = 24 }
	if mode == "NANO" { nodeVisW = 16 }
	
	boxH := 5
	if mode == "NANO" { boxH = 3 }
	if mode == "COMPACT" { boxH = 4 }

	type NodeRect struct {
		X, Y, W, H int
		ID string
		Rendered []string
	}
	
	nodeMap := make(map[string]NodeLiveState)
	for _, n := range state.Nodes { nodeMap[n.ID] = n }

	// Spatial Layout scaling
	maxX, maxY := 1, 1
	for _, n := range state.Nodes {
		if n.X > maxX { maxX = n.X }
		if n.Y > maxY { maxY = n.Y }
	}
	if maxX < 100 { maxX = 800 }
	if maxY < 100 { maxY = 500 }
	
	canvasW := termW - 4
	if canvasW < 40 { canvasW = 80 }
	
	// Default target height for graph portion is termH - 12 (to leave space for logs)
	canvasH := termH - 12
	if canvasH < 20 { canvasH = 20 }
	
	// Add some margins so boxes don't get clipped
	usableW := canvasW - nodeVisW - 2
	usableH := canvasH - boxH - 2
	if usableW < 10 { usableW = 10 }
	if usableH < 10 { usableH = 10 }

	rects := make(map[string]*NodeRect)
	for _, n := range state.Nodes {
		// Map from LLM coordinates to canvas coordinates
		cx := int((float64(n.X) / float64(maxX)) * float64(usableW))
		cy := int((float64(n.Y) / float64(maxY)) * float64(usableH)) + 1
		
		rect := &NodeRect{
			ID: n.ID,
			W: nodeVisW,
			H: boxH,
			X: cx,
			Y: cy,
		}
		
		title := n.Role
		if title == "" { title = "Unknown" }
		
		var content string
		if mode == "FULL" {
			if len(title) > 28 { title = title[:25] + "..." }
			tStr := lipgloss.NewStyle().Bold(true).Render(title)
			parts  := strings.SplitN(n.Model, "\n", 2)
			m1 := strings.TrimSpace(parts[0])
			if len(m1) > 28 { m1 = m1[:25] + "..." }
			content = fmt.Sprintf("%s\n%s\n[%s]", tStr, lipgloss.NewStyle().Faint(true).Render(m1), strings.ToUpper(n.Status))
		} else if mode == "COMPACT" {
			if len(title) > 20 { title = title[:17] + "..." }
			tStr := lipgloss.NewStyle().Bold(true).Render(title)
			content = fmt.Sprintf("%s\n[%s]", tStr, strings.ToUpper(n.Status))
		} else {
			if len(title) > 14 { title = title[:11] + "..." }
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
	
	// Detect bidirectional edges
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

	nodeIndex := make(map[string]int)
	for i, n := range state.Nodes { nodeIndex[n.ID] = i }

	processedEdges := make(map[string]bool)

	for srcToDst := range edgeMap {
		parts := strings.Split(srcToDst, "->")
		src, dst := parts[0], parts[1]
		
		// If bidirectional, only draw once
		if bidirMap[srcToDst] {
			if processedEdges[dst+"->"+src] { continue }
			processedEdges[srcToDst] = true
		}
		
		rSrc, ok1 := rects[src]
		rDst, ok2 := rects[dst]
		if !ok1 || !ok2 { continue }
		
		// Determine best exit/entry points based on relative position
		fx := rSrc.X + rSrc.W/2
		fy := rSrc.Y + rSrc.H // exit bottom
		tx := rDst.X + rDst.W/2
		ty := rDst.Y - 1 // enter top
		
		if rDst.Y < rSrc.Y {
			// Destination is above Source
			fy = rSrc.Y - 1 // exit top
			ty = rDst.Y + rDst.H // enter bottom
		}
		
		// Spatial Bus Offset to prevent overlaps
		busOffset := (nodeIndex[src] % 3) + 1
		busY := fy + busOffset
		if rDst.Y < rSrc.Y {
			busY = fy - busOffset
		}
		
		// Draw vertical from source to bus
		dir := 1
		if fy > busY { dir = -1 }
		for y := fy; y != busY; y += dir { 
			if y >= 0 && y < canvasH && (canvas[y][fx] == ' ' || canvas[y][fx] == '─') { setR(fx, y, '│') }
		}
		setR(fx, busY, '│')
		
		// Draw horizontal bus
		lx, rx := fx, tx
		if lx > rx { lx, rx = rx, lx }
		for x := lx + 1; x < rx; x++ { 
			if busY >= 0 && busY < canvasH && (canvas[busY][x] == ' ' || canvas[busY][x] == '│') { setR(x, busY, '─') }
		}
		
		// Draw vertical from bus to target
		dir = 1
		if busY > ty { dir = -1 }
		for y := busY; y != ty; y += dir {
			if y >= 0 && y < canvasH && (canvas[y][tx] == ' ' || canvas[y][tx] == '─') { setR(tx, y, '│') }
		}
		setR(tx, ty, '│')
		
		// Clean corners
		if fx != tx {
			if fy < busY && tx > fx { setR(fx, busY, '╰'); setR(tx, busY, '╮') } 
			if fy < busY && tx < fx { setR(fx, busY, '╯'); setR(tx, busY, '╭') } 
			if fy > busY && tx > fx { setR(fx, busY, '╭'); setR(tx, busY, '╯') } 
			if fy > busY && tx < fx { setR(fx, busY, '╮'); setR(tx, busY, '╰') } 
		}
		
		// Draw Arrowheads
		if ty >= busY { setR(tx, ty, '▼') } else { setR(tx, ty, '▲') }
		
		if bidirMap[srcToDst] {
			// Draw reverse arrowhead at source
			if fy < busY { setR(fx, fy, '▲') } else { setR(fx, fy, '▼') }
			
			// Optional: Draw text label on the bus line
			label := []rune(" <==> ")
			midX := lx + (rx - lx)/2 - len(label)/2
			if midX > lx && midX+len(label) < rx {
				for i, r := range label { setR(midX+i, busY, r) }
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
