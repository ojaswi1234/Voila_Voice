import sys

code = """
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

	// Now we construct the lines as strings
	lines := make([]string, canvasH)
	for r := 0; r < canvasH; r++ {
		lines[r] = string(canvas[r])
	}

	// Now embed the styled boxes at their coordinates
	for _, n := range state.Nodes {
		pos := positions[n.ID]
		left := pos.x - (nodeW/2)
		top := pos.y - (nodeH/2)

		// Generate the lipgloss box
		title := lipgloss.NewStyle().Bold(true).Render(n.Role)
		modelParts := strings.SplitN(n.Model, "\\n", 2)
		modelLine1 := strings.TrimSpace(modelParts[0])
		modelLine2 := ""
		if len(modelParts) > 1 { modelLine2 = strings.TrimSpace(modelParts[1]) }
		if len(modelLine1) > 34 { modelLine1 = modelLine1[:32] + ".." }
		
		modelLabel := modelLine1
		if modelLine2 != "" { modelLabel = modelLine1 + "\\n" + lipgloss.NewStyle().Faint(true).Italic(true).Render(modelLine2) }
		sub := lipgloss.NewStyle().Faint(true).Render(modelLabel)
		
		content := fmt.Sprintf("%s\\n%s\\n[%s]", title, sub, strings.ToUpper(n.Status))
		
		var box string
		switch n.Status {
		case "running":   box = nodeStyles["running"].Render(content)
		case "completed": box = nodeStyles["completed"].Render(content)
		case "rejected":  box = nodeStyles["rejected"].Render(content)
		default:          box = nodeStyles["pending"].Render(content)
		}

		boxLines := strings.Split(box, "\\n")
		for r, bline := range boxLines {
			rIdx := top + r
			if rIdx >= 0 && rIdx < canvasH {
				// We must replace characters in lines[rIdx] with the ANSI string,
				// but because ANSI has hidden length, we calculate exact byte slice injection based on rune width.
				// For simplicity, we just slice the raw space string and insert the ANSI block.
				// Since we know the canvas was pure spaces/runes, character index == byte index mostly (except our ascii lines)
				
				// Let's convert line to runes to slice it by character safely
				runes := []rune(lines[rIdx])
				if left < 0 { left = 0 }
				if left >= len(runes) { continue }
				
				// The box is strictly `nodeW` wide visually
				right := left + nodeW
				if right > len(runes) { right = len(runes) }
				
				prefix := string(runes[:left])
				suffix := ""
				if right < len(runes) {
					suffix = string(runes[right:])
				}
				
				lines[rIdx] = prefix + bline + suffix
			}
		}
	}

	return strings.Join(lines, "\\n")
}
"""

with open('write_2d.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("ready")
