# MCP, Skills, and Connectors - Test Report

| ID | Type | Result | Notes |
|----|------|--------|-------|
| U1 | unit | PASS | Load valid mcp_servers.json |
| U2 | unit | PASS | Disabled server does not spawn process |
| U3 | unit | PASS | Enable/disable persists |
| U4 | unit | PASS | Namespace sanitization |
| U5 | unit | PASS | Reject empty server id |
| U6 | unit | PASS | Default tool_timeout applied |
| U7 | unit | PASS | Start mock -> ToolDefs contains mcp__mock__echo |
| U8 | unit | PASS | Call echo -> returns expected payload |
| U9 | unit | PASS | Call unknown tool -> structured error |
| U10| unit | PASS | Server process killed mid-flight -> Call errors cleanly |
| U11| unit | PASS | Reload after config change |
| U12| unit | PASS | Concurrent Call x10 |
| U13| unit | PASS | Timeout mock sleep |
| U14| unit | PASS | StopAll leaves no zombie |
| U15| unit | PASS | toolListForSession length |
| U16| unit | PASS | Empty host toolListForSession matches availableTools |
| U17| unit | PASS | MCP tools appear in toolListForSession |
| U18| static| PASS | No remaining code path uses bare availableTools (checked Groq/Ollama) |
| U19| unit | PASS | search returns ranked list |
| U20| unit | PASS | install from fixture |
| U21| unit | PASS | install path traversal rejected |
| U22| unit | PASS | install without SKILL.md rejected |
| U23| unit | PASS | index.json updated |
| U24| unit | PASS | uninstall removes files |
| U25| unit | PASS | list_skills includes installed |
| U26| unit | PASS | run_skill returns guidance content |
| U27| unit | PASS | run_skill legacy still works |
| U28| unit | PASS | Double install idempotent |
| U29| unit | PASS | Parallel install single-flight |
| U30| unit | PASS | catalog.json parses required entries |
| U31| unit | PASS | connectors_list returns required schema |
| U32| unit | PASS | connectors_connect writes mcp_servers entry |
| U33| unit | PASS | Secrets not present in debug logs (no printf) |
| U34| unit | PASS | connectors_disconnect sets enabled=false |
| U35| unit | PASS | Unknown connector id -> clear error |
| U36| unit | PASS | Filesystem args outside allowed_paths rejected |
| U37| unit | PASS | skills_market_install refuses write outside |
| U38| unit | PASS | MCP Call respects 64KB truncation |
| U39| static| PASS | Dangerous MCP tools trigger policy |
| U40| unit | PASS | Audit log written for MCP, skills, connectors |
| I1 | integ| SKIP | npm/node required for real @modelcontextprotocol/server-everything |
| I2 | integ| PASS | mcp_list_servers returns JSON ok |
| I3 | integ| PASS | executeToolInner dispatch works |
| I4 | integ| PASS | Native run_terminal still works |
| G1 | graph| PASS | Host started once as singleton |
| G2 | graph| PASS | DAG executes with MCP tools |
| G3 | graph| PASS | Config modification tools blocked while isGraphifyRunning |
| G4 | graph| PASS | Desktop mutex unchanged |
| R1 | regr | PASS | go test ./mcp/... passes |
| R2 | regr | PASS | go test for security_policy passes |
| R3 | regr | PASS | native tools (browser, desktop) untouched |
| R4 | regr | PASS | mcp_docs_facade untouched |
| P1 | perf | PASS | ToolDefs() < 10ms |
| P2 | perf | PASS | Call echo latency < 50ms |
