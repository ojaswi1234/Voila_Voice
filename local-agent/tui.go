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
		m.termWidth = msg.Width
		m.termHeight = msg.Height
		
		if !m.ready {
			m.vp = viewport.New(msg.Width, msg.Height)
			m.ready = true
		} else {
			m.vp.Width = msg.Width
			m.vp.Height = msg.Height
		}
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
				m.state = s
				m.vp.GotoBottom()
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

func (m tuiModel) View() string {
	if m.err != nil {
		return fmt.Sprintf("Error: %v\nPress q to quit.", m.err)
	}

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

	graphView := renderMeshGraph(m.state, nodeStyles, termW)

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

	content := lipgloss.JoinVertical(lipgloss.Left, header, graphView, logsView)
	
	if !m.ready {
		return content
	}
	m.vp.SetContent(content)
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

func renderMeshGraph(state LiveState, styles map[string]lipgloss.Style, termW int) string {
	if len(state.Nodes) == 0 {
		return "  Waiting for graph data..."
	}

	// ── Build index structures ─────────────────────────────────────────────
	nodeMap  := make(map[string]NodeLiveState)
	outEdges := make(map[string][]string)   // who I point to
	inEdges  := make(map[string][]string)   // who points to me
	edgeSet  := make(map[string]bool)       // "from->to" lookup
	bidir    := make(map[string]bool)       // "a<->b" (canonical a<b)

	for _, n := range state.Nodes {
		nodeMap[n.ID] = n
		outEdges[n.ID] = []string{}
		inEdges[n.ID] = []string{}
	}
	for _, e := range state.Edges {
		if len(e) < 2 { continue }
		a, b := e[0], e[1]
		edgeSet[a+"->"+b] = true
		outEdges[a] = append(outEdges[a], b)
		inEdges[b]  = append(inEdges[b], a)
	}
	for _, e := range state.Edges {
		if len(e) < 2 { continue }
		a, b := e[0], e[1]
		if edgeSet[b+"->"+a] { // bidirectional
			key := a + "<->" + b
			if a > b { key = b + "<->" + a }
			bidir[key] = true
		}
	}
	isBidir := func(a, b string) bool {
		key := a + "<->" + b
		if a > b { key = b + "<->" + a }
		return bidir[key]
	}

	// ── Classify edge "weight" ─────────────────────────────────────────────
	// Returns: "bidir" | "many" | "standard"
	edgeClass := func(from, to string) string {
		if isBidir(from, to) { return "bidir" }
		if len(outEdges[from]) > 1 || len(inEdges[to]) > 1 { return "many" }
		return "standard"
	}

	// ── Build 2D grid ─────────────────────────────────────────────────────
	maxCols := termW / colW
	if maxCols < 1 { maxCols = 1 }
	if maxCols > 5 { maxCols = 5 }

	minX, maxX, minY, maxY := 99999, -99999, 99999, -99999
	for _, n := range state.Nodes {
		if n.X < minX { minX = n.X }; if n.X > maxX { maxX = n.X }
		if n.Y < minY { minY = n.Y }; if n.Y > maxY { maxY = n.Y }
	}
	if maxX == minX { maxX = minX + 1 }
	if maxY == minY { maxY = minY + 1 }

	maxGridRows := 0
	gridPos := make(map[string][2]int)
	for _, n := range state.Nodes {
		normX := float64(n.X-minX) / float64(maxX-minX)
		normY := float64(n.Y-minY) / float64(maxY-minY)
		gc    := int(normX*float64(maxCols-1) + 0.5)
		gr    := int(normY*3 + 0.5)
		if gc >= maxCols { gc = maxCols - 1 }
		if gr > maxGridRows { maxGridRows = gr }
		gridPos[n.ID] = [2]int{gc, gr}
	}
	maxGridRows++

	grid := make([][]string, maxGridRows)
	for r := range grid { grid[r] = make([]string, maxCols) }
	for _, n := range state.Nodes {
		pos     := gridPos[n.ID]
		gc, gr  := pos[0], pos[1]
		for grid[gr][gc] != "" {
			gc++
			if gc >= maxCols {
				gc = 0
				gr++
				if gr >= len(grid) {
					grid = append(grid, make([]string, maxCols))
					maxGridRows = len(grid)
				}
			}
		}
		grid[gr][gc] = n.ID
		gridPos[n.ID] = [2]int{gc, gr}
	}

	// ── Node box renderer ──────────────────────────────────────────────────
	renderBox := func(n NodeLiveState) string {
		title := lipgloss.NewStyle().Bold(true).Render(n.Role)
		parts  := strings.SplitN(n.Model, "\n", 2)
		m1 := strings.TrimSpace(parts[0])
		m2 := ""
		if len(parts) > 1 { m2 = strings.TrimSpace(parts[1]) }
		if len(m1) > 26 { m1 = m1[:24] + ".." }
		ml := m1
		if m2 != "" { ml = m1 + "\n" + lipgloss.NewStyle().Faint(true).Italic(true).Render(m2) }
		content := fmt.Sprintf("%s\n%s\n[%s]", title, lipgloss.NewStyle().Faint(true).Render(ml), strings.ToUpper(n.Status))
		switch n.Status {
		case "running":   return styles["running"].Render(content)
		case "completed": return styles["completed"].Render(content)
		case "rejected":  return styles["rejected"].Render(content)
		default:          return styles["pending"].Render(content)
		}
	}

	// Nodes are typically 3 lines of text + 2 borders = 5 lines tall.
	// We want the horizontal arrows to shoot out perfectly aligned with the middle text (Model).
	boxH := 5
	midH := 2

	// Blank placeholder matching box height
	blank := func() string {
		rows := make([]string, boxH)
		for i := range rows { rows[i] = strings.Repeat(" ", nodeVisW) }
		return strings.Join(rows, "\n")
	}

	// ── Horizontal gap connector ───────────────────────────────────────────
	// Fills the hGap-wide, boxH-tall column between two nodes.
	// Draws styled arrow on mid line if edge exists.
	// If from→to (adjacent): standard/many/bidir arrow
	// If no direct edge: just spaces (non-adjacent handled via bypass zone)
	hConn := func(fromID, toID string) string {
		rows := make([]string, boxH)
		for i := range rows { rows[i] = strings.Repeat(" ", hGap) }

		if fromID == "" || toID == "" {
			return strings.Join(rows, "\n")
		}

		hasFwd := edgeSet[fromID+"->"+toID]
		hasRev := edgeSet[toID+"->"+fromID]
		if !hasFwd && !hasRev {
			return strings.Join(rows, "\n")
		}

		var arrow string
		cls := edgeClass(fromID, toID)
		if cls == "bidir" {
			arrow = "◀══▶════"
		} else if cls == "many" {
			if hasFwd {
				arrow = "───▷────"
			} else {
				arrow = "◁───────"
			}
		} else {
			if hasFwd {
				arrow = "───▶────"
			} else {
				arrow = "◀───────"
			}
		}
		if len([]rune(arrow)) > hGap { arrow = string([]rune(arrow)[:hGap]) }
		for len([]rune(arrow)) < hGap { arrow += "─" }

		rows[midH] = arrow
		// Add subtle routing lines above/below mid
		if midH > 0            { rows[midH-1] = strings.Repeat("·", hGap) }
		if midH < boxH-1       { rows[midH+1] = strings.Repeat("·", hGap) }

		return lipgloss.NewStyle().Foreground(lipgloss.Color("#22C55E")).Render(strings.Join(rows, "\n"))
	}

	// ── Rune canvas helper ─────────────────────────────────────────────────
	// Creates a plain-ASCII rune canvas of given width and height.
	type Canvas struct {
		data [][]rune
		w, h int
	}
	newCanvas := func(w, h int) *Canvas {
		data := make([][]rune, h)
		for i := range data {
			data[i] = []rune(strings.Repeat(" ", w))
		}
		return &Canvas{data: data, w: w, h: h}
	}
	setR := func(c *Canvas, x, y int, ch rune) {
		if y >= 0 && y < c.h && x >= 0 && x < c.w { c.data[y][x] = ch }
	}
	getString := func(c *Canvas) string {
		rows := make([]string, c.h)
		for i, r := range c.data { rows[i] = string(r) }
		return strings.Join(rows, "\n")
	}

	// ── Column center X on canvas ──────────────────────────────────────────
	centerX := func(col int) int { return col*colW + nodeVisW/2 }

	// ── Vertical connector zone (between grid rows) ────────────────────────
	buildVConn := func(rowAbove, rowBelow []string) string {
		stripW := maxCols*nodeVisW + (maxCols-1)*hGap + 2
		if stripW < 10 { stripW = 80 }
		
		vConnH_local := 5 // Force to 5 for Manhattan routing
		c := newCanvas(stripW, vConnH_local)

		busRow := 2

		for ca := 0; ca < maxCols; ca++ {
			fromID := rowAbove[ca]
			if fromID == "" { continue }
			fx := centerX(ca)

			for cb := 0; cb < maxCols; cb++ {
				toID := rowBelow[cb]
				if toID == "" { continue }
				hasFwd := edgeSet[fromID+"->"+toID]
				hasRev := edgeSet[toID+"->"+fromID]
				if !hasFwd && !hasRev { continue }
				
				tx := centerX(cb)

				if fx == tx {
					for li := 0; li < vConnH_local-1; li++ { setR(c, fx, li, '│') }
					if hasFwd { setR(c, fx, vConnH_local-1, '▼') }
					if hasRev { setR(c, fx, 0, '▲') }
				} else {
					// Manhattan routing
					// 1. Drop down to bus
					for li := 0; li < busRow; li++ { setR(c, fx, li, '│') }
					// 2. Horizontal bus
					lx, rx := fx, tx
					if lx > rx { lx, rx = rx, lx }
					for x := lx + 1; x < rx; x++ { setR(c, x, busRow, '─') }
					// 3. Drop from bus to target
					for li := busRow + 1; li < vConnH_local-1; li++ { setR(c, tx, li, '│') }
					
					// Corners
					if tx > fx {
						setR(c, fx, busRow, '╰')
						setR(c, tx, busRow, '╮')
					} else {
						setR(c, fx, busRow, '╯')
						setR(c, tx, busRow, '╭')
					}
					
					if hasFwd { setR(c, tx, vConnH_local-1, '▼') }
					if hasRev { setR(c, fx, 0, '▲') }
				}
			}
		}
		
		// Clean up intersections to make it look like a connected bus
		for y := 0; y < vConnH_local; y++ {
			for x := 0; x < stripW; x++ {
				if c.data[y][x] == '─' {
					hasUp := y > 0 && (c.data[y-1][x] == '│' || c.data[y-1][x] == '╰' || c.data[y-1][x] == '╯')
					hasDown := y < vConnH_local-1 && (c.data[y+1][x] == '│' || c.data[y+1][x] == '╭' || c.data[y+1][x] == '╮')
					if hasUp && hasDown { 
						setR(c, x, y, '┼')
					} else if hasUp { 
						setR(c, x, y, '┴')
					} else if hasDown { 
						setR(c, x, y, '┬')
					}
				}
			}
		}
		
		return lipgloss.NewStyle().Foreground(lipgloss.Color("#22C55E")).Render(getString(c))
	}

	// ── Bypass zone (below a row, for non-adjacent nodes in same row) ──────
	buildBypass := func(row []string) string {
		stripW := maxCols*nodeVisW + (maxCols-1)*hGap + 2
		if stripW < 10 { stripW = 80 }
		c := newCanvas(stripW, bypassH)

		// track already drawn pairs to avoid drawing a<->b twice
		drawn := make(map[string]bool)

		for ca := 0; ca < maxCols; ca++ {
			fromID := row[ca]
			if fromID == "" { continue }
			fx := centerX(ca)

			for cb := 0; cb < maxCols; cb++ {
				if cb == ca || cb == ca+1 || cb == ca-1 { continue } // skip self and adjacent
				toID := row[cb]
				if toID == "" { continue }
				
				hasFwd := edgeSet[fromID+"->"+toID]
				hasRev := edgeSet[toID+"->"+fromID]
				if !hasFwd && !hasRev { continue }
				
				pairKey := fromID + "|" + toID
				if fromID > toID { pairKey = toID + "|" + fromID }
				if drawn[pairKey] { continue }
				drawn[pairKey] = true
				
				tx := centerX(cb)

				cls := edgeClass(fromID, toID)

				// Corner at source side
				if tx > fx {
					setR(c, fx, 0, '╰')
					setR(c, tx, 0, '╮')
				} else {
					setR(c, fx, 0, '╯')
					setR(c, tx, 0, '╭')
				}

				// Horizontal run across line 0
				lx, rx := fx, tx
				if lx > rx { lx, rx = rx, lx }
				lineChar := '─'
				if cls == "bidir" { lineChar = '═' }
				if cls == "many"  { lineChar = '━' }
				for x := lx + 1; x < rx; x++ { setR(c, x, 0, lineChar) }

				// Arrowheads
				if hasFwd {
					if tx > fx { setR(c, tx-1, 0, '▶') } else { setR(c, tx+1, 0, '◀') }
				}
				if hasRev {
					if tx > fx { setR(c, fx+1, 0, '◀') } else { setR(c, fx-1, 0, '▶') }
				}
			}
		}
		return lipgloss.NewStyle().Foreground(lipgloss.Color("#22C55E")).Render(getString(c))
	}

	// ── Assemble complete graph ────────────────────────────────────────────
	var outLines []string

	for rowIdx := 0; rowIdx < maxGridRows; rowIdx++ {
		// Node strip
		var parts []string
		for colIdx := 0; colIdx < maxCols; colIdx++ {
			id := grid[rowIdx][colIdx]
			if id != "" {
				parts = append(parts, renderBox(nodeMap[id]))
			} else {
				parts = append(parts, blank())
			}
			if colIdx < maxCols-1 {
				parts = append(parts, hConn(grid[rowIdx][colIdx], grid[rowIdx][colIdx+1]))
			}
		}
		strip := lipgloss.JoinHorizontal(lipgloss.Top, parts...)
		outLines = append(outLines, strings.Split(strip, "\n")...)

		// Bypass zone (same-row non-adjacent connections routed below)
		bypassStr := buildBypass(grid[rowIdx])
		// Only add if non-empty (has real connections)
		if strings.ContainsAny(bypassStr, "╰╯╭╮─═━▶◀") {
			outLines = append(outLines, strings.Split(bypassStr, "\n")...)
		} else {
			outLines = append(outLines, "") // thin spacer
		}

		// Vertical connector zone
		if rowIdx < maxGridRows-1 {
			vconn := buildVConn(grid[rowIdx], grid[rowIdx+1])
			outLines = append(outLines, strings.Split(vconn, "\n")...)
		}
	}

	// ── Edge legend ────────────────────────────────────────────────────────
	outLines = append(outLines, "")
	outLines = append(outLines, lipgloss.NewStyle().Foreground(lipgloss.Color("#6366F1")).Bold(true).Render(
		"── CONNECTIONS  [══▶ many:many | ──▶ 1:1 | ─▷─ 1:many | ◀══▶ bidirectional] ──"))
	idToRole := make(map[string]string)
	for _, n := range state.Nodes { idToRole[n.ID] = n.Role }

	for _, e := range state.Edges {
		if len(e) < 2 { continue }
		from := idToRole[e[0]]; if from == "" { from = e[0] }
		to   := idToRole[e[1]]; if to   == "" { to   = e[1] }
		cls  := edgeClass(e[0], e[1])
		arrow := "──▶"
		if cls == "bidir" { arrow = "◀══▶" }
		if cls == "many"  { arrow = "──▷" }
		outLines = append(outLines, fmt.Sprintf("  %s  %s  %s",
			lipgloss.NewStyle().Foreground(lipgloss.Color("#818CF8")).Render("["+from+"]"),
			lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B")).Render(arrow),
			lipgloss.NewStyle().Foreground(lipgloss.Color("#34D399")).Render("["+to+"]"),
		))
	}

	return strings.Join(outLines, "\n")
}
