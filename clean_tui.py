import sys
with open('local-agent/tui.go', 'r', encoding='utf-8') as f:
    text = f.read()

import_block = """import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"
	"syscall"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

var (
	kernel32TUI  = syscall.NewLazyDLL("kernel32.dll")
	user32TUI    = syscall.NewLazyDLL("user32.dll")
	allocConsole = kernel32TUI.NewProc("AllocConsole")
	freeConsole  = kernel32TUI.NewProc("FreeConsole")
	getConsole   = kernel32TUI.NewProc("GetConsoleWindow")
	showWindow   = user32TUI.NewProc("ShowWindow")
)

func runGraphifyTUI() {
	// Pop open a visible console window!
	// MUST free any existing hidden console inherited from Python's CREATE_NO_WINDOW first!
	freeConsole.Call()
	time.Sleep(100 * time.Millisecond) // Give OS a tiny moment
	allocConsole.Call()
	
	// Force the console to be visible, overriding Python's CREATE_NO_WINDOW (SW_HIDE)
	hwnd, _, _ := getConsole.Call()
	if hwnd != 0 {
		showWindow.Call(hwnd, 5) // 5 = SW_SHOW
	}
	
	// Bind std streams to the new console window
	out, _ := os.OpenFile("CONOUT$", os.O_RDWR, 0644)
	os.Stdout = out
	os.Stderr = out
	in, _ := os.OpenFile("CONIN$", os.O_RDWR, 0644)
	os.Stdin = in

	p := tea.NewProgram(tuiModel{}, tea.WithAltScreen(), tea.WithInput(in), tea.WithOutput(out))
	if _, err := p.Run(); err != nil {
		fmt.Printf("Alas, there's been an error: %v", err)
	}
	
	// Close window when done
	freeConsole.Call()
}"""

clean_block = """import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func runGraphifyTUI() {
	p := tea.NewProgram(tuiModel{}, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Printf("Alas, there's been an error: %v", err)
		os.Exit(1)
	}
}"""

text = text.replace(import_block, clean_block)
with open('local-agent/tui.go', 'w', encoding='utf-8') as f:
    f.write(text)
print("Removed AllocConsole from tui.go!")
