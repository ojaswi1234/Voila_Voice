# Voila Voice — Tier-3 v1 Status

Generated: 2026-09-20

## Already Existed (Verified)

| Feature | Component | Notes |
|---|---|---|
| Circuit breaker (trip/reset/alerts) | Relay + Agent + Mobile | `tripCircuitBreaker`, `resetCircuitBreaker`, `breaker_open`/`breaker_close` alerts via FCM+WS |
| Decoy mock responses | Relay + Agent | `shared/decoy.GenerateMockResponse`, `handleLocalMockExecution`, threshold=3 |
| Security alerts list UI | Mobile | `_showSecurityAlerts()` bottom sheet, Reset Circuit Breaker button |
| Device picker | Mobile | `_showDeviceSelector()`, `switch_device` WS message |
| `device_id` in commands | Mobile→Relay | All command messages include `device_id` field |
| Job strip auto-hide | Mobile | 3s delay after done/failed/cancelled |
| `save_command_memory` | Agent | `cmd_memory.json` key-value store |
| 26 tools (GROQ+Ollama) | Agent | Full tool suite including browser, docs, PDF, PPT |
| Quiet hours (isCritical) | Mobile | Correctly exempts approvals and breaker alerts |
| `/token-usage` endpoint | Agent (local only) | Returns Groq+Ollama session/day/rate counters |
| Approvals flow | All three | FCM `approval_required`, dialog, agent gate |
| Playbooks (list/run) | Agent | UTF-8/BOM handling, JSON schema execution |

## Newly Added (This Pass)

| Feature | Component | Files Changed |
|---|---|---|
| **A1: Token usage push** | Agent→Relay→Mobile | `local-agent/main.go`, `main.go` (relay), `mobile-agent/lib/main.dart` |
| **A1: Token usage cache** | Mobile | `main.dart` — `_lastTokenUsage`, secure storage persistence |
| **A2: approve_job X-Exec-Secret** | Relay | `main.go` (relay) — security fix |
| **A3: Artifacts navigation** | Mobile | `main.dart` — FCM `task_finished` → navigate |
| **T3.3: Security alerts persist** | Mobile | `main.dart` — secure storage, max 50 entries |
| **T3.4: Scheduled jobs** | Agent | `local-agent/main.go` — `Schedule` struct, tools, 1-min ticker |
| **T3.5: Memory search** | Agent | `local-agent/main.go` — `cmd_memory_log.json`, `search_memory`, `rerun_memory_item` |
| **T3.1: /webhook/token-usage** | Relay | `main.go` (relay) — new webhook endpoint, WS broadcast |
| **T3.6: Local templates** | Agent + Python | `templates/registry.json`, `mcp_docs_facade.py` real local generation |
| **T3.2: Skills system** | Agent | `local-agent/main.go`, `skills/skills.json`, `list_skills`, `run_skill` tools |

## How to Test

### A1 — Token Usage
1. Start local agent (`voila.exe --background`)
2. Open mobile app, go to Settings
3. Within ~5 minutes (periodic push) or after any command, token row should show real numbers
4. Kill app, relaunch — numbers should persist from cache

### A2 — Security Path
1. Send 3 commands from mobile without a valid session token → circuit should trip
2. Mobile security alerts list should show `breaker_open` alert
3. Use Reset Circuit Breaker button in Security Alerts sheet → circuit closes
4. Commands should work again

### T3.3 — Alert Persistence
1. Receive security alert
2. Kill and relaunch mobile app
3. Security alerts list should still show the alert

### T3.4 — Schedules
1. Ask Voila: "add a schedule to run at 09:00 to generate a standup summary"
2. Agent responds with schedule ID
3. Ask: "list my schedules" to verify
4. At the scheduled time (or test by setting time_of_day to 1 minute from now), schedule fires
5. FCM notification arrives with completion

### T3.5 — Memory Search
1. Use `save_command_memory` to save a command
2. Ask: "search my memory for 'standup'"
3. Agent uses `search_memory` and returns matches
4. Ask to rerun a specific memory entry by ID

### T3.6 — Templates
1. Ask Voila: "list available templates"
2. Ask: "create a report using the quarterly_report template for Q3 2026"
3. Agent calls `docs.create_from_template` with `template_id: quarterly_report`
4. Real PDF is generated (not mock text file)
5. Quality gate rejects empty outputs

### T3.2 — Skills
1. Ask Voila: "what skills do you have?"
2. Agent calls `list_skills` and returns platform-specific skills
3. Ask: "open my Desktop in Explorer"
4. Agent calls `run_skill` with `open_in_explorer` and `path: C:\\Users\\...\\Desktop`
5. Explorer opens

## Regression Coverage

- `browser_automation`: tool #2 in registry, unchanged ✅
- `create_pdf`: tool #10, unchanged ✅
- `create_ppt`: tool #13, unchanged ✅
- `list_playbooks`/`run_playbook`: tools #8/#9, unchanged ✅
- `approval_required` FCM flow: unchanged ✅
- Circuit breaker trip/reset: unchanged ✅
- Decoy mock responses: unchanged ✅
