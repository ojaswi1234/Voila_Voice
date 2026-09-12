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
	
	pendingStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#4B5563")).Padding(0, 1).Foreground(lipgloss.Color("#9CA3AF")).Width(20)
	runningStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#F59E0B")).Padding(0, 1).Foreground(lipgloss.Color("#FCD34D")).Width(20)
	completedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#10B981")).Padding(0, 1).Foreground(lipgloss.Color("#34D399")).Width(20)
	rejectedStyle := lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#EF4444")).Padding(0, 1).Foreground(lipgloss.Color("#FCA5A5")).Width(20)

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
		arrow := lipgloss.NewStyle().Foreground(lipgloss.Color("#4B5563")).Padding(1, 1).Render(" ──> ")
		
		// To properly join horizontally, we interleave the arrows and pass as variadic args
		var horizontalArgs []string
		for i, nv := range nodeViews {
			horizontalArgs = append(horizontalArgs, nv)
			if i < len(nodeViews)-1 {
				horizontalArgs = append(horizontalArgs, arrow)
			}
		}
		teamView = lipgloss.JoinHorizontal(lipgloss.Center, horizontalArgs...)
	} else {
		teamView = "Loading team layout..."
	}

	// Render logs
	var formattedLogs []string
	roleStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#60A5FA")) // Blue for role
	toolStyle := lipgloss.NewStyle().Faint(true).Foreground(lipgloss.Color("#A78BFA")) // Purple for tools
	sysStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#F87171")) // Red for system alerts

	for _, l := range m.state.Logs {
		if strings.HasPrefix(l, "[SYSTEM]:") {
			formattedLogs = append(formattedLogs, sysStyle.Render(l))
		} else if strings.HasPrefix(l, "[") && strings.Contains(l, "]") {
			idx := strings.Index(l, "]")
			rolePart := l[:idx+1]
			msgPart := l[idx+1:]
			formattedLogs = append(formattedLogs, roleStyle.Render(rolePart)+msgPart)
		} else if strings.HasPrefix(strings.TrimSpace(l), "> Executed tool:") || strings.HasPrefix(strings.TrimSpace(l), ">") {
			formattedLogs = append(formattedLogs, toolStyle.Render(l))
		} else {
			formattedLogs = append(formattedLogs, l)
		}
	}
	
	logs := strings.Join(formattedLogs, "\n")
	if m.state.ErrorMsg != "" {
		logs += "\n" + lipgloss.NewStyle().Foreground(lipgloss.Color("#EF4444")).Render("FATAL ERROR: "+m.state.ErrorMsg)
	}
	logsView := logStyle.Render(logs)

	return lipgloss.JoinVertical(lipgloss.Left, header, teamView, logsView)
}
