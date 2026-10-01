package main
import "testing"
func TestTerminalPolicy(t *testing.T) {
    if EvaluateTerminalCommand("dir").Level != PolicyAllow { t.Error("dir should allow") }
    if EvaluateTerminalCommand("format c:").Level != PolicyDeny { t.Error("format c: should deny") }
    if EvaluateTerminalCommand("net user").Level != PolicyApprove { t.Error("net user should approve") }
    if EvaluateTerminalCommand("git push").Level != PolicyAllow { t.Error("git push should allow") }
}
func TestDesktopPolicy(t *testing.T) {
    if EvaluateDesktopAction("snapshot", "", "", "", "MyApp", "", "", "").Level != PolicyAllow { t.Error("snapshot allow") }
    if EvaluateDesktopAction("click_ref", "e1", "", "", "User Account Control", "Yes", "", "").Level != PolicyApprove { 
        t.Error("UAC should be approve")
    }
    if EvaluateDesktopAction("type_keys", "", "", "hello", "Notepad", "", "", "").Level != PolicyAllow { t.Error("hello allow") }
    if EvaluateDesktopAction("type_keys", "", "", "diskpart", "Notepad", "", "", "").Level != PolicyApprove { t.Error("diskpart approve") }
}
