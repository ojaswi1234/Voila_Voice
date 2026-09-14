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
	Logs     []string        `json:"logs"`
	ErrorMsg string          `json:"error"`
}

type NodeLiveState struct {
	ID     string `json:"id"`
	Role   string `json:"role"`
	Status string `json:"status"` // "pending", "running", "completed", "rejected"
	Model  string `json:"model"`
}

type tuiModel struct {
	state LiveState
	err   error
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
	
	pendingStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#4B5563")).Padding(0, 1).Foreground(lipgloss.Color("#9CA3AF")).Width(35)
	runningStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#F59E0B")).Padding(0, 1).Foreground(lipgloss.Color("#FCD34D")).Width(35)
	completedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#10B981")).Padding(0, 1).Foreground(lipgloss.Color("#34D399")).Width(35)
	rejectedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#EF4444")).Padding(0, 1).Foreground(lipgloss.Color("#FCA5A5")).Width(35)

	logStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#D1D5DB")).MarginTop(1)

	header := titleStyle.Render("🤖 VOILA GRAPHIFY : LIVE TEAM TRACKER")
	if m.state.Status == "done" {
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#10B981")).Render(" [FINISHED - Press any key to exit]")
	} else if m.state.Status == "error" {
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render(" [ERROR - Press any key to exit]")
	} else {
		header += lipgloss.NewStyle().Foreground(lipgloss.Color("#F59E0B")).Render(" [RUNNING... (Press 'k' to KILL)]")
	}

	// Render nodes horizontally
	var nodeViews []string
	for _, n := range m.state.Nodes {
		var box string
		title := lipgloss.NewStyle().Bold(true).Render(n.Role)
		
		modelName := n.Model
		if len(modelName) > 16 {
			modelName = modelName[:14] + ".."
		}
		sub := lipgloss.NewStyle().Faint(true).Render(modelName)
		
		content := fmt.Sprintf("%s\n%s\n[%s]", title, sub, strings.ToUpper(n.Status))
		
		switch n.Status {
		case "running": box = runningStyle.Render(content)
		case "completed": box = completedStyle.Render(content)
		case "rejected": box = rejectedStyle.Render(content)
		default: box = pendingStyle.Render(content)
		}
		
		nodeViews = append(nodeViews, box)
	}

	var teamView string
	if len(nodeViews) > 0 {
		// Responsive grid wrap instead of hardcoded horizontal chain
		// This prevents UI clipping on large graphs
		var chunks []string
		chunkSize := 3
		for i := 0; i < len(nodeViews); i += chunkSize {
			end := i + chunkSize
			if end > len(nodeViews) { end = len(nodeViews) }
			rowArgs := nodeViews[i:end]
			var rowView []string
			for j, nv := range rowArgs {
				rowView = append(rowView, nv)
				if j < len(rowArgs)-1 {
					rowView = append(rowView, lipgloss.NewStyle().Padding(1, 1).Render("  "))
				}
			}
			chunks = append(chunks, lipgloss.JoinHorizontal(lipgloss.Top, rowView...))
			chunks = append(chunks, lipgloss.NewStyle().Padding(1, 0).Render("")) // spacer row
		}
		teamView = lipgloss.JoinVertical(lipgloss.Left, chunks...)
	} else {
		teamView = "Loading team layout..."
	}

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

	return lipgloss.JoinVertical(lipgloss.Left, header, teamView, logsView)
}
