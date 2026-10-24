# VOILA.md - Project Blueprint & Grounded Memory

> **System Motto**: *Voila: Your Floating AI CLI Assistant — A Zero-Trust, Voice-Controlled Remote Execution System with Multi-Agent Swarm & ML Security.*

---

## 🏗️ Architecture & Core Components

- **`local-agent/` (Desktop Automation & Swarm Node)**:
  - Entry point: [local-agent/main.go](file:///C:/Users/ojasw/Desktop/Voila_Voice/local-agent/main.go)
  - Tool execution & MCP registry: [local-agent/mcp_wiring.go](file:///C:/Users/ojasw/Desktop/Voila_Voice/local-agent/mcp_wiring.go)
  - Concurrency & Process lifecycle: [local-agent/background_tasks.go](file:///C:/Users/ojasw/Desktop/Voila_Voice/local-agent/background_tasks.go)
  - ML Anomaly Guardrails: `local-agent/aegis/` (Markov & Z-score kernel filters)
- **`main.go` (Cloud Relay & Multiplexed Gateway)**:
  - WebSocket tunnel, gRPC bridge, FCM push notifications, and decoupled HTTP result webhooks.
- **`mobile-agent/` (Flutter Mobile UI & Voice HUD)**:
  - Interactive terminal cards, Bento Box AI responses, and streaming visualizer HUD.

---

## ⚡ Build & Verification Commands

- **Build Local Agent**: `go build -o voila.exe ./local-agent`
- **Build Cloud Server**: `go build -o server.exe .`
- **Run Unit Tests**: `Set-Location local-agent; go test -v -run "TestBGTask|TestCheckpoint|TestProcedural|TestAppendMemory|TestAsyncUpdate"`

---

## 🛡️ Critical Operating Invariants

1. **Zero-Trust OS Protection**:
   - Never modify, delete, or touch Windows System32, Program Files, the Registry, or user credentials.
   - For UI interactions, use `desktop_automation` or `browser_automation` (never raw shell script mouse clicks).
2. **Windows PowerShell Rules**:
   - Running in Windows PowerShell: use `Get-ChildItem` (not `ls -la`), `Select-String` (not `grep`), and `Get-Content` (not `cat`).
   - Paths use Windows backslashes (`\`).
3. **.aiignore Policy**:
   - Never explore or read inside `node_modules`, `.venv`, `venv`, `vendor`, `.git`, or build artifact directories.
4. **Plan -> Act -> Verify Workflow**:
   - Always verify on-disk state after executing file writes or terminal commands before declaring success to the user.

---

## 🧠 Continuous Memory & Self-Learning

- **Project Rules & Knowledge**: Persisted here in `./VOILA.md` via `remember_fact(scope="project")`.
- **User Habits & Preferences**: Persisted in `brain/global_memory.md` via `remember_fact(scope="global")`.
- **Command Techniques**: Successfully discovered PowerShell techniques are saved via `save_command_memory` and automatically retrieved JIT via lexical scoring.
