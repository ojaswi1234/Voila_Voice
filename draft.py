import os

go_code = """
// ── 2D SPATIAL GRAPH RENDERER ───────────────────────────────────────────────
func renderSpatialGraph(state LiveState, termW, termH int, styles map[string]lipgloss.Style) string {
	if len(state.Nodes) == 0 {
		return "No nodes to display"
	}

	// 1. Calculate bounding box of raw X,Y to normalize
	minX, maxX, minY, maxY := 99999, -99999, 99999, -99999
	for _, n := range state.Nodes {
		if n.X < minX { minX = n.X }
		if n.X > maxX { maxX = n.X }
		if n.Y < minY { minY = n.Y }
		if n.Y > maxY { maxY = n.Y }
	}
	if minX == maxX { maxX = minX + 100 }
	if minY == maxY { maxY = minY + 100 }

	// 2. Define Canvas dimensions
	// Allow some padding on edges
	nodeW, nodeH := 38, 5 // Dimensions of our rendered node box
	padW, padH := 2, 2
	
	// Term height available for graph = total - header(2) - logs(15) = ~termH - 17
	canvasW := termW
	if canvasW < 100 { canvasW = 100 }
	
	canvasH := termH - 17
	if canvasH < 20 { canvasH = 20 }
	
	// 3. Initialize 2D rune canvas
	canvas := make([][]rune, canvasH)
	for r := 0; r < canvasH; r++ {
		canvas[r] = make([]rune, canvasW)
		for c := 0; c < canvasW; c++ {
			canvas[r][c] = ' '
		}
	}
	
	// Helper to draw string to canvas
	drawString := func(x, y int, s string) {
		lines := strings.Split(s, "\\n")
		for r, line := range lines {
			if y+r < 0 || y+r >= canvasH { continue }
			c := x
			for _, ch := range line {
				// Strip ANSI codes manually is hard, so we just use raw runes for lines,
				// and overlay the actual styled string later?
				// Wait! If we write ANSI to rune array, it breaks.
				if c >= 0 && c < canvasW {
					canvas[y+r][c] = ch
				}
				c++
			}
		}
	}
"""

with open('write_renderer.py', 'w') as f:
    f.write(go_code)
print("done")
