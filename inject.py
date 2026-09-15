import sys

with open('write_2d.py', 'r', encoding='utf-8') as f:
    text2d = f.read().split('\"\"\"')[1]

with open('local-agent/tui.go', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the grid logic in View()
old_view = """	// Render nodes horizontally
	var nodeViews []string
	for _, n := range m.state.Nodes {
		var box string
		title := lipgloss.NewStyle().Bold(true).Render(n.Role)

		// Model string is "modelname\\n(Provider)" — split and display both lines cleanly
		modelParts := strings.SplitN(n.Model, "\\n", 2)
		modelLine1 := strings.TrimSpace(modelParts[0])
		modelLine2 := ""
		if len(modelParts) > 1 {
			modelLine2 = strings.TrimSpace(modelParts[1])
		}
		// Ensure model name never overflows box width (38 - 2 padding = 36)
		if len(modelLine1) > 34 {
			modelLine1 = modelLine1[:32] + ".."
		}
		modelLabel := modelLine1
		if modelLine2 != "" {
			modelLabel = modelLine1 + "\\n" + lipgloss.NewStyle().Faint(true).Italic(true).Render(modelLine2)
		}
		sub := lipgloss.NewStyle().Faint(true).Render(modelLabel)

		content := fmt.Sprintf("%s\\n%s\\n[%s]", title, sub, strings.ToUpper(n.Status))

		switch n.Status {
		case "running":   box = runningStyle.Render(content)
		case "completed": box = completedStyle.Render(content)
		case "rejected":  box = rejectedStyle.Render(content)
		default:          box = pendingStyle.Render(content)
		}

		nodeViews = append(nodeViews, box)
	}

	var teamView string
	if len(nodeViews) > 0 {
		// Dynamically calculate how many nodes fit per row based on terminal width
		// Each node box = 38 wide + 4 space between = 42. Default to 2 if unknown.
		nodeWidth := 42
		chunkSize := 2
		if m.termWidth > 0 {
			chunkSize = m.termWidth / nodeWidth
			if chunkSize < 1 {
				chunkSize = 1
			}
			if chunkSize > 4 {
				chunkSize = 4
			}
		}

		var chunks []string
		for i := 0; i < len(nodeViews); i += chunkSize {
			end := i + chunkSize
			if end > len(nodeViews) {
				end = len(nodeViews)
			}
			rowArgs := nodeViews[i:end]
			var rowView []string
			for j, nv := range rowArgs {
				rowView = append(rowView, nv)
				if j < len(rowArgs)-1 {
					rowView = append(rowView, lipgloss.NewStyle().Padding(2, 1).Render(""))
				}
			}
			chunks = append(chunks, lipgloss.JoinHorizontal(lipgloss.Top, rowView...))
			chunks = append(chunks, "")
		}
		teamView = lipgloss.JoinVertical(lipgloss.Left, chunks...)
	} else {
		teamView = "Loading team layout..."
	}

	// ── CONNECTIONS PANEL ──────────────────────────────────────────────────────
	// Build a role-name lookup from node ID
	idToRole := make(map[string]string)
	for _, n := range m.state.Nodes {
		idToRole[n.ID] = n.Role
	}
	var edgeLines []string
	connStyle  := lipgloss.NewStyle().Foreground(lipgloss.Color("#6366F1")).Bold(true)
	arrowStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B"))
	if len(m.state.Edges) > 0 {
		edgeLines = append(edgeLines, connStyle.Render("── CONNECTIONS & RELATIONSHIPS ──"))
		for _, edge := range m.state.Edges {
			if len(edge) >= 2 {
				fromRole := idToRole[edge[0]]
				toRole   := idToRole[edge[1]]
				if fromRole == "" { fromRole = edge[0] }
				if toRole   == "" { toRole   = edge[1] }
				line := fmt.Sprintf("  %s  %s  %s",
					lipgloss.NewStyle().Foreground(lipgloss.Color("#818CF8")).Render("["+fromRole+"]"),
					arrowStyle.Render("──▶"),
					lipgloss.NewStyle().Foreground(lipgloss.Color("#34D399")).Render("["+toRole+"]"),
				)
				edgeLines = append(edgeLines, line)
			}
		}
	}
	connectionsView := strings.Join(edgeLines, "\\n")"""

new_view = """	nodeStyles := map[string]lipgloss.Style{
		"pending":   pendingStyle,
		"running":   runningStyle,
		"completed": completedStyle,
		"rejected":  rejectedStyle,
	}

	teamView := renderSpatialGraph(m, nodeStyles)
	connectionsView := "" // Replaced by true 2D edges in canvas
"""

text = text.replace(old_view, new_view)
text += "\n\n" + text2d

with open('local-agent/tui.go', 'w', encoding='utf-8') as f:
    f.write(text)
print("done")
