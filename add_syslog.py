import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add definitions
syslog_def = """
type LogEntry struct {
	Category string
	Message  string
	Time     time.Time
}

var (
	sysLogMu sync.Mutex
	sysLogs  []LogEntry
)

func addSysLog(category, msg string) {
	sysLogMu.Lock()
	defer sysLogMu.Unlock()
	sysLogs = append(sysLogs, LogEntry{Category: category, Message: msg, Time: time.Now()})
	if len(sysLogs) > 100 {
		sysLogs = sysLogs[1:] // keep last 100
	}
	if debugLog != nil {
		debugLog.Printf("[%s] %s", category, msg)
	}
}

"""

if "type LogEntry struct" not in text:
    text = text.replace('type ConnectionData struct {', syslog_def + 'type ConnectionData struct {')

# 2. Update menus
text = text.replace('"📊 View Status"', 'fmt.Sprintf("📊 View System Logs (%d)", len(sysLogs))')

# 3. Update view status switch
# case 7: // View Status -> system logs
view_status_switch = """		case 7: // View System Logs
			m.state = "system_logs"
			return m, nil"""
text = re.sub(r'case 7: // View Status.*?(?=case 8: // Exit)', view_status_switch + "\n", text, flags=re.DOTALL)

# Also update the non-connected or background menu indices if necessary, but wait, the indices are determined by their position.
# Actually, View Status is always case 7 for connected. For background, wait, they both use the same switch?
# Yes, they both use the same array indices if length is the same.

# 4. Add system_logs state in Update
# Backspace / Esc to go back to menu
esc_handler = """			} else if m.state == "system_logs" {
				m.state = "menu"
			}"""
text = text.replace('			} else if m.state == "security_phrase_input" || m.state == "ngrok_token_input" {', esc_handler + '\n			} else if m.state == "security_phrase_input" || m.state == "ngrok_token_input" {')

# 5. Add systemLogsView
log_view_func = """
func (m model) systemLogsView() string {
	var content strings.Builder
	content.WriteString(titleStyle.Render("System Message Viewer"))
	content.WriteString("\\n")
	content.WriteString(separatorStyle.Render(strings.Repeat("-", 70)))
	content.WriteString("\\n")
	
	sysLogMu.Lock()
	if len(sysLogs) == 0 {
		content.WriteString(subtitleStyle.Render("No messages recorded yet."))
		content.WriteString("\\n")
	} else {
		// Show last 20 logs
		start := 0
		if len(sysLogs) > 20 {
			start = len(sysLogs) - 20
		}
		for _, l := range sysLogs[start:] {
			catColor := "6"
			if l.Category == "Ngrok" { catColor = "5" }
			if l.Category == "Polling" { catColor = "3" }
			if l.Category == "Backend" { catColor = "2" }
			
			catStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(catColor)).Bold(true)
			timeStr := lipgloss.NewStyle().Foreground(lipgloss.Color("8")).Render(l.Time.Format("15:04:05"))
			
			content.WriteString(fmt.Sprintf("%s %s %s\\n", timeStr, catStyle.Render("["+l.Category+"]"), l.Message))
		}
	}
	sysLogMu.Unlock()
	
	content.WriteString("\\n")
	content.WriteString(separatorStyle.Render(strings.Repeat("-", 70)))
	content.WriteString("\\n")
	content.WriteString(subtitleStyle.Render("Press Esc to return to menu"))
	return content.String()
}
"""

if "func (m model) systemLogsView" not in text:
    text = text.replace('func (m model) ngrokTokenInputView() string {', log_view_func + '\nfunc (m model) ngrokTokenInputView() string {')

# 6. Add system_logs to view switch
view_handler = """	case "system_logs":
		content = m.systemLogsView()
"""
text = text.replace('	case "ngrok_token_input":', view_handler + '	case "ngrok_token_input":')

# 7. Replace muted logs with addSysLog!
text = text.replace('// silenced to prevent tui break', 'addSysLog("Ngrok", fmt.Sprintf("Using ngrok at: %s", ngrokPath))')
text = text.replace('// silenced', 'addSysLog("Ngrok", "Attempting operation...")')
# Let's fix the exact muted lines.

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
