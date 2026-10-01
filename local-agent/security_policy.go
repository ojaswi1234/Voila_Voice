package main

// ================================================================================
// security_policy.go — Voila centralised security policy engine
// ================================================================================
// Single source of truth for ALL risk evaluation. Replaces the 3 duplicated
// dangerousPatterns slices that were scattered in main.go.
//
// Rules are loaded from security_rules.json at startup (embedded as fallback).
// All callers (terminal, desktop type_keys, desktop click/invoke) go through
// EvaluateTerminalCommand or EvaluateDesktopAction.
// ================================================================================

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// ── Decision types ───────────────────────────────────────────────────────────

type PolicyLevel string

const (
	PolicyAllow   PolicyLevel = "allow"
	PolicyApprove PolicyLevel = "approve"
	PolicyDeny    PolicyLevel = "deny"
)

type PolicyDecision struct {
	Level       PolicyLevel
	RiskLevel   string // "low" | "medium" | "high" | "critical"
	Category    string
	Reason      string // one human sentence — shown in popup
	Summary     string // short ≤80 char — shown in notification title
	ActionType  string // "terminal" | "desktop_click" | "desktop_type" | "desktop_window"
	MatchedRule string // the pattern or keyword that triggered this
}

func (d PolicyDecision) IsDenied() bool {
	return d.Level == PolicyDeny
}

func (d PolicyDecision) NeedsApproval() bool {
	return d.Level == PolicyApprove
}

// Keep IsBlocked for backwards compatibility if needed, but make it Deny only
// Approve MUST go through requireSecurityApproval
func (d PolicyDecision) IsBlocked() bool {
	return d.Level == PolicyDeny
}

// ── Rules schema (mirrors security_rules.json) ───────────────────────────────

type terminalRule struct {
	Pattern  string `json:"pattern"`
	Reason   string `json:"reason"`
	Risk     string `json:"risk"`
	Category string `json:"category"`
}

type protectedWindow struct {
	TitleFragment string `json:"title_fragment"`
	Reason        string `json:"reason"`
	Risk          string `json:"risk"`
}

type destructiveKeyword struct {
	Keyword string `json:"keyword"`
	Risk    string `json:"risk"`
	Reason  string `json:"reason"`
}

type typeKeysPattern struct {
	Pattern string `json:"pattern"`
	Risk    string `json:"risk"`
	Reason  string `json:"reason"`
}

type securityRules struct {
	Terminal struct {
		Deny    []terminalRule `json:"deny"`
		Approve []terminalRule `json:"approve"`
	} `json:"terminal"`
	Desktop struct {
		AllowActions               []string             `json:"allow_actions"`
		ProtectedWindows           []protectedWindow    `json:"protected_windows"`
		DestructiveControlKeywords []destructiveKeyword `json:"destructive_control_keywords"`
		TypeKeysPatterns           []typeKeysPattern    `json:"type_keys_patterns"`
	} `json:"desktop"`
}

// ── Singleton ────────────────────────────────────────────────────────────────

var _rules *securityRules
var _rulesLoadErr error

func init() {
	_rules, _rulesLoadErr = loadSecurityRules()
	if _rulesLoadErr != nil {
		log.Printf("[SECURITY_POLICY] WARNING: could not load security_rules.json: %v — using embedded fallback", _rulesLoadErr)
		_rules = embeddedFallbackRules()
	} else {
		log.Printf("[SECURITY_POLICY] Loaded security_rules.json OK (%d terminal deny, %d terminal approve, %d desktop windows)",
			len(_rules.Terminal.Deny),
			len(_rules.Terminal.Approve),
			len(_rules.Desktop.ProtectedWindows),
		)
	}
}

func loadSecurityRules() (*securityRules, error) {
	exe, err := os.Executable()
	if err != nil {
		return nil, err
	}
	candidates := []string{
		filepath.Join(filepath.Dir(exe), "security_rules.json"),
		filepath.Join(currentWorkingDir, "security_rules.json"),
		filepath.Join(currentWorkingDir, "local-agent", "security_rules.json"),
	}
	for _, p := range candidates {
		data, err := os.ReadFile(p)
		if err == nil {
			var r securityRules
			if err2 := json.Unmarshal(data, &r); err2 != nil {
				return nil, fmt.Errorf("parse %s: %w", p, err2)
			}
			return &r, nil
		}
	}
	return nil, fmt.Errorf("security_rules.json not found in any candidate path")
}

// ── EvaluateTerminalCommand ──────────────────────────────────────────────────

func EvaluateTerminalCommand(cmd string) PolicyDecision {
	lower := strings.ToLower(cmd)

	// Check deny rules first (catastrophic)
	for _, rule := range _rules.Terminal.Deny {
		if matchesPattern(lower, rule.Pattern) {
			writeAuditLog(AuditEntry{
				Timestamp:  time.Now().UTC().Format(time.RFC3339),
				Tool:       "run_terminal",
				Action:     "terminal",
				Level:      "deny",
				Risk:       coalesce(rule.Risk, "critical"),
				Decision:   "auto_deny",
				Summary:    rule.Reason,
				MatchedRule: rule.Pattern,
			})
			return PolicyDecision{
				Level:       PolicyDeny,
				RiskLevel:   coalesce(rule.Risk, "critical"),
				Category:    rule.Category,
				Reason:      rule.Reason,
				Summary:     "BLOCKED: " + truncate(rule.Reason, 80),
				ActionType:  "terminal",
				MatchedRule: rule.Pattern,
			}
		}
	}

	// Check approve rules
	for _, rule := range _rules.Terminal.Approve {
		if matchesPattern(lower, rule.Pattern) {
			return PolicyDecision{
				Level:       PolicyApprove,
				RiskLevel:   coalesce(rule.Risk, "high"),
				Category:    rule.Category,
				Reason:      rule.Reason,
				Summary:     truncate(rule.Reason, 80),
				ActionType:  "terminal",
				MatchedRule: rule.Pattern,
			}
		}
	}

	return PolicyDecision{Level: PolicyAllow, ActionType: "terminal"}
}

// ── EvaluateDesktopAction ────────────────────────────────────────────────────

func EvaluateDesktopAction(action, ref, selector, value, window, controlName, controlRole, processName string) PolicyDecision {
	actionLower := strings.ToLower(action)

	// Read-only actions: always allow
	for _, a := range _rules.Desktop.AllowActions {
		if actionLower == strings.ToLower(a) {
			return PolicyDecision{Level: PolicyAllow, ActionType: "desktop_action"}
		}
	}

	// Check protected window titles
	winLower := strings.ToLower(window + " " + processName)
	for _, pw := range _rules.Desktop.ProtectedWindows {
		if strings.Contains(winLower, strings.ToLower(pw.TitleFragment)) {
			return PolicyDecision{
				Level:       PolicyApprove,
				RiskLevel:   coalesce(pw.Risk, "high"),
				Category:    "protected_window",
				Reason:      pw.Reason,
				Summary:     "Protected window: " + truncate(pw.Reason, 60),
				ActionType:  "desktop_window",
				MatchedRule: pw.TitleFragment,
			}
		}
	}

	// Check type_keys / set_value: evaluate typed value
	if actionLower == "type_keys" || actionLower == "set_value" {
		valueLower := strings.ToLower(value)
		for _, tp := range _rules.Desktop.TypeKeysPatterns {
			if matchesPattern(valueLower, tp.Pattern) {
				return PolicyDecision{
					Level:       PolicyApprove,
					RiskLevel:   coalesce(tp.Risk, "high"),
					Category:    "desktop_type",
					Reason:      tp.Reason,
					Summary:     truncate(tp.Reason, 80),
					ActionType:  "desktop_type",
					MatchedRule: tp.Pattern,
				}
			}
		}
	}

	// Check destructive control names / selectors for click/invoke/toggle actions
	sideEffectActions := map[string]bool{
		"invoke": true, "click_ref": true, "right_click": true, "toggle": true,
		"select": true, "drag_ref": true, "close_window": true,
		"min_window": true, "max_window": true, "focus_window": true,
		"switch_desktop": true, "switch_virtual_desktop": true,
		"open_start_menu": true,
	}
	if sideEffectActions[actionLower] {
		combined := strings.ToLower(controlName + " " + selector + " " + ref)
		for _, dk := range _rules.Desktop.DestructiveControlKeywords {
			if strings.Contains(combined, strings.ToLower(dk.Keyword)) {
				return PolicyDecision{
					Level:       PolicyApprove,
					RiskLevel:   coalesce(dk.Risk, "high"),
					Category:    "destructive_control",
					Reason:      dk.Reason,
					Summary:     fmt.Sprintf("Control '%s' — %s", truncate(controlName, 30), truncate(dk.Reason, 50)),
					ActionType:  "desktop_click",
					MatchedRule: dk.Keyword,
				}
			}
		}
	}

	return PolicyDecision{Level: PolicyAllow, ActionType: "desktop_action"}
}

// ── Enhanced mobile approval with rich payload ────────────────────────────────

type ApprovalRequest struct {
	JobID       string `json:"job_id"`
	DeviceID    string `json:"device_id"`
	SecretHash  string `json:"secret_hash"`
	// Rich popup fields
	RiskLevel   string `json:"risk_level"`   // medium | high | critical
	ActionType  string `json:"action_type"`  // terminal | desktop_click | desktop_type | desktop_window
	Summary     string `json:"summary"`      // ≤80 char — notification title
	Detail      string `json:"detail"`       // full command or action description
	Reason      string `json:"reason"`       // why it was flagged
	Tool        string `json:"tool"`         // run_terminal | desktop_automation
	Window      string `json:"window"`       // window title (desktop) or empty
	ControlName string `json:"control_name"` // control name (desktop) or empty
	ExpiresAt   string `json:"expires_at"`   // ISO8601 timeout deadline
}

// requireSecurityApproval replaces the old requireMobileApproval.
// It sends a rich ApprovalRequest payload and waits up to 45s.
// Returns true = user allowed, false = user denied / timeout.
func requireSecurityApproval(decision PolicyDecision, detail, tool, window, controlName string) bool {
	connData, err := loadConnectionData()
	if err != nil {
		return false
	}

	reqID := fmt.Sprintf("sec-%x", time.Now().UnixNano()%0xFFFFFFFF)
	ch := make(chan bool, 1)

	pendingApprovalsMu.Lock()
	pendingApprovals[reqID] = ch
	pendingApprovalsMu.Unlock()

	expiresAt := time.Now().Add(45 * time.Second).UTC().Format(time.RFC3339)

	req := ApprovalRequest{
		JobID:       reqID,
		DeviceID:    connData.DeviceID,
		SecretHash:  hashPhrase(connData.SecurityPhrase, connData.DeviceID),
		RiskLevel:   decision.RiskLevel,
		ActionType:  decision.ActionType,
		Summary:     decision.Summary,
		Detail:      truncate(detail, 400),
		Reason:      decision.Reason,
		Tool:        tool,
		Window:      window,
		ControlName: controlName,
		ExpiresAt:   expiresAt,
	}

	payload, _ := json.Marshal(req)

	backendURL := strings.TrimRight(connData.BackendURL, "/") + "/webhook/approval_request"
	backendURL = strings.Replace(backendURL, "wss://", "https://", 1)
	backendURL = strings.Replace(backendURL, "ws://", "http://", 1)

	go func() {
		client := &http.Client{Timeout: 10 * time.Second}
		client.Post(backendURL, "application/json", bytes.NewBuffer(payload))
	}()

	var userDecision string
	var approved bool
	select {
	case approved = <-ch:
		if approved {
			userDecision = "user_allow"
		} else {
			userDecision = "user_deny"
		}
	case <-time.After(45 * time.Second):
		pendingApprovalsMu.Lock()
		delete(pendingApprovals, reqID)
		pendingApprovalsMu.Unlock()
		approved = false
		userDecision = "timeout_deny"
	}

	// Audit log
	writeAuditLog(AuditEntry{
		Timestamp:   time.Now().UTC().Format(time.RFC3339),
		Tool:        tool,
		Action:      decision.ActionType,
		Level:       string(decision.Level),
		Risk:        decision.RiskLevel,
		Decision:    userDecision,
		Summary:     decision.Summary,
		Window:      window,
		ControlName: controlName,
		MatchedRule: decision.MatchedRule,
	})

	return approved
}

// ── Audit logger ─────────────────────────────────────────────────────────────

type AuditEntry struct {
	Timestamp   string `json:"ts"`
	Tool        string `json:"tool"`
	Action      string `json:"action"`
	Level       string `json:"level"`
	Risk        string `json:"risk"`
	Decision    string `json:"decision"`
	Summary     string `json:"summary"`
	Window      string `json:"window,omitempty"`
	ControlName string `json:"control,omitempty"`
	MatchedRule string `json:"matched_rule,omitempty"`
}

func writeAuditLog(entry AuditEntry) {
	// NOTE: No raw commands/values stored — only the matched rule pattern.
	exe, err := os.Executable()
	if err != nil {
		return
	}
	auditPath := filepath.Join(filepath.Dir(exe), "security_audit.jsonl")
	line, _ := json.Marshal(entry)
	f, err := os.OpenFile(auditPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return
	}
	defer f.Close()
	f.Write(append(line, '\n'))
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func matchesPattern(input, pattern string) bool {
	// Patterns that contain .* are treated as regex; others as substring
	if strings.Contains(pattern, ".*") || strings.Contains(pattern, "^") {
		re, err := regexp.Compile("(?i)" + pattern)
		if err != nil {
			return strings.Contains(input, pattern)
		}
		return re.MatchString(input)
	}
	return strings.Contains(input, strings.ToLower(pattern))
}

func coalesce(a, b string) string {
	if a != "" {
		return a
	}
	return b
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max-3] + "..."
}

// permissionDeniedNote returns a system message injected into the LLM context
// after a popup-deny so it doesn't blindly retry the same destructive action.
func permissionDeniedNote(decision PolicyDecision, detail string) string {
	return fmt.Sprintf(
		"PERMISSION DENIED: The user rejected the security approval popup for this action.\n"+
			"Action: %s\nRisk: %s\nReason: %s\n"+
			"DO NOT retry the same action. Instead, explain the situation to the user and ask "+
			"whether they want to proceed with a safer alternative approach.",
		truncate(detail, 200), decision.RiskLevel, decision.Reason,
	)
}

// ── Embedded fallback (minimal, in case JSON file missing) ───────────────────

func embeddedFallbackRules() *securityRules {
	r := &securityRules{}
	r.Terminal.Deny = []terminalRule{
		{Pattern: "format c:", Reason: "Formats the Windows system drive.", Risk: "critical", Category: "disk_wipe"},
		{Pattern: "diskpart", Reason: "Diskpart can wipe partitions.", Risk: "critical", Category: "disk_wipe"},
	}
	r.Terminal.Approve = []terminalRule{
		{Pattern: "format-volume", Reason: "Volume format operation.", Risk: "critical", Category: "disk_wipe"},
		{Pattern: "clear-disk", Reason: "Full disk erase.", Risk: "critical", Category: "disk_wipe"},
		{Pattern: "vssadmin delete shadows", Reason: "Deletes system restore points.", Risk: "critical", Category: "recovery_destruction"},
		{Pattern: "bcdedit /set", Reason: "Boot config modification.", Risk: "critical", Category: "boot_config"},
		{Pattern: "set-itemproperty hklm:", Reason: "HKLM registry write.", Risk: "high", Category: "registry"},
		{Pattern: "reg add hklm", Reason: "HKLM registry write.", Risk: "high", Category: "registry"},
		{Pattern: "net user", Reason: "User account modification.", Risk: "high", Category: "account_management"},
		{Pattern: "stop-computer", Reason: "Shuts down this PC.", Risk: "high", Category: "power"},
		{Pattern: "restart-computer", Reason: "Restarts this PC.", Risk: "high", Category: "power"},
		{Pattern: "iex (new-object", Reason: "Downloads and executes remote code.", Risk: "critical", Category: "remote_exec"},
		{Pattern: "-recurse -force", Reason: "Recursive forced file deletion.", Risk: "high", Category: "file_delete"},
		{Pattern: "rmdir /s", Reason: "Recursive directory deletion.", Risk: "high", Category: "file_delete"},
		{Pattern: "rd /s", Reason: "Recursive directory deletion.", Risk: "high", Category: "file_delete"},
		{Pattern: "del /s", Reason: "Recursive file deletion.", Risk: "high", Category: "file_delete"},
		{Pattern: "remove-item", Reason: "PowerShell deletion command.", Risk: "high", Category: "file_delete"},
	}
	r.Desktop.AllowActions = []string{
		"list_windows", "foreground", "snapshot", "find", "move_cursor",
		"focus", "scroll", "get_text", "screenshot",
	}
	r.Desktop.ProtectedWindows = []protectedWindow{
		{TitleFragment: "user account control", Reason: "UAC elevation dialog.", Risk: "critical"},
		{TitleFragment: "registry editor", Reason: "Windows registry editor.", Risk: "critical"},
		{TitleFragment: "windows security", Reason: "Windows Security Center.", Risk: "high"},
		{TitleFragment: "reset this pc", Reason: "Factory reset wizard.", Risk: "critical"},
	}
	r.Desktop.DestructiveControlKeywords = []destructiveKeyword{
		{Keyword: "empty recycle", Risk: "high", Reason: "Destructive empty recycle bin."},
		{Keyword: "format volume", Risk: "critical", Reason: "Format volume action."},
		{Keyword: "delete permanently", Risk: "critical", Reason: "Permanent deletion."},
		{Keyword: "factory reset", Risk: "high", Reason: "Factory reset action."},
		{Keyword: "uninstall", Risk: "high", Reason: "Uninstall action."},
		{Keyword: "wipe", Risk: "critical", Reason: "Wipe action."},
	}
	r.Desktop.TypeKeysPatterns = []typeKeysPattern{
		{Pattern: "format c:", Risk: "critical", Reason: "System format command typed."},
		{Pattern: "diskpart", Risk: "critical", Reason: "Diskpart typed into UI."},
		{Pattern: "net user", Risk: "high", Reason: "User management typed."},
		{Pattern: "iex (", Risk: "critical", Reason: "Remote exec typed."},
	}
	return r
}
